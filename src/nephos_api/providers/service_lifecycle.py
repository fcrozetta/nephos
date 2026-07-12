"""Service self-lifecycle provisioning: imperative post-deploy steps a Service
runs on itself (as opposed to app-scoped binding provisioning).

The only implementation today is the OpenBao lifecycle, which initializes,
unseals, and ensures a KV v2 mount on a persistent OpenBao StatefulSet after it
is deployed. It is idempotent so repeated reconciles are safe, and it refuses to
re-initialize an already-initialized store whose unseal keys are missing (that
would be unrecoverable data loss).
"""

import base64
import json
import shlex
from typing import Protocol

from kubernetes import client, stream
from kubernetes.client.rest import ApiException

from nephos_api.kubernetes_runtime import (
    KubernetesRuntimeSafetyError,
    namespace_labels,
    namespace_name,
)
from nephos_api.providers.base import ProviderContext
from nephos_api.runtime_errors import RuntimeBlockedError

MANAGED_BY_LABEL = "app.kubernetes.io/managed-by"
_EXIT_MARKER = "NEPHOS_EXIT"


class ServiceLifecycleProvisioner(Protocol):
    def reconcile(self, context: ProviderContext) -> None: ...


class BaoExecRunner(Protocol):
    def run(
        self,
        *,
        core_v1_api: client.CoreV1Api,
        namespace: str,
        pod_name: str,
        argv: list[str],
        token: str | None = None,
    ) -> tuple[str, str, int]: ...


