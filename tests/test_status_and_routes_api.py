from pathlib import Path

from catalog_fixtures import (
    write_app,
    write_routed_app,
    write_service,
    write_service_with_portal,
)
from fastapi.testclient import TestClient

from nephos_api.config import Settings
from nephos_api.db import migrate_database
from nephos_api.main import create_app
from nephos_api.reconciler import Reconciler
from nephos_api.repository import DesiredStateRepository
from nephos_api.routing import PORTAL_RECONCILE_ACTION


def _client_and_repo(tmp_path: Path) -> tuple[TestClient, DesiredStateRepository]:
    db_path = tmp_path / "nephos.db"
    catalog_root = tmp_path / "catalog"
    write_app(catalog_root)
    write_service(catalog_root)
    migrate_database(db_path=db_path)
    app = create_app(
        settings=Settings(
            db_path=db_path,
            catalog_roots=(catalog_root,),
            kubeconfig=None,
            kube_context=None,
        )
    )
    return TestClient(app), DesiredStateRepository(db_path)


def test_app_routes_include_canonical_url_and_aliases_from_platform_domains(
    tmp_path: Path,
) -> None:
    client, _repo = _client_and_repo(tmp_path)
    assert (
        client.post(
            "/platform/config/domains",
            json={"name": "local", "domain": "nephos.local", "default": True},
        ).status_code
        == 202
    )
    assert (
        client.post(
            "/platform/config/domains",
            json={"name": "public", "domain": "nephos.example", "default": False},
        ).status_code
        == 202
    )
    assert (
        client.post(
            "/services",
            json={"catalogRef": {"kind": "Service", "name": "postgres"}},
        ).status_code
        == 202
    )
    created = client.post(
        "/apps",
        json={"catalogRef": {"kind": "App", "name": "paperless"}},
    )
    assert created.status_code == 202

    route = client.get("/apps/paperless").json()["routes"][0]

    assert route == {
        "name": "web",
        "visibility": "local",
        "target": {"port": "http"},
        "canonicalUrl": "http://paperless.nephos.local",
        "aliases": ["http://paperless.nephos.example"],
        "status": None,
    }


def test_app_route_entries_include_compact_runtime_status(
    tmp_path: Path,
) -> None:
    client, repo = _client_and_repo(tmp_path)
    assert (
        client.post(
            "/platform/config/domains",
            json={"name": "local", "domain": "nephos.local", "default": True},
        ).status_code
        == 202
    )
    assert (
        client.post(
            "/services",
            json={"catalogRef": {"kind": "Service", "name": "postgres"}},
        ).status_code
        == 202
    )
    app = client.post(
        "/apps",
        json={"catalogRef": {"kind": "App", "name": "paperless"}},
    )
    assert app.status_code == 202
    assert Reconciler(repo).run_once() == 1
    assert Reconciler(repo).run_once() == 1
    assert Reconciler(repo).run_once() == 1
    assert Reconciler(repo).run_once() == 1

    route_status = client.get("/apps/paperless").json()["routes"][0]["status"]

    assert route_status == {
        "level": "blocked",
        "reason": "runtime_handler_missing",
        "message": "No runtime handler is implemented for app_instance install.",
        "observedAt": route_status["observedAt"],
    }


def test_service_read_includes_latest_status_snapshot(tmp_path: Path) -> None:
    client, repo = _client_and_repo(tmp_path)
    service = client.post(
        "/services",
        json={"catalogRef": {"kind": "Service", "name": "postgres"}},
    )
    assert service.status_code == 202

    assert Reconciler(repo).run_once() == 1
    status = client.get("/services/postgres").json()["status"]

    assert status["level"] == "blocked"
    assert status["reconciliation"] == "blocked"
    assert status["reason"] == "runtime_handler_missing"
    assert status["message"] == (
        "No runtime handler is implemented for service_instance install."
    )
    assert status["evidence"][0]["source"] == "nephos-api"
    assert status["observedAt"]


