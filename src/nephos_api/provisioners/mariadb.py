import base64
import hashlib
import re
import secrets
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


class MariaDBSqlRunner(Protocol):
    def run_sql(
        self,
        *,
        core_v1_api: client.CoreV1Api,
        namespace: str,
        pod_name: str,
        sql: str,
    ) -> None: ...


class KubernetesMariaDBSqlRunner:
    # Takes no password on purpose. An interpolated credential would sit in
    # argv[2] of `sh -lc`, which is both readable in the pod's /proc and recorded
    # verbatim in the Kubernetes API audit log for every exec. Instead the script
    # dereferences MARIADB_ROOT_PASSWORD, which the `mariadb-service` workload
    # already injects into the container from the runtime Secret -- so the value
    # never crosses the API boundary at all. That injection is a cross-file
    # contract with `_mariadb_service`; the guard below is what makes a broken
    # one say so instead of surfacing as "access denied".
    #
    # This removes the *service-wide* credential only. The per-binding password
    # is still in the SQL payload (`IDENTIFIED BY '...'`), so it still reaches
    # argv and the audit log. That is a strictly smaller exposure -- one app's
    # database rather than the superuser -- and closing it needs a different
    # mechanism than an env var, since the value is part of the statement.
    def run_sql(
        self,
        *,
        core_v1_api: client.CoreV1Api,
        namespace: str,
        pod_name: str,
        sql: str,
    ) -> None:
        marker = "NEPHOS_EXIT"
        # MYSQL_PWD passes the credential to the client through the environment
        # rather than its argv, the same reason the postgres runner uses
        # PGPASSWORD. `mariadb` (not the deprecated `mysql` symlink) aborts on
        # the first error in batch mode, which is what ON_ERROR_STOP=1 buys on
        # the postgres side.
        #
        # The marker is printed on both branches: a bare `${VAR:?msg}` would exit
        # the shell before printing it, and a missing marker is reported as
        # "missing exec exit marker", losing the message that explains why.
        script = (
            'if [ -z "${MARIADB_ROOT_PASSWORD:-}" ]; then\n'
            "  echo 'MARIADB_ROOT_PASSWORD is unset in the mariadb container;"
            " the mariadb-service workload must inject it' >&2\n"
            "  rc=1\n"
            "else\n"
            'MYSQL_PWD="$MARIADB_ROOT_PASSWORD"'
            " mariadb -u root --batch <<'NEPHOS_SQL'\n"
            f"{sql}\n"
            "NEPHOS_SQL\n"
            "rc=$?\n"
            "fi\n"
            f"printf '\\n{marker}:%s\\n' \"$rc\"\n"
            'exit "$rc"'
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
                or "mariadb execution failed"
            )
            raise RuntimeError(message.strip())


