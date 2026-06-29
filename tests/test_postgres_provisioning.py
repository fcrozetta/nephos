import base64

import pytest
from kubernetes import client
from kubernetes.client.rest import ApiException

from nephos_api.kubernetes_runtime import KubernetesRuntimeSafetyError
from nephos_api.provisioning import (
    BindingProvisioningContext,
    KubernetesPsqlRunner,
    PostgresAppScopedProvisioner,
)


class FakeCoreV1Api:
    def __init__(self) -> None:
        self.namespaces: dict[str, client.V1Namespace] = {
            "svc-postgres": client.V1Namespace(
                metadata=client.V1ObjectMeta(
                    name="svc-postgres",
                    labels={
                        "app.kubernetes.io/managed-by": "nephos",
                        "nephos.pro/service-instance": "postgres",
                    },
                )
            )
        }
        self.secrets: dict[tuple[str, str], client.V1Secret] = {
            ("svc-postgres", "svc-postgres-postgresql"): _secret(
                namespace="svc-postgres",
                name="svc-postgres-postgresql",
                data={"postgres-password": "admin-secret"},
            )
        }
        self.created_secrets: list[client.V1Secret] = []
        self.deleted_secrets: list[tuple[str, str]] = []
        self.pods: dict[tuple[str, str], client.V1Pod] = {
            ("svc-postgres", "svc-postgres-postgresql-0"): client.V1Pod(
                metadata=client.V1ObjectMeta(
                    namespace="svc-postgres",
                    name="svc-postgres-postgresql-0",
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


class FakePsqlRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def run_psql(
        self,
        *,
        core_v1_api: client.CoreV1Api,
        namespace: str,
        pod_name: str,
        admin_password: str,
        sql: str,
    ) -> None:
        self.calls.append(
            {
                "namespace": namespace,
                "pod_name": pod_name,
                "admin_password": admin_password,
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


def test_kubernetes_psql_runner_raises_on_nonzero_exec_marker(monkeypatch) -> None:
    captured = {}

    def fake_stream(connect, pod_name, namespace, **kwargs):
        captured["pod_name"] = pod_name
        captured["namespace"] = namespace
        captured["kwargs"] = kwargs
        return FakeExecResponse(
            stdout=["psql output\n", "NEPHOS_EXIT:2\n"],
            stderr=["psql: error\n"],
            returncode=None,
        )

    monkeypatch.setattr("nephos_api.provisioners.postgres.stream.stream", fake_stream)

    with pytest.raises(RuntimeError, match="psql: error"):
        KubernetesPsqlRunner().run_psql(
            core_v1_api=FakeCoreV1Api(),
            namespace="svc-postgres",
            pod_name="svc-postgres-postgresql-0",
            admin_password="admin-secret",
            sql="SELECT broken",
        )

    assert captured["pod_name"] == "svc-postgres-postgresql-0"
    assert captured["namespace"] == "svc-postgres"
    assert captured["kwargs"]["command"][:2] == ["sh", "-lc"]
    assert "NEPHOS_EXIT" in captured["kwargs"]["command"][2]


def test_kubernetes_psql_runner_raises_when_exec_marker_is_missing(
    monkeypatch,
) -> None:
    def fake_stream(connect, pod_name, namespace, **kwargs):
        return FakeExecResponse(
            stdout=["psql output without marker\n"],
            stderr=[],
            returncode=None,
        )

    monkeypatch.setattr("nephos_api.provisioners.postgres.stream.stream", fake_stream)

    with pytest.raises(RuntimeError, match="missing exec exit marker"):
        KubernetesPsqlRunner().run_psql(
            core_v1_api=FakeCoreV1Api(),
            namespace="svc-postgres",
            pod_name="svc-postgres-postgresql-0",
            admin_password="admin-secret",
            sql="SELECT 1",
        )


def test_kubernetes_psql_runner_accepts_zero_exec_marker(monkeypatch) -> None:
    def fake_stream(connect, pod_name, namespace, **kwargs):
        return FakeExecResponse(
            stdout=["ok\n", "NEPHOS_EXIT:0\n"],
            stderr=[],
            returncode=None,
        )

    monkeypatch.setattr("nephos_api.provisioners.postgres.stream.stream", fake_stream)

    KubernetesPsqlRunner().run_psql(
        core_v1_api=FakeCoreV1Api(),
        namespace="svc-postgres",
        pod_name="svc-postgres-postgresql-0",
        admin_password="admin-secret",
        sql="SELECT 1",
    )


def test_postgres_provisioner_creates_credentials_and_returns_outputs() -> None:
    core = FakeCoreV1Api()
    runner = FakePsqlRunner()
    provisioner = PostgresAppScopedProvisioner(
        core_v1_api=core,
        psql_runner=runner,
        password_factory=lambda: "pg-secret!",
    )

    values = provisioner.provision_binding(_context())

    assert values == {
        "host": "svc-postgres-postgresql.svc-postgres.svc.cluster.local",
        "port": "5432",
        "database": "nephos_paperless_database",
        "username": "nephos_paperless_database",
        "password": "pg-secret!",
        "uri": (
            "postgresql://nephos_paperless_database:pg-secret%21@"
            "svc-postgres-postgresql.svc-postgres.svc.cluster.local:5432/"
            "nephos_paperless_database"
        ),
    }

    created = core.created_secrets[0]
    assert created.metadata is not None
    assert created.metadata.name == "nephos-pg-paperless-database"
    assert created.metadata.labels == {
        "app.kubernetes.io/managed-by": "nephos",
        "nephos.pro/app-instance": "paperless",
        "nephos.pro/service-instance": "postgres",
        "nephos.pro/capability": "sql",
        "nephos.pro/protocol": "postgres",
        "nephos.pro/binding-alias": "database",
    }
    assert created.string_data == {
        "database": "nephos_paperless_database",
        "username": "nephos_paperless_database",
        "password": "pg-secret!",
    }
    assert runner.calls[0]["namespace"] == "svc-postgres"
    assert runner.calls[0]["pod_name"] == "svc-postgres-postgresql-0"
    assert runner.calls[0]["admin_password"] == "admin-secret"
    assert "CREATE ROLE" in runner.calls[0]["sql"]
    assert "CREATE DATABASE" in runner.calls[0]["sql"]
    assert "nephos_paperless_database" in runner.calls[0]["sql"]


def test_postgres_provisioner_returns_admin_outputs_for_service_dependency() -> None:
    core = FakeCoreV1Api()
    runner = FakePsqlRunner()
    provisioner = PostgresAppScopedProvisioner(
        core_v1_api=core,
        psql_runner=runner,
        password_factory=lambda: "pg-secret",
    )

    values = provisioner.provision_binding(
        BindingProvisioningContext(
            binding_id="service-zitadel-database",
            app_slug="zitadel",
            service_slug="postgres",
            alias="database",
            capability="sql",
            protocol="postgres",
        )
    )

    assert values is not None
    assert values["adminUsername"] == "postgres"
    assert values["adminPassword"] == "admin-secret"
    created = core.created_secrets[0]
    assert created.string_data == {
        "database": "nephos_zitadel_database",
        "username": "nephos_zitadel_database",
        "password": "pg-secret",
    }


def test_postgres_provisioner_reuses_existing_owned_credential_secret() -> None:
    core = FakeCoreV1Api()
    core.secrets[("svc-postgres", "nephos-pg-paperless-database")] = _secret(
        namespace="svc-postgres",
        name="nephos-pg-paperless-database",
        labels={
            "app.kubernetes.io/managed-by": "nephos",
            "nephos.pro/app-instance": "paperless",
            "nephos.pro/service-instance": "postgres",
            "nephos.pro/capability": "sql",
            "nephos.pro/protocol": "postgres",
            "nephos.pro/binding-alias": "database",
        },
        data={
            "database": "nephos_paperless_database",
            "username": "nephos_paperless_database",
            "password": "existing-secret",
        },
    )
    runner = FakePsqlRunner()
    provisioner = PostgresAppScopedProvisioner(
        core_v1_api=core,
        psql_runner=runner,
        password_factory=lambda: "new-secret",
    )

    values = provisioner.provision_binding(_context())

    assert core.created_secrets == []
    assert values is not None
    assert values["password"] == "existing-secret"
    assert runner.calls[0]["sql"].count("nephos_paperless_database") >= 3


def test_postgres_provisioner_returns_none_for_unsupported_capability() -> None:
    core = FakeCoreV1Api()
    runner = FakePsqlRunner()
    provisioner = PostgresAppScopedProvisioner(
        core_v1_api=core,
        psql_runner=runner,
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


def test_postgres_provisioner_returns_none_for_sql_with_non_postgres_protocol() -> None:
    core = FakeCoreV1Api()
    runner = FakePsqlRunner()
    provisioner = PostgresAppScopedProvisioner(
        core_v1_api=core,
        psql_runner=runner,
        password_factory=lambda: "unused",
    )

    values = provisioner.provision_binding(
        BindingProvisioningContext(
            binding_id="binding_01",
            app_slug="paperless",
            service_slug="arcadedb",
            alias="database",
            capability="sql",
            protocol="arcadedb",
        )
    )

    assert values is None
    assert core.created_secrets == []
    assert runner.calls == []


def test_postgres_provisioner_preserves_legacy_postgres_rows() -> None:
    core = FakeCoreV1Api()
    runner = FakePsqlRunner()
    provisioner = PostgresAppScopedProvisioner(
        core_v1_api=core,
        psql_runner=runner,
        password_factory=lambda: "pg-secret",
    )

    values = provisioner.provision_binding(
        BindingProvisioningContext(
            binding_id="binding_01",
            app_slug="paperless",
            service_slug="postgres",
            alias="database",
            capability="postgres",
        )
    )

    assert values is not None
    created = core.created_secrets[0]
    assert created.metadata is not None
    assert created.metadata.labels == {
        "app.kubernetes.io/managed-by": "nephos",
        "nephos.pro/app-instance": "paperless",
        "nephos.pro/service-instance": "postgres",
        "nephos.pro/capability": "postgres",
        "nephos.pro/binding-alias": "database",
    }


def test_postgres_provisioner_refuses_unowned_existing_credential_secret() -> None:
    core = FakeCoreV1Api()
    core.secrets[("svc-postgres", "nephos-pg-paperless-database")] = _secret(
        namespace="svc-postgres",
        name="nephos-pg-paperless-database",
        labels={},
        data={
            "database": "nephos_paperless_database",
            "username": "nephos_paperless_database",
            "password": "existing-secret",
        },
    )
    provisioner = PostgresAppScopedProvisioner(
        core_v1_api=core,
        psql_runner=FakePsqlRunner(),
        password_factory=lambda: "unused",
    )

    with pytest.raises(KubernetesRuntimeSafetyError):
        provisioner.provision_binding(_context())


def test_postgres_provisioner_refuses_unowned_service_namespace() -> None:
    core = FakeCoreV1Api()
    core.namespaces["svc-postgres"] = client.V1Namespace(
        metadata=client.V1ObjectMeta(name="svc-postgres", labels={})
    )
    provisioner = PostgresAppScopedProvisioner(
        core_v1_api=core,
        psql_runner=FakePsqlRunner(),
        password_factory=lambda: "unused",
    )

    with pytest.raises(
        KubernetesRuntimeSafetyError,
        match="refusing to use unowned namespace svc-postgres",
    ):
        provisioner.provision_binding(_context())


def test_postgres_provisioner_deprovisions_database_user_and_secret() -> None:
    core = FakeCoreV1Api()
    core.secrets[("svc-postgres", "nephos-pg-paperless-database")] = _secret(
        namespace="svc-postgres",
        name="nephos-pg-paperless-database",
        labels={
            "app.kubernetes.io/managed-by": "nephos",
            "nephos.pro/app-instance": "paperless",
            "nephos.pro/service-instance": "postgres",
            "nephos.pro/capability": "sql",
            "nephos.pro/protocol": "postgres",
            "nephos.pro/binding-alias": "database",
        },
        data={
            "database": "nephos_paperless_database",
            "username": "nephos_paperless_database",
            "password": "existing-secret",
        },
    )
    runner = FakePsqlRunner()
    provisioner = PostgresAppScopedProvisioner(
        core_v1_api=core,
        psql_runner=runner,
        password_factory=lambda: "unused",
    )

    provisioner.deprovision_binding(_context())

    assert "DROP DATABASE IF EXISTS" in runner.calls[0]["sql"]
    assert "DROP ROLE IF EXISTS" in runner.calls[0]["sql"]
    assert "nephos_paperless_database" in runner.calls[0]["sql"]
    assert core.deleted_secrets == [
        ("svc-postgres", "nephos-pg-paperless-database")
    ]


def test_postgres_deprovision_is_idempotent_when_secret_is_missing() -> None:
    core = FakeCoreV1Api()
    runner = FakePsqlRunner()
    provisioner = PostgresAppScopedProvisioner(
        core_v1_api=core,
        psql_runner=runner,
        password_factory=lambda: "unused",
    )

    provisioner.deprovision_binding(_context())

    assert runner.calls == []
    assert core.deleted_secrets == []


def _context() -> BindingProvisioningContext:
    return BindingProvisioningContext(
        binding_id="binding_01",
        app_slug="paperless",
        service_slug="postgres",
        alias="database",
        capability="sql",
        protocol="postgres",
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