def test_binding_read_includes_latest_status_snapshot(tmp_path: Path) -> None:
    client, repo = _client_and_repo(tmp_path)
    assert (
        client.post(
            "/services",
            json={"catalogRef": {"kind": "Service", "name": "postgres"}},
        ).status_code
        == 202
    )
    app = client.post(
        "/apps",
        json={"catalogRef": {"kind": "App", "name": "paperless"}},
    )
    assert app.status_code == 202
    binding_id = app.json()["resource"]["bindings"][0]["id"]

    reconcile = client.post(f"/bindings/{binding_id}/actions/reconcile")
    assert reconcile.status_code == 202
    assert Reconciler(repo).run_once() == 1
    assert Reconciler(repo).run_once() == 1
    assert Reconciler(repo).run_once() == 1
    status = client.get(f"/bindings/{binding_id}").json()["status"]

    assert status["level"] == "blocked"
    assert status["reconciliation"] == "blocked"
    assert status["reason"] == "runtime_handler_missing"


def test_app_and_service_nested_binding_entries_include_compact_status(
    tmp_path: Path,
) -> None:
    client, repo = _client_and_repo(tmp_path)
    assert (
        client.post(
            "/services",
            json={"catalogRef": {"kind": "Service", "name": "postgres"}},
        ).status_code
        == 202
    )
    app = client.post(
        "/apps",
        json={"catalogRef": {"kind": "App", "name": "paperless"}},
    )
    assert app.status_code == 202
    binding_id = app.json()["resource"]["bindings"][0]["id"]
    assert client.post(f"/bindings/{binding_id}/actions/reconcile").status_code == 202
    assert Reconciler(repo).run_once() == 1
    assert Reconciler(repo).run_once() == 1
    assert Reconciler(repo).run_once() == 1

    binding_status = client.get("/apps/paperless").json()["bindings"][0]["status"]
    dependent_status = client.get("/services/postgres").json()["dependents"][0][
        "status"
    ]

    assert binding_status == {
        "level": "blocked",
        "reason": "runtime_handler_missing",
        "message": "No runtime handler is implemented for binding reconcile.",
        "observedAt": binding_status["observedAt"],
    }
    assert dependent_status == binding_status


def _portal_client_and_repo(
    tmp_path: Path,
) -> tuple[TestClient, DesiredStateRepository]:
    db_path = tmp_path / "nephos.db"
    catalog_root = tmp_path / "catalog"
    write_service_with_portal(catalog_root)
    migrate_database(db_path=db_path)
    app = create_app(
        settings=Settings(
            db_path=db_path,
            catalog_roots=(catalog_root,),
            kubeconfig=None,
            kube_context=None,
        )
    )
    client = TestClient(app)
    assert (
        client.post(
            "/services",
            json={"catalogRef": {"kind": "Service", "name": "arcadedb"}},
        ).status_code
        == 202
    )
    return client, DesiredStateRepository(db_path)


def test_service_portal_reports_canonical_url_on_eligible_domain(
    tmp_path: Path,
) -> None:
    client, _repo = _portal_client_and_repo(tmp_path)
    assert (
        client.post(
            "/platform/config/domains",
            json={
                "name": "local",
                "domain": "nephos.lcl",
                "default": True,
                "allowsServicePortals": True,
            },
        ).status_code
        == 202
    )

    portal = client.get("/services/arcadedb").json()["portals"][0]

    assert portal == {
        "name": "studio",
        "displayName": "ArcadeDB Studio",
        "target": {"port": "http"},
        "published": True,
        "unpublishedReason": None,
        "canonicalUrl": "http://arcadedb.nephos.lcl",
        "aliases": [],
        "status": None,
    }


def test_service_portal_reports_unpublished_when_no_domain_is_eligible(
    tmp_path: Path,
) -> None:
    client, _repo = _portal_client_and_repo(tmp_path)
    assert (
        client.post(
            "/platform/config/domains",
            json={"name": "local", "domain": "nephos.lcl", "default": True},
        ).status_code
        == 202
    )

    portal = client.get("/services/arcadedb").json()["portals"][0]

    # Default-deny makes unpublished the normal fresh-install state, so it is
    # reported explicitly rather than shown as a URL that resolves nowhere.
    assert portal["published"] is False
    assert portal["unpublishedReason"] == "no_portal_eligible_domain"
    assert portal["canonicalUrl"] is None
    assert portal["aliases"] == []


