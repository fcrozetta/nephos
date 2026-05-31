from __future__ import annotations

import json
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


def _write_app(root, name="paperless", *, requirement_capability="postgres"):
    path = root / "apps" / name / "app.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""
apiVersion: nephos.pro/v1alpha1
kind: App
metadata:
  name: {name}
  displayName: Paperless
  description: Document management for scanned and digital documents.
  version: 0.0.1
spec:
  requires:
    - capability: {requirement_capability}
      as: database
  routes:
    - name: web
      visibility: local
      target:
        port: http
  runtime:
    type: helm
    chart:
      repository: https://charts.example.invalid/paperless
      name: paperless
      version: 1.2.3
    values:
      mappings: []
  config:
    options: []
""".lstrip()
    )
    return path


def _write_service(root, name="postgres", *, capability="postgres"):
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
    - capability: {capability}
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


def _install_service(client: TestClient, name="postgres"):
    return client.post("/services", json={"catalogRef": {"kind": "Service", "name": name}})


def test_app_install_auto_binds_single_service_and_creates_reconciliation(tmp_path):
    catalog_root = tmp_path / "catalog"
    _write_app(catalog_root)
    _write_service(catalog_root)
    client, settings = _client(tmp_path, default_root=catalog_root)
    assert _install_service(client).status_code == 202

    response = client.post(
        "/apps",
        json={
            "catalogRef": {"kind": "App", "name": "paperless"},
            "config": {"timezone": "UTC"},
        },
    )

    assert response.status_code == 202
    body = response.json()
    resource = body["resource"]
    assert resource["id"].startswith("appinst_")
    assert resource["slug"] == "paperless"
    assert resource["kind"] == "App"
    assert resource["lifecycle"] == "running"
    assert resource["config"] == {"timezone": "UTC"}
    assert resource["catalogRef"]["kind"] == "App"
    assert resource["catalogRef"]["name"] == "paperless"
    assert resource["catalogRef"]["source"] == "default"
    assert resource["catalogRef"]["manifestDigest"]
    assert "sourcePath" not in resource["catalogRef"]
    assert resource["bindings"] == [
        {
            "id": resource["bindings"][0]["id"],
            "alias": "database",
            "capability": "postgres",
            "serviceInstance": "postgres",
            "status": None,
        }
    ]
    assert resource["bindings"][0]["id"].startswith("binding_")
    assert resource["routes"] == [
        {
            "name": "web",
            "visibility": "local",
            "target": {"port": "http"},
            "canonicalUrl": None,
            "aliases": [],
            "status": None,
        }
    ]
    assert body["reconciliation"]["targetType"] == "app_instance"
    assert body["reconciliation"]["state"] == "pending"
    assert body["status"]["level"] == "pending"

    detail = client.get("/apps/paperless")
    assert detail.status_code == 200
    assert detail.json()["bindings"] == resource["bindings"]

    service_detail = client.get("/services/postgres")
    assert service_detail.status_code == 200
    assert service_detail.json()["dependents"] == [
        {
            "appInstance": "paperless",
            "bindingId": resource["bindings"][0]["id"],
            "bindingAlias": "database",
            "capability": "postgres",
            "lifecycle": "running",
            "status": None,
        }
    ]

    with sqlite3.connect(settings.db_path) as connection:
        connection.row_factory = sqlite3.Row
        app_count = connection.execute("SELECT COUNT(*) FROM app_instances").fetchone()[0]
        binding_row = connection.execute("SELECT * FROM bindings").fetchone()
        app_request_count = connection.execute(
            """
            SELECT COUNT(*) FROM reconciliation_requests
            WHERE target_type = 'app_instance' AND action = 'app.install'
            """
        ).fetchone()[0]
    assert app_count == 1
    assert binding_row["alias"] == "database"
    assert json.loads(binding_row["output_summary_json"]) == {
        "target": "app-secret",
        "secretName": "nephos-bind-database",
        "namespace": "app-paperless",
        "keys": ["host", "port", "database", "username", "password", "uri"],
        "redacted": True,
    }
    assert app_request_count == 1


def test_app_install_uses_explicit_instance_name(tmp_path):
    catalog_root = tmp_path / "catalog"
    _write_app(catalog_root)
    _write_service(catalog_root)
    client, _settings = _client(tmp_path, default_root=catalog_root)
    _install_service(client)

    response = client.post(
        "/apps",
        json={
            "catalogRef": {"kind": "App", "name": "paperless"},
            "instanceName": "paperless-main",
        },
    )

    assert response.status_code == 202
    assert response.json()["resource"]["slug"] == "paperless-main"
    detail = client.get("/apps/paperless-main")
    assert detail.status_code == 200
    assert detail.json()["slug"] == "paperless-main"


def test_app_list_returns_installed_apps(tmp_path):
    catalog_root = tmp_path / "catalog"
    _write_app(catalog_root)
    _write_service(catalog_root)
    client, _settings = _client(tmp_path, default_root=catalog_root)
    _install_service(client)
    client.post("/apps", json={"catalogRef": {"kind": "App", "name": "paperless"}})

    response = client.get("/apps")

    assert response.status_code == 200
    assert [item["slug"] for item in response.json()["items"]] == ["paperless"]


def test_app_install_rejects_missing_required_provider_without_state(tmp_path):
    catalog_root = tmp_path / "catalog"
    _write_app(catalog_root)
    client, settings = _client(tmp_path, default_root=catalog_root)

    response = client.post("/apps", json={"catalogRef": {"kind": "App", "name": "paperless"}})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "app_binding_provider_not_found"
    assert response.json()["error"]["details"]["requirements"] == [
        {"alias": "database", "capability": "postgres"}
    ]
    with sqlite3.connect(settings.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM app_instances").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM bindings").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM reconciliation_requests").fetchone()[0] == 0


def test_app_install_rejects_ambiguous_required_provider(tmp_path):
    catalog_root = tmp_path / "catalog"
    _write_app(catalog_root)
    _write_service(catalog_root, "postgres")
    _write_service(catalog_root, "postgres-alt")
    client, settings = _client(tmp_path, default_root=catalog_root)
    assert _install_service(client).status_code == 202
    assert _install_service(client, "postgres-alt").status_code == 202

    response = client.post("/apps", json={"catalogRef": {"kind": "App", "name": "paperless"}})

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "app_binding_provider_ambiguous"
    assert [
        candidate["serviceInstance"]
        for candidate in error["details"]["requirements"][0]["candidates"]
    ] == ["postgres", "postgres-alt"]
    with sqlite3.connect(settings.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM app_instances").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM bindings").fetchone()[0] == 0


def test_app_install_rejects_explicit_binding_selection_until_shape_is_approved(tmp_path):
    client, _settings = _client(tmp_path)

    response = client.post(
        "/apps",
        json={
            "catalogRef": {"kind": "App", "name": "paperless"},
            "bindings": {"database": {"serviceInstance": "postgres"}},
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "explicit_binding_selection_unsupported"


def test_app_install_rejects_non_app_catalog_ref(tmp_path):
    client, _settings = _client(tmp_path)

    response = client.post(
        "/apps",
        json={"catalogRef": {"kind": "Service", "name": "postgres"}},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_catalog_ref"


def test_app_get_missing_uses_nephos_error(tmp_path):
    client, _settings = _client(tmp_path)

    response = client.get("/apps/paperless")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "app_instance_not_found"
