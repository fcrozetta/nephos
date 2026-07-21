import pytest

from nephos_api.catalog import Provisioning
from nephos_api.provisioners import (
    BindingProvisioningContext,
    EngineRoutingBindingProvisioner,
)
from nephos_api.runtime_errors import RuntimeBlockedError


class _Recorder:
    def __init__(
        self,
        result: dict | None = None,
        *,
        recognized_entitlements: frozenset[str] = frozenset(),
    ) -> None:
        self.result = result
        self.recognized_entitlements = recognized_entitlements
        self.provisioned: list = []
        self.deprovisioned: list = []

    def provision_binding(self, context):
        self.provisioned.append(context)
        return self.result

    def deprovision_binding(self, context):
        self.deprovisioned.append(context)


def _ctx(engine=None, capability="sql", protocol="postgres", entitlements=frozenset()):
    return BindingProvisioningContext(
        binding_id="b1",
        app_slug="app",
        service_slug="svc",
        alias="db",
        capability=capability,
        protocol=protocol,
        provisioning_engine=engine,
        entitlements=entitlements,
    )


def test_routes_to_declared_engine():
    sql = _Recorder({"uri": "x"})
    oidc = _Recorder({"client": "y"})
    router = EngineRoutingBindingProvisioner({"sql": sql, "oidc": oidc})
    assert router.provision_binding(_ctx(engine="oidc")) == {"client": "y"}
    assert len(oidc.provisioned) == 1
    assert sql.provisioned == []


def test_absent_engine_blocks_loudly():
    sql = _Recorder({"uri": "x"})
    router = EngineRoutingBindingProvisioner({"sql": sql})
    with pytest.raises(RuntimeBlockedError, match="no declared"):
        router.provision_binding(_ctx(engine=None))
    # No fallback: a binding whose manifest declares no engine must block, not be
    # handed to an arbitrary provisioner.
    assert sql.provisioned == []


def test_unknown_declared_engine_blocks_loudly():
    sql = _Recorder({"uri": "x"})
    router = EngineRoutingBindingProvisioner({"sql": sql})
    with pytest.raises(RuntimeBlockedError, match="engine registered for 'nope'"):
        router.provision_binding(_ctx(engine="nope"))
    # A declared-but-unregistered engine must block, not pick another provisioner.
    assert sql.provisioned == []


def test_deprovision_routes_to_declared_engine():
    sql = _Recorder()
    oidc = _Recorder()
    router = EngineRoutingBindingProvisioner({"sql": sql, "oidc": oidc})
    router.deprovision_binding(_ctx(engine="sql"))
    assert len(sql.deprovisioned) == 1
    assert oidc.deprovisioned == []


def test_blocks_entitlement_not_recognized_by_engine():
    sql = _Recorder(
        {"uri": "x"}, recognized_entitlements=frozenset({"admin-credentials"})
    )
    router = EngineRoutingBindingProvisioner({"sql": sql})
    with pytest.raises(RuntimeBlockedError, match="not recognized"):
        router.provision_binding(
            _ctx(engine="sql", entitlements=frozenset({"root-shell"}))
        )
    # Blocked before reaching the engine.
    assert sql.provisioned == []


def test_passes_recognized_entitlement_to_engine():
    sql = _Recorder(
        {"uri": "x"}, recognized_entitlements=frozenset({"admin-credentials"})
    )
    router = EngineRoutingBindingProvisioner({"sql": sql})
    values = router.provision_binding(
        _ctx(engine="sql", entitlements=frozenset({"admin-credentials"}))
    )
    assert values == {"uri": "x"}
    assert len(sql.provisioned) == 1


def test_blocks_entitlement_for_engine_recognizing_none():
    # An engine that recognizes no entitlements (e.g. oidc) blocks any declared
    # entitlement rather than silently ignoring it.
    oidc = _Recorder({"client": "y"})
    router = EngineRoutingBindingProvisioner({"oidc": oidc})
    with pytest.raises(RuntimeBlockedError, match="not recognized"):
        router.provision_binding(
            _ctx(engine="oidc", entitlements=frozenset({"admin-credentials"}))
        )
    assert oidc.provisioned == []


def test_provisioning_manifest_accepts_optional_engine():
    p = Provisioning.model_validate({"mode": "app-scoped-resource", "engine": "sql"})
    assert p.engine == "sql"
    assert Provisioning.model_validate({"mode": "none"}).engine is None
