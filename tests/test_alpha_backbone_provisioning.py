import pytest

import nephos_api.provisioners.zitadel as zitadel_module
from nephos_api.provisioning import (
    ArcadeDBAppScopedProvisioner,
    BindingProvisioningContext,
    CompositeBindingProvisioner,
    KubernetesPulumiZitadelProvisioningClient,
    KubernetesZitadelProvisionerConfig,
    PulumiZitadelProvisionerConfig,
    PulumiZitadelProvisioningClient,
    SeaweedFSS3Provisioner,
    SecretResolvingBindingProvisioner,
    ZitadelAppScopedProvisioner,
)
from nephos_api.runtime_errors import RuntimeBlockedError
from nephos_api.secret_refs import StaticSecretResolver


class FakeZitadelClient:
    def __init__(self) -> None:
        self.oidc_calls: list[BindingProvisioningContext] = []
        self.service_account_calls: list[BindingProvisioningContext] = []

    def ensure_oidc_client(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str]:
        self.oidc_calls.append(context)
        return {
            "issuerUrl": "https://zitadel.example",
            "clientId": f"{context.app_slug}-{context.alias}",
            "clientSecret": "oidc-secret",
            "redirectUris": '["https://paperless.example/callback"]',
        }

    def ensure_service_account(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str]:
        self.service_account_calls.append(context)
        return {
            "issuerUrl": "https://zitadel.example",
            "serviceAccountId": f"svc-{context.app_slug}",
            "keyJson": '{"privateKey":"secret"}',
            "audience": "paperless",
        }

    def delete_oidc_client(self, context: BindingProvisioningContext) -> None:
        pass

    def delete_service_account(self, context: BindingProvisioningContext) -> None:
        pass


class FakePulumiZitadelRunner:
    def __init__(self) -> None:
        self.oidc_specs = []
        self.service_account_specs = []
        self.destroyed_oidc_specs = []
        self.destroyed_service_account_specs = []

    def up_oidc(self, spec):
        self.oidc_specs.append(spec)
        return {"clientId": "client-id", "clientSecret": "client-secret"}

    def up_service_account(self, spec):
        self.service_account_specs.append(spec)
        return {"serviceAccountId": "machine-id", "keyJson": '{"key":"json"}'}

    def destroy_oidc(self, spec) -> None:
        self.destroyed_oidc_specs.append(spec)

    def destroy_service_account(self, spec) -> None:
        self.destroyed_service_account_specs.append(spec)


class FakeForward:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def __enter__(self):
        return zitadel_module._ForwardEndpoint(
            host="127.0.0.1",
            port=23456,
            domain=self.kwargs.get("domain"),
        )

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None


class FakeSeaweedFSClient:
    def __init__(self) -> None:
        self.calls: list[BindingProvisioningContext] = []

    def ensure_s3_binding(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str]:
        self.calls.append(context)
        return {
            "endpointUrl": "http://seaweedfs:8333",
            "bucket": f"{context.app_slug}-{context.alias}",
            "accessKeyId": "access-key",
            "secretAccessKey": "secret-key",
            "region": "local",
        }

    def delete_s3_binding(self, context: BindingProvisioningContext) -> None:
        pass


class FakeArcadeDBClient:
    def __init__(self) -> None:
        self.calls: list[BindingProvisioningContext] = []

    def ensure_database_user(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str]:
        self.calls.append(context)
        return {
            "host": "arcadedb.svc",
            "port": "2480" if context.protocol in {"arcadedb", "n4j"} else "2424",
            "database": f"{context.app_slug}_{context.alias}",
            "username": f"{context.app_slug}_{context.alias}",
            "password": "arcade-secret",
            "protocol": str(context.protocol),
            "uri": f"{context.protocol}://arcadedb.svc",
        }

    def delete_database_user(self, context: BindingProvisioningContext) -> None:
        pass


