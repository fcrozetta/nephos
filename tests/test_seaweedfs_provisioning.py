import base64

import pytest
from kubernetes.client.rest import ApiException

from nephos_api.kubernetes_runtime import (
    KubernetesRuntimeSafetyError,
    binding_secret_labels,
    namespace_labels,
)
from nephos_api.provisioners.base import BindingProvisioningContext
from nephos_api.provisioners.seaweedfs_client import (
    KubernetesSeaweedFSProvisioningClient,
)
from nephos_api.runtime_errors import RuntimeBlockedError


class FakeSecret:
    def __init__(self, data: dict[str, str], labels: dict[str, str]) -> None:
        self.data = {
            key: base64.b64encode(value.encode()).decode()
            for key, value in data.items()
        }
        self.metadata = type(
            "Meta",
            (),
            {"name": "fake", "namespace": "svc-seaweedfs", "labels": labels},
        )()


class FakeCoreV1Api:
    def __init__(self) -> None:
        self.secrets: dict[str, FakeSecret] = {}
        self.created: list[str] = []
        self.deleted: list[str] = []
        self.ns_labels: dict[str, str] = {}
        self.ns_deleting = False

    def read_namespace(self, *, name: str):
        return type(
            "NS",
            (),
            {
                "metadata": type(
                    "Meta",
                    (),
                    {
                        "labels": self.ns_labels,
                        "deletion_timestamp": (
                            "now" if self.ns_deleting else None
                        ),
                    },
                )()
            },
        )()

    def read_namespaced_secret(self, *, namespace: str, name: str):
        if name not in self.secrets:
            raise ApiException(status=404)
        return self.secrets[name]

    def create_namespaced_secret(self, *, namespace: str, body):
        self.created.append(body.metadata.name)
        self.secrets[body.metadata.name] = FakeSecret(
            dict(body.string_data), dict(body.metadata.labels or {})
        )

    def delete_namespaced_secret(self, *, namespace: str, name: str):
        self.deleted.append(name)
        self.secrets.pop(name, None)

    def read_namespaced_pod(self, *, namespace: str, name: str):
        return object()


class RecordingRunner:
    def __init__(self, output: str = "") -> None:
        self.batches: list[list[str]] = []
        self._output = output

    def run(self, *, core_v1_api, namespace, pod_name, commands) -> str:
        self.batches.append(commands)
        return self._output


def _context(app_slug: str = "notes", alias: str = "blobs"):
    return BindingProvisioningContext(
        binding_id=f"bind-{app_slug}-{alias}",
        app_slug=app_slug,
        service_slug="seaweedfs",
        alias=alias,
        capability="object-storage",
        protocol="s3",
    )


def _client(api: FakeCoreV1Api, runner: RecordingRunner):
    api.ns_labels = dict(namespace_labels("service_instance", "seaweedfs"))
    keys = iter(["APPKEY", "APPSECRET"])
    return KubernetesSeaweedFSProvisioningClient(
        core_v1_api=api,
        exec_runner=runner,
        key_factory=lambda length: next(keys),
    )


def test_ensure_returns_the_adr_output_contract() -> None:
    api, runner = FakeCoreV1Api(), RecordingRunner()

    values = _client(api, runner).ensure_s3_binding(_context())

    assert set(values) == {
        "endpointUrl",
        "bucket",
        "accessKeyId",
        "secretAccessKey",
        "region",
    }
    assert values["region"] == "us-east-1"
    assert values["endpointUrl"] == (
        "http://svc-seaweedfs-seaweedfs.svc-seaweedfs.svc.cluster.local:8333"
    )
    assert values["bucket"] == "nephos-notes-blobs"
    assert values["accessKeyId"] == "APPKEY"
    assert values["secretAccessKey"] == "APPSECRET"


def test_ensure_creates_the_bucket_and_scopes_the_identity_to_it() -> None:
    api, runner = FakeCoreV1Api(), RecordingRunner()

    _client(api, runner).ensure_s3_binding(_context())

    commands = runner.batches[0]
    assert commands[0] == "s3.bucket.create -name nephos-notes-blobs"
    configure = commands[1]
    assert "-user nephos-notes-blobs" in configure
    assert "-buckets nephos-notes-blobs" in configure
    assert "-actions Read,Write,List,Tagging" in configure
    assert "Admin" not in configure


