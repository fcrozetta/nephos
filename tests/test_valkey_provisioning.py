import base64
import hashlib

import pytest
from kubernetes import client
from kubernetes.client.rest import ApiException

from nephos_api.kubernetes_runtime import KubernetesRuntimeSafetyError
from nephos_api.provisioners.base import BindingProvisioningContext
from nephos_api.provisioners.valkey import (
    KubernetesValkeyCliRunner,
    ValkeyAppScopedProvisioner,
    assert_valkey_succeeded,
)
from nephos_api.runtime_errors import RuntimeBlockedError

ADMIN_PASSWORD = "valkey-admin-secret"


class FakeCoreV1Api:
    def __init__(self) -> None:
        self.namespaces: dict[str, client.V1Namespace] = {
            "svc-valkey": client.V1Namespace(
                metadata=client.V1ObjectMeta(
                    name="svc-valkey",
                    labels={
                        "app.kubernetes.io/managed-by": "nephos",
                        "nephos.pro/service-instance": "valkey",
                    },
                )
            )
        }
        self.secrets: dict[tuple[str, str], client.V1Secret] = {
            ("svc-valkey", "svc-valkey-valkey"): _secret(
                namespace="svc-valkey",
                name="svc-valkey-valkey",
                data={"valkey-password": ADMIN_PASSWORD},
            )
        }
        self.created_secrets: list[client.V1Secret] = []
        self.deleted_secrets: list[tuple[str, str]] = []
        self.read_secret_names: list[str] = []
        self.pods: dict[tuple[str, str], client.V1Pod] = {
            ("svc-valkey", "svc-valkey-valkey-0"): client.V1Pod(
                metadata=client.V1ObjectMeta(
                    namespace="svc-valkey", name="svc-valkey-valkey-0"
                )
            )
        }

    def read_namespace(self, *, name: str) -> client.V1Namespace:
        namespace = self.namespaces.get(name)
        if namespace is None:
            raise ApiException(status=404)
        return namespace

    def read_namespaced_secret(self, *, namespace: str, name: str) -> client.V1Secret:
        self.read_secret_names.append(name)
        secret = self.secrets.get((namespace, name))
        if secret is None:
            raise ApiException(status=404)
        return secret

    def create_namespaced_secret(
        self, *, namespace: str, body: client.V1Secret
    ) -> client.V1Secret:
        assert body.metadata is not None
        body.metadata.namespace = namespace
        self.created_secrets.append(body)
        self.secrets[(namespace, body.metadata.name)] = body
        return body

    def read_namespaced_pod(self, *, namespace: str, name: str) -> client.V1Pod:
        pod = self.pods.get((namespace, name))
        if pod is None:
            raise ApiException(status=404)
        return pod

    def delete_namespaced_secret(self, *, namespace: str, name: str) -> None:
        if (namespace, name) not in self.secrets:
            raise ApiException(status=404)
        self.deleted_secrets.append((namespace, name))
        del self.secrets[(namespace, name)]

    def connect_get_namespaced_pod_exec(self) -> None:
        pass


class FakeCliRunner:
    def __init__(self, output: str = "OK\nOK\n") -> None:
        self.calls: list[dict[str, object]] = []
        self.output = output

    def run(
        self,
        *,
        core_v1_api: client.CoreV1Api,
        namespace: str,
        pod_name: str,
        commands: list[str],
    ) -> str:
        self.calls.append(
            {"namespace": namespace, "pod_name": pod_name, "commands": commands}
        )
        return self.output


class FakeExecResponse:
    def __init__(self, *, stdout: list[str], stderr: list[str] | None = None) -> None:
        self._stdout = stdout
        self._stderr = stderr or []

    def is_open(self) -> bool:
        return bool(self._stdout or self._stderr)

    def update(self, *, timeout: int) -> None:
        assert timeout == 1

    def peek_stdout(self) -> bool:
        return bool(self._stdout)

    def read_stdout(self) -> str:
        return self._stdout.pop(0)

    def peek_stderr(self) -> bool:
        return bool(self._stderr)

    def read_stderr(self) -> str:
        return self._stderr.pop(0)

    def close(self) -> None:
        pass


