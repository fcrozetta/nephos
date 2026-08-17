"""Post-deploy bootstrap for the SeaweedFS Service (ADR 20260816).

SeaweedFS serves S3 anonymously while its identity list is empty, so seeding the
admin identity is not a convenience -- it is what closes the store. Seeding runs
right after deploy, mirroring KubernetesOpenBaoLifecycle.

Also owns the `weed shell` exec plumbing, which the binding provisioner reuses.
"""

import base64
import shlex
from typing import Protocol

from kubernetes import client, stream

from nephos_api.kubernetes_runtime import namespace_name
from nephos_api.providers.base import ProviderContext
from nephos_api.runtime_errors import RuntimeBlockedError

ADMIN_IDENTITY = "nephos-admin"
ACCESS_KEY_SECRET_KEY = "access-key"
SECRET_KEY_SECRET_KEY = "secret-key"
ADMIN_ACTIONS = "Admin,Read,Write,List,Tagging"

# `weed shell` exits 0 even when a subcommand fails, so failure is read from the
# output text. Deliberately narrow: SeaweedFS prefixes real failures with
# "error:", and a broader match (the bare word "failed") false-positives on the
# body of those same messages and on benign output like the identity document a
# successful `s3.configure` prints.
#
# Lives here, next to the runner whose contract it describes, so every caller
# shares one definition. The binding client used to carry its own copy while the
# lifecycle had none, which is how a failed admin re-seed could record a
# successful reconcile.
_ERROR_MARKERS = ("error:", "panic:")


def assert_representable_credential(value: str, *, field: str) -> None:
    """Reject a credential `weed shell` cannot carry.

    `weed shell` accepts a simple single-quoted argument (`'has space'` stores
    correctly) but it is not a shell: the `'\\''` escape idiom that `shlex.quote`
    emits for an embedded quote is not understood, and the identity is silently
    never created. Verified against 3.85.

    So a value containing a single quote has no representation, and the honest
    answer is to refuse it at the boundary rather than emit a command that seeds
    nothing. Generated credentials are alphanumeric, so only an operator override
    can reach this.
    """
    if "'" in value:
        raise RuntimeBlockedError(
            reason="seaweedfs_credential_unrepresentable",
            message=(
                f"SeaweedFS {field} contains a single quote. weed shell cannot "
                "represent it, and applying it would silently seed no identity. "
                "Use a value without single quotes, or leave the option unset so "
                "Nephos generates one."
            ),
        )


def assert_shell_succeeded(output: str, *, reason: str) -> None:
    if any(marker in output for marker in _ERROR_MARKERS):
        raise RuntimeBlockedError(
            reason=reason,
            message=f"weed shell reported a failure: {output.strip()[:400]}",
        )


class SeaweedShellRunner(Protocol):
    def run(
        self,
        *,
        core_v1_api: client.CoreV1Api,
        namespace: str,
        pod_name: str,
        commands: list[str],
    ) -> str: ...


class KubernetesSeaweedShellRunner:
    """Pipe commands into `weed shell` inside the SeaweedFS pod.

    `weed shell` reads commands from stdin, so a batch is a single exec. It exits
    0 even when a subcommand fails, so callers inspect the returned text rather
    than trusting an exit code -- which is why this returns the combined output
    instead of raising.
    """

    def run(
        self,
        *,
        core_v1_api: client.CoreV1Api,
        namespace: str,
        pod_name: str,
        commands: list[str],
    ) -> str:
        # -filer is explicit on purpose. Relying on master discovery alone was
        # observed failing with "error: getOrCreateConnection : fail to dial"
        # when the filer had not yet registered with the master, which would make
        # provisioning flaky against a freshly started pod.
        script = (
            "weed shell -master=localhost:9333 -filer=localhost:8888 "
            "<<'NEPHOS_WEED'\n" + "\n".join(commands) + "\nNEPHOS_WEED"
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


def s3_configure_command(
    *,
    user: str,
    access_key: str,
    secret_key: str,
    actions: str,
    bucket: str | None = None,
) -> str:
    parts = [
        "s3.configure",
        f"-user {shlex.quote(user)}",
        f"-access_key {shlex.quote(access_key)}",
        f"-secret_key {shlex.quote(secret_key)}",
        f"-actions {actions}",
    ]
    if bucket is not None:
        parts.append(f"-buckets {shlex.quote(bucket)}")
    parts.append("-apply")
    return " ".join(parts)


def seaweedfs_runtime(service_slug: str) -> tuple[str, str, str]:
    """(namespace, pod_name, secret_name) for a SeaweedFS Service instance."""
    release = namespace_name("service_instance", service_slug)
    name = f"{release}-seaweedfs"
    return release, f"{name}-0", name


class KubernetesSeaweedFSLifecycle:
    def __init__(
        self,
        *,
        core_v1_api: client.CoreV1Api,
        exec_runner: SeaweedShellRunner | None = None,
    ) -> None:
        self._core_v1_api = core_v1_api
        self._exec_runner = exec_runner or KubernetesSeaweedShellRunner()

    def reconcile(self, context: ProviderContext) -> None:
        namespace, pod_name, secret_name = seaweedfs_runtime(context.slug)
        secret = self._core_v1_api.read_namespaced_secret(
            namespace=namespace, name=secret_name
        )
        access_key = _decode(secret, ACCESS_KEY_SECRET_KEY)
        secret_key = _decode(secret, SECRET_KEY_SECRET_KEY)
        assert_representable_credential(access_key, field="s3-access-key")
        assert_representable_credential(secret_key, field="s3-secret-key")
        self._core_v1_api.read_namespaced_pod(namespace=namespace, name=pod_name)
        # Re-applying an identical identity is a verified no-op, so this is safe
        # on every reconcile and never rotates a credential already in use.
        output = self._exec_runner.run(
            core_v1_api=self._core_v1_api,
            namespace=namespace,
            pod_name=pod_name,
            commands=[
                s3_configure_command(
                    user=ADMIN_IDENTITY,
                    access_key=access_key,
                    secret_key=secret_key,
                    actions=ADMIN_ACTIONS,
                )
            ],
        )
        # Without this a failed re-seed records a successful Service reconcile
        # while the filer keeps the old admin credential and the Secret
        # advertises a new one that does not work.
        assert_shell_succeeded(output, reason="seaweedfs_admin_seed_failed")


def _decode(secret: object, key: str) -> str:
    data = getattr(secret, "data", None) or {}
    value = data.get(key)
    if value is None:
        raise RuntimeBlockedError(
            reason="seaweedfs_admin_credentials_missing",
            message=(
                f"SeaweedFS admin Secret is missing key {key!r}; the S3 API "
                "cannot be closed to anonymous access until it is present."
            ),
        )
    return base64.b64decode(value).decode()
