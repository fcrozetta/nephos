import os
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import yaml
from fastapi.testclient import TestClient

from nephos_api.config import Settings
from nephos_api.db import migrate_database
from nephos_api.dev_reference import (
    _assert_accepted,
    _delete_owned_namespace_if_present,
    _ensure_platform_domain,
)
from nephos_api.main import (
    create_app,
    default_postgres_provisioner_factory,
    default_provider_deployer_factory,
)
from nephos_api.reconciler import Reconciler
from nephos_api.repository import DesiredStateRepository
from nephos_api.runtime_errors import RuntimeBlockedError

BACKBONE_SERVICE_NAMES = ("postgres", "zitadel", "seaweedfs", "arcadedb")
BACKBONE_APP_NAME = "backbone-check"

EXPECTED_BINDING_SECRET_KEYS = {
    "postgres": ("host", "port", "database", "username", "password", "uri"),
    "identity": ("issuerUrl", "clientId", "clientSecret"),
    "object-storage": (
        "endpointUrl",
        "bucket",
        "accessKeyId",
        "secretAccessKey",
        "region",
    ),
    "graph": ("host", "port", "database", "username", "password", "protocol", "uri"),
}


@dataclass(frozen=True)
class BackboneSmokeResult:
    status: str
    message: str
    blocker_code: str | None = None
    app_slug: str | None = None
    service_slugs: list[str] = field(default_factory=list)
    binding_reports: list[dict[str, object]] = field(default_factory=list)


def run_backbone_smoke(
    *,
    settings: Settings,
    timeout_seconds: int = 600,
    progress: Callable[[str], None] | None = None,
    environ: Mapping[str, str] | None = None,
    live: bool | None = None,
) -> BackboneSmokeResult:
    env = os.environ if environ is None else environ
    if live is False:
        return _run_non_live_backbone_flow(
            settings=settings,
            timeout_seconds=timeout_seconds,
            progress=progress,
        )
    should_run_live = _live_smoke_requested(env) if live is None else live
    if not should_run_live:
        return BackboneSmokeResult(
            status="skipped",
            blocker_code="pulumi_passphrase_missing",
            message=(
                "PULUMI_CONFIG_PASSPHRASE or PULUMI_CONFIG_PASSPHRASE_FILE "
                "is required for live alpha backbone smoke."
            ),
        )
    return _run_live_backbone_flow(
        settings=settings,
        timeout_seconds=timeout_seconds,
        progress=progress,
    )


