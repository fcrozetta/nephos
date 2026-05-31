from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from nephos_api.config import Settings
from nephos_api.main import create_app
from nephos_api.migrations import apply_migrations

pytestmark = pytest.mark.unit


def _client(tmp_path, *, default_root=None) -> tuple[TestClient, Settings]:
    settings = Settings(
        db_path=tmp_path / "nephos.db",
        repo_catalog_root=default_root or (tmp_path / "catalog"),
    )
    apply_migrations(settings)
    return TestClient(create_app(settings)), settings


def _write_service(root, name="postgres"):
    path = root / "services" / name / "service.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""
apiVersion: nephos.pro/v1alpha1
kind: Service
metadata:
  name: {name}
  displayName: PostgreSQL
  description: Relational database Service exposing the postgres capability.
  version: 0.0.1
spec:
  provides:
    - capability: postgres
      as: database
      version: "16"
  bindings:
    outputs:
      - name: connection
        target: app-secret
  provisioning:
    mode: app-scoped-resource
  runtime:
    type: helm
    chart:
      repository: https://charts.example.invalid/postgres
      name: postgresql
      version: 16.0.0
    values:
      mappings: []
  operations: []
""".lstrip()
    )
    return path


def test_service_install_persists_desired_state_and_reconciliation(tmp_path):
    catalog_root = tmp_path / "catalog"
    _write_service(catalog_root)
    client, settings = _client(tmp_path, default_root=catalog_root)

    response = client.post(
        "/services",
        json={
            "catalogRef": {"kind": "Service", "name": "postgres"},
            "config": {"profile": "small"},
        },
    )

    assert response.status_code == 202
    body = response.json()
    resource = body["resource"]
    assert resource["id"].startswith("svcinst_")
    assert resource["slug"] == "postgres"
    assert resource["kind"] == "Service"
    assert resource["lifecycle"] == "running"
    assert resource["config"] == {"profile": "small"}
    assert resource["catalogRef"]["kind"] == "Service"
    assert resource["catalogRef"]["name"] == "postgres"
    assert resource["catalogRef"]["source"] == "default"
    assert resource["catalogRef"]["manifestDigest"]
    assert "sourcePath" not in resource["catalogRef"]
    assert resource["provides"] == [
        {
            "capability": "postgres",
            "alias": "database",
            "version": "16",
            "bindingOutputTargets": ["app-secret"],
        }
    ]
    assert resource["dependents"] == []
    assert body["reconciliation"]["targetType"] == "service_instance"
    assert body["reconciliation"]["state"] == "pending"
    assert body["status"]["level"] == "pending"

    with sqlite3.connect(settings.db_path) as connection:
        service_count = connection.execute("SELECT COUNT(*) FROM service_instances").fetchone()[0]
        request_count = connection.execute(
            "SELECT COUNT(*) FROM reconciliation_requests"
        ).fetchone()[0]
    assert service_count == 1
    assert request_count == 1


def test_service_install_uses_explicit_instance_name(tmp_path):
    catalog_root = tmp_path / "catalog"
    _write_service(catalog_root)
    client, _settings = _client(tmp_path, default_root=catalog_root)

    response = client.post(
        "/services",
        json={
            "catalogRef": {"kind": "Service", "name": "postgres"},
            "instanceName": "postgres-main",
        },
    )

    assert response.status_code == 202
    assert response.json()["resource"]["slug"] == "postgres-main"
    detail = client.get("/services/postgres-main")
    assert detail.status_code == 200
    assert detail.json()["slug"] == "postgres-main"


def test_service_list_returns_installed_services(tmp_path):
    catalog_root = tmp_path / "catalog"
    _write_service(catalog_root)
    client, _settings = _client(tmp_path, default_root=catalog_root)
    client.post("/services", json={"catalogRef": {"kind": "Service", "name": "postgres"}})

    response = client.get("/services")

    assert response.status_code == 200
    assert [item["slug"] for item in response.json()["items"]] == ["postgres"]


def test_service_install_rejects_duplicate_instance_name(tmp_path):
    catalog_root = tmp_path / "catalog"
    _write_service(catalog_root)
    client, _settings = _client(tmp_path, default_root=catalog_root)
    body = {"catalogRef": {"kind": "Service", "name": "postgres"}}
    assert client.post("/services", json=body).status_code == 202

    response = client.post("/services", json=body)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "service_instance_conflict"


def test_service_install_rejects_non_service_catalog_ref(tmp_path):
    client, _settings = _client(tmp_path)

    response = client.post(
        "/services",
        json={"catalogRef": {"kind": "App", "name": "paperless"}},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_catalog_ref"


def test_service_get_missing_uses_nephos_error(tmp_path):
    client, _settings = _client(tmp_path)

    response = client.get("/services/postgres")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "service_instance_not_found"