def test_composite_binding_provisioner_dispatches_by_capability_and_protocol() -> None:
    zitadel = ZitadelAppScopedProvisioner(client=FakeZitadelClient())
    seaweedfs_client = FakeSeaweedFSClient()
    seaweedfs = SeaweedFSS3Provisioner(client=seaweedfs_client)
    composite = CompositeBindingProvisioner([zitadel, seaweedfs])
    context = _context(
        service_slug="seaweedfs",
        alias="files",
        capability="object-storage",
        protocol="s3",
    )

    values = composite.provision_binding(context)

    assert values == {
        "endpointUrl": "http://seaweedfs:8333",
        "bucket": "paperless-files",
        "accessKeyId": "access-key",
        "secretAccessKey": "secret-key",
        "region": "local",
    }
    assert seaweedfs_client.calls == [context]


def test_zitadel_fake_client_outputs_oidc_and_service_account_material() -> None:
    client = FakeZitadelClient()
    provisioner = ZitadelAppScopedProvisioner(client=client)

    oidc = provisioner.provision_binding(
        _context(
            service_slug="zitadel",
            alias="auth",
            capability="oidc",
            protocol="oidc",
        )
    )
    service_account = provisioner.provision_binding(
        _context(
            service_slug="zitadel",
            alias="machine",
            capability="service-account",
            protocol="jwt",
        )
    )

    assert oidc == {
        "issuerUrl": "https://zitadel.example",
        "clientId": "paperless-auth",
        "clientSecret": "oidc-secret",
        "redirectUris": '["https://paperless.example/callback"]',
    }
    assert service_account == {
        "issuerUrl": "https://zitadel.example",
        "serviceAccountId": "svc-paperless",
        "keyJson": '{"privateKey":"secret"}',
        "audience": "paperless",
    }


def test_pulumi_zitadel_client_derives_oidc_outputs_from_app_route(
    tmp_path,
) -> None:
    runner = FakePulumiZitadelRunner()
    client = PulumiZitadelProvisioningClient(
        config=PulumiZitadelProvisionerConfig(
            work_dir=tmp_path / "workspaces",
            state_dir=tmp_path / "state",
            issuer_url="https://zitadel.example",
            domain="127.0.0.1",
            port=18080,
            insecure=True,
            jwt_profile_json='{"key":"bootstrap"}',
        ),
        runner=runner,
    )
    context = _context(
        service_slug="zitadel",
        alias="auth",
        capability="oidc",
        protocol="oidc",
        app_routes=(
            {"name": "web", "visibility": "local", "target": {"port": "http"}},
        ),
        platform_domains=(
            {"name": "local", "domain": "nephos.local", "default": True},
        ),
    )

    values = client.ensure_oidc_client(context)

    assert values == {
        "issuerUrl": "https://zitadel.example",
        "clientId": "client-id",
        "clientSecret": "client-secret",
        "redirectUris": '["http://paperless.nephos.local/oauth/callback"]',
        "postLogoutRedirectUris": '["http://paperless.nephos.local/"]',
        "authorizationUrl": "https://zitadel.example/oauth/v2/authorize",
        "tokenUrl": "https://zitadel.example/oauth/v2/token",
        "jwksUrl": "https://zitadel.example/oauth/v2/keys",
    }
    assert len(runner.oidc_specs) == 1
    spec = runner.oidc_specs[0]
    assert spec.stack_name == "zitadel-oidc-binding_auth"
    assert spec.redirect_uris == ("http://paperless.nephos.local/oauth/callback",)
    assert spec.post_logout_redirect_uris == ("http://paperless.nephos.local/",)


def test_pulumi_zitadel_client_uses_https_redirects_for_nonlocal_domains(
    tmp_path,
) -> None:
    runner = FakePulumiZitadelRunner()
    client = PulumiZitadelProvisioningClient(
        config=PulumiZitadelProvisionerConfig(
            work_dir=tmp_path / "workspaces",
            state_dir=tmp_path / "state",
            issuer_url="https://zitadel.example",
            domain="127.0.0.1",
            port=18080,
            insecure=True,
            jwt_profile_json='{"key":"bootstrap"}',
        ),
        runner=runner,
    )

    client.ensure_oidc_client(
        _context(
            service_slug="zitadel",
            alias="auth",
            capability="oidc",
            protocol="oidc",
            app_routes=(
                {"name": "web", "visibility": "public", "target": {"port": "http"}},
            ),
            platform_domains=(
                {"name": "prod", "domain": "apps.example.test", "default": True},
            ),
        )
    )

    assert runner.oidc_specs[0].redirect_uris == (
        "https://paperless.apps.example.test/oauth/callback",
    )
    assert runner.oidc_specs[0].post_logout_redirect_uris == (
        "https://paperless.apps.example.test/",
    )


