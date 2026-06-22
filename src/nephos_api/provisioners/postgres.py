import base64
import hashlib
import re
import secrets
import shlex
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote

from kubernetes import client, stream
from kubernetes.client.rest import ApiException

from nephos_api.kubernetes_runtime import (
    KubernetesRuntimeSafetyError,
    binding_secret_labels,
    namespace_labels,
    namespace_name,
)
from nephos_api.provisioners.base import BindingProvisioningContext


class PostgresPsqlRunner(Protocol):
    def run_psql(
        self,
        *,
        core_v1_api: client.CoreV1Api,
        namespace: str,
        pod_name: str,
        admin_password: str,
        sql: str,
    ) -> None: ...


class KubernetesPsqlRunner:
    def run_psql(
        self,
        *,
        core_v1_api: client.CoreV1Api,
        namespace: str,
        pod_name: str,
        admin_password: str,
        sql: str,
    ) -> None:
        marker = "NEPHOS_EXIT"
        script = (
            f"PGPASSWORD={shlex.quote(admin_password)} "
            "psql -U postgres -d postgres -v ON_ERROR_STOP=1 <<'NEPHOS_SQL'\n"
            f"{sql}\n"
            "NEPHOS_SQL\n"
            "rc=$?\n"
            f"printf '\\n{marker}:%s\\n' \"$rc\"\n"
            "exit \"$rc\""
        )
        response = stream.stream(
            core_v1_api.connect_get_namespaced_pod_exec,
            pod_name,
            namespace,
            command=["sh", "-lc", script],
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False,
            _preload_content=False,
        )
        stdout: list[str] = []
        stderr: list[str] = []
        while response.is_open():
            response.update(timeout=1)
            if response.peek_stdout():
                stdout.append(response.read_stdout())
            if response.peek_stderr():
                stderr.append(response.read_stderr())
        response.close()
        stdout_text = "".join(stdout)
        stderr_text = "".join(stderr)
        return_code = _exec_exit_code(stdout_text, marker=marker)
        if return_code is None:
            stream_return_code = getattr(response, "returncode", None)
            if stream_return_code not in (0, None):
                return_code = int(stream_return_code)
            else:
                raise RuntimeError("missing exec exit marker")
        if return_code not in (0, None):
            message = (
                stderr_text
                or _stdout_without_exec_marker(stdout_text, marker=marker)
                or "psql execution failed"
            )
            raise RuntimeError(message.strip())


