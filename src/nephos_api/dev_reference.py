from __future__ import annotations

import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from nephos_api.config import Settings
from nephos_api.db import migrate_database
from nephos_api.kubernetes_client import load_kubernetes_config
from nephos_api.kubernetes_runtime import KubernetesRuntime
from nephos_api.main import (
    create_app,
    default_postgres_provisioner_factory,
    default_provider_deployer_factory,
)


@dataclass(frozen=True)
class ReferenceSmokeResult:
    app_slug: str
    service_slug: str
    canonical_url: str


def run_reference_smoke(
    *,
    settings: Settings,
    timeout_seconds: int = 240,
    progress: Callable[[str], None] | None = None,
) -> ReferenceSmokeResult:
    suffix = uuid4().hex[:8]
    service_slug = f"postgres-{suffix}"
    app_slug = f"reference-web-{suffix}"
    log = progress or (lambda _message: None)
    migrate_database(db_path=settings.db_path)
    with tempfile.TemporaryDirectory(prefix="nephos-reference-") as temp_dir:
        catalog_root = Path(temp_dir) / "catalog"
        write_reference_catalog(catalog_root)
        reference_settings = Settings(
            db_path=settings.db_path,
            catalog_roots=(catalog_root,),
            kubeconfig=settings.kubeconfig,
            kube_context=settings.kube_context,
            internal_domain=settings.internal_domain,
            ingress_class=settings.ingress_class,
        )
        api_app = create_app(
            settings=reference_settings,
            start_reconciler=True,
            deployer_factory=default_provider_deployer_factory,
            provisioner_factory=default_postgres_provisioner_factory,
            reconciler_interval_seconds=1,
        )
        try:
            with TestClient(api_app) as api:
                log("configuring local platform domain")
                _ensure_platform_domain(
                    api,
                    domain=settings.internal_domain,
                    name_hint="local",
                )
                log(f"installing Service {service_slug}")
                _assert_accepted(
                    api.post(
                        "/services",
                        json={
                            "catalogRef": {"kind": "Service", "name": "postgres"},
                            "instanceName": service_slug,
                            "config": {"admin-password": uuid4().hex},
                        },
                    ),
                    "service install",
                )
                log(f"installing App {app_slug}")
                created_app = api.post(
                    "/apps",
                    json={
                        "catalogRef": {"kind": "App", "name": "reference-web"},
                        "instanceName": app_slug,
                    },
                )
                _assert_accepted(created_app, "app install")
                binding_id = created_app.json()["resource"]["bindings"][0]["id"]
                log("waiting for runtime convergence")
                _eventually(
                    lambda: (
                        _resource_status_reason(api, f"/services/{service_slug}")
                        == "runtime_deployed"
                        and _resource_status_reason(api, f"/bindings/{binding_id}")
                        == "binding_secret_ready"
                        and _resource_status_reason(api, f"/apps/{app_slug}")
                        == "runtime_deployed"
                    ),
                    timeout_seconds=timeout_seconds,
                )
                route = api.get(f"/apps/{app_slug}").json()["routes"][0]
                canonical_url = route["canonicalUrl"]
                log(f"verified route {canonical_url}")
                log("verifying stop/start lifecycle")
                _assert_accepted(
                    api.post(f"/apps/{app_slug}/actions/stop", json={}),
                    "app stop",
                )
                _eventually(
                    lambda: (
                        _resource_status_reason(api, f"/apps/{app_slug}")
                        == "runtime_stopped"
                    ),
                    timeout_seconds=60,
                )
                _assert_accepted(
                    api.post(f"/apps/{app_slug}/actions/start", json={}),
                    "app start",
                )
                _eventually(
                    lambda: (
                        _resource_status_reason(api, f"/apps/{app_slug}")
                        == "runtime_deployed"
                    ),
                    timeout_seconds=timeout_seconds,
                )
                log("destroying reference App and Service")
                _assert_accepted(
                    api.post(
                        f"/apps/{app_slug}/actions/destroy",
                        json={"confirm": f"destroy {app_slug}"},
                    ),
                    "app destroy",
                )
                _eventually(
                    lambda: api.get(f"/apps/{app_slug}").status_code == 404,
                    timeout_seconds=120,
                )
                _assert_accepted(
                    api.post(
                        f"/services/{service_slug}/actions/destroy",
                        json={"confirm": f"destroy {service_slug}"},
                    ),
                    "service destroy",
                )
                _eventually(
                    lambda: api.get(f"/services/{service_slug}").status_code == 404,
                    timeout_seconds=120,
                )
                return ReferenceSmokeResult(
                    app_slug=app_slug,
                    service_slug=service_slug,
                    canonical_url=canonical_url,
                )
        finally:
            _delete_owned_namespace_if_present(
                reference_settings,
                "app_instance",
                app_slug,
            )
            _delete_owned_namespace_if_present(
                reference_settings,
                "service_instance",
                service_slug,
            )


