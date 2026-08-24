import base64

import pytest
from kubernetes import client
from kubernetes.client.rest import ApiException

from nephos_api.kubernetes_runtime import KubernetesRuntimeSafetyError
from nephos_api.provisioning import (
    BindingProvisioningContext,
    KubernetesMariaDBSqlRunner,
    MariaDBAppScopedProvisioner,
)


class FakeCoreV1Api:
    def __init__(self) -> None:
        self.namespaces: dict[str, client.V1Namespace] = {
            "svc-mariadb": client.V1Namespace(
                metadata=client.V1ObjectMeta(
                    name="svc-mariadb",
                    labels={
                        "app.kubernetes.io/managed-by": "nephos",
                        "nephos.pro/service-instance": "mariadb",
                    },
                )
            )
        }
        self.secrets: dict[tuple[str, str], client.V1Secret] = {
            ("svc-mariadb", "svc-mariadb-mariadb"): _secret(
                namespace="svc-mariadb",
                name="svc-mariadb-mariadb",
                data={"root-password": "root-secret"},
            )
        }
        self.created_secrets: list[client.V1Secret] = []
        self.deleted_secrets: list[tuple[str, str]] = []
        self.pods: dict[tuple[str, str], client.V1Pod] = {
            ("svc-mariadb", "svc-mariadb-mariadb-0"): client.V1Pod(
                metadata=client.V1ObjectMeta(
                    namespace="svc-mariadb",
                    name="svc-mariadb-mariadb-0",
                )
            )
        }

    def read_namespace(self, *, name: str) -> client.V1Namespace:
        namespace = self.namespaces.get(name)
        if namespace is None:
            raise ApiException(status=404)
        return namespace

    def read_namespaced_secret(
        self,
        *,
        namespace: str,
        name: str,
    ) -> client.V1Secret:
        secret = self.secrets.get((namespace, name))
        if secret is None:
            raise ApiException(status=404)
        return secret

    def create_namespaced_secret(
        self,
        *,
        namespace: str,
        body: client.V1Secret,
    ) -> client.V1Secret:
        assert body.metadata is not None
        body.metadata.namespace = namespace
        self.created_secrets.append(body)
        self.secrets[(namespace, body.metadata.name)] = body
        return body

    def read_namespaced_pod(
        self,
        *,
        namespace: str,
        name: str,
    ) -> client.V1Pod:
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


class FakeSqlRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def run_sql(
        self,
        *,
        core_v1_api: client.CoreV1Api,
        namespace: str,
        pod_name: str,
        root_password: str,
        sql: str,
    ) -> None:
        self.calls.append(
            {
                "namespace": namespace,
                "pod_name": pod_name,
                "root_password": root_password,
                "sql": sql,
            }
        )


class FakeExecResponse:
    def __init__(
        self,
        *,
        stdout: list[str],
        stderr: list[str] | None = None,
        returncode: int | None = None,
    ) -> None:
        self._stdout = stdout
        self._stderr = stderr or []
        self.returncode = returncode

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


def test_mariadb_runner_keeps_password_out_of_argv_and_uses_mariadb_client(
    monkeypatch,
) -> None:
    """MYSQL_PWD, not `-p<password>`: argv is world-readable inside the pod."""
    captured = {}

    def fake_stream(connect, pod_name, namespace, **kwargs):
        captured["pod_name"] = pod_name
        captured["namespace"] = namespace
        captured["kwargs"] = kwargs
        return FakeExecResponse(stdout=["ok\n", "NEPHOS_EXIT:0\n"])

    monkeypatch.setattr("nephos_api.provisioners.mariadb.stream.stream", fake_stream)

    KubernetesMariaDBSqlRunner().run_sql(
        core_v1_api=FakeCoreV1Api(),
        namespace="svc-mariadb",
        pod_name="svc-mariadb-mariadb-0",
        root_password="admin secret",
        sql="SELECT 1",
    )

    script = captured["kwargs"]["command"][2]
    assert captured["kwargs"]["command"][:2] == ["sh", "-lc"]
    assert "MYSQL_PWD='admin secret'" in script
    # The deprecated `mysql` symlink is scheduled for removal upstream.
    assert "mariadb -u root --batch" in script
    assert "--password" not in script
    assert "-p'" not in script


