import base64
import json

import httpx
import pytest

from nephos_api.provisioners.arcadedb_client import (
    KubernetesArcadeDBProvisioningClient,
)
from nephos_api.provisioners.base import BindingProvisioningContext
from nephos_api.runtime_errors import RuntimeBlockedError


class _FakeSecrets:
    def __init__(self, existing=None):
        self.existing = existing
        self.created = []
        self.deleted = []

    def read_namespaced_secret(self, name, namespace):
        if self.existing is None:
            raise RuntimeError("not found")
        return self.existing

    def create_namespaced_secret(self, *, namespace, body):
        self.created.append(body)

    def delete_namespaced_secret(self, name, namespace):
        self.deleted.append(name)


class _Stored:
    def __init__(self, password):
        self.data = {"password": base64.b64encode(password.encode()).decode()}


def _ctx(protocol="bolt"):
    return BindingProvisioningContext(
        binding_id="b1",
        app_slug="graph-demo",
        service_slug="arcadedb",
        alias="graph",
        capability="opencypher",
        protocol=protocol,
        service_config={"root-password": "rootpw"},
    )


def _client(handler, secrets_api, password="generated-pw"):
    return KubernetesArcadeDBProvisioningClient(
        core_v1_api=secrets_api,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        password_factory=lambda: password,
    )


def _ok(request):
    return httpx.Response(200, json={"result": "ok"})


def test_provisioning_creates_a_scoped_database_and_user():
    seen = []

    def handler(request):
        # The user payload is JSON nested inside the command string, so decode
        # the envelope rather than substring-matching escaped text.
        seen.append(json.loads(request.read())["command"])
        return _ok(request)

    values = _client(handler, _FakeSecrets()).ensure_database_user(_ctx())

    assert seen[0] == "create database graph_demo_graph"
    user = json.loads(seen[1].removeprefix("create user "))
    assert user["name"] == "graph_demo_graph"
    assert user["password"] == "generated-pw"
    assert user["databases"] == {"graph_demo_graph": ["admin"]}
    assert values["database"] == "graph_demo_graph"
    assert values["username"] == "graph_demo_graph"
    assert values["password"] == "generated-pw"
    assert values["protocol"] == "bolt"
    assert values["port"] == "7687"
    assert values["host"].startswith("svc-arcadedb-arcadedb.svc-arcadedb")


def test_http_protocols_get_the_command_endpoint_port():
    values = _client(_ok, _FakeSecrets()).ensure_database_user(_ctx(protocol="n4j"))

    assert values["port"] == "2480"


def test_an_existing_database_is_not_an_error():
    # Provisioning runs on every reconcile, so a second create must succeed.
    def handler(request):
        return httpx.Response(
            400,
            json={"error": "Cannot execute command", "detail": "already exists"},
        )

    values = _client(handler, _FakeSecrets()).ensure_database_user(_ctx())

    assert values["database"] == "graph_demo_graph"


def test_the_password_is_read_back_rather_than_regenerated():
    # Minting a new password each reconcile would rewrite the App's binding
    # Secret and leave the running workload holding a stale credential.
    secrets_api = _FakeSecrets(existing=_Stored("original-pw"))

    values = _client(_ok, secrets_api).ensure_database_user(_ctx())

    assert values["password"] == "original-pw"
    assert secrets_api.created == []


def test_a_real_rejection_still_blocks():
    def handler(request):
        return httpx.Response(
            400, json={"error": "Cannot execute command", "detail": "syntax error"}
        )

    with pytest.raises(RuntimeBlockedError) as excinfo:
        _client(handler, _FakeSecrets()).ensure_database_user(_ctx())

    assert excinfo.value.reason == "binding_provisioner_unavailable"


def test_unreachable_arcadedb_blocks_with_the_host_named():
    def handler(request):
        raise httpx.ConnectError("no route")

    with pytest.raises(RuntimeBlockedError) as excinfo:
        _client(handler, _FakeSecrets()).ensure_database_user(_ctx())

    assert "unreachable" in str(excinfo.value)


def test_missing_root_password_blocks():
    context = BindingProvisioningContext(
        binding_id="b1",
        app_slug="graph-demo",
        service_slug="arcadedb",
        alias="graph",
        capability="opencypher",
        protocol="bolt",
        service_config={},
    )

    with pytest.raises(RuntimeBlockedError) as excinfo:
        _client(_ok, _FakeSecrets()).ensure_database_user(context)

    assert "root-password" in str(excinfo.value)


def test_teardown_drops_user_database_and_credential():
    seen = []

    def handler(request):
        seen.append(json.loads(request.read())["command"])
        return _ok(request)

    secrets_api = _FakeSecrets()
    _client(handler, secrets_api).delete_database_user(_ctx())

    assert seen[0] == "drop user graph_demo_graph"
    assert seen[1] == "drop database graph_demo_graph"
    assert secrets_api.deleted == ["nephos-arcadedb-graph-demo-graph"]


def test_teardown_tolerates_an_already_absent_user():
    def handler(request):
        return httpx.Response(
            400, json={"error": "Cannot execute command", "detail": "not found"}
        )

    _client(handler, _FakeSecrets()).delete_database_user(_ctx())
