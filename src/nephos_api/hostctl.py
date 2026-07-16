"""Thin host-side wrappers around docker / k3d / kubectl for the `nephos` CLI.

Everything funnels through the module-level ``_run`` so tests monkeypatch a
single seam and never touch a real cluster. These are orchestration helpers used
by the setup/up/status/down commands; the in-cluster control plane never calls
them.
"""

from __future__ import annotations

import base64
import contextlib
import os
import shutil
import socket
import subprocess
import time
from collections.abc import Iterator, Sequence
from pathlib import Path


class HostCommandError(RuntimeError):
    def __init__(self, cmd: Sequence[str], returncode: int, output: str) -> None:
        super().__init__(
            f"command failed ({returncode}): {' '.join(cmd)}\n{output}".rstrip()
        )
        self.cmd = list(cmd)
        self.returncode = returncode
        self.output = output


def _run(
    cmd: Sequence[str],
    *,
    input_text: str | None = None,
    check: bool = True,
) -> str:
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        list(cmd),
        input=input_text,
        capture_output=True,
        text=True,
    )
    if check and proc.returncode != 0:
        raise HostCommandError(cmd, proc.returncode, proc.stderr or proc.stdout)
    return proc.stdout


def require_tools(*tools: str) -> None:
    missing = [tool for tool in tools if shutil.which(tool) is None]
    if missing:
        raise HostCommandError(
            ["which", *missing], 1, f"missing required tools: {', '.join(missing)}"
        )


# --- docker / k3d -----------------------------------------------------------


def docker_build(tag: str, *, context: str = ".", platform: str | None = None) -> None:
    cmd = ["docker", "build", "-t", tag]
    if platform:
        cmd += ["--platform", platform]
    cmd += [context]
    _run(cmd)


def k3d_cluster_exists(cluster: str) -> bool:
    try:
        _run(["k3d", "cluster", "list", cluster])
        return True
    except HostCommandError:
        return False


def k3d_image_import(image: str, *, cluster: str) -> None:
    _run(["k3d", "image", "import", image, "-c", cluster])


def k3d_cluster_delete(cluster: str) -> None:
    _run(["k3d", "cluster", "delete", cluster])


def run_local_routing_script(script: Path, *, domain: str, cluster: str) -> None:
    """Run scripts/setup-local-routing.sh interactively (it uses sudo)."""
    env = {**os.environ, "NEPHOS_K3D_CLUSTER": cluster}
    proc = subprocess.run(  # noqa: S603 - fixed argv, inherits tty for sudo prompts
        [str(script), domain], env=env
    )
    if proc.returncode != 0:
        raise HostCommandError(
            [str(script), domain], proc.returncode, "local routing setup failed"
        )


# --- kubectl ----------------------------------------------------------------


def kubectl(
    args: Sequence[str],
    *,
    context: str | None = None,
    input_text: str | None = None,
    check: bool = True,
) -> str:
    cmd = ["kubectl"]
    if context:
        cmd += ["--context", context]
    cmd += list(args)
    return _run(cmd, input_text=input_text, check=check)


def kubectl_apply(manifest_yaml: str, *, context: str | None = None) -> str:
    return kubectl(["apply", "-f", "-"], context=context, input_text=manifest_yaml)


def kubectl_get_secret_value(
    name: str,
    *,
    namespace: str,
    key: str,
    context: str | None = None,
) -> str | None:
    # --ignore-not-found + check=True so a genuinely absent Secret returns None
    # (safe to generate) while a real read failure (RBAC, transient api error)
    # raises instead of masquerading as absence -- the latter would let the
    # caller regenerate and overwrite the authoritative Pulumi passphrase.
    out = kubectl(
        [
            "get",
            "secret",
            name,
            "-n",
            namespace,
            "--ignore-not-found",
            "-o",
            f"jsonpath={{.data.{key}}}",
        ],
        context=context,
    ).strip()
    if not out:
        return None
    return base64.b64decode(out).decode()


def kubectl_rollout_status(
    deployment: str,
    *,
    namespace: str,
    context: str | None = None,
    timeout: str = "180s",
) -> str:
    return kubectl(
        [
            "rollout",
            "status",
            f"deploy/{deployment}",
            "-n",
            namespace,
            f"--timeout={timeout}",
        ],
        context=context,
    )


def kubectl_scale(
    deployment: str,
    *,
    replicas: int,
    namespace: str,
    context: str | None = None,
) -> str:
    return kubectl(
        ["scale", f"deploy/{deployment}", f"--replicas={replicas}", "-n", namespace],
        context=context,
    )


def kubectl_delete_namespace(namespace: str, *, context: str | None = None) -> str:
    return kubectl(
        ["delete", "namespace", namespace, "--ignore-not-found"], context=context
    )


def cluster_reachable(context: str | None = None) -> bool:
    try:
        kubectl(["version", "-o", "json"], context=context)
        return True
    except HostCommandError:
        return False


# --- port-forward (bootstrap-only; not a runtime dependency) -----------------


@contextlib.contextmanager
def port_forward(
    service: str,
    *,
    namespace: str,
    local_port: int,
    remote_port: int,
    context: str | None = None,
    ready_timeout: float = 20.0,
) -> Iterator[None]:
    # Refuse to run if the local port is already taken: otherwise the new
    # kubectl silently fails to bind and the readiness probe connects to the
    # foreign listener, driving the bootstrap at the wrong backend.
    if _port_in_use(local_port):
        raise HostCommandError(
            ["kubectl", "port-forward"],
            1,
            f"local port {local_port} is already in use "
            "(a stale port-forward?); free it and retry",
        )
    cmd = ["kubectl"]
    if context:
        cmd += ["--context", context]
    cmd += [
        "port-forward",
        f"svc/{service}",
        f"{local_port}:{remote_port}",
        "-n",
        namespace,
    ]
    proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    try:
        _wait_for_port(local_port, proc=proc, timeout=ready_timeout)
        yield
    finally:
        proc.terminate()
        with contextlib.suppress(Exception):
            proc.wait(timeout=5)


def _port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket() as sock:
        sock.settimeout(1.0)
        return sock.connect_ex((host, port)) == 0


def _wait_for_port(
    port: int,
    *,
    proc: subprocess.Popen | None = None,
    host: str = "127.0.0.1",
    timeout: float = 20.0,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc is not None and proc.poll() is not None:
            raise HostCommandError(
                ["kubectl", "port-forward"],
                proc.returncode or 1,
                "port-forward exited before it was ready (port bind failed?)",
            )
        with socket.socket() as sock:
            sock.settimeout(1.0)
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(0.3)
    raise HostCommandError(["kubectl", "port-forward"], 1, f"port {port} unreachable")
