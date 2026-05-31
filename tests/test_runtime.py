from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from nephos_api.catalog import RuntimeSpec
from nephos_api.config import Settings
from nephos_api.main import create_app
from nephos_api.migrations import apply_migrations
from nephos_api.reconciler import Reconciler
from nephos_api.repositories import BindingRepository, ReconciliationRepository
from nephos_api.runtime import (
    POSTGRES_SECRET_KEYS,
    HelmSubprocessClient,
    RuntimeHandler,
    RuntimeResult,
)

pytestmark = pytest.mark.unit


class FakeHelmClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def upgrade_install(
        self,
        *,
        release: str,
        runtime: RuntimeSpec,
        namespace: str,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "release": release,
                "chart": runtime.chart.name,
                "repository": runtime.chart.repository,
                "version": runtime.chart.version,
                "namespace": namespace,
                "values": values,
            }
        )
        return {"command": ["helm", "fake", release], "stdout": "ok"}


class FakeSecretClient:
    def __init__(self) -> None:
        self.namespaces: list[dict[str, Any]] = []
        self.secrets: dict[tuple[str, str], dict[str, str]] = {}
        self.upserts: list[dict[str, Any]] = []

    def ensure_namespace(self, name: str, *, labels: dict[str, str]) -> None:
        self.namespaces.append({"name": name, "labels": labels})

    def read_secret(self, namespace: str, name: str) -> dict[str, str] | None:
        return self.secrets.get((namespace, name))

    def upsert_secret(
        self,
        *,
        namespace: str,
        name: str,
        data: dict[str, str],
        labels: dict[str, str],
    ) -> None:
        stored = data.copy()
        self.secrets[(namespace, name)] = stored
        self.upserts.append(
            {
                "namespace": namespace,
                "name": name,
                "data": stored,
                "labels": labels.copy(),
            }
        )


class FakeRuntimeHandler:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def handle(self, request: dict[str, Any]) -> RuntimeResult:
        self.requests.append(request)
        return RuntimeResult(
            state="succeeded",
            level="healthy",
            lifecycle="running",
            reason="fake_runtime_succeeded",
            message="Fake runtime handler processed the request.",
            evidence=[
                {
                    "source": "test.runtime",
                    "subject": f"{request['targetType']}:{request['targetId']}",
                    "reason": "fake_runtime_succeeded",
                    "message": "Fake runtime evidence.",
                    "observedAt": "2026-05-23T00:00:00Z",
                }
            ],
        )


def _settings(tmp_path, *, runtime_mode: str = "shell") -> Settings:
    return Settings(
        db_path=tmp_path / "nephos.db",
        repo_catalog_root=tmp_path / "catalog",
        runtime_mode=runtime_mode,
    )


def _client(settings: Settings) -> TestClient:
    apply_migrations(settings)
    return TestClient(create_app(settings))


def _write_service(root: Path, *, name: str = "postgres", mapped: bool = False) -> None:
    mappings = (
        """
      mappings:
        - from:
            kind: config
            name: profile
          to:
            helmValue: postgresql.primary.resourcesPreset
""".rstrip()
        if mapped
        else "      mappings: []"
    )
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
{mappings}
  operations: []
""".lstrip()
    )


def _write_app(root: Path, *, name: str = "paperless", mapped: bool = False) -> None:
    mappings = (
        """
      mappings:
        - from:
            kind: config
            name: timezone
          to:
            helmValue: env.timezone
        - from:
            kind: binding
            name: database
            field: host
          to:
            helmValue: env.database.host
        - from:
            kind: binding
            name: database
            field: uri
          to:
            helmValue: env.database.uri
""".rstrip()
        if mapped
        else "      mappings: []"
    )
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
  routes: []
  runtime:
    type: helm
    chart:
      repository: https://charts.example.invalid/paperless
      name: paperless
      version: 1.2.3
    values:
{mappings}
  config:
    options: []
""".lstrip()
    )


