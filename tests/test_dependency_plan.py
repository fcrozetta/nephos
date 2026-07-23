from pathlib import Path

from fastapi.testclient import TestClient

from nephos_api.catalog import CatalogLoader
from nephos_api.config import Settings
from nephos_api.db import migrate_database
from nephos_api.dependency_plan import build_app_dependency_plan
from nephos_api.main import create_app


def _write_consumer_app(root: Path, *, provider: str | None = None) -> None:
    pin = f"\n      provider: {provider}" if provider else ""
    path = root / "apps" / "consumer" / "app.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""
apiVersion: nephos.pro/v1alpha1
kind: App
metadata:
  name: consumer
spec:
  requires:
    - capability: sql
      protocol: postgres
      as: db{pin}
  runtime:
    type: provider
    provider:
      name: reference-web
    values:
      mappings: []
""".strip()
    )


def _write_provider_service(root: Path, name: str) -> None:
    path = root / "services" / name / "service.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""
apiVersion: nephos.pro/v1alpha1
kind: Service
metadata:
  name: {name}
spec:
  provides:
    - capability: sql
      protocol: postgres
      as: postgres
  provisioning:
    mode: app-scoped-resource
  runtime:
    type: provider
    provider:
      name: {name}
    values:
      mappings: []
""".strip()
    )


def _service_row(
    slug: str,
    *,
    catalog_name: str = "postgres",
    source: str = "core-registry",
    lifecycle: str = "running",
    delete_requested_at: object = None,
) -> dict[str, object]:
    return {
        "slug": slug,
        "catalog_name": catalog_name,
        "catalog_source_id": source,
        "lifecycle": lifecycle,
        "delete_requested_at": delete_requested_at,
    }


def _loader(*roots_and_ids: tuple[Path, str]) -> CatalogLoader:
    roots = tuple(root for root, _ in roots_and_ids)
    ids = tuple(source_id for _, source_id in roots_and_ids)
    return CatalogLoader(roots, source_ids=ids)


def _only_requirement(plan: dict) -> dict:
    assert len(plan["requirements"]) == 1
    return plan["requirements"][0]


def test_plan_installable_single_candidate(tmp_path: Path) -> None:
    core = tmp_path / "core"
    _write_consumer_app(core)
    _write_provider_service(core, "postgres")
    loader = _loader((core, "core-registry"))

    plan = build_app_dependency_plan(
        app_entry=loader.get_app("consumer"), service_rows=[], loader=loader
    )
    req = _only_requirement(plan)

    assert req["state"] == "installable"
    assert req["installedProviders"] == []
    assert req["candidates"] == [{"name": "postgres", "source": "core-registry"}]
    assert plan["satisfiable"] is True


def test_plan_installable_ranks_candidates_by_registry_precedence(
    tmp_path: Path,
) -> None:
    core = tmp_path / "core"
    mythos = tmp_path / "mythos"
    _write_consumer_app(core)
    _write_provider_service(core, "postgres")
    _write_provider_service(mythos, "pgalt")
    loader = _loader((core, "core-registry"), (mythos, "mythos-registry"))

    plan = build_app_dependency_plan(
        app_entry=loader.get_app("consumer"), service_rows=[], loader=loader
    )
    req = _only_requirement(plan)

    assert req["state"] == "installable"
    assert req["candidates"] == [
        {"name": "postgres", "source": "core-registry"},
        {"name": "pgalt", "source": "mythos-registry"},
    ]


def test_plan_unresolvable_when_no_provider_anywhere(tmp_path: Path) -> None:
    core = tmp_path / "core"
    _write_consumer_app(core)  # no provider service written
    loader = _loader((core, "core-registry"))

    plan = build_app_dependency_plan(
        app_entry=loader.get_app("consumer"), service_rows=[], loader=loader
    )
    req = _only_requirement(plan)

    assert req["state"] == "unresolvable"
    assert req["candidates"] == []
    assert plan["satisfiable"] is False