def write_alpha_backbone_catalog(root: Path) -> None:
    _write_backbone_check_app(root)
    _write_service(
        root,
        name="postgres",
        display_name="PostgreSQL",
        provider_name="postgres",
        provides=[("sql", "postgres", "postgres")],
        config_options=[
            {"name": "storage-size", "type": "string", "default": "1Gi"},
            {"name": "storage-class-name", "type": "string"},
        ],
        runtime_mappings=[
            ("storage-size", "storageSize"),
            ("storage-class-name", "storageClassName"),
        ],
    )
    _write_service(
        root,
        name="zitadel",
        display_name="Zitadel",
        provider_name="zitadel",
        provides=[("oidc", "oidc", "oidc"), ("service-account", "jwt", "jwt")],
        config_options=[
            {
                "name": "image",
                "type": "string",
                "default": "ghcr.io/zitadel/zitadel:v2.58.0",
            },
            {
                "name": "external-host",
                "type": "string",
                "default": "zitadel.nephos.localhost",
            },
            {"name": "external-port", "type": "integer", "default": 8080},
            {"name": "external-secure", "type": "boolean", "default": False},
            {"name": "ingress-enabled", "type": "boolean", "default": False},
            {"name": "ingress-class-name", "type": "string", "default": ""},
            {
                "name": "admin-username",
                "type": "string",
                "default": "root@zitadel.nephos.localhost",
            },
            {
                "name": "admin-password",
                "type": "string",
                "default": "Nephos-local-zitadel-1!",
            },
            {
                "name": "master-key",
                "type": "string",
                "default": "0123456789abcdef0123456789abcdef",
            },
            {
                "name": "database-password",
                "type": "string",
                "default": "nephos-local-zitadel-db",
            },
            {
                "name": "bootstrap-machine-username",
                "type": "string",
                "default": "nephos-provisioner",
            },
            {
                "name": "bootstrap-machine-name",
                "type": "string",
                "default": "Nephos Provisioner",
            },
            {
                "name": "bootstrap-machine-key-path",
                "type": "string",
                "default": "/var/lib/zitadel-bootstrap/nephos-provisioner-key.json",
            },
            {
                "name": "bootstrap-machine-key-expiration",
                "type": "string",
                "default": "2036-01-01T00:00:00Z",
            },
            {
                "name": "provisioning-transport",
                "type": "string",
                "default": "auto",
            },
            {"name": "storage-size", "type": "string", "default": "1Gi"},
        ],
        runtime_mappings=[
            ("image", "image"),
            ("external-host", "externalHost"),
            ("external-port", "externalPort"),
            ("external-secure", "externalSecure"),
            ("ingress-enabled", "ingressEnabled"),
            ("ingress-class-name", "ingressClassName"),
            ("admin-username", "adminUsername"),
            ("admin-password", "adminPassword"),
            ("master-key", "masterKey"),
            ("database-password", "databasePassword"),
            ("bootstrap-machine-username", "bootstrapMachineUsername"),
            ("bootstrap-machine-name", "bootstrapMachineName"),
            ("bootstrap-machine-key-path", "bootstrapMachineKeyPath"),
            (
                "bootstrap-machine-key-expiration",
                "bootstrapMachineKeyExpiration",
            ),
            ("storage-size", "storageSize"),
        ],
    )
    _write_service(
        root,
        name="seaweedfs",
        display_name="SeaweedFS",
        provider_name="seaweedfs",
        provides=[("object-storage", "s3", "s3")],
        config_options=[
            {"name": "image", "type": "string", "default": "chrislusf/seaweedfs:3.85"},
            {"name": "storage-size", "type": "string", "default": "1Gi"},
            {
                "name": "s3-access-key",
                "type": "string",
                "default": "nephos-local-seaweedfs",
            },
            {
                "name": "s3-secret-key",
                "type": "string",
                "default": "nephos-local-seaweedfs",
            },
        ],
        runtime_mappings=[
            ("image", "image"),
            ("storage-size", "storageSize"),
            ("s3-access-key", "s3AccessKey"),
            ("s3-secret-key", "s3SecretKey"),
        ],
    )
    _write_service(
        root,
        name="arcadedb",
        display_name="ArcadeDB",
        provider_name="arcadedb",
        provides=[
            ("sql", "arcadedb", "sql"),
            ("opencypher", "bolt", "bolt"),
            ("opencypher", "n4j", "n4j"),
        ],
        config_options=[
            {
                "name": "image",
                "type": "string",
                "default": "arcadedata/arcadedb:25.5.1",
            },
            {"name": "storage-size", "type": "string", "default": "1Gi"},
            {
                "name": "root-password",
                "type": "string",
                "default": "nephos-local-arcadedb",
            },
            {"name": "enable-gremlin", "type": "boolean", "default": False},
            {"name": "enable-mongo", "type": "boolean", "default": False},
        ],
        runtime_mappings=[
            ("image", "image"),
            ("storage-size", "storageSize"),
            ("root-password", "rootPassword"),
            ("enable-gremlin", "enableGremlin"),
            ("enable-mongo", "enableMongo"),
        ],
    )
    _write_service(
        root,
        name="cloudflared",
        display_name="Cloudflare Tunnel",
        provider_name="cloudflared",
        provides=[("external-routing", "cloudflare-tunnel", "cloudflare-tunnel")],
        config_options=[
            {
                "name": "image",
                "type": "string",
                "default": "cloudflare/cloudflared:2026.6.1",
            },
            {"name": "tunnel-name", "type": "string", "default": "nephos"},
            {"name": "credentials-secret-name", "type": "string"},
            {
                "name": "credentials-secret-key",
                "type": "string",
                "default": "credentials.json",
            },
            {"name": "hostname", "type": "string"},
            {
                "name": "origin-service-url",
                "type": "string",
                "default": (
                    "http://ingress-nginx-controller.ingress-nginx.svc.cluster.local"
                ),
            },
            {"name": "origin-host-header", "type": "string", "default": ""},
        ],
        runtime_mappings=[
            ("image", "image"),
            ("tunnel-name", "tunnelName"),
            ("credentials-secret-name", "credentialsSecretName"),
            ("credentials-secret-key", "credentialsSecretKey"),
            ("hostname", "hostname"),
            ("origin-service-url", "originServiceUrl"),
            ("origin-host-header", "originHostHeader"),
        ],
        provisioning_mode="none",
        binding_outputs=False,
    )

