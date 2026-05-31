from __future__ import annotations

import base64
import json
import secrets
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml

from nephos_api.catalog import AppManifest, CatalogLoader, RuntimeSpec, ServiceManifest
from nephos_api.config import Settings
from nephos_api.db import connect
from nephos_api.domain import utc_now
from nephos_api.errors import NephosError

MANAGED_BY_LABEL = "app.kubernetes.io/managed-by"
MANAGED_BY_VALUE = "nephos"
POSTGRES_SECRET_KEYS = ["host", "port", "database", "username", "password", "uri"]


class RuntimeBlocked(Exception):
    def __init__(self, reason: str, message: str, *, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.data = data or {}


class RuntimeExecutionError(Exception):
    def __init__(self, reason: str, message: str, *, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.data = data or {}


@dataclass(frozen=True)
class RuntimeResult:
    state: str
    level: str
    lifecycle: str
    reason: str
    message: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


class HelmClientProtocol(Protocol):
    def upgrade_install(
        self,
        *,
        release: str,
        runtime: RuntimeSpec,
        namespace: str,
        values: dict[str, Any],
    ) -> dict[str, Any]: ...


class SecretClientProtocol(Protocol):
    def ensure_namespace(self, name: str, *, labels: dict[str, str]) -> None: ...

    def read_secret(self, namespace: str, name: str) -> dict[str, str] | None: ...

    def upsert_secret(
        self,
        *,
        namespace: str,
        name: str,
        data: dict[str, str],
        labels: dict[str, str],
    ) -> None: ...


class HelmSubprocessClient:
    def __init__(self, *, timeout: str = "10m") -> None:
        self.timeout = timeout

    def upgrade_install(
        self,
        *,
        release: str,
        runtime: RuntimeSpec,
        namespace: str,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        chart = runtime.chart
        values_path = self._write_values_file(values)
        command = [
            "helm",
            "upgrade",
            "--install",
            release,
            chart.name,
            "--repo",
            chart.repository,
            "--version",
            chart.version,
            "--namespace",
            namespace,
            "--create-namespace",
            "--wait",
            "--timeout",
            self.timeout,
            "-f",
            str(values_path),
        ]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=None,
            )
        except OSError as exc:
            raise RuntimeExecutionError(
                "helm_command_unavailable",
                "Helm CLI could not be executed.",
                data={"command": self._safe_command(command), "error": str(exc)},
            ) from exc
        finally:
            values_path.unlink(missing_ok=True)
        if completed.returncode != 0:
            raise RuntimeExecutionError(
                "helm_failed",
                "Helm upgrade/install failed.",
                data={
                    "command": self._safe_command(command),
                    "returnCode": completed.returncode,
                    "stderr": completed.stderr[-2000:],
                },
            )
        return {
            "command": self._safe_command(command),
            "stdout": completed.stdout[-2000:],
        }

    def _write_values_file(self, values: dict[str, Any]) -> Path:
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
            yaml.safe_dump(values, handle, sort_keys=True)
            return Path(handle.name)

    def _safe_command(self, command: list[str]) -> list[str]:
        safe = command.copy()
        if "-f" in safe:
            index = safe.index("-f") + 1
            if index < len(safe):
                safe[index] = "<generated-values-file>"
        return safe


class KubernetesSecretClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._core_api: Any | None = None
        self._client_module: Any | None = None

    def ensure_namespace(self, name: str, *, labels: dict[str, str]) -> None:
        client = self._client()
        body = client.V1Namespace(metadata=client.V1ObjectMeta(name=name, labels=labels))
        try:
            self._core().read_namespace(name)
        except self._api_exception() as exc:
            if exc.status != 404:
                raise
            self._core().create_namespace(body)

    def read_secret(self, namespace: str, name: str) -> dict[str, str] | None:
        try:
            secret = self._core().read_namespaced_secret(name=name, namespace=namespace)
        except self._api_exception() as exc:
            if exc.status == 404:
                return None
            raise
        decoded: dict[str, str] = {}
        for key, raw in (secret.data or {}).items():
            decoded[key] = base64.b64decode(raw).decode("utf-8")
        return decoded

    def upsert_secret(
        self,
        *,
        namespace: str,
        name: str,
        data: dict[str, str],
        labels: dict[str, str],
    ) -> None:
        client = self._client()
        body = client.V1Secret(
            metadata=client.V1ObjectMeta(name=name, labels=labels),
            type="Opaque",
            string_data=data,
        )
        try:
            self._core().read_namespaced_secret(name=name, namespace=namespace)
        except self._api_exception() as exc:
            if exc.status != 404:
                raise
            self._core().create_namespaced_secret(namespace=namespace, body=body)
            return
        self._core().patch_namespaced_secret(name=name, namespace=namespace, body=body)

    def _core(self) -> Any:
        if self._core_api is None:
            client = self._client()
            self._core_api = client.CoreV1Api()
        return self._core_api

    def _client(self) -> Any:
        if self._client_module is not None:
            return self._client_module
        try:
            from kubernetes import client, config
            from kubernetes.config.config_exception import ConfigException
        except ImportError as exc:  # pragma: no cover - depends on optional runtime extra
            raise RuntimeExecutionError(
                "kubernetes_client_missing",
                "The kubernetes Python package is required for helm runtime mode.",
            ) from exc
        try:
            config.load_kube_config(
                config_file=str(self.settings.kubeconfig) if self.settings.kubeconfig else None,
                context=self.settings.kube_context,
            )
        except ConfigException:
            try:
                config.load_incluster_config()
            except ConfigException as exc:
                raise RuntimeExecutionError(
                    "kubernetes_config_unavailable",
                    "Kubernetes configuration could not be loaded for helm runtime mode.",
                    data={
                        "kubeconfig": str(self.settings.kubeconfig)
                        if self.settings.kubeconfig
                        else None,
                        "context": self.settings.kube_context,
                    },
                ) from exc
        self._client_module = client
        return client

    def _api_exception(self) -> type[Exception]:
        try:
            from kubernetes.client.exceptions import ApiException
        except ImportError as exc:  # pragma: no cover - depends on optional runtime extra
            raise RuntimeExecutionError(
                "kubernetes_client_missing",
                "The kubernetes Python package is required for helm runtime mode.",
            ) from exc
        return ApiException


class RuntimeHandler:
    def __init__(
        self,
        settings: Settings,
        *,
        helm_client: HelmClientProtocol | None = None,
        secret_client: SecretClientProtocol | None = None,
    ) -> None:
        self.settings = settings
        self.helm_client = helm_client or HelmSubprocessClient(timeout=settings.helm_timeout)
        self.secret_client = secret_client or KubernetesSecretClient(settings)

    def handle(self, request: dict[str, Any]) -> RuntimeResult:
        try:
            if request["targetType"] == "service_instance":
                return self._handle_service(request)
            if request["targetType"] == "app_instance":
                return self._handle_app(request)
            if request["targetType"] == "binding":
                return self._handle_binding(request)
            raise RuntimeBlocked(
                "runtime_target_unsupported",
                "Runtime mode does not handle this reconciliation target type.",
                data={"targetType": request["targetType"]},
            )
        except RuntimeBlocked as exc:
            return self._result(
                request,
                state="blocked",
                level="blocked",
                reason=exc.reason,
                message=exc.message,
                data=exc.data,
            )
        except RuntimeExecutionError as exc:
            return self._result(
                request,
                state="failed",
                level="degraded",
                reason=exc.reason,
                message=exc.message,
                data=exc.data,
                error=exc.message,
            )

    def _handle_service(self, request: dict[str, Any]) -> RuntimeResult:
        action = request["action"]
        if action not in {"service.install", "service.reconcile", "service.start"}:
            raise RuntimeBlocked(
                "runtime_lifecycle_action_unsupported",
                "Helm runtime mode currently supports Service install/reconcile/start only.",
                data={"action": action},
            )
        row = self._resource_row("service_instances", request["targetId"])
        entry = self._catalog_entry("Service", row)
        if not isinstance(entry.manifest, ServiceManifest):
            raise RuntimeExecutionError(
                "invalid_catalog_entry",
                "Resolved catalog entry is not a Service.",
            )
        values = self._mapped_values(
            entry.manifest.spec.runtime,
            config=self._json(row["config_json"]),
        )
        helm_result = self.helm_client.upgrade_install(
            release=f"svc-{row['slug']}",
            runtime=entry.manifest.spec.runtime,
            namespace=f"svc-{row['slug']}",
            values=values,
        )
        return self._result(
            request,
            state="succeeded",
            level="healthy",
            lifecycle=row["lifecycle"],
            reason="helm_release_applied",
            message="Service Helm release was applied using draft runtime assumptions.",
            data={"helm": helm_result},
        )

    def _handle_app(self, request: dict[str, Any]) -> RuntimeResult:
        action = request["action"]
        if action not in {"app.install", "app.reconcile", "app.start"}:
            raise RuntimeBlocked(
                "runtime_lifecycle_action_unsupported",
                "Helm runtime mode currently supports App install/reconcile/start only.",
                data={"action": action},
            )
        row = self._resource_row("app_instances", request["targetId"])
        entry = self._catalog_entry("App", row)
        if not isinstance(entry.manifest, AppManifest):
            raise RuntimeExecutionError(
                "invalid_catalog_entry",
                "Resolved catalog entry is not an App.",
            )
        if entry.manifest.spec.routes:
            self._require_platform_domain(entry.manifest)
            raise RuntimeBlocked(
                "route_runtime_not_implemented",
                (
                    "App route intent exists, but Ingress runtime materialization is "
                    "not implemented yet."
                ),
                data={"routes": [route.name for route in entry.manifest.spec.routes]},
            )
        binding_outputs, binding_summaries = self._materialized_bindings_for_app(row["id"])
        values = self._mapped_values(
            entry.manifest.spec.runtime,
            config=self._json(row["config_json"]),
            bindings=binding_outputs,
        )
        self.secret_client.ensure_namespace(
            f"app-{row['slug']}",
            labels={MANAGED_BY_LABEL: MANAGED_BY_VALUE, "nephos.pro/app-instance": row["slug"]},
        )
        helm_result = self.helm_client.upgrade_install(
            release=f"app-{row['slug']}",
            runtime=entry.manifest.spec.runtime,
            namespace=f"app-{row['slug']}",
            values=values,
        )
        message = "App Helm release was applied using draft runtime assumptions."
        if binding_summaries:
            message = (
                f"{message} Binding Secrets were materialized, but SQL-level "
                "app-scoped resource provisioning is not implemented yet."
            )
        return self._result(
            request,
            state="succeeded",
            level="degraded" if binding_summaries else "healthy",
            lifecycle=row["lifecycle"],
            reason="helm_release_applied",
            message=message,
            data={"helm": helm_result, "bindings": binding_summaries},
        )

    def _handle_binding(self, request: dict[str, Any]) -> RuntimeResult:
        action = request["action"]
        if action != "binding.reconcile":
            raise RuntimeBlocked(
                "runtime_lifecycle_action_unsupported",
                "Helm runtime mode currently supports binding manual reconcile only.",
                data={"action": action},
            )
        binding = self._binding_row(request["targetId"])
        output = self._materialize_postgres_binding(binding)
        return self._result(
            request,
            state="succeeded",
            level="degraded",
            lifecycle="not_applicable",
            reason="binding_secret_materialized",
            message=(
                "Binding Secret was materialized using draft PostgreSQL assumptions; "
                "SQL-level app-scoped resource provisioning is not implemented yet."
            ),
            data=self._binding_summary(binding["alias"], output),
        )

    def _materialized_bindings_for_app(
        self,
        app_id: str,
    ) -> tuple[dict[str, dict[str, str]], list[dict[str, Any]]]:
        outputs: dict[str, dict[str, str]] = {}
        summaries: list[dict[str, Any]] = []
        with connect(self.settings.db_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    b.*,
                    a.slug AS app_slug,
                    s.slug AS service_slug
                FROM bindings b
                JOIN app_instances a ON a.id = b.app_instance_id
                JOIN service_instances s ON s.id = b.service_instance_id
                WHERE b.app_instance_id = ?
                ORDER BY b.alias ASC
                """,
                (app_id,),
            ).fetchall()
        for row in rows:
            output = self._materialize_postgres_binding(row)
            outputs[row["alias"]] = output["values"]
            summaries.append(self._binding_summary(row["alias"], output))
        return outputs, summaries

    def _binding_summary(self, alias: str, output: dict[str, Any]) -> dict[str, Any]:
        return {
            "alias": alias,
            "namespace": output["namespace"],
            "secretName": output["secretName"],
            "keys": POSTGRES_SECRET_KEYS,
            "credentialsReused": output["credentialsReused"],
            "sqlProvisioning": output["sqlProvisioning"],
        }

    def _materialize_postgres_binding(self, row: Any) -> dict[str, Any]:
        if row["capability"] != "postgres":
            raise RuntimeBlocked(
                "binding_capability_unsupported",
                "Runtime binding materialization currently supports only postgres.",
                data={"capability": row["capability"]},
            )
        summary = self._json(row["output_summary_json"])
        if summary.get("target") != "app-secret":
            raise RuntimeBlocked(
                "binding_output_target_unsupported",
                "Runtime binding materialization currently supports only app-secret outputs.",
                data={"target": summary.get("target")},
            )
        namespace = summary.get("namespace") or f"app-{row['app_slug']}"
        secret_name = summary.get("secretName") or f"nephos-bind-{row['alias']}"
        labels = {
            MANAGED_BY_LABEL: MANAGED_BY_VALUE,
            "nephos.pro/app-instance": row["app_slug"],
            "nephos.pro/service-instance": row["service_slug"],
            "nephos.pro/capability": row["capability"],
            "nephos.pro/binding-alias": row["alias"],
        }
        self.secret_client.ensure_namespace(
            namespace,
            labels={MANAGED_BY_LABEL: MANAGED_BY_VALUE, "nephos.pro/app-instance": row["app_slug"]},
        )
        existing = self.secret_client.read_secret(namespace, secret_name)
        if existing and all(key in existing for key in POSTGRES_SECRET_KEYS):
            values = {key: existing[key] for key in POSTGRES_SECRET_KEYS}
            credentials_reused = True
        else:
            values = self._postgres_values(
                app_slug=row["app_slug"],
                service_slug=row["service_slug"],
            )
            credentials_reused = False
            self.secret_client.upsert_secret(
                namespace=namespace,
                name=secret_name,
                data=values,
                labels=labels,
            )
        return {
            "namespace": namespace,
            "secretName": secret_name,
            "values": values,
            "credentialsReused": credentials_reused,
            "sqlProvisioning": self._postgres_sql_provisioning_status(),
        }

    def _postgres_sql_provisioning_status(self) -> dict[str, str]:
        return {
            "state": "not_implemented",
            "message": (
                "The first runtime spike materializes connection Secrets only; "
                "database/user SQL provisioning is not implemented yet."
            ),
        }

    def _postgres_values(self, *, app_slug: str, service_slug: str) -> dict[str, str]:
        database = app_slug.replace("-", "_")
        username = database
        password = secrets.token_urlsafe(32)
        host = f"svc-{service_slug}-postgresql.svc-{service_slug}.svc.cluster.local"
        port = "5432"
        uri = f"postgresql://{username}:{password}@{host}:{port}/{database}"
        return {
            "host": host,
            "port": port,
            "database": database,
            "username": username,
            "password": password,
            "uri": uri,
        }

    def _mapped_values(
        self,
        runtime: RuntimeSpec,
        *,
        config: dict[str, Any],
        bindings: dict[str, dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for mapping in (runtime.values.mappings if runtime.values else []):
            source = mapping.get("from", {})
            target = mapping.get("to", {})
            helm_value = target.get("helmValue")
            if not isinstance(helm_value, str):
                raise RuntimeBlocked(
                    "runtime_mapping_invalid",
                    "Runtime mapping is missing to.helmValue.",
                    data={"mapping": mapping},
                )
            value = self._mapping_value(source, config=config, bindings=bindings or {})
            self._set_dot_path(values, helm_value, value)
        return values

    def _mapping_value(
        self,
        source: dict[str, Any],
        *,
        config: dict[str, Any],
        bindings: dict[str, dict[str, str]],
    ) -> Any:
        kind = source.get("kind")
        if kind == "config":
            name = source.get("name")
            if name not in config:
                raise RuntimeBlocked(
                    "runtime_mapping_source_missing",
                    "Runtime config mapping source is missing.",
                    data={"source": source},
                )
            return config[name]
        if kind == "binding":
            alias = source.get("name")
            field = source.get("field")
            if alias not in bindings or field not in bindings[alias]:
                raise RuntimeBlocked(
                    "runtime_mapping_source_missing",
                    "Runtime binding mapping source is missing.",
                    data={"source": source},
                )
            return bindings[alias][field]
        raise RuntimeBlocked(
            "runtime_mapping_source_unsupported",
            "Runtime mapping source kind is unsupported.",
            data={"source": source},
        )

    def _set_dot_path(self, values: dict[str, Any], path: str, value: Any) -> None:
        current = values
        parts = path.split(".")
        for part in parts[:-1]:
            next_value = current.setdefault(part, {})
            if not isinstance(next_value, dict):
                raise RuntimeBlocked(
                    "runtime_mapping_target_conflict",
                    "Runtime mapping target conflicts with an existing scalar value.",
                    data={"helmValue": path},
                )
            current = next_value
        current[parts[-1]] = value

    def _require_platform_domain(self, manifest: AppManifest) -> None:
        with connect(self.settings.db_path) as connection:
            count = connection.execute("SELECT COUNT(*) FROM platform_domains").fetchone()[0]
        if not count:
            raise RuntimeBlocked(
                "platform_root_domain_missing",
                "App route reconciliation requires at least one configured root domain.",
                data={"routes": [route.name for route in manifest.spec.routes]},
            )

    def _resource_row(self, table: str, resource_id: str) -> Any:
        with connect(self.settings.db_path) as connection:
            row = connection.execute(
                f"SELECT * FROM {table} WHERE id = ?",
                (resource_id,),
            ).fetchone()
        if row is None:
            raise RuntimeExecutionError(
                "target_not_found",
                "Runtime target desired-state row was not found.",
                data={"table": table, "id": resource_id},
            )
        return row

    def _binding_row(self, binding_id: str) -> Any:
        with connect(self.settings.db_path) as connection:
            row = connection.execute(
                """
                SELECT
                    b.*,
                    a.slug AS app_slug,
                    s.slug AS service_slug
                FROM bindings b
                JOIN app_instances a ON a.id = b.app_instance_id
                JOIN service_instances s ON s.id = b.service_instance_id
                WHERE b.id = ?
                """,
                (binding_id,),
            ).fetchone()
        if row is None:
            raise RuntimeExecutionError(
                "target_not_found",
                "Runtime binding target was not found.",
                data={"bindingId": binding_id},
            )
        return row

    def _catalog_entry(self, kind: str, row: Any) -> Any:
        try:
            return CatalogLoader(self.settings).resolve_entry(
                kind, row["catalog_name"], source_id=row["catalog_source_id"]
            )
        except NephosError as exc:
            raise RuntimeBlocked(
                "catalog_entry_unavailable",
                "Installed resource catalog entry is unavailable for runtime reconciliation.",
                data={"code": exc.code, "details": exc.details},
            ) from exc

    def _json(self, raw: str) -> Any:
        return json.loads(raw)

    def _result(
        self,
        request: dict[str, Any],
        *,
        state: str,
        level: str,
        reason: str,
        message: str,
        data: dict[str, Any] | None = None,
        lifecycle: str | None = None,
        error: str | None = None,
    ) -> RuntimeResult:
        evidence: dict[str, Any] = {
            "source": "nephos.runtime",
            "subject": f"{request['targetType']}:{request['targetId']}",
            "reason": reason,
            "message": message,
            "observedAt": utc_now(),
        }
        if data is not None:
            evidence["data"] = data
        return RuntimeResult(
            state=state,
            level=level,
            lifecycle=lifecycle or "not_applicable",
            reason=reason,
            message=message,
            evidence=[evidence],
            error=error,
        )