def test_plan_satisfied_by_single_installed_provider(tmp_path: Path) -> None:
    core = tmp_path / "core"
    _write_consumer_app(core)
    _write_provider_service(core, "postgres")
    loader = _loader((core, "core-registry"))

    plan = build_app_dependency_plan(
        app_entry=loader.get_app("consumer"),
        service_rows=[_service_row("postgres-1")],
        loader=loader,
    )
    req = _only_requirement(plan)

    assert req["state"] == "satisfied"
    assert req["installedProviders"] == ["postgres-1"]


def test_plan_needs_selection_with_multiple_installed_providers(
    tmp_path: Path,
) -> None:
    core = tmp_path / "core"
    _write_consumer_app(core)
    _write_provider_service(core, "postgres")
    loader = _loader((core, "core-registry"))

    plan = build_app_dependency_plan(
        app_entry=loader.get_app("consumer"),
        service_rows=[_service_row("postgres-1"), _service_row("postgres-2")],
        loader=loader,
    )
    req = _only_requirement(plan)

    assert req["state"] == "needs_selection"
    assert sorted(req["installedProviders"]) == ["postgres-1", "postgres-2"]


def test_plan_ignores_unavailable_installed_provider(tmp_path: Path) -> None:
    core = tmp_path / "core"
    _write_consumer_app(core)
    _write_provider_service(core, "postgres")
    loader = _loader((core, "core-registry"))

    # A stopped instance is not an eligible provider, so it falls back to the
    # installable catalog candidate instead of counting as satisfied.
    plan = build_app_dependency_plan(
        app_entry=loader.get_app("consumer"),
        service_rows=[_service_row("postgres-1", lifecycle="stopped")],
        loader=loader,
    )
    req = _only_requirement(plan)

    assert req["state"] == "installable"
    assert req["installedProviders"] == []


def test_plan_provider_pin_filters_candidates(tmp_path: Path) -> None:
    core = tmp_path / "core"
    mythos = tmp_path / "mythos"
    _write_consumer_app(core, provider="postgres")
    _write_provider_service(core, "postgres")
    _write_provider_service(mythos, "pgalt")
    loader = _loader((core, "core-registry"), (mythos, "mythos-registry"))

    plan = build_app_dependency_plan(
        app_entry=loader.get_app("consumer"), service_rows=[], loader=loader
    )
    req = _only_requirement(plan)

    assert req["state"] == "installable"
    assert req["candidates"] == [{"name": "postgres", "source": "core-registry"}]


def test_plan_provider_pin_selects_installed(tmp_path: Path) -> None:
    # Two installed providers match the capability, but the pin narrows to one,
    # so the plan reports satisfied (mirrors the install path honoring the pin).
    core = tmp_path / "core"
    _write_consumer_app(core, provider="postgres")
    _write_provider_service(core, "postgres")
    _write_provider_service(core, "pgalt")
    loader = _loader((core, "core-registry"))

    plan = build_app_dependency_plan(
        app_entry=loader.get_app("consumer"),
        service_rows=[
            _service_row("postgres-1", catalog_name="postgres"),
            _service_row("pgalt-1", catalog_name="pgalt"),
        ],
        loader=loader,
    )
    req = _only_requirement(plan)

    assert req["state"] == "satisfied"
    assert req["installedProviders"] == ["postgres-1"]


def test_plan_endpoint_returns_installable(tmp_path: Path) -> None:
    core = tmp_path / "core"
    _write_consumer_app(core)
    _write_provider_service(core, "postgres")
    db = tmp_path / "nephos.db"
    migrate_database(db_path=db)
    app = create_app(
        settings=Settings(
            db_path=db,
            catalog_roots=(core,),
            catalog_source_ids=("core-registry",),
            kubeconfig=None,
            kube_context=None,
        ),
        start_reconciler=False,
    )
    client = TestClient(app)

    response = client.get("/catalog/apps/consumer/plan")

    assert response.status_code == 200
    plan = response.json()
    assert plan["satisfiable"] is True
    req = _only_requirement(plan)
    assert req["state"] == "installable"
    assert req["candidates"] == [{"name": "postgres", "source": "core-registry"}]
