from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from nephos_api.cli import app as cli_app
from nephos_api.config import Settings
from nephos_api.main import create_app
from nephos_api.migrations import apply_migrations
from nephos_api.reconciler import Reconciler
from nephos_api.repositories import PlatformDomainRepository, ReconciliationRepository

pytestmark = pytest.mark.unit


def _settings(tmp_path, *, default_root=None) -> Settings:
    return Settings(
        db_path=tmp_path / "nephos.db",
        repo_catalog_root=default_root or (tmp_path / "catalog"),
    )


def _client(tmp_path, *, default_root=None) -> tuple[TestClient, Settings]:
    settings = _settings(tmp_path, default_root=default_root)
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


def test_reconciler_run_once_no_pending_request_is_noop(tmp_path):
    settings = _settings(tmp_path)
    apply_migrations(settings)

    result = Reconciler(settings).run_once()
    drain = Reconciler(settings).drain()

    assert result.processed == 0
    assert result.request is None
    assert drain.processed == 0
    assert drain.states == {}


def test_reconciliation_repository_claims_oldest_pending_as_running(tmp_path):
    settings = _settings(tmp_path)
    apply_migrations(settings)
    created = PlatformDomainRepository(settings).add_domain(
        name="local",
        domain="nephos.local",
        is_default=True,
    )
    request_id = created["reconciliation"]["id"]
    repository = ReconciliationRepository(settings)

    claimed = repository.claim_next_pending()

    assert claimed is not None
    assert claimed["id"] == request_id
    assert claimed["state"] == "running"
    with sqlite3.connect(settings.db_path) as connection:
        state = connection.execute(
            "SELECT state FROM reconciliation_requests WHERE id = ?",
            (request_id,),
        ).fetchone()[0]
    assert state == "running"
    repository.finish_request(request_id=request_id, state="succeeded")


def test_reconciler_marks_platform_domain_request_succeeded_with_status(tmp_path):
    settings = _settings(tmp_path)
    apply_migrations(settings)
    created = PlatformDomainRepository(settings).add_domain(
        name="local",
        domain="nephos.local",
        is_default=True,
    )
    request_id = created["reconciliation"]["id"]
    domain_id = created["resource"]["id"]

    result = Reconciler(settings).run_once()

    assert result.processed == 1
    assert result.final_state == "succeeded"
    repository = ReconciliationRepository(settings)
    request = repository.get_request(request_id=request_id)
    assert request["state"] == "succeeded"
    status = repository.get_status(resource_type="platform_domain", resource_id=domain_id)
    assert status is not None
    assert status["level"] == "healthy"
    assert status["reconciliation"] == "succeeded"
    assert status["reason"] == "desired_state_reconciled"
    assert status["evidence"][0]["source"] == "nephos.reconciler"


def test_reconciler_drain_blocks_runtime_shell_targets_and_app_missing_domain(tmp_path):
    catalog_root = tmp_path / "catalog"
    _write_service(catalog_root)
    _write_app(catalog_root)
    client, settings = _client(tmp_path, default_root=catalog_root)
    service_response = client.post(
        "/services",
        json={"catalogRef": {"kind": "Service", "name": "postgres"}},
    )
    assert service_response.status_code == 202
    app_response = client.post(
        "/apps",
        json={"catalogRef": {"kind": "App", "name": "paperless"}},
    )
    assert app_response.status_code == 202
    service_request_id = service_response.json()["reconciliation"]["id"]
    app_request_id = app_response.json()["reconciliation"]["id"]
    app_id = app_response.json()["resource"]["id"]

    result = Reconciler(settings).drain()

    assert result.processed == 2
    assert result.states == {"blocked": 2}
    repository = ReconciliationRepository(settings)
    service_request = repository.get_request(request_id=service_request_id)
    app_request = repository.get_request(request_id=app_request_id)
    assert service_request["state"] == "blocked"
    assert app_request["state"] == "blocked"
    service_status = repository.get_status(
        resource_type="service_instance",
        resource_id=service_response.json()["resource"]["id"],
    )
    assert service_status is not None
    assert service_status["reason"] == "runtime_handler_not_implemented"
    app_status = repository.get_status(resource_type="app_instance", resource_id=app_id)
    assert app_status is not None
    assert app_status["level"] == "blocked"
    assert app_status["reconciliation"] == "blocked"
    assert app_status["reason"] == "platform_root_domain_missing"
    assert app_status["evidence"][0]["data"] == {"routes": ["web"]}


def test_cli_reconcile_run_once_processes_pending_request(tmp_path):
    settings = _settings(tmp_path)
    apply_migrations(settings)
    PlatformDomainRepository(settings).add_domain(
        name="local",
        domain="nephos.local",
        is_default=True,
    )
    runner = CliRunner()

    result = runner.invoke(
        cli_app,
        ["reconcile", "run-once"],
        env={"NEPHOS_API_DB_PATH": str(settings.db_path)},
    )

    assert result.exit_code == 0, result.output
    assert "Processed reconcile_" in result.output
    assert "-> succeeded" in result.output
