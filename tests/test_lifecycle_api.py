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


def _write_app(root, name="paperless"):
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
    - capability: postgres
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


def _install_bound_app(tmp_path) -> tuple[TestClient, Settings, dict, dict]:
    catalog_root = tmp_path / "catalog"
    _write_service(catalog_root)
    _write_app(catalog_root)
    client, settings = _client(tmp_path, default_root=catalog_root)
    service = client.post(
        "/services",
        json={"catalogRef": {"kind": "Service", "name": "postgres"}},
    )
    assert service.status_code == 202
    app = client.post(
        "/apps",
        json={"catalogRef": {"kind": "App", "name": "paperless"}},
    )
    assert app.status_code == 202
    return client, settings, service.json()["resource"], app.json()["resource"]


def test_app_lifecycle_actions_update_desired_state_and_enqueue_requests(tmp_path):
    client, settings, _service, app = _install_bound_app(tmp_path)

    stopped = client.post(f"/apps/{app['slug']}/actions/stop")

    assert stopped.status_code == 202
    assert stopped.json()["resource"]["lifecycle"] == "stopped"
    assert stopped.json()["resource"]["generation"] == app["generation"] + 1
    assert stopped.json()["reconciliation"]["action"] == "app.stop"
    assert stopped.json()["status"]["reason"] == "reconciliation_pending"

    started = client.post(f"/apps/{app['slug']}/actions/start")
    assert started.status_code == 202
    assert started.json()["resource"]["lifecycle"] == "running"
    assert started.json()["reconciliation"]["action"] == "app.start"

    removed = client.post(f"/apps/{app['slug']}/actions/remove")
    assert removed.status_code == 202
    assert removed.json()["resource"]["lifecycle"] == "removed"
    assert removed.json()["reconciliation"]["action"] == "app.remove"

    missing_confirm = client.post(f"/apps/{app['slug']}/actions/destroy")
    assert missing_confirm.status_code == 422
    assert missing_confirm.json()["error"]["code"] == "destroy_confirmation_required"

    destroyed = client.post(
        f"/apps/{app['slug']}/actions/destroy",
        json={"confirm": "destroy paperless"},
    )
    assert destroyed.status_code == 202
    assert destroyed.json()["resource"]["slug"] == "paperless"
    assert destroyed.json()["reconciliation"]["action"] == "app.destroy"
    assert client.get("/apps/paperless").status_code == 200

    with sqlite3.connect(settings.db_path) as connection:
        delete_requested_at = connection.execute(
            "SELECT delete_requested_at FROM app_instances WHERE slug = 'paperless'"
        ).fetchone()[0]
    assert delete_requested_at is not None


def test_manual_app_and_service_reconcile_enqueue_requests(tmp_path):
    client, _settings, service, app = _install_bound_app(tmp_path)

    app_response = client.post(f"/apps/{app['slug']}/actions/reconcile")
    service_response = client.post(f"/services/{service['slug']}/actions/reconcile")

    assert app_response.status_code == 202
    assert app_response.json()["reconciliation"]["action"] == "app.reconcile"
    assert app_response.json()["status"]["reason"] == "manual_reconciliation_requested"
    assert service_response.status_code == 202
    assert service_response.json()["reconciliation"]["action"] == "service.reconcile"
    assert service_response.json()["status"]["reason"] == "manual_reconciliation_requested"


def test_service_lifecycle_with_dependents_requires_force(tmp_path):
    client, _settings, service, app = _install_bound_app(tmp_path)
    binding = app["bindings"][0]

    blocked = client.post(f"/services/{service['slug']}/actions/stop")

    assert blocked.status_code == 409
    error = blocked.json()["error"]
    assert error["code"] == "service_dependency_blocked"
    assert error["details"]["impact"] == [
        {
            "requiresForce": True,
            "appInstance": app["slug"],
            "bindingId": binding["id"],
            "bindingAlias": binding["alias"],
            "capability": binding["capability"],
        }
    ]

    forced = client.post(f"/services/{service['slug']}/actions/stop", json={"force": True})
    assert forced.status_code == 202
    assert forced.json()["resource"]["lifecycle"] == "stopped"
    assert forced.json()["reconciliation"]["action"] == "service.stop"
    assert forced.json()["reconciliation"]["targetType"] == "service_instance"


def test_binding_read_and_manual_reconcile(tmp_path):
    client, _settings, service, app = _install_bound_app(tmp_path)
    binding = app["bindings"][0]

    read = client.get(f"/bindings/{binding['id']}")

    assert read.status_code == 200
    body = read.json()
    assert body["id"] == binding["id"]
    assert body["alias"] == "database"
    assert body["capability"] == "postgres"
    assert body["appInstance"] == app["slug"]
    assert body["serviceInstance"] == service["slug"]
    assert body["output"]["redacted"] is True
    assert body["output"]["secretName"] == "nephos-bind-database"

    reconcile = client.post(f"/bindings/{binding['id']}/actions/reconcile")
    assert reconcile.status_code == 202
    assert reconcile.json()["resource"]["id"] == binding["id"]
    assert reconcile.json()["reconciliation"]["action"] == "binding.reconcile"
    assert reconcile.json()["status"]["reason"] == "manual_reconciliation_requested"

    missing = client.get("/bindings/binding_missing")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "binding_not_found"


def test_platform_domain_manual_reconcile_uses_default_domain(tmp_path):
    client, _settings = _client(tmp_path)
    missing = client.post("/platform/config/domains/actions/reconcile")
    assert missing.status_code == 409
    assert missing.json()["error"]["code"] == "platform_domain_not_configured"

    add = client.post(
        "/platform/config/domains",
        json={"name": "local", "domain": "nephos.local", "default": True},
    )
    assert add.status_code == 202

    response = client.post("/platform/config/domains/actions/reconcile")

    assert response.status_code == 202
    assert response.json()["resource"]["name"] == "local"
    assert response.json()["reconciliation"]["action"] == "platform_domain.reconcile"