def test_pulumi_zitadel_client_blocks_oidc_without_route_metadata(tmp_path) -> None:
    client = PulumiZitadelProvisioningClient(
        config=PulumiZitadelProvisionerConfig(
            work_dir=tmp_path / "workspaces",
            state_dir=tmp_path / "state",
            issuer_url="https://zitadel.example",
            domain="127.0.0.1",
            port=18080,
            insecure=True,
            jwt_profile_json='{"key":"bootstrap"}',
        ),
        runner=FakePulumiZitadelRunner(),
    )

    with pytest.raises(RuntimeBlockedError) as exc_info:
        client.ensure_oidc_client(
            _context(
                service_slug="zitadel",
                alias="auth",
                capability="oidc",
                protocol="oidc",
            )
        )

    assert exc_info.value.reason == "binding_provisioner_unavailable"
    assert "requires at least one App route" in str(exc_info.value)


def test_pulumi_zitadel_client_outputs_service_account_material(tmp_path) -> None:
    runner = FakePulumiZitadelRunner()
    client = PulumiZitadelProvisioningClient(
        config=PulumiZitadelProvisionerConfig(
            work_dir=tmp_path / "workspaces",
            state_dir=tmp_path / "state",
            issuer_url="https://zitadel.example",
            domain="127.0.0.1",
            port=18080,
            insecure=True,
            jwt_profile_json='{"key":"bootstrap"}',
        ),
        runner=runner,
    )

    values = client.ensure_service_account(
        _context(
            service_slug="zitadel",
            alias="machine",
            capability="service-account",
            protocol="jwt",
        )
    )

    assert values == {
        "issuerUrl": "https://zitadel.example",
        "serviceAccountId": "machine-id",
        "keyJson": '{"key":"json"}',
        "audience": "https://zitadel.example",
    }
    assert len(runner.service_account_specs) == 1
    assert runner.service_account_specs[0].stack_name == "zitadel-jwt-binding_machine"


def test_kubernetes_zitadel_client_uses_issuer_endpoint_for_nonlocal_host(
    tmp_path,
    monkeypatch,
) -> None:
    runner = FakePulumiZitadelRunner()
    forwards = []

    def fake_forward(**kwargs):
        forward = FakeForward(**kwargs)
        forwards.append(forward)
        return forward

    monkeypatch.setattr(zitadel_module, "_KubectlPortForward", fake_forward)
    monkeypatch.setattr(
        zitadel_module,
        "_bootstrap_machine_key_json",
        lambda core_v1_api, *, context: '{"key":"bootstrap"}',
    )
    client = KubernetesPulumiZitadelProvisioningClient(
        core_v1_api=object(),
        config=KubernetesZitadelProvisionerConfig(
            work_dir=tmp_path / "workspaces",
            state_dir=tmp_path / "state",
            kube_context="docker-desktop",
        ),
        runner=runner,
    )
    context = _context(
        service_slug="zitadel",
        alias="auth",
        capability="oidc",
        protocol="oidc",
        service_config={
            "external-host": "login.example.test",
            "external-port": 8443,
            "external-secure": True,
        },
        app_routes=(
            {"name": "web", "visibility": "local", "target": {"port": "http"}},
        ),
        platform_domains=(
            {"name": "local", "domain": "nephos.local", "default": True},
        ),
    )

    values = client.ensure_oidc_client(context)

    assert values["issuerUrl"] == "https://login.example.test:8443"
    assert values["clientId"] == "client-id"
    assert forwards == []
    assert runner.oidc_specs[0].domain == "login.example.test"
    assert runner.oidc_specs[0].port == 8443
    assert runner.oidc_specs[0].insecure is False
    assert runner.oidc_specs[0].jwt_profile_json == '{"key":"bootstrap"}'