def test_runner_never_puts_a_credential_in_the_exec_command(monkeypatch) -> None:
    """The exec command array is recorded verbatim in the Kubernetes audit log.
    The admin password comes from REDISCLI_AUTH in the container, and the binding
    credential appears only as a SHA-256 verifier, so neither is recoverable."""
    captured = {}

    def fake_stream(connect, pod_name, namespace, **kwargs):
        captured["kwargs"] = kwargs
        return FakeExecResponse(stdout=["OK\n", "\nNEPHOS_EXIT:0\n"])

    monkeypatch.setattr("nephos_api.provisioners.valkey.stream.stream", fake_stream)

    secret = "super-secret-binding-password"
    digest = hashlib.sha256(secret.encode()).hexdigest()
    KubernetesValkeyCliRunner().run(
        core_v1_api=FakeCoreV1Api(),
        namespace="svc-valkey",
        pod_name="svc-valkey-valkey-0",
        commands=[f"ACL SETUSER u reset on #{digest} ~p:* +@all", "ACL SAVE"],
    )

    command = captured["kwargs"]["command"]
    script = command[2]
    assert command[:2] == ["sh", "-lc"]
    # No plaintext, of either credential.
    assert secret not in script
    assert ADMIN_PASSWORD not in script
    # Only the verifier, and no password-bearing flag.
    assert digest in script
    assert "--pass" not in script
    assert "-a " not in script
    # redis-cli picks the admin credential up from the container environment.
    assert "REDISCLI_AUTH" in script


def test_runner_guards_a_missing_rediscli_auth(monkeypatch) -> None:
    """Without the env var the server answers NOAUTH, which reads like a broken
    ACL rather than a broken workload. The guard names the real cause."""
    captured = {}

    def fake_stream(connect, pod_name, namespace, **kwargs):
        captured["kwargs"] = kwargs
        return FakeExecResponse(stdout=["OK\n", "\nNEPHOS_EXIT:0\n"])

    monkeypatch.setattr("nephos_api.provisioners.valkey.stream.stream", fake_stream)
    KubernetesValkeyCliRunner().run(
        core_v1_api=FakeCoreV1Api(),
        namespace="svc-valkey",
        pod_name="svc-valkey-valkey-0",
        commands=["ACL SAVE"],
    )

    script = captured["kwargs"]["command"][2]
    assert 'if [ -z "${REDISCLI_AUTH:-}" ]; then' in script
    assert "REDISCLI_AUTH is unset in the valkey container" in script


@pytest.mark.parametrize(
    "output",
    [
        "ERR Error in ACL SETUSER modifier '#nothex': The password hash must be",
        "NOPERM this user has no permissions",
        "WRONGPASS invalid username-password pair",
        "NOAUTH Authentication required.",
        "(error) unknown command",
    ],
)
def test_assert_valkey_succeeded_rejects_every_real_error_reply(output: str) -> None:
    """valkey-cli exits 0 on command errors, so the output text is the only signal.
    These are the reply shapes Valkey actually emits for reachable failures."""
    with pytest.raises(RuntimeBlockedError) as excinfo:
        assert_valkey_succeeded(output, reason="binding_provisioner_failed")
    assert excinfo.value.reason == "binding_provisioner_failed"


def test_assert_valkey_succeeded_accepts_ok() -> None:
    assert_valkey_succeeded("OK\nOK\n", reason="binding_provisioner_failed")


def test_provisioner_creates_credentials_and_returns_outputs() -> None:
    core = FakeCoreV1Api()
    runner = FakeCliRunner()
    provisioner = ValkeyAppScopedProvisioner(
        core_v1_api=core, cli_runner=runner, password_factory=lambda: "valkey-pw!"
    )

    values = provisioner.provision_binding(_context())

    assert values == {
        "host": "svc-valkey-valkey.svc-valkey.svc.cluster.local",
        "port": "6379",
        "username": "nephos_paperless_cache_9ec2cb8c8517",
        "password": "valkey-pw!",
        "database": "0",
        "keyPrefix": "nephos:paperless:cache:9ec2cb8c8517:",
        "uri": (
            "redis://nephos_paperless_cache_9ec2cb8c8517:valkey-pw%21@"
            "svc-valkey-valkey.svc-valkey.svc.cluster.local:6379/0"
        ),
    }
    created = core.created_secrets[0]
    assert created.metadata is not None
    assert created.metadata.name == "nephos-valkey-paperless-cache-9ec2cb8c8517"
    assert created.metadata.labels == {
        "app.kubernetes.io/managed-by": "nephos",
        "nephos.pro/app-instance": "paperless",
        "nephos.pro/service-instance": "valkey",
        "nephos.pro/capability": "kv",
        "nephos.pro/protocol": "redis",
        "nephos.pro/binding-alias": "cache",
    }
    assert created.string_data == {
        "username": "nephos_paperless_cache_9ec2cb8c8517",
        "password": "valkey-pw!",
        "keyPrefix": "nephos:paperless:cache:9ec2cb8c8517:",
    }