def test_mariadb_runner_raises_on_nonzero_exec_marker(monkeypatch) -> None:
    def fake_stream(connect, pod_name, namespace, **kwargs):
        return FakeExecResponse(
            stdout=["mariadb output\n", "NEPHOS_EXIT:1\n"],
            stderr=["ERROR 1064 (42000): You have an error\n"],
            returncode=None,
        )

    monkeypatch.setattr("nephos_api.provisioners.mariadb.stream.stream", fake_stream)

    with pytest.raises(RuntimeError, match="ERROR 1064"):
        KubernetesMariaDBSqlRunner().run_sql(
            core_v1_api=FakeCoreV1Api(),
            namespace="svc-mariadb",
            pod_name="svc-mariadb-mariadb-0",
            root_password="root-secret",
            sql="SELECT broken",
        )


def test_mariadb_runner_raises_when_exec_marker_is_missing(monkeypatch) -> None:
    def fake_stream(connect, pod_name, namespace, **kwargs):
        return FakeExecResponse(
            stdout=["output without marker\n"],
            stderr=[],
            returncode=None,
        )

    monkeypatch.setattr("nephos_api.provisioners.mariadb.stream.stream", fake_stream)

    with pytest.raises(RuntimeError, match="missing exec exit marker"):
        KubernetesMariaDBSqlRunner().run_sql(
            core_v1_api=FakeCoreV1Api(),
            namespace="svc-mariadb",
            pod_name="svc-mariadb-mariadb-0",
            root_password="root-secret",
            sql="SELECT 1",
        )


def test_mariadb_runner_accepts_zero_exec_marker(monkeypatch) -> None:
    def fake_stream(connect, pod_name, namespace, **kwargs):
        return FakeExecResponse(stdout=["ok\n", "NEPHOS_EXIT:0\n"])

    monkeypatch.setattr("nephos_api.provisioners.mariadb.stream.stream", fake_stream)

    KubernetesMariaDBSqlRunner().run_sql(
        core_v1_api=FakeCoreV1Api(),
        namespace="svc-mariadb",
        pod_name="svc-mariadb-mariadb-0",
        root_password="root-secret",
        sql="SELECT 1",
    )


def test_mariadb_provisioner_creates_credentials_and_returns_outputs() -> None:
    core = FakeCoreV1Api()
    runner = FakeSqlRunner()
    provisioner = MariaDBAppScopedProvisioner(
        core_v1_api=core,
        sql_runner=runner,
        password_factory=lambda: "my-secret!",
    )

    values = provisioner.provision_binding(_context())

    assert values == {
        "host": "svc-mariadb-mariadb.svc-mariadb.svc.cluster.local",
        "port": "3306",
        "database": "nephos_paperless_database",
        "username": "nephos_paperless_database",
        "password": "my-secret!",
        "uri": (
            "mysql://nephos_paperless_database:my-secret%21@"
            "svc-mariadb-mariadb.svc-mariadb.svc.cluster.local:3306/"
            "nephos_paperless_database"
        ),
    }

    created = core.created_secrets[0]
    assert created.metadata is not None
    assert created.metadata.name == "nephos-my-paperless-database"
    assert created.metadata.labels == {
        "app.kubernetes.io/managed-by": "nephos",
        "nephos.pro/app-instance": "paperless",
        "nephos.pro/service-instance": "mariadb",
        "nephos.pro/capability": "sql",
        "nephos.pro/protocol": "mysql",
        "nephos.pro/binding-alias": "database",
    }
    assert created.string_data == {
        "database": "nephos_paperless_database",
        "username": "nephos_paperless_database",
        "password": "my-secret!",
    }
    assert runner.calls[0]["namespace"] == "svc-mariadb"
    assert runner.calls[0]["pod_name"] == "svc-mariadb-mariadb-0"
    assert runner.calls[0]["root_password"] == "root-secret"