def test_kubernetes_zitadel_client_uses_internal_forward_for_localhost_host(
    tmp_path,
    monkeypatch,
) -> None:
    runner = FakePulumiZitadelRunner()
    forwards = []

    def fake_forward(**kwargs):
        forward = FakeForward(**kwargs)
        forwards.append(forward)
        return forward

    monkeypatch.setattr(zitadel_module, "_KubectlPortForward", fake_forward)
    monkeypatch.setattr(
        zitadel_module,
        "_bootstrap_machine_key_json",
        lambda core_v1_api, *, context: '{"key":"bootstrap"}',
    )
    client = KubernetesPulumiZitadelProvisioningClient(
        core_v1_api=object(),
        config=KubernetesZitadelProvisionerConfig(
            work_dir=tmp_path / "workspaces",
            state_dir=tmp_path / "state",
            kube_context="docker-desktop",
        ),
        runner=runner,
    )

    client.ensure_oidc_client(
        _context(
            service_slug="zitadel-smoke",
            alias="auth",
            capability="oidc",
            protocol="oidc",
            service_config={
                "external-host": "zitadel-smoke.nephos.localhost",
                "external-port": 8080,
                "external-secure": False,
            },
            app_routes=(
                {"name": "web", "visibility": "local", "target": {"port": "http"}},
            ),
            platform_domains=(
                {"name": "local", "domain": "nephos.localhost", "default": True},
            ),
        )
    )

    assert forwards[0].kwargs == {
        "namespace": "svc-zitadel-smoke",
        "service_name": "svc-zitadel-smoke-zitadel",
        "remote_port": 8080,
        "host": "127.0.0.1",
        "domain": "zitadel-smoke.nephos.localhost",
        "kubeconfig": None,
        "kube_context": "docker-desktop",
    }
    assert runner.oidc_specs[0].domain == "zitadel-smoke.nephos.localhost"
    assert runner.oidc_specs[0].port == 23456
    assert runner.oidc_specs[0].insecure is True


def test_bootstrap_machine_key_uses_bootstrap_reader_container(
    monkeypatch,
) -> None:
    import importlib

    kubernetes_stream = importlib.import_module("kubernetes.stream")

    captured = {}

    class FakeMetadata:
        labels = {
            "app.kubernetes.io/managed-by": "nephos",
            "nephos.pro/service-instance": "zitadel",
        }

    class FakeNamespace:
        metadata = FakeMetadata()

    class FakeCoreV1Api:
        def read_namespace(self, name: str):
            assert name == "svc-zitadel"
            return FakeNamespace()

        def connect_get_namespaced_pod_exec(self):
            raise AssertionError("stream.stream should wrap this method")

    def fake_stream(method, pod_name, namespace, **kwargs):
        captured.update(
            {
                "method": method,
                "pod_name": pod_name,
                "namespace": namespace,
                **kwargs,
            }
        )
        return '{"key":"bootstrap"}'

    monkeypatch.setattr(kubernetes_stream, "stream", fake_stream)

    key_json = zitadel_module._bootstrap_machine_key_json(
        FakeCoreV1Api(),
        context=_context(
            service_slug="zitadel",
            alias="auth",
            capability="oidc",
            protocol="oidc",
        ),
    )

    assert key_json == '{"key": "bootstrap"}'
    assert captured["pod_name"] == "svc-zitadel-zitadel-0"
    assert captured["namespace"] == "svc-zitadel"
    assert captured["container"] == "bootstrap-reader"
    assert captured["command"] == [
        "sh",
        "-lc",
        "cat /var/lib/zitadel-bootstrap/nephos-provisioner-key.json",
    ]