def _run_non_live_backbone_flow(
    *,
    settings: Settings,
    timeout_seconds: int,
    progress: Callable[[str], None] | None,
) -> BackboneSmokeResult:
    log = progress or (lambda _message: None)
    with tempfile.TemporaryDirectory(prefix="nephos-backbone-") as temp_dir:
        temp_path = Path(temp_dir)
        catalog_root = temp_path / "catalog"
        db_path = temp_path / "state" / "nephos.db"
        write_alpha_backbone_catalog(catalog_root)
        smoke_settings = _smoke_settings(
            settings,
            db_path=db_path,
            catalog_root=catalog_root,
        )
        migrate_database(db_path=smoke_settings.db_path)
        api_app = create_app(settings=smoke_settings, start_reconciler=False)
        runtime = _MemoryRuntime()
        repo = DesiredStateRepository(smoke_settings.db_path)
        reconciler = Reconciler(
            repo,
            runtime=runtime,
            provisioner=_MissingLiveBackboneProvisioner(),
        )
        with TestClient(api_app) as api:
            _install_backbone_desired_state(api, log=log)
            _drain_reconciler(reconciler, timeout_seconds=timeout_seconds)
            blocker = _first_blocked_status(api)
            if blocker is None:
                return BackboneSmokeResult(
                    status="passed",
                    message="Alpha backbone desired-state flow converged.",
                    app_slug=BACKBONE_APP_NAME,
                    service_slugs=list(BACKBONE_SERVICE_NAMES),
                )
            return BackboneSmokeResult(
                status="blocked",
                blocker_code=str(blocker["reason"]),
                message=str(blocker["message"]),
                app_slug=BACKBONE_APP_NAME,
                service_slugs=list(BACKBONE_SERVICE_NAMES),
            )


def _run_live_backbone_flow(
    *,
    settings: Settings,
    timeout_seconds: int,
    progress: Callable[[str], None] | None,
) -> BackboneSmokeResult:
    suffix = uuid4().hex[:8]
    service_slugs = [f"{name}-{suffix}" for name in BACKBONE_SERVICE_NAMES]
    app_slug = f"{BACKBONE_APP_NAME}-{suffix}"
    log = progress or (lambda _message: None)
    with tempfile.TemporaryDirectory(prefix="nephos-backbone-") as temp_dir:
        temp_path = Path(temp_dir)
        catalog_root = temp_path / "catalog"
        db_path = temp_path / "state" / "nephos.db"
        write_alpha_backbone_catalog(catalog_root)
        smoke_settings = _smoke_settings(
            settings,
            db_path=db_path,
            catalog_root=catalog_root,
        )
        migrate_database(db_path=smoke_settings.db_path)
        api_app = create_app(
            settings=smoke_settings,
            start_reconciler=True,
            deployer_factory=default_provider_deployer_factory,
            provisioner_factory=default_postgres_provisioner_factory,
            reconciler_interval_seconds=1,
        )
        try:
            with TestClient(api_app) as api:
                _install_backbone_desired_state(
                    api,
                    service_slugs=dict(
                        zip(BACKBONE_SERVICE_NAMES, service_slugs, strict=True)
                    ),
                    app_slug=app_slug,
                    log=log,
                )
                result = _wait_for_live_result(
                    api,
                    app_slug=app_slug,
                    timeout_seconds=timeout_seconds,
                )
                if result.status != "passed":
                    return result
                reports = _verify_live_binding_secrets(app_slug=app_slug)
                return BackboneSmokeResult(
                    status="passed",
                    message="Alpha backbone smoke passed.",
                    app_slug=app_slug,
                    service_slugs=service_slugs,
                    binding_reports=reports,
                )
        finally:
            _cleanup_live_backbone(settings=smoke_settings, app_slug=app_slug)
            for service_slug in reversed(service_slugs):
                _cleanup_live_backbone(
                    settings=smoke_settings,
                    service_slug=service_slug,
                )


