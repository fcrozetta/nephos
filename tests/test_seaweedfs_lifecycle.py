import base64

import pytest

from nephos_api.providers.base import ProviderContext
from nephos_api.providers.seaweedfs_lifecycle import KubernetesSeaweedFSLifecycle
from nephos_api.runtime_errors import RuntimeBlockedError


class FakeSecret:
    def __init__(self, data: dict[str, str]) -> None:
        self.data = {
            key: base64.b64encode(value.encode()).decode()
            for key, value in data.items()
        }
        self.metadata = type("Meta", (), {"name": "svc-seaweedfs-seaweedfs"})()


class FakeCoreV1Api:
    def __init__(self, secret: FakeSecret) -> None:
        self._secret = secret
        self.read_pods: list[tuple[str, str]] = []

    def read_namespaced_secret(self, *, namespace: str, name: str) -> FakeSecret:
        return self._secret

    def read_namespaced_pod(self, *, namespace: str, name: str) -> object:
        self.read_pods.append((namespace, name))
        return object()


class RecordingRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.namespace: str | None = None
        self.pod_name: str | None = None

    def run(self, *, core_v1_api, namespace, pod_name, commands) -> str:
        self.namespace = namespace
        self.pod_name = pod_name
        self.commands.append(commands)
        return ""


def _context() -> ProviderContext:
    return ProviderContext(
        target_type="service_instance",
        slug="seaweedfs",
        runtime_name="svc-seaweedfs",
        manifest=None,
        chart=None,
        values={},
        provider_name="seaweedfs",
    )


def _lifecycle(
    data: dict[str, str], runner: RecordingRunner
) -> KubernetesSeaweedFSLifecycle:
    return KubernetesSeaweedFSLifecycle(
        core_v1_api=FakeCoreV1Api(FakeSecret(data)),
        exec_runner=runner,
    )


def test_reconcile_seeds_admin_identity_from_the_service_secret() -> None:
    runner = RecordingRunner()

    lifecycle = _lifecycle(
        {"access-key": "ADMINKEY", "secret-key": "ADMINSECRET"}, runner
    )
    lifecycle.reconcile(_context())

    assert len(runner.commands) == 1
    command = runner.commands[0][0]
    assert command.startswith("s3.configure ")
    assert "-user nephos-admin" in command
    assert "-access_key ADMINKEY" in command
    assert "-secret_key ADMINSECRET" in command
    assert "-actions Admin,Read,Write,List,Tagging" in command
    assert command.endswith("-apply")
    # No -buckets: the admin identity is deliberately unscoped.
    assert "-buckets" not in command


def test_reconcile_targets_the_service_namespace_and_pod() -> None:
    runner = RecordingRunner()

    _lifecycle({"access-key": "K", "secret-key": "S"}, runner).reconcile(_context())

    assert runner.namespace == "svc-seaweedfs"
    assert runner.pod_name == "svc-seaweedfs-seaweedfs-0"


def test_reconcile_blocks_when_the_admin_secret_is_missing_a_key() -> None:
    runner = RecordingRunner()

    with pytest.raises(RuntimeBlockedError) as excinfo:
        _lifecycle({"access-key": "K"}, runner).reconcile(_context())

    assert excinfo.value.reason == "seaweedfs_admin_credentials_missing"
    # Nothing was applied, so a half-configured identity cannot be left behind.
    assert runner.commands == []


def test_reconcile_quotes_credentials_that_would_break_the_shell() -> None:
    """Generated keys are alphanumeric, but an operator-supplied one is free
    text and reaches a shell heredoc."""
    runner = RecordingRunner()

    _lifecycle(
        {"access-key": "key with spaces", "secret-key": "s3cr3t'; rm -rf /"}, runner
    ).reconcile(_context())

    command = runner.commands[0][0]
    assert "-access_key 'key with spaces'" in command
    assert "rm -rf /" in command
    # The injected quote must be escaped rather than closing the argument.
    assert "'; rm -rf /" not in command.replace("'\"'\"'", "<escaped>")