def test_mariadb_provision_sql_grants_from_any_host() -> None:
    """A localhost-scoped grant authenticates only from inside the MariaDB pod,
    so every app pod would fail with access denied while the SQL looked fine."""
    core = FakeCoreV1Api()
    runner = FakeSqlRunner()
    provisioner = MariaDBAppScopedProvisioner(
        core_v1_api=core,
        sql_runner=runner,
        password_factory=lambda: "my-secret",
    )

    provisioner.provision_binding(_context())

    sql = runner.calls[0]["sql"]
    assert "@'localhost'" not in sql
    assert sql.count("@'%'") == 3
    assert "CREATE DATABASE IF NOT EXISTS `nephos_paperless_database`;" in sql
    assert (
        "CREATE USER IF NOT EXISTS 'nephos_paperless_database'@'%' "
        "IDENTIFIED BY 'my-secret';" in sql
    )
    assert (
        "ALTER USER 'nephos_paperless_database'@'%' IDENTIFIED BY 'my-secret';" in sql
    )
    assert (
        "GRANT ALL PRIVILEGES ON `nephos_paperless_database`.* "
        "TO 'nephos_paperless_database'@'%';" in sql
    )


def test_mariadb_provision_sql_escapes_backslashes_in_the_password() -> None:
    """MariaDB honours backslash escapes in string literals by default, so a
    trailing backslash would escape the closing quote and break the statement."""
    core = FakeCoreV1Api()
    runner = FakeSqlRunner()
    provisioner = MariaDBAppScopedProvisioner(
        core_v1_api=core,
        sql_runner=runner,
        password_factory=lambda: "back\\slash'quote",
    )

    provisioner.provision_binding(_context())

    assert "IDENTIFIED BY 'back\\\\slash''quote'" in runner.calls[0]["sql"]


def test_mariadb_service_dep_no_admin_without_entitlement() -> None:
    # ADR 20260721: default-deny, matching the sql engine. A service dependency
    # gets only the app-scoped credential unless it declares the entitlement.
    core = FakeCoreV1Api()
    runner = FakeSqlRunner()
    provisioner = MariaDBAppScopedProvisioner(
        core_v1_api=core,
        sql_runner=runner,
        password_factory=lambda: "my-secret",
    )

    values = provisioner.provision_binding(
        BindingProvisioningContext(
            binding_id="service-wiki-database",
            app_slug="wiki",
            service_slug="mariadb",
            alias="database",
            capability="sql",
            protocol="mysql",
        )
    )

    assert values is not None
    assert "adminUsername" not in values
    assert "adminPassword" not in values


def test_mariadb_provisioner_grants_admin_via_entitlement() -> None:
    core = FakeCoreV1Api()
    runner = FakeSqlRunner()
    provisioner = MariaDBAppScopedProvisioner(
        core_v1_api=core,
        sql_runner=runner,
        password_factory=lambda: "my-secret",
    )

    values = provisioner.provision_binding(
        BindingProvisioningContext(
            binding_id="binding_01",
            app_slug="reporting",
            service_slug="mariadb",
            alias="database",
            capability="sql",
            protocol="mysql",
            entitlements=frozenset({"admin-credentials"}),
        )
    )

    assert values is not None
    assert values["adminUsername"] == "root"
    assert values["adminPassword"] == "root-secret"


def test_mariadb_engine_recognizes_only_admin_credentials() -> None:
    """The router reads this attribute via getattr with a frozenset() default, so
    omitting it would block every admin-credentials binding as unrecognized."""
    assert MariaDBAppScopedProvisioner.recognized_entitlements == frozenset(
        {"admin-credentials"}
    )


def test_mariadb_provisioner_reuses_existing_owned_credential_secret() -> None:
    core = FakeCoreV1Api()
    core.secrets[("svc-mariadb", "nephos-my-paperless-database")] = _secret(
        namespace="svc-mariadb",
        name="nephos-my-paperless-database",
        labels=_owned_labels(),
        data={
            "database": "nephos_paperless_database",
            "username": "nephos_paperless_database",
            "password": "existing-secret",
        },
    )
    runner = FakeSqlRunner()
    provisioner = MariaDBAppScopedProvisioner(
        core_v1_api=core,
        sql_runner=runner,
        password_factory=lambda: "new-secret",
    )

    values = provisioner.provision_binding(_context())

    assert core.created_secrets == []
    assert values is not None
    assert values["password"] == "existing-secret"
    assert runner.calls[0]["sql"].count("nephos_paperless_database") >= 3