def test_ensure_is_idempotent_and_never_rotates_an_existing_credential() -> None:
    api, runner = FakeCoreV1Api(), RecordingRunner()
    client = _client(api, runner)

    first = client.ensure_s3_binding(_context())
    second = client.ensure_s3_binding(_context())

    assert first == second
    assert api.created == ["nephos-s3-notes-blobs"]


def test_ensure_labels_the_credential_secret_as_owned() -> None:
    api, runner = FakeCoreV1Api(), RecordingRunner()

    _client(api, runner).ensure_s3_binding(_context())

    secret = api.secrets["nephos-s3-notes-blobs"]
    assert secret.metadata.labels == binding_secret_labels(
        app_slug="notes",
        service_slug="seaweedfs",
        alias="blobs",
        capability="object-storage",
        protocol="s3",
    )


def test_delete_revokes_the_identity_and_removes_the_bucket() -> None:
    api, runner = FakeCoreV1Api(), RecordingRunner()
    client = _client(api, runner)
    client.ensure_s3_binding(_context())

    client.delete_s3_binding(_context())

    commands = runner.batches[-1]
    assert commands[0] == "s3.configure -user nephos-notes-blobs -delete -apply"
    assert commands[1] == "s3.bucket.delete -name nephos-notes-blobs"
    assert api.deleted == ["nephos-s3-notes-blobs"]


def test_delete_is_a_no_op_when_nothing_was_provisioned() -> None:
    api, runner = FakeCoreV1Api(), RecordingRunner()

    _client(api, runner).delete_s3_binding(_context())

    assert runner.batches == []
    assert api.deleted == []


def test_refuses_an_unowned_service_namespace() -> None:
    api, runner = FakeCoreV1Api(), RecordingRunner()
    client = _client(api, runner)
    api.ns_labels = {"app.kubernetes.io/managed-by": "someone-else"}

    with pytest.raises(KubernetesRuntimeSafetyError):
        client.ensure_s3_binding(_context())

    assert runner.batches == []


def test_refuses_a_terminating_service_namespace() -> None:
    api, runner = FakeCoreV1Api(), RecordingRunner()
    client = _client(api, runner)
    api.ns_deleting = True

    with pytest.raises(KubernetesRuntimeSafetyError):
        client.ensure_s3_binding(_context())


def test_refuses_a_credential_secret_it_does_not_own() -> None:
    api, runner = FakeCoreV1Api(), RecordingRunner()
    client = _client(api, runner)
    api.secrets["nephos-s3-notes-blobs"] = FakeSecret(
        {"accessKeyId": "X", "secretAccessKey": "Y"}, {"owner": "someone-else"}
    )

    with pytest.raises(KubernetesRuntimeSafetyError):
        client.ensure_s3_binding(_context())


def test_shell_failure_blocks_loudly() -> None:
    api = FakeCoreV1Api()
    runner = RecordingRunner(output="error: bucket owned by a different identity")

    with pytest.raises(RuntimeBlockedError) as excinfo:
        _client(api, runner).ensure_s3_binding(_context())

    assert excinfo.value.reason == "seaweedfs_provisioning_failed"


def test_benign_shell_output_does_not_trip_the_failure_check() -> None:
    """Verified no-ops (re-creating a bucket, deleting a missing identity) print
    ordinary output; a broad marker list would turn them into false failures."""
    api = FakeCoreV1Api()
    runner = RecordingRunner(output="create bucket under /buckets\ncreated bucket x\n")

    values = _client(api, runner).ensure_s3_binding(_context())

    assert values["bucket"] == "nephos-notes-blobs"


def test_long_names_are_truncated_to_valid_kubernetes_and_bucket_names() -> None:
    api, runner = FakeCoreV1Api(), RecordingRunner()

    values = _client(api, runner).ensure_s3_binding(
        _context(app_slug="a" * 40, alias="b" * 40)
    )

    assert len(values["bucket"]) <= 63
    assert len(api.created[0]) <= 63
    assert not values["bucket"].endswith("-")
