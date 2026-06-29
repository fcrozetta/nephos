import asyncio
import time
from collections.abc import Callable
from pathlib import Path
from typing import cast

from catalog_fixtures import write_app, write_service
from fastapi.testclient import TestClient

from nephos_api.config import Settings
from nephos_api.db import migrate_database
from nephos_api.main import create_app
from nephos_api.reconciler import Reconciler
from nephos_api.reconciler_worker import ReconcilerWorker


class FakeRuntime:
    def __init__(self) -> None:
        self.namespaces: list[tuple[str, str]] = []
        self.deleted_namespaces: list[tuple[str, str]] = []
        self.binding_secrets: list[dict[str, object]] = []
        self.deleted_binding_secrets: list[dict[str, object]] = []
        self.app_ingresses: list[dict[str, object]] = []
        self.scaled_workloads: list[tuple[str, str, int]] = []

    def ensure_namespace(self, resource_type: str, slug: str) -> None:
        self.namespaces.append((resource_type, slug))

    def delete_namespace_if_owned(self, resource_type: str, slug: str) -> bool:
        self.deleted_namespaces.append((resource_type, slug))
        return True

    def ensure_binding_secret(
        self,
        *,
        app_slug: str,
        service_slug: str,
        alias: str,
        capability: str,
        protocol: str | None = None,
        values: dict[str, str],
    ) -> None:
        self.binding_secrets.append(
            {
                "app_slug": app_slug,
                "service_slug": service_slug,
                "alias": alias,
                "capability": capability,
                "values": values,
            }
        )

    def delete_binding_secret_if_owned(
        self,
        *,
        app_slug: str,
        service_slug: str,
        alias: str,
        capability: str,
        protocol: str | None = None,
    ) -> bool:
        self.deleted_binding_secrets.append(
            {
                "app_slug": app_slug,
                "service_slug": service_slug,
                "alias": alias,
                "capability": capability,
            }
        )
        return True

    def ensure_app_ingresses(
        self,
        *,
        app_slug: str,
        routes: list[dict[str, object]],
        domains: list[dict[str, object]],
    ) -> None:
        self.app_ingresses.append(
            {"app_slug": app_slug, "routes": routes, "domains": domains}
        )

    def delete_app_ingresses(
        self,
        *,
        app_slug: str,
        routes: list[dict[str, object]],
    ) -> None:
        pass

    def scale_workloads(self, resource_type: str, slug: str, replicas: int) -> None:
        self.scaled_workloads.append((resource_type, slug, replicas))


class FakeDeployer:
    def __init__(self) -> None:
        self.deployed: list[tuple[str, str]] = []
        self.uninstalled: list[tuple[str, str]] = []

    def deploy(self, *, target_type: str, slug: str) -> None:
        self.deployed.append((target_type, slug))

    def uninstall(self, *, target_type: str, slug: str) -> None:
        self.uninstalled.append((target_type, slug))


class FakeProvisioner:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values
        self.contexts = []
        self.deprovisioned_contexts = []

    def provision_binding(self, context):
        self.contexts.append(context)
        return self.values

    def deprovision_binding(self, context):
        self.deprovisioned_contexts.append(context)


def test_reconciler_worker_runs_reconciler_off_event_loop(monkeypatch) -> None:
    calls = []

    class FakeReconciler:
        def run_once(self) -> int:
            return 0

    async def fake_to_thread(function):
        calls.append(function)
        return function()

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    reconciler = FakeReconciler()
    worker = ReconcilerWorker(cast(Reconciler, reconciler), interval_seconds=60)

    async def run_worker_once() -> None:
        task = asyncio.create_task(worker.run())
        while not calls:
            await asyncio.sleep(0)
        await worker.stop()
        await asyncio.wait_for(task, timeout=1)

    asyncio.run(run_worker_once())

    assert calls == [reconciler.run_once]