def test_mariadb_provisioner_returns_none_for_unsupported_capability() -> None:
    core = FakeCoreV1Api()
    runner = FakeSqlRunner()
    provisioner = MariaDBAppScopedProvisioner(
        core_v1_api=core,
        sql_runner=runner,
        password_factory=lambda: "unused",
    )

    values = provisioner.provision_binding(
        BindingProvisioningContext(
            binding_id="binding_01",
            app_slug="paperless",
            service_slug="redis",
            alias="cache",
            capability="redis",
        )
    )

    assert values is None
    assert core.created_secrets == []
    assert runner.calls == []


def test_mariadb_provisioner_returns_none_for_postgres_protocol() -> None:
    """The two sql engines must not answer for each other's protocol: values from
    the wrong engine would hand an app credentials for a database it cannot use."""
    core = FakeCoreV1Api()
    runner = FakeSqlRunner()
    provisioner = MariaDBAppScopedProvisioner(
        core_v1_api=core,
        sql_runner=runner,
        password_factory=lambda: "unused",
    )

    values = provisioner.provision_binding(
        BindingProvisioningContext(
            binding_id="binding_01",
            app_slug="paperless",
            service_slug="postgres",
            alias="database",
            capability="sql",
            protocol="postgres",
        )
    )

    assert values is None
    assert core.created_secrets == []
    assert runner.calls == []


def test_mariadb_provisioner_returns_none_for_sql_without_protocol() -> None:
    """Unlike postgres there is no legacy bare-capability row to honour, so an
    unqualified `sql` binding is not this engine's."""
    core = FakeCoreV1Api()
    runner = FakeSqlRunner()
    provisioner = MariaDBAppScopedProvisioner(
        core_v1_api=core,
        sql_runner=runner,
        password_factory=lambda: "unused",
    )

    values = provisioner.provision_binding(
        BindingProvisioningContext(
            binding_id="binding_01",
            app_slug="paperless",
            service_slug="mariadb",
            alias="database",
            capability="sql",
        )
    )

    assert values is None
    assert runner.calls == []


def test_mariadb_provisioner_refuses_unowned_existing_credential_secret() -> None:
    core = FakeCoreV1Api()
    core.secrets[("svc-mariadb", "nephos-my-paperless-database")] = _secret(
        namespace="svc-mariadb",
        name="nephos-my-paperless-database",
        labels={},
        data={
            "database": "nephos_paperless_database",
            "username": "nephos_paperless_database",
            "password": "existing-secret",
        },
    )
    provisioner = MariaDBAppScopedProvisioner(
        core_v1_api=core,
        sql_runner=FakeSqlRunner(),
        password_factory=lambda: "unused",
    )

    with pytest.raises(KubernetesRuntimeSafetyError):
        provisioner.provision_binding(_context())


def test_mariadb_provisioner_refuses_unowned_service_namespace() -> None:
    core = FakeCoreV1Api()
    core.namespaces["svc-mariadb"] = client.V1Namespace(
        metadata=client.V1ObjectMeta(name="svc-mariadb", labels={})
    )
    provisioner = MariaDBAppScopedProvisioner(
        core_v1_api=core,
        sql_runner=FakeSqlRunner(),
        password_factory=lambda: "unused",
    )

    with pytest.raises(
        KubernetesRuntimeSafetyError,
        match="refusing to use unowned namespace svc-mariadb",
    ):
        provisioner.provision_binding(_context())


