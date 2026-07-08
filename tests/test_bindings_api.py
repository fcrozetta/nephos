from pathlib import Path

from catalog_fixtures import write_app, write_service
from fastapi.testclient import TestClient

from nephos_api.config import Settings
from nephos_api.db import migrate_database
from nephos_api.main import create_app


def _client_with_binding(tmp_path: Path) -> tuple[TestClient, str]:
    db_path = tmp_path / "nephos.db"
    catalog_root = tmp_path / "catalog"
    write_app(catalog_root, capability="sql", protocol="postgres")
    write_service(
        catalog_root,
        capability="sql",
        protocol="postgres",
        alias="postgres",
    )
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
            json={"catalogRef": {"kind": "Service", "name": "postgres"}},
        ).status_code
        == 202
    )
    app_response = client.post(
        "/apps",
        json={"catalogRef": {"kind": "App", "name": "paperless"}},
    )
    assert app_response.status_code == 202
    binding_id = app_response.json()["resource"]["bindings"][0]["id"]
    return client, binding_id


def test_list_bindings_returns_redacted_binding_snapshots(tmp_path: Path) -> None:
    client, binding_id = _client_with_binding(tmp_path)

    response = client.get("/bindings")

    assert response.status_code == 200
    assert response.json() == {
        "bindings": [
            {
                "id": binding_id,
                "alias": "database",
                "capability": "sql",
                "protocol": "postgres",
                "appInstance": {
                    "id": response.json()["bindings"][0]["appInstance"]["id"],
                    "slug": "paperless",
                },
                "serviceInstance": {
                    "id": response.json()["bindings"][0]["serviceInstance"]["id"],
                    "slug": "postgres",
                },
                "output": {
                    "target": "app-secret",
                    "secretName": "nephos-bind-database",
                    "namespace": "app-paperless",
                    "keys": ["redacted"],
                    "redacted": True,
                },
                "status": None,
                "createdAt": response.json()["bindings"][0]["createdAt"],
                "updatedAt": response.json()["bindings"][0]["updatedAt"],
            }
        ]
    }


def test_get_binding_returns_snapshot_by_id(tmp_path: Path) -> None:
    client, binding_id = _client_with_binding(tmp_path)

    response = client.get(f"/bindings/{binding_id}")

    assert response.status_code == 200
    assert response.json()["id"] == binding_id
    assert response.json()["alias"] == "database"


def test_manual_binding_reconcile_returns_mutation_envelope(tmp_path: Path) -> None:
    client, binding_id = _client_with_binding(tmp_path)

    response = client.post(f"/bindings/{binding_id}/actions/reconcile")

    assert response.status_code == 202
    assert response.json()["resource"]["id"] == binding_id
    assert response.json()["reconciliation"]["id"].startswith("reconcile_")
    assert response.json()["reconciliation"]["state"] == "pending"


def test_get_binding_returns_not_found_error(tmp_path: Path) -> None:
    client, _binding_id = _client_with_binding(tmp_path)

    response = client.get("/bindings/binding_missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "binding_not_found"