def test_service_portal_excludes_ineligible_domains_from_aliases(
    tmp_path: Path,
) -> None:
    client, _repo = _portal_client_and_repo(tmp_path)
    # The realistic shape: the default domain is the public tunnelled one and only
    # the local domain carries portals. The admin UI must not appear on the public
    # host, and canonical must still resolve to the local one.
    assert (
        client.post(
            "/platform/config/domains",
            json={"name": "public", "domain": "nephos.example", "default": True},
        ).status_code
        == 202
    )
    assert (
        client.post(
            "/platform/config/domains",
            json={
                "name": "local",
                "domain": "nephos.lcl",
                "default": False,
                "allowsServicePortals": True,
            },
        ).status_code
        == 202
    )

    portal = client.get("/services/arcadedb").json()["portals"][0]

    assert portal["canonicalUrl"] == "http://arcadedb.nephos.lcl"
    assert portal["aliases"] == []


def test_service_without_portals_reports_an_empty_portal_list(
    tmp_path: Path,
) -> None:
    client, _repo = _client_and_repo(tmp_path)
    assert (
        client.post(
            "/services",
            json={"catalogRef": {"kind": "Service", "name": "postgres"}},
        ).status_code
        == 202
    )

    assert client.get("/services/postgres").json()["portals"] == []


def _collision_client(tmp_path: Path) -> TestClient:
    """Catalog with an App and a Service whose slugs both generate a bare host."""
    db_path = tmp_path / "nephos.db"
    catalog_root = tmp_path / "catalog"
    write_routed_app(catalog_root, name="auth")
    write_service_with_portal(catalog_root, name="auth")
    migrate_database(db_path=db_path)
    app = create_app(
        settings=Settings(
            db_path=db_path,
            catalog_roots=(catalog_root,),
            kubeconfig=None,
            kube_context=None,
        )
    )
    return TestClient(app)


def test_service_portal_install_rejects_hostname_claimed_by_an_app(
    tmp_path: Path,
) -> None:
    # ADR 20260517: collisions fail, never silently override. Reachable only since
    # the first portal became bare and joined the App hostname namespace.
    client = _collision_client(tmp_path)
    assert (
        client.post(
            "/apps", json={"catalogRef": {"kind": "App", "name": "auth"}}
        ).status_code
        == 202
    )

    response = client.post(
        "/services",
        json={"catalogRef": {"kind": "Service", "name": "auth"}},
    )

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "hostname_conflict"
    assert error["details"]["conflicts"] == ["auth"]
    assert error["details"]["conflictingKind"] == "App"


def test_app_install_rejects_hostname_claimed_by_a_service_portal(
    tmp_path: Path,
) -> None:
    client = _collision_client(tmp_path)
    assert (
        client.post(
            "/services", json={"catalogRef": {"kind": "Service", "name": "auth"}}
        ).status_code
        == 202
    )

    response = client.post(
        "/apps", json={"catalogRef": {"kind": "App", "name": "auth"}}
    )

    assert response.status_code == 409
    assert response.json()["error"]["details"]["conflictingKind"] == "Service"


def test_install_allows_distinct_hostnames(tmp_path: Path) -> None:
    # The realistic case this must not break: Zitadel installed as instance `auth`
    # alongside an App on its own host.
    db_path = tmp_path / "nephos.db"
    catalog_root = tmp_path / "catalog"
    write_routed_app(catalog_root, name="paperless")
    write_service_with_portal(catalog_root, name="zitadel")
    migrate_database(db_path=db_path)
    client = TestClient(
        create_app(
            settings=Settings(
                db_path=db_path,
                catalog_roots=(catalog_root,),
                kubeconfig=None,
                kube_context=None,
            )
        )
    )

    assert (
        client.post(
            "/apps", json={"catalogRef": {"kind": "App", "name": "paperless"}}
        ).status_code
        == 202
    )
    installed = client.post(
        "/services",
        json={
            "catalogRef": {"kind": "Service", "name": "zitadel"},
            "instanceName": "auth",
        },
    )

    assert installed.status_code == 202
    assert installed.json()["resource"]["slug"] == "auth"