def test_mariadb_provisioner_refuses_terminating_service_namespace() -> None:
    core = FakeCoreV1Api()
    core.namespaces["svc-mariadb"] = client.V1Namespace(
        metadata=client.V1ObjectMeta(
            name="svc-mariadb",
            labels={
                "app.kubernetes.io/managed-by": "nephos",
                "nephos.pro/service-instance": "mariadb",
            },
            deletion_timestamp="2026-08-24T00:00:00Z",
        )
    )
    provisioner = MariaDBAppScopedProvisioner(
        core_v1_api=core,
        sql_runner=FakeSqlRunner(),
        password_factory=lambda: "unused",
    )

    with pytest.raises(
        KubernetesRuntimeSafetyError,
        match="refusing to use terminating namespace svc-mariadb",
    ):
        provisioner.provision_binding(_context())


def test_mariadb_provisioner_deprovisions_database_user_and_secret() -> None:
    core = FakeCoreV1Api()
    core.secrets[("svc-mariadb", "nephos-my-paperless-database")] = _secret(
        namespace="svc-mariadb",
        name="nephos-my-paperless-database",
        labels=_owned_labels(),
        data={
            "database": "nephos_paperless_database",
            "username": "nephos_paperless_database",
            "password": "existing-secret",
        },
    )
    runner = FakeSqlRunner()
    provisioner = MariaDBAppScopedProvisioner(
        core_v1_api=core,
        sql_runner=runner,
        password_factory=lambda: "unused",
    )

    provisioner.deprovision_binding(_context())

    sql = runner.calls[0]["sql"]
    assert "DROP DATABASE IF EXISTS `nephos_paperless_database`;" in sql
    assert "DROP USER IF EXISTS 'nephos_paperless_database'@'%';" in sql
    assert core.deleted_secrets == [("svc-mariadb", "nephos-my-paperless-database")]


def test_mariadb_deprovision_is_idempotent_when_secret_is_missing() -> None:
    core = FakeCoreV1Api()
    runner = FakeSqlRunner()
    provisioner = MariaDBAppScopedProvisioner(
        core_v1_api=core,
        sql_runner=runner,
        password_factory=lambda: "unused",
    )

    provisioner.deprovision_binding(_context())

    assert runner.calls == []
    assert core.deleted_secrets == []


def test_mariadb_identifiers_stay_within_the_length_budget() -> None:
    """A 64-char database name and an 80-char user name are MariaDB's hard
    limits; the truncated form must also stay a legal Kubernetes Secret name."""
    core = FakeCoreV1Api()
    runner = FakeSqlRunner()
    provisioner = MariaDBAppScopedProvisioner(
        core_v1_api=core,
        sql_runner=runner,
        password_factory=lambda: "my-secret",
    )
    long_slug = "a" * 40
    core.namespaces["svc-mariadb"] = client.V1Namespace(
        metadata=client.V1ObjectMeta(
            name="svc-mariadb",
            labels={
                "app.kubernetes.io/managed-by": "nephos",
                "nephos.pro/service-instance": "mariadb",
            },
        )
    )

    values = provisioner.provision_binding(
        BindingProvisioningContext(
            binding_id="binding_01",
            app_slug=long_slug,
            service_slug="mariadb",
            alias="b" * 40,
            capability="sql",
            protocol="mysql",
        )
    )

    assert values is not None
    assert len(values["database"]) <= 63
    created = core.created_secrets[0]
    assert created.metadata is not None
    assert len(created.metadata.name) <= 63


def _owned_labels() -> dict[str, str]:
    return {
        "app.kubernetes.io/managed-by": "nephos",
        "nephos.pro/app-instance": "paperless",
        "nephos.pro/service-instance": "mariadb",
        "nephos.pro/capability": "sql",
        "nephos.pro/protocol": "mysql",
        "nephos.pro/binding-alias": "database",
    }


def _context() -> BindingProvisioningContext:
    return BindingProvisioningContext(
        binding_id="binding_01",
        app_slug="paperless",
        service_slug="mariadb",
        alias="database",
        capability="sql",
        protocol="mysql",
    )


def _secret(
    *,
    namespace: str,
    name: str,
    data: dict[str, str],
    labels: dict[str, str] | None = None,
) -> client.V1Secret:
    return client.V1Secret(
        metadata=client.V1ObjectMeta(
            namespace=namespace,
            name=name,
            labels=labels,
        ),
        data={
            key: base64.b64encode(value.encode()).decode()
            for key, value in data.items()
        },
    )