def test_kubectl_port_forward_is_terminated_when_readiness_fails(monkeypatch) -> None:
    class FakeProcess:
        stdout = None

        def __init__(self) -> None:
            self.terminated = False
            self.killed = False
            self.waits = []

        def terminate(self) -> None:
            self.terminated = True

        def wait(self, timeout=None) -> int:
            self.waits.append(timeout)
            return 0

        def kill(self) -> None:
            self.killed = True

    process = FakeProcess()

    monkeypatch.setattr(
        zitadel_module.shutil,
        "which",
        lambda command: "/usr/bin/kubectl",
    )
    monkeypatch.setattr(zitadel_module, "_free_local_port", lambda host: 19000)
    monkeypatch.setattr(
        zitadel_module.subprocess,
        "Popen",
        lambda *args, **kwargs: process,
    )

    def fail_ready(self) -> None:
        raise RuntimeBlockedError(
            reason="binding_provisioner_unavailable",
            message="Timed out waiting for Zitadel internal port-forward.",
        )

    monkeypatch.setattr(
        zitadel_module._KubectlPortForward,
        "_wait_ready",
        fail_ready,
    )
    forward = zitadel_module._KubectlPortForward(
        namespace="svc-zitadel",
        service_name="svc-zitadel-zitadel",
        remote_port=8080,
        host="127.0.0.1",
        domain="zitadel.nephos.localhost",
        kubeconfig=None,
        kube_context=None,
    )

    with pytest.raises(RuntimeBlockedError, match="port-forward"):
        forward.__enter__()

    assert process.terminated is True
    assert process.killed is False
    assert process.waits == [5]
    assert forward._process is None


def test_kubernetes_zitadel_client_rejects_invalid_provisioning_transport(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        zitadel_module,
        "_bootstrap_machine_key_json",
        lambda core_v1_api, *, context: '{"key":"bootstrap"}',
    )
    client = KubernetesPulumiZitadelProvisioningClient(
        core_v1_api=object(),
        config=KubernetesZitadelProvisionerConfig(
            work_dir=tmp_path / "workspaces",
            state_dir=tmp_path / "state",
        ),
        runner=FakePulumiZitadelRunner(),
    )

    with pytest.raises(RuntimeBlockedError, match="provisioning-transport"):
        client.ensure_oidc_client(
            _context(
                service_slug="zitadel",
                alias="auth",
                capability="oidc",
                protocol="oidc",
                service_config={
                    "external-host": "login.example.test",
                    "provisioning-transport": "debug-tunnel",
                },
                app_routes=(
                    {"name": "web", "visibility": "local", "target": {"port": "http"}},
                ),
                platform_domains=(
                    {"name": "local", "domain": "nephos.local", "default": True},
                ),
            )
        )


def test_live_external_provisioners_block_when_client_is_not_configured() -> None:
    with pytest.raises(RuntimeBlockedError, match="Zitadel client is not configured"):
        ZitadelAppScopedProvisioner().provision_binding(
            _context(
                service_slug="zitadel",
                alias="auth",
                capability="oidc",
                protocol="oidc",
            )
        )

    with pytest.raises(RuntimeBlockedError, match="SeaweedFS client is not configured"):
        SeaweedFSS3Provisioner().provision_binding(
            _context(
                service_slug="seaweedfs",
                alias="files",
                capability="object-storage",
                protocol="s3",
            )
        )

    with pytest.raises(RuntimeBlockedError, match="ArcadeDB client is not configured"):
        ArcadeDBAppScopedProvisioner().provision_binding(
            _context(
                service_slug="arcadedb",
                alias="graph",
                capability="sql",
                protocol="arcadedb",
            )
        )


def test_arcadedb_fake_client_outputs_supported_core_protocols() -> None:
    client = FakeArcadeDBClient()
    provisioner = ArcadeDBAppScopedProvisioner(client=client)

    sql = provisioner.provision_binding(
        _context(
            service_slug="arcadedb",
            alias="data",
            capability="sql",
            protocol="arcadedb",
        )
    )
    bolt = provisioner.provision_binding(
        _context(
            service_slug="arcadedb",
            alias="graph",
            capability="opencypher",
            protocol="bolt",
        )
    )
    n4j = provisioner.provision_binding(
        _context(
            service_slug="arcadedb",
            alias="neo",
            capability="opencypher",
            protocol="n4j",
        )
    )

    assert sql is not None
    assert sql["protocol"] == "arcadedb"
    assert bolt is not None
    assert bolt["protocol"] == "bolt"
    assert n4j is not None
    assert n4j["protocol"] == "n4j"
    assert len(client.calls) == 3