def test_provision_commands_reset_scope_and_save() -> None:
    """Four properties, each of which fails silently if dropped: `reset` (or a
    changed prefix leaves the old pattern granted), the key pattern, the channel
    pattern (acl-pubsub-default is resetchannels, so pub/sub is otherwise dead),
    and -@dangerous (FLUSHALL is not constrained by key patterns)."""
    core = FakeCoreV1Api()
    runner = FakeCliRunner()
    provisioner = ValkeyAppScopedProvisioner(
        core_v1_api=core, cli_runner=runner, password_factory=lambda: "valkey-pw"
    )

    provisioner.provision_binding(_context())

    commands = runner.calls[0]["commands"]
    digest = hashlib.sha256(b"valkey-pw").hexdigest()
    assert commands == [
        f"ACL SETUSER nephos_paperless_cache_9ec2cb8c8517 reset on #{digest} "
        "~nephos:paperless:cache:9ec2cb8c8517:* "
        "&nephos:paperless:cache:9ec2cb8c8517:* +@all -@dangerous",
        "ACL SAVE",
    ]


def test_provision_uses_a_hash_not_the_plaintext() -> None:
    core = FakeCoreV1Api()
    runner = FakeCliRunner()
    provisioner = ValkeyAppScopedProvisioner(
        core_v1_api=core, cli_runner=runner, password_factory=lambda: "plaintext-pw"
    )

    provisioner.provision_binding(_context())

    joined = " ".join(runner.calls[0]["commands"])
    assert "plaintext-pw" not in joined
    assert ">" not in joined
    # Valkey rejects anything that is not exactly 64 lowercase hex characters, and
    # exits 0 while doing it, so the shape matters.
    digest = joined.split("#")[1].split()[0]
    assert len(digest) == 64
    assert digest == digest.lower()
    assert all(c in "0123456789abcdef" for c in digest)


def test_provision_blocks_when_acl_save_fails() -> None:
    """An unsaved SETUSER looks like success and then breaks every binding at the
    next pod restart, so the save is checked as strictly as the grant."""
    core = FakeCoreV1Api()
    runner = FakeCliRunner(output="OK\nERR ACL SAVE failed: no aclfile configured\n")
    provisioner = ValkeyAppScopedProvisioner(
        core_v1_api=core, cli_runner=runner, password_factory=lambda: "valkey-pw"
    )

    with pytest.raises(RuntimeBlockedError) as excinfo:
        provisioner.provision_binding(_context())
    assert excinfo.value.reason == "binding_provisioner_failed"


def test_unentitled_binding_never_reads_the_admin_secret() -> None:
    core = FakeCoreV1Api()
    provisioner = ValkeyAppScopedProvisioner(
        core_v1_api=core, cli_runner=FakeCliRunner(), password_factory=lambda: "pw"
    )

    values = provisioner.provision_binding(_context())

    assert "svc-valkey-valkey" not in core.read_secret_names
    assert values is not None
    assert "adminPassword" not in values


def test_entitled_binding_gets_the_default_user_credential() -> None:
    core = FakeCoreV1Api()
    provisioner = ValkeyAppScopedProvisioner(
        core_v1_api=core, cli_runner=FakeCliRunner(), password_factory=lambda: "pw"
    )

    values = provisioner.provision_binding(
        BindingProvisioningContext(
            binding_id="binding_02",
            app_slug="reporting",
            service_slug="valkey",
            alias="cache",
            capability="kv",
            protocol="redis",
            entitlements=frozenset({"admin-credentials"}),
        )
    )

    assert values is not None
    assert values["adminUsername"] == "default"
    assert values["adminPassword"] == ADMIN_PASSWORD
    assert "svc-valkey-valkey" in core.read_secret_names


def test_engine_recognizes_only_admin_credentials() -> None:
    assert ValkeyAppScopedProvisioner.recognized_entitlements == frozenset(
        {"admin-credentials"}
    )