def _install_service(client: TestClient, *, config: dict[str, Any] | None = None) -> dict[str, Any]:
    response = client.post(
        "/services",
        json={"catalogRef": {"kind": "Service", "name": "postgres"}, "config": config or {}},
    )
    assert response.status_code == 202, response.text
    return response.json()


def _install_app(client: TestClient, *, config: dict[str, Any] | None = None) -> dict[str, Any]:
    response = client.post(
        "/apps",
        json={"catalogRef": {"kind": "App", "name": "paperless"}, "config": config or {}},
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_helm_subprocess_client_generates_safe_upgrade_install_command(monkeypatch):
    seen: dict[str, Any] = {}

    def fake_run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        timeout: Any,
    ) -> subprocess.CompletedProcess[str]:
        values_path = Path(command[command.index("-f") + 1])
        seen["command"] = command
        seen["valuesPath"] = values_path
        seen["values"] = yaml.safe_load(values_path.read_text())
        assert check is False
        assert capture_output is True
        assert text is True
        assert timeout is None
        return subprocess.CompletedProcess(command, 0, stdout="release applied", stderr="")

    monkeypatch.setattr("nephos_api.runtime.subprocess.run", fake_run)
    runtime = RuntimeSpec.model_validate(
        {
            "type": "helm",
            "chart": {
                "repository": "https://charts.example.invalid/postgres",
                "name": "postgresql",
                "version": "16.0.0",
            },
        }
    )

    result = HelmSubprocessClient(timeout="5m").upgrade_install(
        release="svc-postgres",
        runtime=runtime,
        namespace="svc-postgres",
        values={"postgresql": {"auth": {"database": "paperless"}}},
    )

    assert seen["command"][:4] == ["helm", "upgrade", "--install", "svc-postgres"]
    assert "--repo" in seen["command"]
    assert "--create-namespace" in seen["command"]
    assert "--wait" in seen["command"]
    assert seen["values"] == {"postgresql": {"auth": {"database": "paperless"}}}
    assert not seen["valuesPath"].exists()
    assert result["command"][result["command"].index("-f") + 1] == "<generated-values-file>"
    assert result["stdout"] == "release applied"


def test_runtime_handler_applies_service_helm_release_with_mapped_values(tmp_path):
    settings = _settings(tmp_path)
    _write_service(settings.repo_catalog_root, mapped=True)
    client = _client(settings)
    service = _install_service(client, config={"profile": "small"})
    request = ReconciliationRepository(settings).get_request(
        request_id=service["reconciliation"]["id"]
    )
    helm = FakeHelmClient()
    secrets = FakeSecretClient()

    result = RuntimeHandler(settings, helm_client=helm, secret_client=secrets).handle(request)

    assert result.state == "succeeded"
    assert result.level == "healthy"
    assert result.reason == "helm_release_applied"
    assert helm.calls == [
        {
            "release": "svc-postgres",
            "chart": "postgresql",
            "repository": "https://charts.example.invalid/postgres",
            "version": "16.0.0",
            "namespace": "svc-postgres",
            "values": {"postgresql": {"primary": {"resourcesPreset": "small"}}},
        }
    ]
    assert secrets.namespaces == []


