import pytest

from nephos_api.catalog import Provisioning
from nephos_api.provisioners import (
    BindingProvisioningContext,
    EngineRoutingBindingProvisioner,
)
from nephos_api.runtime_errors import RuntimeBlockedError


class _Recorder:
    def __init__(self, result: dict | None = None) -> None:
        self.result = result
        self.provisioned: list = []
        self.deprovisioned: list = []

    def provision_binding(self, context):
        self.provisioned.append(context)
        return self.result

    def deprovision_binding(self, context):
        self.deprovisioned.append(context)


def _ctx(engine=None, capability="sql", protocol="postgres"):
    return BindingProvisioningContext(
        binding_id="b1",
        app_slug="app",
        service_slug="svc",
        alias="db",
        capability=capability,
        protocol=protocol,
        provisioning_engine=engine,
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


def test_provisioning_manifest_accepts_optional_engine():
    p = Provisioning.model_validate({"mode": "app-scoped-resource", "engine": "sql"})
    assert p.engine == "sql"
    assert Provisioning.model_validate({"mode": "none"}).engine is None