def test_provisioner_reuses_existing_owned_credential_secret() -> None:
    core = FakeCoreV1Api()
    core.secrets[("svc-valkey", "nephos-valkey-paperless-cache-9ec2cb8c8517")] = (
        _secret(
            namespace="svc-valkey",
            name="nephos-valkey-paperless-cache-9ec2cb8c8517",
            labels=_owned_labels(),
            data={
                "username": "nephos_paperless_cache_9ec2cb8c8517",
                "password": "existing-pw",
                "keyPrefix": "nephos:paperless:cache:9ec2cb8c8517:",
            },
        )
    )
    provisioner = ValkeyAppScopedProvisioner(
        core_v1_api=core, cli_runner=FakeCliRunner(), password_factory=lambda: "new-pw"
    )

    values = provisioner.provision_binding(_context())

    assert core.created_secrets == []
    assert values is not None
    assert values["password"] == "existing-pw"


@pytest.mark.parametrize(
    ("capability", "protocol"),
    [
        ("sql", "mysql"),
        ("sql", "postgres"),
        ("kv", None),
        ("kv", "memcached"),
        ("cache", "redis"),
    ],
)
def test_provisioner_returns_none_for_other_bindings(capability, protocol) -> None:
    """Only (kv, redis). Answering for anything else would hand an app
    credentials it cannot use."""
    core = FakeCoreV1Api()
    runner = FakeCliRunner()
    provisioner = ValkeyAppScopedProvisioner(
        core_v1_api=core, cli_runner=runner, password_factory=lambda: "unused"
    )

    values = provisioner.provision_binding(
        BindingProvisioningContext(
            binding_id="b",
            app_slug="paperless",
            service_slug="valkey",
            alias="cache",
            capability=capability,
            protocol=protocol,
        )
    )

    assert values is None
    assert core.created_secrets == []
    assert runner.calls == []


def test_provisioner_refuses_unowned_service_namespace() -> None:
    core = FakeCoreV1Api()
    core.namespaces["svc-valkey"] = client.V1Namespace(
        metadata=client.V1ObjectMeta(name="svc-valkey", labels={})
    )
    provisioner = ValkeyAppScopedProvisioner(
        core_v1_api=core, cli_runner=FakeCliRunner(), password_factory=lambda: "unused"
    )

    with pytest.raises(
        KubernetesRuntimeSafetyError,
        match="refusing to use unowned namespace svc-valkey",
    ):
        provisioner.provision_binding(_context())


def test_provisioner_refuses_terminating_service_namespace() -> None:
    core = FakeCoreV1Api()
    core.namespaces["svc-valkey"] = client.V1Namespace(
        metadata=client.V1ObjectMeta(
            name="svc-valkey",
            labels={
                "app.kubernetes.io/managed-by": "nephos",
                "nephos.pro/service-instance": "valkey",
            },
            deletion_timestamp="2026-08-25T00:00:00Z",
        )
    )
    provisioner = ValkeyAppScopedProvisioner(
        core_v1_api=core, cli_runner=FakeCliRunner(), password_factory=lambda: "unused"
    )

    with pytest.raises(
        KubernetesRuntimeSafetyError,
        match="refusing to use terminating namespace svc-valkey",
    ):
        provisioner.provision_binding(_context())


def test_provisioner_refuses_unowned_existing_credential_secret() -> None:
    core = FakeCoreV1Api()
    core.secrets[("svc-valkey", "nephos-valkey-paperless-cache-9ec2cb8c8517")] = (
        _secret(
            namespace="svc-valkey",
            name="nephos-valkey-paperless-cache-9ec2cb8c8517",
            labels={},
            data={"username": "u", "password": "p", "keyPrefix": "x:"},
        )
    )
    provisioner = ValkeyAppScopedProvisioner(
        core_v1_api=core, cli_runner=FakeCliRunner(), password_factory=lambda: "unused"
    )

    with pytest.raises(KubernetesRuntimeSafetyError):
        provisioner.provision_binding(_context())