def _install_backbone_desired_state(
    api: TestClient,
    *,
    service_slugs: dict[str, str] | None = None,
    app_slug: str = BACKBONE_APP_NAME,
    log: Callable[[str], None],
) -> None:
    resolved_service_slugs = service_slugs or {
        service_name: service_name for service_name in BACKBONE_SERVICE_NAMES
    }
    _ensure_platform_domain(api, domain="nephos.localhost", name_hint="local")
    for service_name in BACKBONE_SERVICE_NAMES:
        service_slug = resolved_service_slugs[service_name]
        log(f"installing Service {service_slug}")
        _assert_accepted(
            api.post(
                "/services",
                json={
                    "catalogRef": {"kind": "Service", "name": service_name},
                    "instanceName": service_slug,
                },
            ),
            f"service install {service_name}",
        )
    log(f"installing App {app_slug}")
    _assert_accepted(
        api.post(
            "/apps",
            json={
                "catalogRef": {"kind": "App", "name": BACKBONE_APP_NAME},
                "instanceName": app_slug,
                "bindings": {
                    "postgres": {"serviceInstance": resolved_service_slugs["postgres"]},
                    "identity": {"serviceInstance": resolved_service_slugs["zitadel"]},
                    "object-storage": {
                        "serviceInstance": resolved_service_slugs["seaweedfs"]
                    },
                    "graph": {"serviceInstance": resolved_service_slugs["arcadedb"]},
                },
            },
        ),
        "app install backbone-check",
    )


def _verify_key_only_binding_report(
    *,
    alias: str,
    expected_keys: tuple[str, ...],
    secret_values: Mapping[str, str],
) -> dict[str, object]:
    missing_or_empty = [
        key for key in expected_keys if not str(secret_values.get(key) or "")
    ]
    if missing_or_empty:
        keys = ", ".join(sorted(missing_or_empty))
        raise RuntimeError(f"{alias} missing or empty Secret keys: {keys}")
    return {
        "alias": alias,
        "keys": sorted(expected_keys),
        "redacted": True,
    }


def _write_backbone_check_app(root: Path) -> None:
    path = root / "apps" / BACKBONE_APP_NAME / "app.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
apiVersion: nephos.pro/v1alpha1
kind: App
metadata:
  name: backbone-check
  displayName: Backbone Check
  description: Temporary non-canonical alpha backbone smoke App
  version: "0.0.1"
spec:
  requires:
    - capability: sql
      protocol: postgres
      as: postgres
    - capability: oidc
      protocol: oidc
      as: identity
    - capability: object-storage
      protocol: s3
      as: object-storage
    - capability: opencypher
      protocol: bolt
      as: graph
  routes: []
  config:
    options: []
  runtime:
    type: provider
    provider:
      name: reference-web
    values:
      mappings: []
