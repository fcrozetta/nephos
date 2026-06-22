import pytest

from nephos_api.provisioning import (
    ArcadeDBAppScopedProvisioner,
    BindingProvisioningContext,
    CompositeBindingProvisioner,
    SeaweedFSS3Provisioner,
    ZitadelAppScopedProvisioner,
)
from nephos_api.runtime_errors import RuntimeBlockedError


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
) -> BindingProvisioningContext:
    return BindingProvisioningContext(
        binding_id=f"binding_{alias}",
        app_slug="paperless",
        service_slug=service_slug,
        alias=alias,
        capability=capability,
        protocol=protocol,
    )