def test_arcadedb_optional_protocol_blocks_until_enabled() -> None:
    provisioner = ArcadeDBAppScopedProvisioner(client=FakeArcadeDBClient())

    with pytest.raises(RuntimeBlockedError) as exc_info:
        provisioner.provision_binding(
            _context(
                service_slug="arcadedb",
                alias="gremlin",
                capability="gremlin",
                protocol="gremlin",
            )
        )

    assert exc_info.value.reason == "binding_provisioner_unavailable"
    assert "gremlin/gremlin is not enabled" in str(exc_info.value)


def test_arcadedb_optional_protocol_dispatches_when_enabled() -> None:
    client = FakeArcadeDBClient()
    provisioner = ArcadeDBAppScopedProvisioner(
        client=client,
        enabled_optional_protocols={("gremlin", "gremlin")},
    )
    context = _context(
        service_slug="arcadedb",
        alias="gremlin",
        capability="gremlin",
        protocol="gremlin",
    )

    values = provisioner.provision_binding(context)

    assert values is not None
    assert values["protocol"] == "gremlin"
    assert client.calls == [context]


def _context(
    *,
    service_slug: str,
    alias: str,
    capability: str,
    protocol: str,
    app_routes=(),
    platform_domains=(),
    service_config=None,
) -> BindingProvisioningContext:
    return BindingProvisioningContext(
        binding_id=f"binding_{alias}",
        app_slug="paperless",
        service_slug=service_slug,
        alias=alias,
        capability=capability,
        protocol=protocol,
        service_config=service_config,
        app_routes=app_routes,
        platform_domains=platform_domains,
    )


class _RecordingProvisioner:
    def __init__(self) -> None:
        self.contexts: list[BindingProvisioningContext] = []

    def provision_binding(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str]:
        self.contexts.append(context)
        return {"issuerUrl": str((context.service_config or {})["external-host"])}

    def deprovision_binding(self, context: BindingProvisioningContext) -> None:
        self.contexts.append(context)


def test_secret_resolving_provisioner_resolves_op_refs_in_service_config() -> None:
    inner = _RecordingProvisioner()
    provisioner = SecretResolvingBindingProvisioner(
        inner,
        resolver=StaticSecretResolver(
            {
                "op://nephos-lcl/zitadel-bootstrap/external_host": (
                    "zitadel.nephos.localhost"
                )
            }
        ),
    )
    context = _context(
        service_slug="zitadel",
        alias="identity",
        capability="oidc",
        protocol="oidc",
        service_config={
            "external-host": "op://nephos-lcl/zitadel-bootstrap/external_host",
            "external-port": 80,
            "provisioning-transport": "port-forward",
        },
    )

    values = provisioner.provision_binding(context)

    resolved_config = inner.contexts[0].service_config
    # op:// reference is resolved before the inner provisioner sees it.
    assert resolved_config["external-host"] == "zitadel.nephos.localhost"
    # Non-secret values pass through unchanged.
    assert resolved_config["external-port"] == 80
    assert resolved_config["provisioning-transport"] == "port-forward"
    assert values == {"issuerUrl": "zitadel.nephos.localhost"}


def test_secret_resolving_provisioner_resolves_on_deprovision() -> None:
    inner = _RecordingProvisioner()
    provisioner = SecretResolvingBindingProvisioner(
        inner,
        resolver=StaticSecretResolver(
            {
                "op://nephos-lcl/zitadel-bootstrap/external_host": (
                    "zitadel.nephos.localhost"
                )
            }
        ),
    )
    context = _context(
        service_slug="zitadel",
        alias="identity",
        capability="oidc",
        protocol="oidc",
        service_config={
            "external-host": "op://nephos-lcl/zitadel-bootstrap/external_host"
        },
    )

    provisioner.deprovision_binding(context)

    assert (
        inner.contexts[0].service_config["external-host"]
        == "zitadel.nephos.localhost"
    )