class KubernetesBaoExecRunner:
    """Run a `bao` command inside the OpenBao pod via the Kubernetes exec API,
    returning (stdout, stderr, exit_code). Unlike the psql runner it does not
    raise on a non-zero exit, because `bao status` uses exit code 2 to mean
    "sealed" rather than "error"."""

    def run(
        self,
        *,
        core_v1_api: client.CoreV1Api,
        namespace: str,
        pod_name: str,
        argv: list[str],
        token: str | None = None,
    ) -> tuple[str, str, int]:
        env = 'BAO_ADDR="http://127.0.0.1:8200" '
        if token:
            env += f"BAO_TOKEN={shlex.quote(token)} "
        command = env + " ".join(shlex.quote(arg) for arg in argv)
        script = (
            f'{command}\nrc=$?\nprintf \'\\n{_EXIT_MARKER}:%s\\n\' "$rc"\nexit "$rc"'
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
        return_code = _exit_code(stdout_text)
        if return_code is None:
            stream_rc = getattr(response, "returncode", None)
            return_code = int(stream_rc) if stream_rc not in (None,) else 1
        return _strip_marker(stdout_text), "".join(stderr), return_code


class KubernetesOpenBaoLifecycle:
    def __init__(
        self,
        *,
        core_v1_api: client.CoreV1Api,
        secret_name: str = "openbao-init",
        root_token_key: str = "root-token",
        unseal_key_key: str = "unseal-key",
        kv_mount: str = "secret",
        exec_runner: BaoExecRunner | None = None,
    ) -> None:
        self._core_v1_api = core_v1_api
        self._secret_name = secret_name
        self._root_token_key = root_token_key
        self._unseal_key_key = unseal_key_key
        self._kv_mount = kv_mount
        self._exec_runner = exec_runner or KubernetesBaoExecRunner()

    def reconcile(self, context: ProviderContext) -> None:
        namespace = namespace_name(context.target_type, context.slug)
        pod_name = f"{namespace}-openbao-0"
        self._assert_active_owned_namespace(context.slug, namespace)

        status = self._status(namespace, pod_name)
        if not status["initialized"]:
            root_token, unseal_key = self._initialize(namespace, pod_name)
            # Persist keys immediately: they are shown once and are otherwise
            # unrecoverable. A crash before this leaves the store unusable.
            self._persist_keys(namespace, root_token, unseal_key)
            status = self._status(namespace, pod_name)
        else:
            keys = self._read_keys(namespace)
            if keys is None:
                raise RuntimeBlockedError(
                    reason="openbao_unseal_keys_missing",
                    message=(
                        "OpenBao is initialized but its unseal-keys Secret "
                        f"{self._secret_name} is missing; refusing to re-initialize "
                        "(that would be unrecoverable data loss). Manual recovery "
                        "required."
                    ),
                )
            root_token, unseal_key = keys

        if status["sealed"]:
            self._unseal(namespace, pod_name, unseal_key)
        self._ensure_kv_mount(namespace, pod_name, root_token)

    def _status(self, namespace: str, pod_name: str) -> dict[str, bool]:
        stdout, stderr, rc = self._exec(namespace, pod_name, ["status", "-format=json"])
        # `bao status` exits 0 (unsealed) or 2 (sealed) and prints JSON either
        # way; any other code with no JSON is a real failure.
        data = _parse_json(stdout)
        if data is None:
            raise RuntimeBlockedError(
                reason="openbao_status_failed",
                message=(stderr.strip() or "openbao status did not return JSON"),
            )
        return {
            "initialized": bool(data.get("initialized", False)),
            "sealed": bool(data.get("sealed", True)),
        }

    def _initialize(self, namespace: str, pod_name: str) -> tuple[str, str]:
        stdout, stderr, rc = self._exec(
            namespace,
            pod_name,
            ["operator", "init", "-key-shares=1", "-key-threshold=1", "-format=json"],
        )
        if rc != 0:
            raise RuntimeBlockedError(
                reason="openbao_init_failed",
                message=(stderr.strip() or "openbao init failed"),
            )
        data = _parse_json(stdout) or {}
        keys = data.get("unseal_keys_b64") or data.get("keys_base64") or []
        root_token = data.get("root_token")
        if not keys or not root_token:
            raise RuntimeBlockedError(
                reason="openbao_init_failed",
                message="openbao init did not return unseal keys and a root token",
            )
        return str(root_token), str(keys[0])

    def _unseal(self, namespace: str, pod_name: str, unseal_key: str) -> None:
        stdout, stderr, rc = self._exec(
            namespace, pod_name, ["operator", "unseal", unseal_key]
        )
        if rc != 0:
            raise RuntimeBlockedError(
                reason="openbao_unseal_failed",
                message=(stderr.strip() or "openbao unseal failed"),
            )

    def _ensure_kv_mount(self, namespace: str, pod_name: str, root_token: str) -> None:
        stdout, stderr, rc = self._exec(
            namespace, pod_name, ["secrets", "list", "-format=json"], token=root_token
        )
        mounts = _parse_json(stdout) or {}
        if f"{self._kv_mount}/" in mounts:
            return
        _out, mount_err, mount_rc = self._exec(
            namespace,
            pod_name,
            ["secrets", "enable", f"-path={self._kv_mount}", "-version=2", "kv"],
            token=root_token,
        )
        if mount_rc != 0 and "path is already in use" not in mount_err:
            raise RuntimeBlockedError(
                reason="openbao_mount_failed",
                message=(mount_err.strip() or "openbao kv mount failed"),
            )

    def _exec(
        self,
        namespace: str,
        pod_name: str,
        argv: list[str],
        *,
        token: str | None = None,
    ) -> tuple[str, str, int]:
        return self._exec_runner.run(
            core_v1_api=self._core_v1_api,
            namespace=namespace,
            pod_name=pod_name,
            argv=argv,
            token=token,
        )

    def _persist_keys(self, namespace: str, root_token: str, unseal_key: str) -> None:
        body = client.V1Secret(
            metadata=client.V1ObjectMeta(
                name=self._secret_name,
                namespace=namespace,
                labels={MANAGED_BY_LABEL: "nephos"},
            ),
            type="Opaque",
            string_data={
                self._root_token_key: root_token,
                self._unseal_key_key: unseal_key,
            },
        )
        try:
            self._core_v1_api.create_namespaced_secret(namespace=namespace, body=body)
        except ApiException as exc:
            if exc.status == 409:
                self._core_v1_api.replace_namespaced_secret(
                    name=self._secret_name, namespace=namespace, body=body
                )
            else:
                raise

    def _read_keys(self, namespace: str) -> tuple[str, str] | None:
        try:
            secret = self._core_v1_api.read_namespaced_secret(
                name=self._secret_name, namespace=namespace
            )
        except ApiException as exc:
            if exc.status == 404:
                return None
            raise
        labels = (secret.metadata.labels or {}) if secret.metadata else {}
        if labels.get(MANAGED_BY_LABEL) != "nephos":
            raise KubernetesRuntimeSafetyError(
                f"refusing to use unowned openbao secret {self._secret_name}"
            )
        data = secret.data or {}
        root = data.get(self._root_token_key)
        key = data.get(self._unseal_key_key)
        if not root or not key:
            return None
        return (
            base64.b64decode(root).decode("utf-8"),
            base64.b64decode(key).decode("utf-8"),
        )

    def _assert_active_owned_namespace(self, slug: str, namespace: str) -> None:
        try:
            resource = self._core_v1_api.read_namespace(name=namespace)
        except ApiException as exc:
            if exc.status == 404:
                resource = None
            else:
                raise
        if resource is None or resource.metadata is None:
            raise KubernetesRuntimeSafetyError(
                f"refusing to use unowned namespace {namespace}"
            )
        labels = resource.metadata.labels or {}
        expected = namespace_labels("service_instance", slug)
        if not all(labels.get(key) == value for key, value in expected.items()):
            raise KubernetesRuntimeSafetyError(
                f"refusing to use unowned namespace {namespace}"
            )


def _exit_code(text: str) -> int | None:
    for line in reversed(text.splitlines()):
        if line.startswith(f"{_EXIT_MARKER}:"):
            try:
                return int(line.split(":", 1)[1])
            except ValueError:
                return None
    return None


def _strip_marker(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines() if not line.startswith(f"{_EXIT_MARKER}:")
    )


def _parse_json(text: str) -> dict | None:
    text = text.strip()
    if not text:
        return None
    start = text.find("{")
    if start == -1:
        return None
    try:
        return json.loads(text[start:])
    except json.JSONDecodeError:
        return None