class MariaDBAppScopedProvisioner:
    # ADR 20260721: the mysql engine grants the "admin-credentials" entitlement,
    # matching the sql engine. The engine router blocks any binding requesting an
    # entitlement outside this set.
    recognized_entitlements = frozenset({"admin-credentials"})

    def __init__(
        self,
        *,
        core_v1_api: client.CoreV1Api,
        sql_runner: MariaDBSqlRunner | None = None,
        password_factory: Callable[[], str] | None = None,
    ) -> None:
        self._core_v1_api = core_v1_api
        self._sql_runner = sql_runner or KubernetesMariaDBSqlRunner()
        self._password_factory = password_factory or (lambda: secrets.token_urlsafe(24))

    def provision_binding(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str] | None:
        if not _is_mariadb_binding(context):
            return None

        runtime = _mariadb_runtime(context.service_slug)
        _assert_active_owned_service_namespace(
            self._core_v1_api,
            service_slug=context.service_slug,
            namespace=runtime.namespace,
        )
        credentials = self._ensure_credential_secret(
            context,
            namespace=runtime.namespace,
        )
        self._core_v1_api.read_namespaced_pod(
            namespace=runtime.namespace,
            name=runtime.pod_name,
        )
        self._sql_runner.run_sql(
            core_v1_api=self._core_v1_api,
            namespace=runtime.namespace,
            pod_name=runtime.pod_name,
            sql=_provision_database_sql(credentials),
        )
        # Read only when this binding is actually owed the credential. The runner
        # gets it from the container's own environment, so an unentitled binding
        # never pulls the service-wide root password into the control plane.
        return _binding_values(
            credentials,
            host=runtime.host,
            # Stays `admin_password` here on purpose: this feeds the
            # adminUsername/adminPassword binding outputs, whose names are the
            # cross-provider contract shared with postgres (ADR 20260630).
            admin_password=(
                self._read_root_password(runtime)
                if _grants_admin_credentials(context)
                else None
            ),
        )

    def _read_root_password(self, runtime: "_MariaDBRuntime") -> str:
        return _decode_secret_key(
            _read_required_secret(
                self._core_v1_api,
                namespace=runtime.namespace,
                name=runtime.root_secret_name,
            ),
            "root-password",
        )

    def deprovision_binding(self, context: BindingProvisioningContext) -> None:
        if not _is_mariadb_binding(context):
            return

        runtime = _mariadb_runtime(context.service_slug)
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
        self._core_v1_api.read_namespaced_pod(
            namespace=runtime.namespace,
            name=runtime.pod_name,
        )
        # Teardown reads no Secret at all now: the runner authenticates from the
        # container's environment, and deprovision owes nobody a credential. It
        # also stops a missing root Secret from blocking a teardown that no
        # longer needs it.
        self._sql_runner.run_sql(
            core_v1_api=self._core_v1_api,
            namespace=runtime.namespace,
            pod_name=runtime.pod_name,
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

        identifier = _mariadb_identifier(context)
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
class _MariaDBRuntime:
    namespace: str
    host: str
    root_secret_name: str
    pod_name: str


def _mariadb_runtime(service_slug: str) -> _MariaDBRuntime:
    # Names are the `mariadb-service` Pulumi workload's, not a chart's: it emits
    # `{release}-mariadb` for the Service, the Secret and the StatefulSet.
    release = namespace_name("service_instance", service_slug)
    return _MariaDBRuntime(
        namespace=release,
        host=f"{release}-mariadb.{release}.svc.cluster.local",
        root_secret_name=f"{release}-mariadb",
        pod_name=f"{release}-mariadb-0",
    )


def _is_mariadb_binding(context: BindingProvisioningContext) -> bool:
    # Narrow on purpose. Returning values for a binding this engine does not own
    # would hand an app the wrong credentials; returning None for one it does own
    # leaves the app with an empty binding secret and a permanent "unavailable"
    # page. There is no legacy bare-`mysql` capability to preserve, unlike
    # postgres, so `sql`/`mysql` is the only accepted shape.
    return context.capability == "sql" and context.protocol == "mysql"


def _credential_secret_name(context: BindingProvisioningContext) -> str:
    base = f"nephos-my-{context.app_slug}-{context.alias}"
    if len(base) <= 63:
        return base
    suffix = hashlib.sha256(context.binding_id.encode()).hexdigest()[:12]
    prefix = base[: 63 - len(suffix) - 1].rstrip("-")
    return f"{prefix}-{suffix}"


def _mariadb_identifier(context: BindingProvisioningContext) -> str:
    # 63 is postgres' limit, kept here rather than MariaDB's looser 64 (database)
    # / 80 (user) so one identifier is legal on both engines and the truncation
    # arithmetic stays identical to the postgres provisioner's.
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
        raise KubernetesRuntimeSafetyError(f"refusing to use unowned Secret {name}")
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


def _binding_values(
    credentials: dict[str, str],
    *,
    host: str,
    admin_password: str | None = None,
) -> dict[str, str]:
    database = credentials["database"]
    username = credentials["username"]
    password = credentials["password"]
    port = "3306"
    values = {
        "host": host,
        "port": port,
        "database": database,
        "username": username,
        "password": password,
        # `mysql://` rather than `mariadb://`: it is what the Go, Node and
        # SQLAlchemy ecosystems parse, and MariaDB-native drivers use their own
        # prefixed forms (`jdbc:mariadb://`) that no generic consumer accepts.
        "uri": (
            f"mysql://{quote(username, safe='')}:"
            f"{quote(password, safe='')}@{host}:{port}/"
            f"{quote(database, safe='')}"
        ),
    }
    if admin_password is not None:
        values.update(
            {
                "adminUsername": "root",
                "adminPassword": admin_password,
            }
        )
    return values


def _grants_admin_credentials(context: BindingProvisioningContext) -> bool:
    # ADR 20260721: admin credentials go only to a binding that explicitly
    # declares the entitlement (default-deny).
    return "admin-credentials" in context.entitlements


def _provision_database_sql(credentials: dict[str, str]) -> str:
    database = credentials["database"]
    username = credentials["username"]
    password = credentials["password"]
    user_literal = _quote_literal(username)
    password_literal = _quote_literal(password)
    database_identifier = _quote_identifier(database)
    # `@'%'` and not `@'localhost'`: every consumer connects over the cluster
    # Service from another pod, so a localhost-scoped grant authenticates only
    # from inside the MariaDB pod itself and fails for every real app.
    #
    # CREATE ... IF NOT EXISTS then ALTER USER reproduces the postgres
    # branch (create with password, else reset password) without a procedural
    # block, and leaves a re-provision idempotent.
    return f"""
CREATE DATABASE IF NOT EXISTS {database_identifier};
CREATE USER IF NOT EXISTS {user_literal}@'%' IDENTIFIED BY {password_literal};
ALTER USER {user_literal}@'%' IDENTIFIED BY {password_literal};
GRANT ALL PRIVILEGES ON {database_identifier}.* TO {user_literal}@'%';
""".strip()


def _deprovision_database_sql(credentials: dict[str, str]) -> str:
    database = credentials["database"]
    username = credentials["username"]
    database_identifier = _quote_identifier(database)
    # No pg_terminate_backend analogue: MariaDB drops a database with sessions
    # still attached, so the postgres provisioner's session-termination step has
    # nothing to prevent here.
    return f"""
DROP DATABASE IF EXISTS {database_identifier};
DROP USER IF EXISTS {_quote_literal(username)}@'%';
""".strip()


def _quote_identifier(value: str) -> str:
    if re.fullmatch(r"[a-z_][a-z0-9_]*", value) is None:
        raise ValueError(f"invalid MariaDB identifier {value}")
    return f"`{value}`"


def _quote_literal(value: str) -> str:
    # MariaDB honours backslash escapes inside string literals by default (no
    # standard_conforming_strings equivalent), so doubling quotes alone is not
    # enough -- a lone trailing backslash would escape the closing quote.
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


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
