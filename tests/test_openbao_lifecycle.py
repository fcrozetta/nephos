import json

from kubernetes.client.rest import ApiException

from nephos_api.kubernetes_runtime import namespace_labels
from nephos_api.providers.base import ProviderContext
from nephos_api.providers.service_lifecycle import KubernetesOpenBaoLifecycle
from nephos_api.runtime_errors import RuntimeBlockedError

OWNED_LABELS = namespace_labels("service_instance", "openbao")


def _context() -> ProviderContext:
    return ProviderContext(
        target_type="service_instance",
        slug="openbao",
        runtime_name="svc-openbao",
        manifest=None,
        chart=None,
        values={},
        provider_name="openbao",
    )


class _Meta:
    def __init__(self, labels):
        self.labels = labels


class _Obj:
    def __init__(self, labels, data=None):
        self.metadata = _Meta(labels)
        self.data = data


class _FakeCoreV1:
    def __init__(self, *, ns_labels=OWNED_LABELS, secret=None):
        self._ns_labels = ns_labels
        self._secret = secret
        self.created: list[object] = []

    def read_namespace(self, name):
        if self._ns_labels is None:
            raise ApiException(status=404)
        return _Obj(self._ns_labels)

    def read_namespaced_secret(self, name, namespace):
        if self._secret is None:
            raise ApiException(status=404)
        return self._secret

    def create_namespaced_secret(self, namespace, body):
        self.created.append(body)

    def replace_namespaced_secret(self, name, namespace, body):
        self.created.append(body)


class _FakeExec:
    def __init__(self, *, initialized_sequence, sealed=False, mounts=None):
        self._init_seq = list(initialized_sequence)
        self._sealed = sealed
        self._mounts = mounts if mounts is not None else {"secret/": {}}
        self.calls: list[list[str]] = []

    def run(self, *, core_v1_api, namespace, pod_name, argv, token=None):
        self.calls.append(list(argv))
        if argv[0] == "status":
            initialized = self._init_seq.pop(0) if self._init_seq else True
            body = json.dumps({"initialized": initialized, "sealed": self._sealed})
            return body, "", (0 if not self._sealed else 2)
        if argv[:2] == ["operator", "init"]:
            body = json.dumps(
                {"unseal_keys_b64": ["key-abc"], "root_token": "root-xyz"}
            )
            return body, "", 0
        if argv[:2] == ["operator", "unseal"]:
            self._sealed = False
            return "", "", 0
        if argv[:2] == ["secrets", "list"]:
            return json.dumps(self._mounts), "", 0
        if argv[:2] == ["secrets", "enable"]:
            self._mounts["secret/"] = {}
            return "", "", 0
        return "", "unexpected", 1

    def ran(self, prefix):
        return any(c[: len(prefix)] == prefix for c in self.calls)


def test_lifecycle_is_noop_when_initialized_unsealed_mounted() -> None:
    runner = _FakeExec(initialized_sequence=[True], sealed=False)
    core = _FakeCoreV1(
        secret=_Obj(
            {"app.kubernetes.io/managed-by": "nephos"},
            {"root-token": _b64("root-xyz"), "unseal-key": _b64("key-abc")},
        )
    )
    KubernetesOpenBaoLifecycle(core_v1_api=core, exec_runner=runner).reconcile(
        _context()
    )
    assert not runner.ran(["operator", "init"])
    assert not runner.ran(["operator", "unseal"])
    assert not runner.ran(["secrets", "enable"])
    assert core.created == []


def test_lifecycle_initializes_unseals_and_mounts_when_fresh() -> None:
    # First status: uninitialized. After init+persist, status: initialized+sealed.
    runner = _FakeExec(initialized_sequence=[False, True], sealed=True, mounts={})
    core = _FakeCoreV1(secret=None)
    KubernetesOpenBaoLifecycle(core_v1_api=core, exec_runner=runner).reconcile(
        _context()
    )
    assert runner.ran(["operator", "init"])
    assert runner.ran(["operator", "unseal"])
    assert runner.ran(["secrets", "enable"])
    assert len(core.created) == 1


def test_lifecycle_refuses_reinit_when_keys_secret_missing() -> None:
    # Initialized but the unseal-keys Secret is gone: re-init would be data loss.
    runner = _FakeExec(initialized_sequence=[True], sealed=True)
    core = _FakeCoreV1(secret=None)
    try:
        KubernetesOpenBaoLifecycle(core_v1_api=core, exec_runner=runner).reconcile(
            _context()
        )
    except RuntimeBlockedError as exc:
        assert exc.reason == "openbao_unseal_keys_missing"
    else:
        raise AssertionError("expected refusal when keys secret is missing")
    assert not runner.ran(["operator", "init"])


def _b64(value: str) -> str:
    import base64

    return base64.b64encode(value.encode()).decode()


def test_bao_shell_script_invokes_bao_with_env_and_token() -> None:
    from nephos_api.providers.service_lifecycle import _bao_shell_script

    script = _bao_shell_script(["status", "-format=json"], None)
    # Regression guard: the command must actually invoke the `bao` binary.
    assert "bao status -format=json" in script
    assert 'BAO_ADDR="http://127.0.0.1:8200"' in script
    assert "NEPHOS_EXIT" in script

    with_token = _bao_shell_script(["secrets", "list"], "tok-123")
    assert "BAO_TOKEN=tok-123 bao secrets list" in with_token