def test_install_keeps_a_host_claim_when_the_catalog_entry_is_gone(
    tmp_path: Path,
) -> None:
    """A vanished catalog entry does not release the host.

    The resource's generated Ingress survives until remove/destroy, so treating a
    failed lookup as "claims nothing" would let the opposite kind take the same
    host and leave two live Ingresses serving it.
    """
    db_path = tmp_path / "nephos.db"
    catalog_root = tmp_path / "catalog"
    write_routed_app(catalog_root, name="auth")
    write_service_with_portal(catalog_root, name="auth")
    migrate_database(db_path=db_path)
    client = TestClient(
        create_app(
            settings=Settings(
                db_path=db_path,
                catalog_roots=(catalog_root,),
                kubeconfig=None,
                kube_context=None,
            )
        )
    )
    assert (
        client.post(
            "/apps", json={"catalogRef": {"kind": "App", "name": "auth"}}
        ).status_code
        == 202
    )

    # The App's catalog entry disappears, as if its registry were removed.
    (catalog_root / "apps" / "auth" / "app.yaml").unlink()

    response = client.post(
        "/services", json={"catalogRef": {"kind": "Service", "name": "auth"}}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "hostname_conflict"


def test_service_portal_reports_a_failed_routing_pass(tmp_path: Path) -> None:
    """A revoked portal whose teardown failed must not read as cleanly unpublished.

    Routing-only reconciliation writes no status snapshot, by design, so its failure
    used to live only on a request no endpoint exposed. Meanwhile `published` is
    derived from domain eligibility, which is desired state. An operator could
    therefore be told the UI was off the network while its Ingress was still
    serving, which is a false negative on the one control that takes a portal down.
    """
    client, repo = _portal_client_and_repo(tmp_path)
    assert (
        client.post(
            "/platform/config/domains",
            json={"name": "local", "domain": "nephos.lcl", "default": True},
        ).status_code
        == 202
    )
    service_id = str(repo.get_service_row("arcadedb")["id"])
    with repo.transaction() as tx:
        request = tx.create_reconciliation_request(
            target_type="service_instance",
            target_id=service_id,
            target_generation=1,
            action=PORTAL_RECONCILE_ACTION,
            target_snapshot={"slug": "arcadedb"},
        )
        tx.update_reconciliation_request_state(
            request_id=request.id,
            state="blocked",
            error="could not list ingresses",
        )

    portal = client.get("/services/arcadedb").json()["portals"][0]

    assert portal["unpublishedReason"] == "portal_routing_failed"
    assert portal["status"]["level"] == "blocked"
    assert portal["status"]["reason"] == "portal_routing_failed"
    assert portal["status"]["message"] == "could not list ingresses"


def test_service_portal_routing_success_does_not_mask_workload_status(
    tmp_path: Path,
) -> None:
    # The failure surface must not swallow the normal case: a succeeded routing pass
    # leaves the workload's own status showing through.
    client, repo = _portal_client_and_repo(tmp_path)
    assert (
        client.post(
            "/platform/config/domains",
            json={"name": "local", "domain": "nephos.lcl", "default": True},
        ).status_code
        == 202
    )
    service_id = str(repo.get_service_row("arcadedb")["id"])
    with repo.transaction() as tx:
        request = tx.create_reconciliation_request(
            target_type="service_instance",
            target_id=service_id,
            target_generation=1,
            action=PORTAL_RECONCILE_ACTION,
            target_snapshot={"slug": "arcadedb"},
        )
        tx.update_reconciliation_request_state(request_id=request.id, state="succeeded")

    portal = client.get("/services/arcadedb").json()["portals"][0]

    assert portal["unpublishedReason"] == "no_portal_eligible_domain"
    status = portal["status"]
    assert status is None or status["reason"] != "portal_routing_failed"