def test_runtime_handler_materializes_postgres_binding_secret_and_reuses_credentials(tmp_path):
    settings = _settings(tmp_path)
    _write_service(settings.repo_catalog_root)
    _write_app(settings.repo_catalog_root)
    client = _client(settings)
    _install_service(client)
    app = _install_app(client)
    binding_id = app["resource"]["bindings"][0]["id"]
    binding_reconcile = BindingRepository(settings).reconcile(binding_id=binding_id)
    request = ReconciliationRepository(settings).get_request(
        request_id=binding_reconcile["reconciliation"]["id"]
    )
    helm = FakeHelmClient()
    secrets = FakeSecretClient()
    handler = RuntimeHandler(settings, helm_client=helm, secret_client=secrets)

    result = handler.handle(request)

    assert result.state == "succeeded"
    assert result.level == "degraded"
    assert helm.calls == []
    created_secret = secrets.secrets[("app-paperless", "nephos-bind-database")]
    assert list(created_secret) == POSTGRES_SECRET_KEYS
    assert created_secret["database"] == "paperless"
    assert created_secret["username"] == "paperless"
    assert created_secret["password"] in created_secret["uri"]
    assert "***" not in created_secret["uri"]
    data = result.evidence[0]["data"]
    assert data["credentialsReused"] is False
    assert data["sqlProvisioning"]["state"] == "not_implemented"
    assert len(secrets.upserts) == 1

    second = handler.handle(request)

    assert second.state == "succeeded"
    assert second.evidence[0]["data"]["credentialsReused"] is True
    assert len(secrets.upserts) == 1
    assert secrets.secrets[("app-paperless", "nephos-bind-database")] == created_secret


def test_runtime_handler_applies_app_helm_with_binding_values_and_evidence(tmp_path):
    settings = _settings(tmp_path)
    _write_service(settings.repo_catalog_root)
    _write_app(settings.repo_catalog_root, mapped=True)
    client = _client(settings)
    _install_service(client)
    app = _install_app(client, config={"timezone": "UTC"})
    request = ReconciliationRepository(settings).get_request(request_id=app["reconciliation"]["id"])
    helm = FakeHelmClient()
    secrets = FakeSecretClient()

    result = RuntimeHandler(settings, helm_client=helm, secret_client=secrets).handle(request)

    assert result.state == "succeeded"
    assert result.level == "degraded"
    assert len(helm.calls) == 1
    call = helm.calls[0]
    assert call["release"] == "app-paperless"
    assert call["namespace"] == "app-paperless"
    secret = secrets.secrets[("app-paperless", "nephos-bind-database")]
    assert call["values"] == {
        "env": {
            "timezone": "UTC",
            "database": {"host": secret["host"], "uri": secret["uri"]},
        }
    }
    data = result.evidence[0]["data"]
    assert data["helm"]["command"] == ["helm", "fake", "app-paperless"]
    assert data["bindings"][0]["alias"] == "database"
    assert data["bindings"][0]["secretName"] == "nephos-bind-database"
    assert data["bindings"][0]["sqlProvisioning"]["state"] == "not_implemented"


def test_reconciler_helm_mode_delegates_runtime_and_persists_status(tmp_path):
    settings = _settings(tmp_path, runtime_mode="helm")
    _write_service(settings.repo_catalog_root)
    client = _client(settings)
    service = _install_service(client)
    runtime = FakeRuntimeHandler()

    result = Reconciler(settings, runtime_handler=runtime).run_once()

    assert result.processed == 1
    assert result.final_state == "succeeded"
    assert runtime.requests[0]["targetType"] == "service_instance"
    assert runtime.requests[0]["targetId"] == service["resource"]["id"]
    repository = ReconciliationRepository(settings)
    status = repository.get_status(
        resource_type="service_instance",
        resource_id=service["resource"]["id"],
    )
    assert status is not None
    assert status["reason"] == "fake_runtime_succeeded"
    assert status["evidence"][0]["source"] == "test.runtime"


def test_runtime_handler_blocks_unsupported_lifecycle_actions_without_helm_calls(tmp_path):
    settings = _settings(tmp_path)
    _write_service(settings.repo_catalog_root)
    client = _client(settings)
    _install_service(client)
    stop_response = client.post("/services/postgres/actions/stop", json={})
    assert stop_response.status_code == 202
    request = ReconciliationRepository(settings).get_request(
        request_id=stop_response.json()["reconciliation"]["id"]
    )
    helm = FakeHelmClient()

    result = RuntimeHandler(
        settings,
        helm_client=helm,
        secret_client=FakeSecretClient(),
    ).handle(request)

    assert result.state == "blocked"
    assert result.level == "blocked"
    assert result.reason == "runtime_lifecycle_action_unsupported"
    assert helm.calls == []