class PostgresAppScopedProvisioner:
    def __init__(
        self,
        *,
        core_v1_api: client.CoreV1Api,
        psql_runner: PostgresPsqlRunner | None = None,
        password_factory: Callable[[], str] | None = None,
    ) -> None:
        self._core_v1_api = core_v1_api
        self._psql_runner = psql_runner or KubernetesPsqlRunner()
        self._password_factory = password_factory or (lambda: secrets.token_urlsafe(24))

    def provision_binding(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str] | None:
        if not _is_postgres_binding(context):
            return None

        runtime = _postgres_runtime(context.service_slug)
        _assert_active_owned_service_namespace(
            self._core_v1_api,
            service_slug=context.service_slug,
            namespace=runtime.namespace,
        )
        credentials = self._ensure_credential_secret(
            context,
            namespace=runtime.namespace,
        )
        admin_password = _decode_secret_key(
            _read_required_secret(
                self._core_v1_api,
                namespace=runtime.namespace,
                name=runtime.admin_secret_name,
            ),
            "postgres-password",
        )
        self._core_v1_api.read_namespaced_pod(
            namespace=runtime.namespace,
            name=runtime.pod_name,
        )
        self._psql_runner.run_psql(
            core_v1_api=self._core_v1_api,
            namespace=runtime.namespace,
            pod_name=runtime.pod_name,
            admin_password=admin_password,
            sql=_provision_database_sql(credentials),
        )
        return _binding_values(credentials, host=runtime.host)

    def deprovision_binding(self, context: BindingProvisioningContext) -> None:
        if not _is_postgres_binding(context):
            return

        runtime = _postgres_runtime(context.service_slug)
        _assert_active_owned_service_namespace(
            self._core_v1_api,
            service_slug=context.service_slug,
            namespace=runtime.namespace,
        )
        name = _credential_secret_name(context)
        existing = _read_optional_secret(
            self._core_v1_api,
            namespace=runtime.namespace,
            name=name,
        )
        if existing is None:
            return
        _assert_owned_credential_secret(existing, context=context, name=name)
        credentials = {
            "database": _decode_secret_key(existing, "database"),
            "username": _decode_secret_key(existing, "username"),
            "password": _decode_secret_key(existing, "password"),
        }
        admin_password = _decode_secret_key(
            _read_required_secret(
                self._core_v1_api,
                namespace=runtime.namespace,
                name=runtime.admin_secret_name,
            ),
            "postgres-password",
        )
        self._core_v1_api.read_namespaced_pod(
            namespace=runtime.namespace,
            name=runtime.pod_name,
        )
        self._psql_runner.run_psql(
            core_v1_api=self._core_v1_api,
            namespace=runtime.namespace,
            pod_name=runtime.pod_name,
            admin_password=admin_password,
            sql=_deprovision_database_sql(credentials),
        )
        self._core_v1_api.delete_namespaced_secret(
            namespace=runtime.namespace,
            name=name,
        )

    def _ensure_credential_secret(
        self,
        context: BindingProvisioningContext,
        *,
        namespace: str,
    ) -> dict[str, str]:
        name = _credential_secret_name(context)
        existing = _read_optional_secret(
            self._core_v1_api,
            namespace=namespace,
            name=name,
        )
        if existing is not None:
            _assert_owned_credential_secret(existing, context=context, name=name)
            return {
                "database": _decode_secret_key(existing, "database"),
                "username": _decode_secret_key(existing, "username"),
                "password": _decode_secret_key(existing, "password"),
            }

        identifier = _postgres_identifier(context)
        credentials = {
            "database": identifier,
            "username": identifier,
            "password": self._password_factory(),
        }
        self._core_v1_api.create_namespaced_secret(
            namespace=namespace,
            body=client.V1Secret(
                metadata=client.V1ObjectMeta(
                    name=name,
                    namespace=namespace,
                    labels=binding_secret_labels(
                        app_slug=context.app_slug,
                        service_slug=context.service_slug,
                        alias=context.alias,
                        capability=context.capability,
                        protocol=context.protocol,
                    ),
                ),
                type="Opaque",
                string_data=credentials,
            ),
        )
        return credentials


@dataclass(frozen=True)
class _PostgresRuntime:
    namespace: str
    host: str
    admin_secret_name: str
    pod_name: str


def _postgres_runtime(service_slug: str) -> _PostgresRuntime:
    release = namespace_name("service_instance", service_slug)
    return _PostgresRuntime(
        namespace=release,
        host=f"{release}-postgresql.{release}.svc.cluster.local",
        admin_secret_name=f"{release}-postgresql",
        pod_name=f"{release}-postgresql-0",
    )


def _is_postgres_binding(context: BindingProvisioningContext) -> bool:
    return (
        context.capability == "postgres" and context.protocol is None
    ) or (
        context.capability == "sql" and context.protocol == "postgres"
    )


def _credential_secret_name(context: BindingProvisioningContext) -> str:
    base = f"nephos-pg-{context.app_slug}-{context.alias}"
    if len(base) <= 63:
        return base
    suffix = hashlib.sha256(context.binding_id.encode()).hexdigest()[:12]
    prefix = base[: 63 - len(suffix) - 1].rstrip("-")
    return f"{prefix}-{suffix}"


def _postgres_identifier(context: BindingProvisioningContext) -> str:
    base = f"nephos_{context.app_slug}_{context.alias}".replace("-", "_")
    if len(base) <= 63:
        return base
    suffix = hashlib.sha256(context.binding_id.encode()).hexdigest()[:12]
    prefix = base[: 63 - len(suffix) - 1].rstrip("_")
    return f"{prefix}_{suffix}"


def _read_optional_secret(
    core_v1_api: client.CoreV1Api,
    *,
    namespace: str,
    name: str,
) -> client.V1Secret | None:
    try:
        return core_v1_api.read_namespaced_secret(namespace=namespace, name=name)
    except ApiException as exc:
        if exc.status == 404:
            return None
        raise


