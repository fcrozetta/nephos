from pathlib import Path

from catalog_fixtures import write_app, write_service
from fastapi.testclient import TestClient

from nephos_api.config import Settings
from nephos_api.db import migrate_database
from nephos_api.main import create_app
from nephos_api.reconciler import Reconciler
from nephos_api.repository import DesiredStateRepository


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