def write_reference_catalog(root: Path) -> None:
    _write_reference_app(root)
    _write_reference_service(root)


def _write_reference_app(root: Path) -> None:
    path = root / "apps" / "reference-web" / "app.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
apiVersion: nephos.pro/v1alpha1
kind: App
metadata:
  name: reference-web
  displayName: Reference Web
  description: Nephos API 0.0.1 reference web workload
  version: "0.0.1"
spec:
  requires:
    - capability: sql
      protocol: postgres
      as: database
  routes:
    - name: web
      visibility: local
      target:
        port: http
  config:
    options: []
  runtime:
    type: provider
    provider:
      name: reference-web
    values:
      mappings:
        - from:
            kind: binding
            name: database
            field: uri
          to:
            helmValue: env.DATABASE_URL
""".strip()
    )


def _write_reference_service(root: Path) -> None:
    path = root / "services" / "postgres" / "service.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
apiVersion: nephos.pro/v1alpha1
kind: Service
metadata:
  name: postgres
  displayName: PostgreSQL
spec:
  provides:
    - capability: sql
      protocol: postgres
      as: postgres
      version: "16"
  bindings:
    outputs:
      - name: connection
        target: app-secret
  config:
    options:
      - name: admin-password
        type: string
        required: true
  provisioning:
    mode: app-scoped-resource
  operations: []
  runtime:
    type: provider
    provider:
      name: postgres
    values:
      mappings:
        - from:
            kind: config
            name: admin-password
          to:
            helmValue: adminPassword
""".strip()
    )


def _assert_accepted(response, label: str) -> None:
    if response.status_code != 202:
        raise RuntimeError(f"{label} failed: {response.status_code} {response.text}")


def _ensure_platform_domain(api, *, domain: str, name_hint: str) -> None:
    response = api.get("/platform/config/domains")
    if response.status_code != 200:
        raise RuntimeError(
            f"platform domain list failed: {response.status_code} {response.text}"
        )
    domains = response.json()["domains"]
    for existing in domains:
        if existing["domain"] != domain:
            continue
        if existing["default"]:
            return
        _assert_accepted(
            api.post(
                f"/platform/config/domains/{existing['name']}/actions/set-default"
            ),
            "platform domain default",
        )
        return

    existing_names = {existing["name"] for existing in domains}
    name = _available_domain_name(name_hint, existing_names)
    _assert_accepted(
        api.post(
            "/platform/config/domains",
            json={"name": name, "domain": domain, "default": True},
        ),
        "platform domain",
    )


def _available_domain_name(name_hint: str, existing_names: set[str]) -> str:
    if name_hint not in existing_names:
        return name_hint
    name = f"{name_hint}-smoke"
    index = 2
    while name in existing_names:
        name = f"{name_hint}-smoke-{index}"
        index += 1
    return name


def _eventually(check, *, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(1)
    if not check():
        raise TimeoutError("timed out waiting for reference runtime convergence")


def _resource_status_reason(api: TestClient, path: str) -> str | None:
    response = api.get(path)
    if response.status_code != 200:
        return None
    status = response.json()["status"]
    return status["reason"] if status else None


def _delete_owned_namespace_if_present(
    settings: Settings,
    resource_type,
    slug: str,
) -> None:
    from kubernetes import client

    load_kubernetes_config(settings)
    runtime = KubernetesRuntime(client.CoreV1Api())
    runtime.delete_namespace_if_owned(resource_type, slug)