""".strip()
    )


def _write_service(
    root: Path,
    *,
    name: str,
    display_name: str,
    provider_name: str,
    provides: list[tuple[str, str, str]],
    config_options: list[dict[str, object]],
    runtime_mappings: list[tuple[str, str]],
    provisioning_mode: str = "app-scoped-resource",
    binding_outputs: bool = True,
) -> None:
    path = root / "services" / name / "service.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    spec = {
        "provides": [
            {
                "capability": capability,
                "protocol": protocol,
                "as": alias,
            }
            for capability, protocol, alias in provides
        ],
        "config": {"options": config_options},
        "provisioning": {"mode": provisioning_mode},
        "operations": [],
        "runtime": {
            "type": "provider",
            "provider": {"name": provider_name},
            "values": {
                "mappings": [
                    {
                        "from": {"kind": "config", "name": source},
                        "to": {"helmValue": target},
                    }
                    for source, target in runtime_mappings
                ]
            },
        },
    }
    if binding_outputs:
        spec["bindings"] = {
            "outputs": [{"name": "connection", "target": "app-secret"}]
        }
    manifest = {
        "apiVersion": "nephos.pro/v1alpha1",
        "kind": "Service",
        "metadata": {
            "name": name,
            "displayName": display_name,
        },
        "spec": spec,
    }
    path.write_text(
        yaml.safe_dump(manifest, sort_keys=False).strip()
    )


def _smoke_settings(
    settings: Settings,
    *,
    db_path: Path,
    catalog_root: Path,
) -> Settings:
    return Settings(
        db_path=db_path,
        catalog_roots=(catalog_root,),
        kubeconfig=settings.kubeconfig,
        kube_context=settings.kube_context,
        internal_domain=settings.internal_domain,
        ingress_class=settings.ingress_class,
    )


def _live_smoke_requested(env: Mapping[str, str]) -> bool:
    return bool(
        env.get("PULUMI_CONFIG_PASSPHRASE")
        or env.get("PULUMI_CONFIG_PASSPHRASE_FILE")
    )


def _drain_reconciler(reconciler: Reconciler, *, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if reconciler.run_once() == 0:
            return
    raise TimeoutError("timed out waiting for backbone desired-state reconciliation")


def _first_blocked_status(api: TestClient) -> dict[str, object] | None:
    resources = []
    resources.extend(api.get("/bindings").json()["bindings"])
    resources.extend(api.get("/apps").json()["apps"])
    resources.extend(api.get("/services").json()["services"])
    for resource in resources:
        status = resource.get("status")
        if isinstance(status, dict) and status.get("reconciliation") == "blocked":
            return status
    return None


def _wait_for_live_result(
    api: TestClient,
    *,
    app_slug: str,
    timeout_seconds: int,
) -> BackboneSmokeResult:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        blocker = _first_blocked_status(api)
        if blocker is not None:
            return BackboneSmokeResult(
                status="blocked",
                blocker_code=str(blocker["reason"]),
                message=str(blocker["message"]),
                app_slug=app_slug,
            )
        app_response = api.get(f"/apps/{app_slug}")
        if app_response.status_code == 200:
            app_status = app_response.json()["status"]
            if app_status and app_status["reason"] == "runtime_deployed":
                return BackboneSmokeResult(
                    status="passed",
                    message="Alpha backbone runtime converged.",
                    app_slug=app_slug,
                )
        time.sleep(1)
    return BackboneSmokeResult(
        status="blocked",
        blocker_code="backbone_smoke_timeout",
        message="Timed out waiting for alpha backbone runtime convergence.",
        app_slug=app_slug,
    )


def _verify_live_binding_secrets(*, app_slug: str) -> list[dict[str, object]]:
    from kubernetes import client

    core_v1_api = client.CoreV1Api()
    namespace = f"app-{app_slug}"
    reports = []
    for alias, expected_keys in EXPECTED_BINDING_SECRET_KEYS.items():
        secret = core_v1_api.read_namespaced_secret(
            namespace=namespace,
            name=f"nephos-bind-{alias}",
        )
        data = secret.data or {}
        reports.append(
            _verify_key_only_binding_report(
                alias=alias,
                expected_keys=expected_keys,
                secret_values={key: value for key, value in data.items()},
            )
        )
    return reports


def _cleanup_live_backbone(
    *,
    settings: Settings,
    app_slug: str | None = None,
    service_slug: str | None = None,
) -> None:
    if app_slug is not None:
        _delete_owned_namespace_if_present(settings, "app_instance", app_slug)
    if service_slug is not None:
        _delete_owned_namespace_if_present(settings, "service_instance", service_slug)


class _MissingLiveBackboneProvisioner:
    def provision_binding(self, _context) -> dict[str, str] | None:
        raise RuntimeBlockedError(
            reason="binding_provisioner_unavailable",
            message=(
                "Alpha backbone live external API details are intentionally blocked "
                "until verified."
            ),
        )

    def deprovision_binding(self, _context) -> None:
        return None


class _MemoryRuntime:
    def ensure_namespace(self, resource_type, slug: str) -> object:
        return {"resourceType": resource_type, "slug": slug}

    def delete_namespace_if_owned(self, resource_type, slug: str) -> bool:
        return True

    def ensure_binding_secret(
        self,
        *,
        app_slug: str,
        service_slug: str,
        alias: str,
        capability: str,
        protocol: str | None = None,
        values: dict[str, str],
    ) -> object:
        return {
            "appSlug": app_slug,
            "serviceSlug": service_slug,
            "alias": alias,
            "capability": capability,
            "protocol": protocol,
            "keys": sorted(values),
        }

    def delete_binding_secret_if_owned(
        self,
        *,
        app_slug: str,
        service_slug: str,
        alias: str,
        capability: str,
        protocol: str | None = None,
    ) -> bool:
        return True

    def scale_workloads(self, resource_type, slug: str, replicas: int) -> object:
        return {"resourceType": resource_type, "slug": slug, "replicas": replicas}

    def ensure_app_ingresses(
        self,
        *,
        app_slug: str,
        routes: list[dict[str, object]],
        domains: list[dict[str, object]],
    ) -> object:
        return {"appSlug": app_slug, "routes": routes, "domains": domains}

    def delete_app_ingresses(
        self,
        *,
        app_slug: str,
        routes: list[dict[str, object]],
    ) -> object:
        return {"appSlug": app_slug, "routes": routes}