def _assert_active_owned_service_namespace(
    core_v1_api: client.CoreV1Api,
    *,
    service_slug: str,
    namespace: str,
) -> None:
    try:
        namespace_resource = core_v1_api.read_namespace(name=namespace)
    except ApiException as exc:
        if exc.status == 404:
            namespace_resource = None
        else:
            raise
    if namespace_resource is None or namespace_resource.metadata is None:
        raise KubernetesRuntimeSafetyError(
            f"refusing to use unowned namespace {namespace}"
        )
    labels = namespace_resource.metadata.labels or {}
    expected = namespace_labels("service_instance", service_slug)
    if not all(labels.get(key) == value for key, value in expected.items()):
        raise KubernetesRuntimeSafetyError(
            f"refusing to use unowned namespace {namespace}"
        )
    if namespace_resource.metadata.deletion_timestamp is not None:
        raise KubernetesRuntimeSafetyError(
            f"refusing to use terminating namespace {namespace}"
        )


def _read_required_secret(
    core_v1_api: client.CoreV1Api,
    *,
    namespace: str,
    name: str,
) -> client.V1Secret:
    return core_v1_api.read_namespaced_secret(namespace=namespace, name=name)


def _decode_secret_key(secret: client.V1Secret, key: str) -> str:
    data = secret.data or {}
    value = data.get(key)
    if value is None:
        raise RuntimeError(f"Secret {secret.metadata.name} is missing key {key}")
    return base64.b64decode(value).decode()


def _assert_owned_credential_secret(
    secret: client.V1Secret,
    *,
    context: BindingProvisioningContext,
    name: str,
) -> None:
    if secret.metadata is None:
        raise KubernetesRuntimeSafetyError(
            f"refusing to use unowned Secret {name}"
        )
    labels = secret.metadata.labels or {}
    expected = binding_secret_labels(
        app_slug=context.app_slug,
        service_slug=context.service_slug,
        alias=context.alias,
        capability=context.capability,
        protocol=context.protocol,
    )
    if not all(labels.get(key) == value for key, value in expected.items()):
        raise KubernetesRuntimeSafetyError(
            f"refusing to use unowned Secret {secret.metadata.namespace}/{name}"
        )


def _binding_values(credentials: dict[str, str], *, host: str) -> dict[str, str]:
    database = credentials["database"]
    username = credentials["username"]
    password = credentials["password"]
    port = "5432"
    return {
        "host": host,
        "port": port,
        "database": database,
        "username": username,
        "password": password,
        "uri": (
            f"postgresql://{quote(username, safe='')}:{quote(password, safe='')}"
            f"@{host}:{port}/{quote(database, safe='')}"
        ),
    }


def _provision_database_sql(credentials: dict[str, str]) -> str:
    database = credentials["database"]
    username = credentials["username"]
    password = credentials["password"]
    role_identifier = _quote_identifier(username)
    database_identifier = _quote_identifier(database)
    return f"""
DO $nephos$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = {_quote_literal(username)}
    ) THEN
        CREATE ROLE {role_identifier} LOGIN PASSWORD {_quote_literal(password)};
    ELSE
        ALTER ROLE {role_identifier} WITH LOGIN PASSWORD {_quote_literal(password)};
    END IF;
END
$nephos$;

SELECT 'CREATE DATABASE {database_identifier} OWNER {role_identifier}'
WHERE NOT EXISTS (
    SELECT 1 FROM pg_database WHERE datname = {_quote_literal(database)}
)\\gexec

GRANT ALL PRIVILEGES ON DATABASE {database_identifier} TO {role_identifier};
""".strip()


def _deprovision_database_sql(credentials: dict[str, str]) -> str:
    database = credentials["database"]
    username = credentials["username"]
    database_identifier = _quote_identifier(database)
    role_identifier = _quote_identifier(username)
    return f"""
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = {_quote_literal(database)};

DROP DATABASE IF EXISTS {database_identifier};
DROP ROLE IF EXISTS {role_identifier};
""".strip()


def _quote_identifier(value: str) -> str:
    if re.fullmatch(r"[a-z_][a-z0-9_]*", value) is None:
        raise ValueError(f"invalid PostgreSQL identifier {value}")
    return f'"{value}"'


def _quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _exec_exit_code(stdout: str, *, marker: str) -> int | None:
    matches = re.findall(rf"^{re.escape(marker)}:(\d+)$", stdout, flags=re.MULTILINE)
    if not matches:
        return None
    return int(matches[-1])


def _stdout_without_exec_marker(stdout: str, *, marker: str) -> str:
    return "\n".join(
        line
        for line in stdout.splitlines()
        if re.fullmatch(rf"{re.escape(marker)}:\d+", line) is None
    )
