"""Live Valkey provisioning over `valkey-cli` (ADR 20260825).

One ACL user per binding, scoped to its own key prefix and pub/sub channel
prefix. Valkey has no per-app databases: the numeric db index is not an ACL
boundary (a user may `SELECT` any index), so key patterns are the only isolation
Valkey actually enforces. Credentials are cached in an owned Secret in the Service
namespace so a reconcile re-reads rather than rotates -- an App holding a working
credential must never have it changed underneath it.
"""

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
from nephos_api.runtime_errors import RuntimeBlockedError

VALKEY_PORT = 6379
# Valkey applies key patterns across every numeric db, and a binding user may
# still `SELECT` another index (verified), so the db index carries no isolation.
# It is reported as an output purely because clients ask for one.
BINDING_DB_INDEX = "0"
# `valkey-cli` exits 0 even when a command returns an error reply, exactly like
# `weed shell` (ADR 20260816), so success is judged from the output text. These
# are the reply prefixes Valkey actually emits for the failures reachable here:
# a malformed ACL rule, a rejected password hash, a denied command or key, and
# an unauthenticated or mis-authenticated connection.
_ERROR_MARKERS = ("ERR ", "NOPERM", "WRONGPASS", "NOAUTH", "(error)")


class ValkeyCliRunner(Protocol):
    def run(
        self,
        *,
        core_v1_api: client.CoreV1Api,
        namespace: str,
        pod_name: str,
        commands: list[str],
    ) -> str: ...