def test_deprovision_deletes_the_acl_user_and_saves() -> None:
    core = FakeCoreV1Api()
    core.secrets[("svc-valkey", "nephos-valkey-paperless-cache-9ec2cb8c8517")] = (
        _secret(
            namespace="svc-valkey",
            name="nephos-valkey-paperless-cache-9ec2cb8c8517",
            labels=_owned_labels(),
            data={
                "username": "nephos_paperless_cache_9ec2cb8c8517",
                "password": "existing-pw",
                "keyPrefix": "nephos:paperless:cache:9ec2cb8c8517:",
            },
        )
    )
    runner = FakeCliRunner()
    provisioner = ValkeyAppScopedProvisioner(
        core_v1_api=core, cli_runner=runner, password_factory=lambda: "unused"
    )

    provisioner.deprovision_binding(_context())

    assert runner.calls[0]["commands"] == [
        "ACL DELUSER nephos_paperless_cache_9ec2cb8c8517",
        "ACL SAVE",
    ]
    assert core.deleted_secrets == [
        ("svc-valkey", "nephos-valkey-paperless-cache-9ec2cb8c8517")
    ]


def test_deprovision_blocks_when_save_fails_so_a_restart_cannot_resurrect() -> None:
    core = FakeCoreV1Api()
    core.secrets[("svc-valkey", "nephos-valkey-paperless-cache-9ec2cb8c8517")] = (
        _secret(
            namespace="svc-valkey",
            name="nephos-valkey-paperless-cache-9ec2cb8c8517",
            labels=_owned_labels(),
            data={
                "username": "nephos_paperless_cache_9ec2cb8c8517",
                "password": "pw",
                "keyPrefix": "nephos:paperless:cache:9ec2cb8c8517:",
            },
        )
    )
    runner = FakeCliRunner(output="1\nERR ACL SAVE failed\n")
    provisioner = ValkeyAppScopedProvisioner(
        core_v1_api=core, cli_runner=runner, password_factory=lambda: "unused"
    )

    with pytest.raises(RuntimeBlockedError):
        provisioner.deprovision_binding(_context())
    # The Secret must survive a failed teardown, or the binding becomes
    # unrecoverable: nothing would remember which ACL user to remove.
    assert core.deleted_secrets == []


def test_deprovision_is_idempotent_when_secret_is_missing() -> None:
    core = FakeCoreV1Api()
    runner = FakeCliRunner()
    provisioner = ValkeyAppScopedProvisioner(
        core_v1_api=core, cli_runner=runner, password_factory=lambda: "unused"
    )

    provisioner.deprovision_binding(_context())

    assert runner.calls == []
    assert core.deleted_secrets == []


def test_username_and_prefix_stay_within_budget_for_long_slugs() -> None:
    core = FakeCoreV1Api()
    provisioner = ValkeyAppScopedProvisioner(
        core_v1_api=core, cli_runner=FakeCliRunner(), password_factory=lambda: "pw"
    )

    values = provisioner.provision_binding(
        BindingProvisioningContext(
            binding_id="binding_long",
            app_slug="a" * 40,
            service_slug="valkey",
            alias="b" * 40,
            capability="kv",
            protocol="redis",
        )
    )

    assert values is not None
    assert len(values["username"]) <= 63
    created = core.created_secrets[0]
    assert created.metadata is not None
    assert len(created.metadata.name) <= 63


def test_username_shape_is_enforced_before_composing_commands() -> None:
    """Commands are composed as text, so a username with whitespace could append
    arguments to ACL SETUSER."""
    from nephos_api.provisioners.valkey import _deprovision_commands

    with pytest.raises(ValueError, match="invalid Valkey username"):
        _deprovision_commands("evil name +@all")


def test_scopes_are_distinct_when_an_app_and_a_service_share_a_slug() -> None:
    """`app_instances.slug` and `service_instances.slug` are UNIQUE on separate
    tables, and a service dependency passes the consumer slug as `app_slug`
    (deployer.py). Without an unconditional discriminator an App `foo` and a
    Service `foo` binding the same alias get the same ACL user, password, Secret
    and key prefix -- they read each other's data, and deprovisioning either
    revokes both. Same fix seaweedfs already carries."""
    from nephos_api.provisioners.valkey import (
        _credential_secret_name,
        _key_prefix,
        _valkey_identifier,
    )

    def ctx(binding_id: str) -> BindingProvisioningContext:
        return BindingProvisioningContext(
            binding_id=binding_id,
            app_slug="foo",
            service_slug="valkey",
            alias="cache",
            capability="kv",
            protocol="redis",
        )

    app, service = ctx("binding_01"), ctx("service-foo-cache")

    assert _valkey_identifier(app) != _valkey_identifier(service)
    assert _credential_secret_name(app) != _credential_secret_name(service)
    # The key prefix matters most: it is this engine's entire isolation story, so
    # a shared prefix is not a naming clash, it is one App reading another's data.
    assert _key_prefix(app) != _key_prefix(service)