def test_api_lifespan_worker_reconciles_created_service_request(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "nephos.db"
    catalog_root = tmp_path / "catalog"
    runtime = FakeRuntime()
    write_service(catalog_root)
    migrate_database(db_path=db_path)
    app = create_app(
        settings=Settings(
            db_path=db_path,
            catalog_roots=(catalog_root,),
            kubeconfig=None,
            kube_context=None,
        ),
        start_reconciler=True,
        runtime_factory=lambda _settings: runtime,
        reconciler_interval_seconds=0.01,
    )

    with TestClient(app) as client:
        response = client.post(
            "/services",
            json={"catalogRef": {"kind": "Service", "name": "postgres"}},
        )
        assert response.status_code == 202

        _eventually(
            lambda: _service_status_reason(client) == "runtime_namespace_ready"
        )

    assert runtime.namespaces == [("service_instance", "postgres")]


def test_api_lifespan_worker_defers_runtime_factories_until_reconciliation(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "nephos.db"
    catalog_root = tmp_path / "catalog"
    migrate_database(db_path=db_path)

    def fail_runtime(_settings):
        raise AssertionError("runtime factory should not run during startup")

    def fail_deployer(_settings, _repository):
        raise AssertionError("deployer factory should not run during startup")

    def fail_provisioner(_settings):
        raise AssertionError("provisioner factory should not run during startup")

    app = create_app(
        settings=Settings(
            db_path=db_path,
            catalog_roots=(catalog_root,),
            kubeconfig=None,
            kube_context=None,
        ),
        start_reconciler=True,
        runtime_factory=fail_runtime,
        deployer_factory=fail_deployer,
        provisioner_factory=fail_provisioner,
        reconciler_interval_seconds=0.01,
    )

    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200


def test_api_lifespan_worker_uses_deployer_factory_for_service_install(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "nephos.db"
    catalog_root = tmp_path / "catalog"
    runtime = FakeRuntime()
    deployer = FakeDeployer()
    write_service(catalog_root)
    migrate_database(db_path=db_path)
    app = create_app(
        settings=Settings(
            db_path=db_path,
            catalog_roots=(catalog_root,),
            kubeconfig=None,
            kube_context=None,
        ),
        start_reconciler=True,
        runtime_factory=lambda _settings: runtime,
        deployer_factory=lambda _settings, _repository: deployer,
        reconciler_interval_seconds=0.01,
    )

    with TestClient(app) as client:
        response = client.post(
            "/services",
            json={"catalogRef": {"kind": "Service", "name": "postgres"}},
        )
        assert response.status_code == 202

        _eventually(lambda: _service_status_reason(client) == "runtime_deployed")

    assert runtime.namespaces == [("service_instance", "postgres")]
    assert deployer.deployed == [("service_instance", "postgres")]


def test_service_runtime_status_includes_production_readiness_evidence(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "nephos.db"
    catalog_root = tmp_path / "catalog"
    runtime = FakeRuntime()
    deployer = FakeDeployer()
    write_service(catalog_root, name="zitadel", capability="oidc", protocol="oidc")
    migrate_database(db_path=db_path)
    app = create_app(
        settings=Settings(
            db_path=db_path,
            catalog_roots=(catalog_root,),
            kubeconfig=None,
            kube_context=None,
        ),
        start_reconciler=True,
        runtime_factory=lambda _settings: runtime,
        deployer_factory=lambda _settings, _repository: deployer,
        reconciler_interval_seconds=0.01,
    )

    with TestClient(app) as client:
        response = client.post(
            "/services",
            json={"catalogRef": {"kind": "Service", "name": "zitadel"}},
        )
        assert response.status_code == 202

        _eventually(
            lambda: _service_status_reason(client, "zitadel") == "runtime_deployed"
        )
        status = client.get("/services/zitadel").json()["status"]

    readiness = next(
        item for item in status["evidence"] if item["reason"] == "production_readiness"
    )
    assert readiness["source"] == "nephos-api"
    assert readiness["subject"] == "zitadel"
    checks = {check["name"]: check for check in readiness["data"]["checks"]}
    assert checks["runtime"]["status"] == "ready"
    assert checks["secrets"]["storage"] == "kubernetes-secrets"
    assert checks["backup"]["status"] == "deferred"
    assert checks["exposure"]["public"] is True
    assert checks["exposure"]["private"] is True
    assert checks["tls"]["termination"] == "external"
    assert checks["database-topology"]["topology"] == "embedded-postgres-sidecar"
    assert checks["provisioning"]["issuerHostPolicy"] == "same-host-private-path"



def test_api_lifespan_worker_reconciles_app_flow_until_provisioning_output_block(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "nephos.db"
    catalog_root = tmp_path / "catalog"
    runtime = FakeRuntime()
    write_service(catalog_root)
    write_app(catalog_root)
    migrate_database(db_path=db_path)
    app = create_app(
        settings=Settings(
            db_path=db_path,
            catalog_roots=(catalog_root,),
            kubeconfig=None,
            kube_context=None,
        ),
        start_reconciler=True,
        runtime_factory=lambda _settings: runtime,
        reconciler_interval_seconds=0.01,
    )

    with TestClient(app) as client:
        assert client.post(
            "/platform/config/domains",
            json={"name": "local", "domain": "nephos.local", "default": True},
        ).status_code == 202
        assert client.post(
            "/services",
            json={"catalogRef": {"kind": "Service", "name": "postgres"}},
        ).status_code == 202
        response = client.post(
            "/apps",
            json={"catalogRef": {"kind": "App", "name": "paperless"}},
        )
        assert response.status_code == 202
        binding_id = response.json()["resource"]["bindings"][0]["id"]

        _eventually(
            lambda: _service_status_reason(client) == "runtime_namespace_ready"
            and _app_status_reason(client) == "runtime_namespace_ready"
            and _binding_status_reason(client, binding_id)
            == "binding_output_unavailable"
        )

    assert ("service_instance", "postgres") in runtime.namespaces
    assert ("app_instance", "paperless") in runtime.namespaces
    assert runtime.binding_secrets == []


def test_api_lifespan_worker_uses_provisioner_factory_for_binding(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "nephos.db"
    catalog_root = tmp_path / "catalog"
    runtime = FakeRuntime()
    values = {
        "host": "svc-postgres-postgresql.svc-postgres.svc.cluster.local",
        "port": "5432",
        "database": "nephos_paperless_database",
        "username": "nephos_paperless_database",
        "password": "secret",
        "uri": (
            "postgresql://nephos_paperless_database:secret"
            "@svc-postgres-postgresql.svc-postgres.svc.cluster.local:5432/"
            "nephos_paperless_database"
        ),
    }
    provisioner = FakeProvisioner(values)
    write_service(catalog_root)
    write_app(catalog_root)
    migrate_database(db_path=db_path)
    app = create_app(
        settings=Settings(
            db_path=db_path,
            catalog_roots=(catalog_root,),
            kubeconfig=None,
            kube_context=None,
        ),
        start_reconciler=True,
        runtime_factory=lambda _settings: runtime,
        provisioner_factory=lambda _settings: provisioner,
        reconciler_interval_seconds=0.01,
    )

    with TestClient(app) as client:
        assert client.post(
            "/platform/config/domains",
            json={"name": "local", "domain": "nephos.local", "default": True},
        ).status_code == 202
        assert client.post(
            "/services",
            json={"catalogRef": {"kind": "Service", "name": "postgres"}},
        ).status_code == 202
        response = client.post(
            "/apps",
            json={"catalogRef": {"kind": "App", "name": "paperless"}},
        )
        assert response.status_code == 202
        binding_id = response.json()["resource"]["bindings"][0]["id"]

        _eventually(
            lambda: _binding_status_reason(client, binding_id)
            == "binding_secret_ready"
        )

    assert runtime.binding_secrets[0]["values"] == values
    assert len(provisioner.contexts) == 1


def test_api_lifespan_worker_uses_lazy_provisioner_for_app_destroy_deprovision(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "nephos.db"
    catalog_root = tmp_path / "catalog"
    runtime = FakeRuntime()
    values = {
        "host": "svc-postgres-postgresql.svc-postgres.svc.cluster.local",
        "port": "5432",
        "database": "nephos_paperless_database",
        "username": "nephos_paperless_database",
        "password": "secret",
        "uri": (
            "postgresql://nephos_paperless_database:secret"
            "@svc-postgres-postgresql.svc-postgres.svc.cluster.local:5432/"
            "nephos_paperless_database"
        ),
    }
    provisioner = FakeProvisioner(values)
    write_service(catalog_root)
    write_app(catalog_root)
    migrate_database(db_path=db_path)
    app = create_app(
        settings=Settings(
            db_path=db_path,
            catalog_roots=(catalog_root,),
            kubeconfig=None,
            kube_context=None,
        ),
        start_reconciler=True,
        runtime_factory=lambda _settings: runtime,
        provisioner_factory=lambda _settings: provisioner,
        reconciler_interval_seconds=0.01,
    )

    with TestClient(app) as client:
        assert client.post(
            "/platform/config/domains",
            json={"name": "local", "domain": "nephos.local", "default": True},
        ).status_code == 202
        assert client.post(
            "/services",
            json={"catalogRef": {"kind": "Service", "name": "postgres"}},
        ).status_code == 202
        response = client.post(
            "/apps",
            json={"catalogRef": {"kind": "App", "name": "paperless"}},
        )
        assert response.status_code == 202
        binding_id = response.json()["resource"]["bindings"][0]["id"]
        _eventually(
            lambda: _binding_status_reason(client, binding_id)
            == "binding_secret_ready"
        )

        destroy = client.post(
            "/apps/paperless/actions/destroy",
            json={"confirm": "destroy paperless"},
        )
        assert destroy.status_code == 202
        _eventually(lambda: client.get("/apps/paperless").status_code == 404)

    assert len(provisioner.deprovisioned_contexts) == 1


def test_api_lifespan_worker_uses_lazy_runtime_for_app_stop(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "nephos.db"
    catalog_root = tmp_path / "catalog"
    runtime = FakeRuntime()
    write_app(catalog_root)
    migrate_database(db_path=db_path)
    app = create_app(
        settings=Settings(
            db_path=db_path,
            catalog_roots=(catalog_root,),
            kubeconfig=None,
            kube_context=None,
        ),
        start_reconciler=True,
        runtime_factory=lambda _settings: runtime,
        reconciler_interval_seconds=0.01,
    )

    with TestClient(app) as client:
        with app.state.repository.transaction() as tx:
            app_instance = tx.create_app_instance(
                slug="paperless",
                catalog_name="paperless",
                catalog_source_id="default",
                catalog_source_path=str(
                    catalog_root / "apps" / "paperless" / "app.yaml"
                ),
                manifest_digest="sha256:paperless",
            )
        stop = client.post("/apps/paperless/actions/stop", json={})
        assert stop.status_code == 202
        _eventually(lambda: _app_status_reason(client) == "runtime_stopped")

    assert app_instance.id
    assert runtime.scaled_workloads == [("app_instance", "paperless", 0)]


def _eventually(check: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.01)
    assert check()


def _service_status_reason(client: TestClient, slug: str = "postgres") -> str | None:
    status = client.get(f"/services/{slug}").json()["status"]
    return status["reason"] if status else None


def _app_status_reason(client: TestClient) -> str | None:
    status = client.get("/apps/paperless").json()["status"]
    return status["reason"] if status else None


def _binding_status_reason(client: TestClient, binding_id: str) -> str | None:
    status = client.get(f"/bindings/{binding_id}").json()["status"]
    return status["reason"] if status else None