class KubernetesValkeyCliRunner:
    """Pipe commands into `valkey-cli` inside the Valkey pod.

    Carries no credential of its own. `valkey-cli` authenticates from
    REDISCLI_AUTH -- Valkey kept the Redis client's env var name, verified on 8.1:
    VALKEYCLI_AUTH is not honoured even by `valkey-cli` -- which the
    `valkey-service` workload injects into the container
    from the runtime Secret, so the admin password never reaches the exec command
    array -- and therefore never reaches the Kubernetes audit log. That injection
    is a cross-file contract with `_valkey_service`; the guard below is what makes
    a broken one say so rather than surfacing as a bare NOAUTH.

    Per-binding credentials are passed to `ACL SETUSER` as `#<sha256>` rather than
    `>plaintext`, so the payload carries a verifier instead of a usable secret.
    Unlike the SQL provisioners (see issue #112) nothing sensitive is left in
    argv at all.

    Returns the combined output instead of raising, because the exit code is not
    a failure signal here; callers pass it to `assert_valkey_succeeded`.
    """

    def run(
        self,
        *,
        core_v1_api: client.CoreV1Api,
        namespace: str,
        pod_name: str,
        commands: list[str],
    ) -> str:
        script = (
            'if [ -z "${REDISCLI_AUTH:-}" ]; then\n'
            "  echo 'REDISCLI_AUTH is unset in the valkey container;"
            " the valkey-service workload must inject it' >&2\n"
            "  exit 1\n"
            "fi\n"
            "valkey-cli --no-auth-warning <<'NEPHOS_VALKEY'\n"
            + "\n".join(commands)
            + "\nNEPHOS_VALKEY"
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
        return "".join(stdout) + "".join(stderr)


def assert_valkey_succeeded(output: str, *, reason: str) -> None:
    if any(marker in output for marker in _ERROR_MARKERS):
        raise RuntimeBlockedError(
            reason=reason,
            message=f"valkey-cli reported a failure: {output.strip()[:400]}",
        )


class ValkeyAppScopedProvisioner:
    # ADR 20260721: the valkey engine grants the "admin-credentials" entitlement,
    # matching the sql and mysql engines. The engine router blocks any binding
    # requesting an entitlement outside this set.
    recognized_entitlements = frozenset({"admin-credentials"})

    def __init__(
        self,
        *,
        core_v1_api: client.CoreV1Api,
        cli_runner: ValkeyCliRunner | None = None,
        password_factory: Callable[[], str] | None = None,
    ) -> None:
        self._core_v1_api = core_v1_api
        self._cli_runner = cli_runner or KubernetesValkeyCliRunner()
        # Must stay high-entropy. Valkey stores an unsalted single-round SHA-256,
        # and this provisioner puts that hash in the exec payload, so a short or
        # caller-supplied password would turn an audit-log entry into a
        # brute-forceable one. 32 urlsafe chars is ~192 bits.
        self._password_factory = password_factory or (lambda: secrets.token_urlsafe(24))

    def provision_binding(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str] | None:
        if not _is_valkey_binding(context):
            return None

        runtime = _valkey_runtime(context.service_slug)
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
        output = self._cli_runner.run(
            core_v1_api=self._core_v1_api,
            namespace=runtime.namespace,
            pod_name=runtime.pod_name,
            commands=_provision_commands(credentials),
        )
        # ACL SAVE is checked as strictly as SETUSER on purpose. Runtime ACL
        # changes live in memory; if the save is skipped or fails, provisioning
        # looks successful, the app connects, and then every binding breaks at
        # once the next time the pod restarts.
        assert_valkey_succeeded(output, reason="binding_provisioner_failed")
        return _binding_values(
            credentials,
            host=runtime.host,
            # Read only when this binding is actually owed the credential. The
            # runner authenticates from the container's own environment, so an
            # unentitled binding never pulls the service-wide password into the
            # control plane.
            admin_password=(
                self._read_admin_password(runtime)
                if _grants_admin_credentials(context)
                else None
            ),
        )

    def _read_admin_password(self, runtime: "_ValkeyRuntime") -> str:
        return _decode_secret_key(
            _read_required_secret(
                self._core_v1_api,
                namespace=runtime.namespace,
                name=runtime.admin_secret_name,
            ),
            "valkey-password",
        )

    def deprovision_binding(self, context: BindingProvisioningContext) -> None:
        if not _is_valkey_binding(context):
            return

        runtime = _valkey_runtime(context.service_slug)
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
        username = _decode_secret_key(existing, "username")
        self._core_v1_api.read_namespaced_pod(
            namespace=runtime.namespace,
            name=runtime.pod_name,
        )
        # Teardown reads no Secret beyond the binding's own: the runner
        # authenticates from the container environment and deprovision owes
        # nobody a credential.
        output = self._cli_runner.run(
            core_v1_api=self._core_v1_api,
            namespace=runtime.namespace,
            pod_name=runtime.pod_name,
            commands=_deprovision_commands(username),
        )
        # Same reasoning as provision, mirrored: an unsaved DELUSER means a pod
        # restart resurrects a user whose binding is gone.
        assert_valkey_succeeded(output, reason="binding_deprovisioner_failed")
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
                "username": _decode_secret_key(existing, "username"),
                "password": _decode_secret_key(existing, "password"),
                "keyPrefix": _decode_secret_key(existing, "keyPrefix"),
            }

        identifier = _valkey_identifier(context)
        credentials = {
            "username": identifier,
            "password": self._password_factory(),
            "keyPrefix": _key_prefix(context),
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
class _ValkeyRuntime:
    namespace: str
    host: str
    admin_secret_name: str
    pod_name: str


def _valkey_runtime(service_slug: str) -> _ValkeyRuntime:
    # Names are the `valkey-service` Pulumi workload's, not a chart's: it emits
    # `{release}-valkey` for the Service, the Secret and the StatefulSet.
    release = namespace_name("service_instance", service_slug)
    return _ValkeyRuntime(
        namespace=release,
        host=f"{release}-valkey.{release}.svc.cluster.local",
        admin_secret_name=f"{release}-valkey",
        pod_name=f"{release}-valkey-0",
    )


def _is_valkey_binding(context: BindingProvisioningContext) -> bool:
    # Narrow on purpose, as the sql engines are. Answering for a binding this
    # engine does not own would hand an app the wrong credentials; returning None
    # for one it does own leaves the app with an empty binding Secret and a
    # permanent "unavailable" page.
    return context.capability == "kv" and context.protocol == "redis"


def _credential_secret_name(context: BindingProvisioningContext) -> str:
    base = f"nephos-valkey-{context.app_slug}-{context.alias}"
    if len(base) <= 63:
        return base
    suffix = hashlib.sha256(context.binding_id.encode()).hexdigest()[:12]
    prefix = base[: 63 - len(suffix) - 1].rstrip("-")
    return f"{prefix}-{suffix}"


def _valkey_identifier(context: BindingProvisioningContext) -> str:
    # Valkey usernames are freer than SQL identifiers, but the 63-char budget and
    # underscore form are kept so one identifier shape is legal on every engine.
    base = f"nephos_{context.app_slug}_{context.alias}".replace("-", "_")
    if len(base) <= 63:
        return base
    suffix = hashlib.sha256(context.binding_id.encode()).hexdigest()[:12]
    prefix = base[: 63 - len(suffix) - 1].rstrip("_")
    return f"{prefix}_{suffix}"


def _key_prefix(context: BindingProvisioningContext) -> str:
    # Colon-separated, which is the conventional Redis/Valkey namespace separator, and
    # reported to the App as `keyPrefix` because the App has to apply it: Valkey
    # enforces the pattern, it does not rewrite keys.
    app = context.app_slug.replace("-", "_")
    alias = context.alias.replace("-", "_")
    return f"nephos:{app}:{alias}:"


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
    username = credentials["username"]
    password = credentials["password"]
    key_prefix = credentials["keyPrefix"]
    port = str(VALKEY_PORT)
    values = {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "database": BINDING_DB_INDEX,
        # Not part of the SQL contract, and it has to be: Valkey enforces the key
        # pattern but never rewrites keys, so an App that ignores this gets
        # NOPERM on its first write.
        "keyPrefix": key_prefix,
        # `redis://`, not `valkey://`: this is the RESP wire protocol's scheme and
        # it is what client libraries parse. A valkey:// URI would be rejected by
        # every redis client, which is the whole point of wire compatibility.
        "uri": (
            f"redis://{quote(username, safe='')}:"
            f"{quote(password, safe='')}@{host}:{port}/{BINDING_DB_INDEX}"
        ),
    }
    if admin_password is not None:
        values.update(
            {
                "adminUsername": "default",
                "adminPassword": admin_password,
            }
        )
    return values


def _grants_admin_credentials(context: BindingProvisioningContext) -> bool:
    # ADR 20260721: admin credentials go only to a binding that explicitly
    # declares the entitlement (default-deny).
    return "admin-credentials" in context.entitlements


def _password_hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _provision_commands(credentials: dict[str, str]) -> list[str]:
    username = _validate_username(credentials["username"])
    pattern = f"{credentials['keyPrefix']}*"
    digest = _password_hash(credentials["password"])
    return [
        # `reset` first, or SETUSER is additive: re-provisioning after a prefix
        # change would leave the old pattern granted, which passes on the first
        # run and is wrong on the second.
        #
        # `-@dangerous` is not hygiene, it is the isolation. Key patterns do not
        # constrain FLUSHALL, so without it a binding user cannot read a
        # neighbour's keys but can delete all of them (verified). It also removes
        # ACL, CONFIG and SHUTDOWN, so a binding cannot escalate itself.
        #
        # The channel grant is required because Valkey defaults
        # acl-pubsub-default to resetchannels, so a key-pattern-only user has no
        # pub/sub at all.
        f"ACL SETUSER {username} reset on #{digest} "
        f"~{pattern} &{pattern} +@all -@dangerous",
        "ACL SAVE",
    ]


def _deprovision_commands(username: str) -> list[str]:
    return [f"ACL DELUSER {_validate_username(username)}", "ACL SAVE"]


def _validate_username(value: str) -> str:
    # Valkey command arguments are whitespace-delimited in the CLI, and these
    # commands are composed as text, so anything outside this shape could add
    # arguments to SETUSER. Generated identifiers already match it; this refuses
    # a value that reached here from anywhere else.
    if re.fullmatch(r"[a-z_][a-z0-9_]*", value) is None:
        raise ValueError(f"invalid Valkey username {value}")
    return value