def test_scopes_are_stable_across_calls() -> None:
    """Derived from binding_id, not random: deprovision recomputes these names
    from the context and would otherwise miss the user it created."""
    from nephos_api.provisioners.valkey import _key_prefix, _valkey_identifier

    first, second = _context(), _context()
    assert _valkey_identifier(first) == _valkey_identifier(second)
    assert _key_prefix(first) == _key_prefix(second)


@pytest.mark.parametrize(
    ("label", "stdout", "code"),
    [
        (
            "connection refused",
            "Could not connect to Redis at 1.2.3.4:6379: Connection refused",
            1,
        ),
        (
            "the REDISCLI_AUTH guard's own message",
            "REDISCLI_AUTH is unset in the valkey container",
            1,
        ),
        ("missing binary", "sh: valkey-cli: not found", 127),
    ],
)
def test_runner_raises_on_exec_failures_that_carry_no_valkey_error_reply(
    monkeypatch, label: str, stdout: str, code: int
) -> None:
    """These exit nonzero while printing text containing no Valkey error reply, so
    the marker scan alone reports success and publishes binding outputs for an ACL
    user that was never created. The guard's own message was itself invisible."""

    def fake_stream(connect, pod_name, namespace, **kwargs):
        return FakeExecResponse(stdout=[f"{stdout}\n", f"\nNEPHOS_EXIT:{code}\n"])

    monkeypatch.setattr("nephos_api.provisioners.valkey.stream.stream", fake_stream)

    with pytest.raises(RuntimeError, match=stdout.split(":")[0]):
        KubernetesValkeyCliRunner().run(
            core_v1_api=FakeCoreV1Api(),
            namespace="svc-valkey",
            pod_name="svc-valkey-valkey-0",
            commands=["ACL SAVE"],
        )


def test_runner_raises_when_the_exit_marker_is_missing(monkeypatch) -> None:
    def fake_stream(connect, pod_name, namespace, **kwargs):
        return FakeExecResponse(stdout=["output with no marker\n"])

    monkeypatch.setattr("nephos_api.provisioners.valkey.stream.stream", fake_stream)

    with pytest.raises(RuntimeError, match="missing exec exit marker"):
        KubernetesValkeyCliRunner().run(
            core_v1_api=FakeCoreV1Api(),
            namespace="svc-valkey",
            pod_name="svc-valkey-valkey-0",
            commands=["ACL SAVE"],
        )


def test_acl_saved_check_catches_a_state_with_no_marker_and_exit_zero() -> None:
    """LOADING exits 0 and matches no error marker. Every batch ends with
    ACL SAVE, so its OK is the positive signal that the grant both applied and
    persisted -- the failure that otherwise stays invisible until a restart."""
    from nephos_api.provisioners.valkey import assert_acl_saved

    with pytest.raises(RuntimeBlockedError, match="did not confirm ACL SAVE"):
        assert_acl_saved(
            "LOADING Valkey is loading the dataset in memory",
            reason="binding_provisioner_failed",
        )
    # Both real batches end with the ACL SAVE reply.
    assert_acl_saved("OK\nOK\n", reason="r")
    assert_acl_saved("1\nOK\n", reason="r")


def _owned_labels() -> dict[str, str]:
    return {
        "app.kubernetes.io/managed-by": "nephos",
        "nephos.pro/app-instance": "paperless",
        "nephos.pro/service-instance": "valkey",
        "nephos.pro/capability": "kv",
        "nephos.pro/protocol": "redis",
        "nephos.pro/binding-alias": "cache",
    }


def _context() -> BindingProvisioningContext:
    return BindingProvisioningContext(
        binding_id="binding_01",
        app_slug="paperless",
        service_slug="valkey",
        alias="cache",
        capability="kv",
        protocol="redis",
    )


def _secret(
    *,
    namespace: str,
    name: str,
    data: dict[str, str],
    labels: dict[str, str] | None = None,
) -> client.V1Secret:
    return client.V1Secret(
        metadata=client.V1ObjectMeta(namespace=namespace, name=name, labels=labels),
        data={
            key: base64.b64encode(value.encode()).decode()
            for key, value in data.items()
        },
    )
