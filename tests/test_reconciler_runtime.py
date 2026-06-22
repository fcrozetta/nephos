import json
import sqlite3
from pathlib import Path

from catalog_fixtures import write_app

from nephos_api.db import migrate_database
from nephos_api.kubernetes_runtime import KubernetesRuntimeSafetyError
from nephos_api.provisioning import BindingProvisioningContext
from nephos_api.reconciler import Reconciler
from nephos_api.repository import DesiredStateRepository
from nephos_api.runtime_errors import RuntimeBlockedError


class FakeRuntime:
    def __init__(self) -> None:
        self.namespaces: list[tuple[str, str]] = []
        self.deleted_namespaces: list[tuple[str, str]] = []
        self.binding_secrets: list[dict[str, object]] = []
        self.deleted_binding_secrets: list[dict[str, object]] = []
        self.scaled_workloads: list[tuple[str, str, int]] = []
        self.app_ingresses: list[dict[str, object]] = []
        self.deleted_app_ingresses: list[dict[str, object]] = []

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
        record = {
            "app_slug": app_slug,
            "service_slug": service_slug,
            "alias": alias,
            "capability": capability,
            "values": values,
        }
        if protocol is not None:
            record["protocol"] = protocol
        self.binding_secrets.append(record)

    def delete_binding_secret_if_owned(
        self,
        *,
        app_slug: str,
        service_slug: str,
        alias: str,
        capability: str,
        protocol: str | None = None,
    ) -> bool:
        record = {
            "app_slug": app_slug,
            "service_slug": service_slug,
            "alias": alias,
            "capability": capability,
        }
        if protocol is not None:
            record["protocol"] = protocol
        self.deleted_binding_secrets.append(record)
        return True

    def scale_workloads(
        self,
        resource_type: str,
        slug: str,
        replicas: int,
    ) -> None:
        self.scaled_workloads.append((resource_type, slug, replicas))

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
        self.deleted_app_ingresses.append({"app_slug": app_slug, "routes": routes})


class FailingRuntime:
    def ensure_namespace(self, resource_type: str, slug: str) -> None:
        raise RuntimeError(f"boom for {resource_type} {slug}")

    def delete_namespace_if_owned(self, resource_type: str, slug: str) -> bool:
        raise RuntimeError(f"boom for {resource_type} {slug}")

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
        raise RuntimeError(f"boom for binding {alias}")

    def delete_binding_secret_if_owned(
        self,
        *,
        app_slug: str,
        service_slug: str,
        alias: str,
        capability: str,
        protocol: str | None = None,
    ) -> bool:
        raise RuntimeError(f"boom for binding {alias}")

    def scale_workloads(
        self,
        resource_type: str,
        slug: str,
        replicas: int,
    ) -> None:
        raise RuntimeError(f"boom for {resource_type} {slug}")

    def ensure_app_ingresses(
        self,
        *,
        app_slug: str,
        routes: list[dict[str, object]],
        domains: list[dict[str, object]],
    ) -> None:
        raise RuntimeError(f"boom for app ingress {app_slug}")

    def delete_app_ingresses(
        self,
        *,
        app_slug: str,
        routes: list[dict[str, object]],
    ) -> None:
        raise RuntimeError(f"boom for app ingress {app_slug}")


class SafetyBlockedRuntime(FakeRuntime):
    def ensure_namespace(self, resource_type: str, slug: str) -> None:
        raise KubernetesRuntimeSafetyError(f"refusing unsafe namespace {slug}")


class FakeProvisioner:
    def __init__(self, values: dict[str, str] | None) -> None:
        self.values = values
        self.contexts: list[BindingProvisioningContext] = []
        self.deprovisioned_contexts: list[BindingProvisioningContext] = []

    def provision_binding(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str] | None:
        self.contexts.append(context)
        return self.values

    def deprovision_binding(self, context: BindingProvisioningContext) -> None:
        self.deprovisioned_contexts.append(context)


class FakeDeployer:
    def __init__(self) -> None:
        self.deployed: list[tuple[str, str]] = []
        self.uninstalled: list[tuple[str, str]] = []

    def deploy(self, *, target_type: str, slug: str) -> None:
        self.deployed.append((target_type, slug))

    def uninstall(self, *, target_type: str, slug: str) -> None:
        self.uninstalled.append((target_type, slug))


class RecordingProvisioner(FakeProvisioner):
    def __init__(self, events: list[str]) -> None:
        super().__init__(values=None)
        self.events = events

    def deprovision_binding(self, context: BindingProvisioningContext) -> None:
        self.events.append(f"deprovision:{context.alias}")
        super().deprovision_binding(context)


class FailingDeprovisionProvisioner(RecordingProvisioner):
    def deprovision_binding(self, context: BindingProvisioningContext) -> None:
        super().deprovision_binding(context)
        raise RuntimeError("service runtime is already gone")


class RecordingDeployer(FakeDeployer):
    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self.events = events

    def uninstall(self, *, target_type: str, slug: str) -> None:
        self.events.append(f"uninstall:{target_type}:{slug}")
        super().uninstall(target_type=target_type, slug=slug)


class RecordingRuntime(FakeRuntime):
    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self.events = events

    def delete_binding_secret_if_owned(
        self,
        *,
        app_slug: str,
        service_slug: str,
        alias: str,
        capability: str,
        protocol: str | None = None,
    ) -> bool:
        self.events.append(f"delete-binding-secret:{alias}")
        return super().delete_binding_secret_if_owned(
            app_slug=app_slug,
            service_slug=service_slug,
            alias=alias,
            capability=capability,
            protocol=protocol,
        )

    def delete_namespace_if_owned(self, resource_type: str, slug: str) -> bool:
        self.events.append(f"delete-namespace:{resource_type}:{slug}")
        return super().delete_namespace_if_owned(resource_type, slug)


class BlockingDeployer:
    def deploy(self, *, target_type: str, slug: str) -> None:
        raise RuntimeBlockedError(
            reason="runtime_mapping_source_missing",
            message="Binding database.uri is not available.",
        )

    def uninstall(self, *, target_type: str, slug: str) -> None:
        raise AssertionError("unexpected uninstall")


def _repo(tmp_path: Path) -> DesiredStateRepository:
    db_path = tmp_path / "nephos.db"
    migrate_database(db_path=db_path)
    return DesiredStateRepository(db_path)


def test_service_install_request_creates_service_namespace_and_succeeds(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    runtime = FakeRuntime()
    with repo.transaction() as tx:
        service = tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path="catalog/services/postgres/service.yaml",
            manifest_digest="sha256:postgres",
        )
        request = tx.create_reconciliation_request(
            target_type="service_instance",
            target_id=service.id,
            target_generation=service.generation,
            action="install",
            target_snapshot={"slug": service.slug},
        )

    assert Reconciler(repo, runtime=runtime).run_once() == 1

    assert runtime.namespaces == [("service_instance", "postgres")]
    _assert_reconciled_namespace_status(
        repo,
        request_id=request.id,
        resource_type="service_instance",
        resource_id=service.id,
    )


def test_app_install_request_creates_app_namespace_and_succeeds(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    runtime = FakeRuntime()
    with repo.transaction() as tx:
        app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(_write_routeless_app(tmp_path)),
            manifest_digest="sha256:paperless",
        )
        request = tx.create_reconciliation_request(
            target_type="app_instance",
            target_id=app.id,
            target_generation=app.generation,
            action="install",
            target_snapshot={"slug": app.slug},
        )

    assert Reconciler(repo, runtime=runtime).run_once() == 1

    assert runtime.namespaces == [("app_instance", "paperless")]
    _assert_reconciled_namespace_status(
        repo,
        request_id=request.id,
        resource_type="app_instance",
        resource_id=app.id,
    )


def test_app_install_request_reconciles_declared_routes_to_ingress(
    tmp_path: Path,
) -> None:
    catalog_root = tmp_path / "catalog"
    manifest_path = write_app(catalog_root)
    repo = _repo(tmp_path)
    runtime = FakeRuntime()
    with repo.transaction() as tx:
        domain = tx.create_platform_domain(
            name="local",
            domain="nephos.local",
            is_default=True,
        )
        app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(manifest_path),
            manifest_digest="sha256:paperless",
        )
        request = tx.create_reconciliation_request(
            target_type="app_instance",
            target_id=app.id,
            target_generation=app.generation,
            action="install",
            target_snapshot={"slug": app.slug},
        )

    assert Reconciler(repo, runtime=runtime).run_once() == 1

    assert runtime.app_ingresses == [
        {
            "app_slug": "paperless",
            "routes": [
                {"name": "web", "visibility": "local", "target": {"port": "http"}}
            ],
            "domains": [
                {
                    "name": "local",
                    "domain": "nephos.local",
                    "default": True,
                    "id": domain.id,
                }
            ],
        }
    ]
    _assert_reconciled_namespace_status(
        repo,
        request_id=request.id,
        resource_type="app_instance",
        resource_id=app.id,
    )


def test_app_install_request_blocks_route_reconciliation_without_root_domain(
    tmp_path: Path,
) -> None:
    catalog_root = tmp_path / "catalog"
    manifest_path = write_app(catalog_root)
    repo = _repo(tmp_path)
    runtime = FakeRuntime()
    with repo.transaction() as tx:
        app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(manifest_path),
            manifest_digest="sha256:paperless",
        )
        request = tx.create_reconciliation_request(
            target_type="app_instance",
            target_id=app.id,
            target_generation=app.generation,
            action="install",
            target_snapshot={"slug": app.slug},
        )

    assert Reconciler(repo, runtime=runtime).run_once() == 1

    assert runtime.app_ingresses == []
    with sqlite3.connect(repo.db_path) as connection:
        request_row = connection.execute(
            "SELECT state, error FROM reconciliation_requests WHERE id = ?",
            (request.id,),
        ).fetchone()
        status_row = connection.execute(
            """
            SELECT level, reconciliation, reason, message, observed_generation
            FROM status_snapshots
            WHERE resource_type = ? AND resource_id = ?
            """,
            ("app_instance", app.id),
        ).fetchone()
    assert request_row == ("blocked", "App routes require a platform root domain.")
    assert status_row == (
        "blocked",
        "blocked",
        "platform_root_domain_missing",
        "App routes require a platform root domain.",
        1,
    )


def test_platform_domain_reconcile_enqueues_routed_app_reconcile_requests(
    tmp_path: Path,
) -> None:
    catalog_root = tmp_path / "catalog"
    routed_manifest = write_app(catalog_root)
    repo = _repo(tmp_path)
    with repo.transaction() as tx:
        domain = tx.create_platform_domain(
            name="local",
            domain="nephos.local",
            is_default=True,
        )
        routed_app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(routed_manifest),
            manifest_digest="sha256:paperless",
        )
        tx.create_app_instance(
            slug="worker",
            catalog_name="paperless-routeless",
            catalog_source_id="default",
            catalog_source_path=str(_write_routeless_app(tmp_path)),
            manifest_digest="sha256:worker",
        )
        request = tx.create_reconciliation_request(
            target_type="platform_domain",
            target_id=domain.id,
            target_generation=domain.generation,
            action="set-default",
            target_snapshot={"name": domain.name, "domain": domain.domain},
        )

    assert Reconciler(repo).run_once() == 1

    with sqlite3.connect(repo.db_path) as connection:
        app_reconcile_rows = connection.execute(
            """
            SELECT target_type, target_id, target_generation, action, state,
                target_snapshot_json
            FROM reconciliation_requests
            WHERE target_type = 'app_instance'
            """
        ).fetchall()

    assert len(app_reconcile_rows) == 1
    app_reconcile = app_reconcile_rows[0]
    assert app_reconcile[:5] == (
        "app_instance",
        routed_app.id,
        routed_app.generation,
        "reconcile",
        "pending",
    )
    assert json.loads(app_reconcile[5]) == {"slug": "paperless"}
    _assert_platform_domain_reconciled_status(repo, request.id, domain.id)


def test_platform_domain_reconcile_skips_removed_apps(
    tmp_path: Path,
) -> None:
    catalog_root = tmp_path / "catalog"
    routed_manifest = write_app(catalog_root)
    repo = _repo(tmp_path)
    with repo.transaction() as tx:
        domain = tx.create_platform_domain(
            name="local",
            domain="nephos.local",
            is_default=True,
        )
        tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(routed_manifest),
            manifest_digest="sha256:paperless",
            lifecycle="removed",
        )
        request = tx.create_reconciliation_request(
            target_type="platform_domain",
            target_id=domain.id,
            target_generation=domain.generation,
            action="remove",
            target_snapshot={"name": domain.name, "domain": domain.domain},
        )

    assert Reconciler(repo).run_once() == 1

    with sqlite3.connect(repo.db_path) as connection:
        app_reconcile_count = connection.execute(
            """
            SELECT count(*) AS count
            FROM reconciliation_requests
            WHERE target_type = 'app_instance'
            """
        ).fetchone()

    assert app_reconcile_count[0] == 0
    _assert_platform_domain_reconciled_status(repo, request.id, domain.id)


def test_service_install_request_deploys_helm_runtime_when_deployer_is_present(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    runtime = FakeRuntime()
    deployer = FakeDeployer()
    with repo.transaction() as tx:
        service = tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path="catalog/services/postgres/service.yaml",
            manifest_digest="sha256:postgres",
        )
        request = tx.create_reconciliation_request(
            target_type="service_instance",
            target_id=service.id,
            target_generation=service.generation,
            action="install",
            target_snapshot={"slug": service.slug},
        )

    assert Reconciler(repo, runtime=runtime, deployer=deployer).run_once() == 1

    assert runtime.namespaces == [("service_instance", "postgres")]
    assert deployer.deployed == [("service_instance", "postgres")]
    _assert_reconciled_deployment_status(repo, request.id, service.id)


def test_service_deployment_enqueues_dependent_binding_reconciles(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    runtime = FakeRuntime()
    deployer = FakeDeployer()
    with repo.transaction() as tx:
        service = tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path="catalog/services/postgres/service.yaml",
            manifest_digest="sha256:postgres",
        )
        app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(_write_routeless_app(tmp_path)),
            manifest_digest="sha256:paperless",
        )
        binding = tx.create_binding(
            app_instance_id=app.id,
            service_instance_id=service.id,
            alias="database",
            capability="postgres",
            output_summary={"redacted": True},
        )
        request = tx.create_reconciliation_request(
            target_type="service_instance",
            target_id=service.id,
            target_generation=service.generation,
            action="install",
            target_snapshot={"slug": service.slug},
        )

    assert Reconciler(repo, runtime=runtime, deployer=deployer).run_once() == 1

    with sqlite3.connect(repo.db_path) as connection:
        binding_requests = connection.execute(
            """
            SELECT target_type, target_id, target_generation, action, state
            FROM reconciliation_requests
            WHERE target_type = 'binding'
            """
        ).fetchall()

    assert binding_requests == [
        ("binding", binding.id, binding.generation, "reconcile", "pending")
    ]
    _assert_reconciled_deployment_status(repo, request.id, service.id)


def test_service_deployment_does_not_duplicate_pending_binding_reconciles(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    runtime = FakeRuntime()
    deployer = FakeDeployer()
    with repo.transaction() as tx:
        service = tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path="catalog/services/postgres/service.yaml",
            manifest_digest="sha256:postgres",
        )
        app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(_write_routeless_app(tmp_path)),
            manifest_digest="sha256:paperless",
        )
        binding = tx.create_binding(
            app_instance_id=app.id,
            service_instance_id=service.id,
            alias="database",
            capability="postgres",
            output_summary={"redacted": True},
        )
        binding_request = tx.create_reconciliation_request(
            target_type="binding",
            target_id=binding.id,
            target_generation=binding.generation,
            action="reconcile",
            target_snapshot={"id": binding.id, "alias": binding.alias},
        )
        request = tx.create_reconciliation_request(
            target_type="service_instance",
            target_id=service.id,
            target_generation=service.generation,
            action="install",
            target_snapshot={"slug": service.slug},
        )
    with sqlite3.connect(repo.db_path) as connection:
        connection.execute(
            """
            UPDATE reconciliation_requests
            SET created_at = ?
            WHERE id = ?
            """,
            ("2026-05-23T00:00:00Z", request.id),
        )
        connection.execute(
            """
            UPDATE reconciliation_requests
            SET created_at = ?
            WHERE id = ?
            """,
            ("2026-05-23T00:00:01Z", binding_request.id),
        )

    assert Reconciler(repo, runtime=runtime, deployer=deployer).run_once() == 1

    with sqlite3.connect(repo.db_path) as connection:
        binding_request_count = connection.execute(
            """
            SELECT count(*)
            FROM reconciliation_requests
            WHERE target_type = 'binding'
                AND target_id = ?
                AND action = 'reconcile'
                AND state = 'pending'
            """,
            (binding.id,),
        ).fetchone()[0]

    assert binding_request_count == 1
    _assert_reconciled_deployment_status(repo, request.id, service.id)


def test_service_deployment_does_not_requeue_bindings_for_pending_destroy_apps(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    runtime = FakeRuntime()
    deployer = FakeDeployer()
    with repo.transaction() as tx:
        service = tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path="catalog/services/postgres/service.yaml",
            manifest_digest="sha256:postgres",
        )
        app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(_write_routeless_app(tmp_path)),
            manifest_digest="sha256:paperless",
        )
        binding = tx.create_binding(
            app_instance_id=app.id,
            service_instance_id=service.id,
            alias="database",
            capability="postgres",
            output_summary={"redacted": True},
        )
        tx.mark_app_delete_requested(slug=app.slug)
        request = tx.create_reconciliation_request(
            target_type="service_instance",
            target_id=service.id,
            target_generation=service.generation,
            action="install",
            target_snapshot={"slug": service.slug},
        )

    assert Reconciler(repo, runtime=runtime, deployer=deployer).run_once() == 1

    with sqlite3.connect(repo.db_path) as connection:
        binding_request_count = connection.execute(
            """
            SELECT count(*)
            FROM reconciliation_requests
            WHERE target_type = 'binding'
                AND target_id = ?
                AND action = 'reconcile'
            """,
            (binding.id,),
        ).fetchone()[0]

    assert binding_request_count == 0
    _assert_reconciled_deployment_status(repo, request.id, service.id)


def test_app_install_request_deploys_helm_runtime_when_deployer_is_present(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    runtime = FakeRuntime()
    deployer = FakeDeployer()
    with repo.transaction() as tx:
        app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(_write_routeless_app(tmp_path)),
            manifest_digest="sha256:paperless",
        )
        request = tx.create_reconciliation_request(
            target_type="app_instance",
            target_id=app.id,
            target_generation=app.generation,
            action="install",
            target_snapshot={"slug": app.slug},
        )

    assert Reconciler(repo, runtime=runtime, deployer=deployer).run_once() == 1

    assert runtime.namespaces == [("app_instance", "paperless")]
    assert deployer.deployed == [("app_instance", "paperless")]
    _assert_reconciled_deployment_status(repo, request.id, app.id)


def test_app_stop_request_scales_runtime_workloads_to_zero(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    runtime = FakeRuntime()
    with repo.transaction() as tx:
        app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(_write_routeless_app(tmp_path)),
            manifest_digest="sha256:paperless",
        )
        request = tx.create_reconciliation_request(
            target_type="app_instance",
            target_id=app.id,
            target_generation=app.generation,
            action="stop",
            target_snapshot={"slug": app.slug},
        )

    assert Reconciler(repo, runtime=runtime).run_once() == 1

    assert runtime.scaled_workloads == [("app_instance", "paperless", 0)]
    _assert_runtime_stopped_status(repo, request.id, app.id)


def test_app_status_snapshot_records_desired_lifecycle(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    runtime = FakeRuntime()
    with repo.transaction() as tx:
        app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(_write_routeless_app(tmp_path)),
            manifest_digest="sha256:paperless",
            lifecycle="stopped",
        )
        tx.create_reconciliation_request(
            target_type="app_instance",
            target_id=app.id,
            target_generation=app.generation,
            action="stop",
            target_snapshot={"slug": app.slug},
        )

    assert Reconciler(repo, runtime=runtime).run_once() == 1

    with sqlite3.connect(repo.db_path) as connection:
        status_lifecycle = connection.execute(
            """
            SELECT lifecycle
            FROM status_snapshots
            WHERE resource_type = 'app_instance' AND resource_id = ?
            """,
            (app.id,),
        ).fetchone()[0]
    assert status_lifecycle == "stopped"


def test_stopped_app_reconcile_keeps_ingress_current_and_workloads_stopped(
    tmp_path: Path,
) -> None:
    catalog_root = tmp_path / "catalog"
    manifest_path = write_app(catalog_root)
    repo = _repo(tmp_path)
    runtime = FakeRuntime()
    deployer = FakeDeployer()
    with repo.transaction() as tx:
        domain = tx.create_platform_domain(
            name="local",
            domain="nephos.local",
            is_default=True,
        )
        app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(manifest_path),
            manifest_digest="sha256:paperless",
            lifecycle="stopped",
        )
        request = tx.create_reconciliation_request(
            target_type="app_instance",
            target_id=app.id,
            target_generation=app.generation,
            action="reconcile",
            target_snapshot={"slug": app.slug},
        )

    assert Reconciler(repo, runtime=runtime, deployer=deployer).run_once() == 1

    assert deployer.deployed == []
    assert runtime.app_ingresses == [
        {
            "app_slug": "paperless",
            "routes": [
                {"name": "web", "visibility": "local", "target": {"port": "http"}}
            ],
            "domains": [
                {
                    "name": "local",
                    "domain": "nephos.local",
                    "default": True,
                    "id": domain.id,
                }
            ],
        }
    ]
    assert runtime.scaled_workloads == [("app_instance", "paperless", 0)]
    _assert_runtime_stopped_status(repo, request.id, app.id)


def test_service_remove_uninstalls_runtime_without_deleting_desired_state(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    runtime = FakeRuntime()
    deployer = FakeDeployer()
    with repo.transaction() as tx:
        service = tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path="catalog/services/postgres/service.yaml",
            manifest_digest="sha256:postgres",
            lifecycle="removed",
        )
        request = tx.create_reconciliation_request(
            target_type="service_instance",
            target_id=service.id,
            target_generation=service.generation,
            action="remove",
            target_snapshot={"slug": service.slug},
        )

    assert Reconciler(repo, runtime=runtime, deployer=deployer).run_once() == 1

    assert deployer.uninstalled == [("service_instance", "postgres")]
    assert runtime.deleted_namespaces == []
    assert repo.get_service_row("postgres") is not None
    _assert_runtime_removed_status(repo, request.id, service.id)


def test_app_remove_deletes_ingress_and_uninstalls_runtime(
    tmp_path: Path,
) -> None:
    catalog_root = tmp_path / "catalog"
    manifest_path = write_app(catalog_root)
    repo = _repo(tmp_path)
    runtime = FakeRuntime()
    deployer = FakeDeployer()
    with repo.transaction() as tx:
        app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(manifest_path),
            manifest_digest="sha256:paperless",
            lifecycle="removed",
        )
        request = tx.create_reconciliation_request(
            target_type="app_instance",
            target_id=app.id,
            target_generation=app.generation,
            action="remove",
            target_snapshot={"slug": app.slug},
        )

    assert Reconciler(repo, runtime=runtime, deployer=deployer).run_once() == 1

    assert runtime.deleted_app_ingresses == [
        {
            "app_slug": "paperless",
            "routes": [
                {"name": "web", "visibility": "local", "target": {"port": "http"}}
            ],
        }
    ]
    assert deployer.uninstalled == [("app_instance", "paperless")]
    assert repo.get_app_row("paperless") is not None
    _assert_runtime_removed_status(repo, request.id, app.id)


def test_removed_app_reconcile_removes_runtime_without_redeploying(
    tmp_path: Path,
) -> None:
    catalog_root = tmp_path / "catalog"
    manifest_path = write_app(catalog_root)
    repo = _repo(tmp_path)
    runtime = FakeRuntime()
    deployer = FakeDeployer()
    with repo.transaction() as tx:
        tx.create_platform_domain(
            name="local",
            domain="nephos.local",
            is_default=True,
        )
        app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(manifest_path),
            manifest_digest="sha256:paperless",
            lifecycle="removed",
        )
        request = tx.create_reconciliation_request(
            target_type="app_instance",
            target_id=app.id,
            target_generation=app.generation,
            action="reconcile",
            target_snapshot={"slug": app.slug},
        )

    assert Reconciler(repo, runtime=runtime, deployer=deployer).run_once() == 1

    assert runtime.namespaces == []
    assert runtime.app_ingresses == []
    assert deployer.deployed == []
    assert runtime.deleted_app_ingresses == [
        {
            "app_slug": "paperless",
            "routes": [
                {"name": "web", "visibility": "local", "target": {"port": "http"}}
            ],
        }
    ]
    assert deployer.uninstalled == [("app_instance", "paperless")]
    assert repo.get_app_row("paperless") is not None
    _assert_runtime_removed_status(repo, request.id, app.id)


def test_service_destroy_deletes_namespace_and_desired_state_row(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    runtime = FakeRuntime()
    with repo.transaction() as tx:
        service = tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path="catalog/services/postgres/service.yaml",
            manifest_digest="sha256:postgres",
        )
        request = tx.create_reconciliation_request(
            target_type="service_instance",
            target_id=service.id,
            target_generation=service.generation,
            action="destroy",
            target_snapshot={"slug": service.slug},
        )

    assert Reconciler(repo, runtime=runtime).run_once() == 1

    assert runtime.deleted_namespaces == [("service_instance", "postgres")]
    assert repo.get_service_row("postgres") is None
    _assert_request_succeeded(repo, request.id)


def test_forced_service_destroy_cleans_dependent_bindings_before_row_delete(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    events: list[str] = []
    runtime = RecordingRuntime(events)
    provisioner = RecordingProvisioner(events)
    deployer = RecordingDeployer(events)
    with repo.transaction() as tx:
        service = tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path="catalog/services/postgres/service.yaml",
            manifest_digest="sha256:postgres",
        )
        app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(_write_routeless_app(tmp_path)),
            manifest_digest="sha256:paperless",
        )
        binding = tx.create_binding(
            app_instance_id=app.id,
            service_instance_id=service.id,
            alias="database",
            capability="postgres",
            output_summary={"target": "app-secret", "redacted": True},
        )
        request = tx.create_reconciliation_request(
            target_type="service_instance",
            target_id=service.id,
            target_generation=service.generation,
            action="destroy",
            target_snapshot={"slug": service.slug},
        )

    assert (
        Reconciler(
            repo,
            runtime=runtime,
            provisioner=provisioner,
            deployer=deployer,
        ).run_once()
        == 1
    )

    assert events == [
        "deprovision:database",
        "delete-binding-secret:database",
        "uninstall:service_instance:postgres",
        "delete-namespace:service_instance:postgres",
    ]
    assert provisioner.deprovisioned_contexts == [
        BindingProvisioningContext(
            binding_id=binding.id,
            app_slug="paperless",
            service_slug="postgres",
            alias="database",
            capability="postgres",
        )
    ]
    assert runtime.deleted_binding_secrets == [
        {
            "app_slug": "paperless",
            "service_slug": "postgres",
            "alias": "database",
            "capability": "postgres",
        }
    ]
    assert repo.get_service_row("postgres") is None
    assert repo.get_app_row("paperless") is not None
    assert repo.list_bindings_for_app(app.id) == []
    with sqlite3.connect(repo.db_path) as connection:
        app_reconcile = connection.execute(
            """
            SELECT target_type, target_id, target_generation, action, state,
                target_snapshot_json
            FROM reconciliation_requests
            WHERE target_type = 'app_instance'
            """
        ).fetchone()
        status = connection.execute(
            """
            SELECT level, reconciliation, reason, message, observed_generation
            FROM status_snapshots
            WHERE resource_type = 'app_instance' AND resource_id = ?
            """,
            (app.id,),
        ).fetchone()

    assert app_reconcile is not None
    assert app_reconcile[:5] == (
        "app_instance",
        app.id,
        app.generation,
        "reconcile",
        "pending",
    )
    assert json.loads(app_reconcile[5]) == {"slug": "paperless"}
    assert status == (
        "blocked",
        "blocked",
        "binding_provider_destroyed",
        (
            "A bound Service was destroyed; App reconciliation is queued to remove "
            "stale binding data."
        ),
        app.generation,
    )
    _assert_request_succeeded(repo, request.id)


def test_forced_service_destroy_continues_when_deprovision_runtime_is_gone(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    events: list[str] = []
    runtime = RecordingRuntime(events)
    provisioner = FailingDeprovisionProvisioner(events)
    deployer = RecordingDeployer(events)
    with repo.transaction() as tx:
        service = tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path="catalog/services/postgres/service.yaml",
            manifest_digest="sha256:postgres",
        )
        app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(_write_routeless_app(tmp_path)),
            manifest_digest="sha256:paperless",
        )
        binding = tx.create_binding(
            app_instance_id=app.id,
            service_instance_id=service.id,
            alias="database",
            capability="postgres",
            output_summary={"target": "app-secret", "redacted": True},
        )
        request = tx.create_reconciliation_request(
            target_type="service_instance",
            target_id=service.id,
            target_generation=service.generation,
            action="destroy",
            target_snapshot={"slug": service.slug},
        )

    assert (
        Reconciler(
            repo,
            runtime=runtime,
            provisioner=provisioner,
            deployer=deployer,
        ).run_once()
        == 1
    )

    assert events == [
        "deprovision:database",
        "delete-binding-secret:database",
        "uninstall:service_instance:postgres",
        "delete-namespace:service_instance:postgres",
    ]
    assert provisioner.deprovisioned_contexts == [
        BindingProvisioningContext(
            binding_id=binding.id,
            app_slug="paperless",
            service_slug="postgres",
            alias="database",
            capability="postgres",
        )
    ]
    assert runtime.deleted_binding_secrets == [
        {
            "app_slug": "paperless",
            "service_slug": "postgres",
            "alias": "database",
            "capability": "postgres",
        }
    ]
    assert repo.get_service_row("postgres") is None
    assert repo.get_app_row("paperless") is not None
    assert repo.list_bindings_for_app(app.id) == []
    _assert_request_succeeded(repo, request.id)


def test_app_destroy_deletes_namespace_and_desired_state_row(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    runtime = FakeRuntime()
    with repo.transaction() as tx:
        app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(_write_routeless_app(tmp_path)),
            manifest_digest="sha256:paperless",
        )
        request = tx.create_reconciliation_request(
            target_type="app_instance",
            target_id=app.id,
            target_generation=app.generation,
            action="destroy",
            target_snapshot={"slug": app.slug},
        )

    assert Reconciler(repo, runtime=runtime).run_once() == 1

    assert runtime.deleted_namespaces == [("app_instance", "paperless")]
    assert repo.get_app_row("paperless") is None
    _assert_request_succeeded(repo, request.id)


def test_app_destroy_deprovisions_bindings_before_deleting_desired_state(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    runtime = FakeRuntime()
    provisioner = FakeProvisioner(values=None)
    with repo.transaction() as tx:
        service = tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path="catalog/services/postgres/service.yaml",
            manifest_digest="sha256:postgres",
        )
        app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(_write_routeless_app(tmp_path)),
            manifest_digest="sha256:paperless",
        )
        tx.create_binding(
            app_instance_id=app.id,
            service_instance_id=service.id,
            alias="database",
            capability="postgres",
            output_summary={"target": "app-secret", "redacted": True},
        )
        tx.create_reconciliation_request(
            target_type="app_instance",
            target_id=app.id,
            target_generation=app.generation,
            action="destroy",
            target_snapshot={"slug": app.slug},
        )

    assert Reconciler(repo, runtime=runtime, provisioner=provisioner).run_once() == 1

    assert provisioner.deprovisioned_contexts == [
        BindingProvisioningContext(
            binding_id=provisioner.deprovisioned_contexts[0].binding_id,
            app_slug="paperless",
            service_slug="postgres",
            alias="database",
            capability="postgres",
        )
    ]
    assert repo.get_app_row("paperless") is None


def test_app_destroy_uninstalls_runtime_before_deprovisioning_bindings(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    runtime = FakeRuntime()
    events: list[str] = []
    provisioner = RecordingProvisioner(events)
    deployer = RecordingDeployer(events)
    with repo.transaction() as tx:
        service = tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path="catalog/services/postgres/service.yaml",
            manifest_digest="sha256:postgres",
        )
        app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(_write_routeless_app(tmp_path)),
            manifest_digest="sha256:paperless",
        )
        tx.create_binding(
            app_instance_id=app.id,
            service_instance_id=service.id,
            alias="database",
            capability="postgres",
            output_summary={"target": "app-secret", "redacted": True},
        )
        tx.create_reconciliation_request(
            target_type="app_instance",
            target_id=app.id,
            target_generation=app.generation,
            action="destroy",
            target_snapshot={"slug": app.slug},
        )

    assert (
        Reconciler(
            repo,
            runtime=runtime,
            provisioner=provisioner,
            deployer=deployer,
        ).run_once()
        == 1
    )

    assert events == [
        "uninstall:app_instance:paperless",
        "deprovision:database",
    ]


def test_destroy_uninstalls_helm_runtime_before_namespace_teardown(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    runtime = FakeRuntime()
    deployer = FakeDeployer()
    with repo.transaction() as tx:
        service = tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path="catalog/services/postgres/service.yaml",
            manifest_digest="sha256:postgres",
        )
        request = tx.create_reconciliation_request(
            target_type="service_instance",
            target_id=service.id,
            target_generation=service.generation,
            action="destroy",
            target_snapshot={"slug": service.slug},
        )

    assert Reconciler(repo, runtime=runtime, deployer=deployer).run_once() == 1

    assert deployer.uninstalled == [("service_instance", "postgres")]
    assert runtime.deleted_namespaces == [("service_instance", "postgres")]
    assert repo.get_service_row("postgres") is None
    _assert_request_succeeded(repo, request.id)


def test_runtime_failure_marks_request_failed_and_writes_status(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    with repo.transaction() as tx:
        service = tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path="catalog/services/postgres/service.yaml",
            manifest_digest="sha256:postgres",
        )
        request = tx.create_reconciliation_request(
            target_type="service_instance",
            target_id=service.id,
            target_generation=service.generation,
            action="install",
            target_snapshot={"slug": service.slug},
        )

    assert Reconciler(repo, runtime=FailingRuntime()).run_once() == 1

    with sqlite3.connect(repo.db_path) as connection:
        request_row = connection.execute(
            "SELECT state, error FROM reconciliation_requests WHERE id = ?",
            (request.id,),
        ).fetchone()
        status_row = connection.execute(
            """
            SELECT level, reconciliation, reason, message, observed_generation
            FROM status_snapshots
            WHERE resource_type = ? AND resource_id = ?
            """,
            ("service_instance", service.id),
        ).fetchone()

    assert request_row == ("failed", "boom for service_instance postgres")
    assert status_row == (
        "degraded",
        "failed",
        "runtime_error",
        "boom for service_instance postgres",
        1,
    )


def test_runtime_safety_refusal_marks_request_blocked_and_writes_status(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    with repo.transaction() as tx:
        service = tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path="catalog/services/postgres/service.yaml",
            manifest_digest="sha256:postgres",
        )
        request = tx.create_reconciliation_request(
            target_type="service_instance",
            target_id=service.id,
            target_generation=service.generation,
            action="install",
            target_snapshot={"slug": service.slug},
        )

    assert Reconciler(repo, runtime=SafetyBlockedRuntime()).run_once() == 1

    with sqlite3.connect(repo.db_path) as connection:
        request_row = connection.execute(
            "SELECT state, error FROM reconciliation_requests WHERE id = ?",
            (request.id,),
        ).fetchone()
        status_row = connection.execute(
            """
            SELECT level, reconciliation, reason, message, observed_generation
            FROM status_snapshots
            WHERE resource_type = ? AND resource_id = ?
            """,
            ("service_instance", service.id),
        ).fetchone()

    assert request_row == ("blocked", "refusing unsafe namespace postgres")
    assert status_row == (
        "blocked",
        "blocked",
        "runtime_safety_blocked",
        "refusing unsafe namespace postgres",
        1,
    )


def test_runtime_blocker_marks_request_blocked_and_writes_status(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    runtime = FakeRuntime()
    with repo.transaction() as tx:
        app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(_write_routeless_app(tmp_path)),
            manifest_digest="sha256:paperless",
        )
        request = tx.create_reconciliation_request(
            target_type="app_instance",
            target_id=app.id,
            target_generation=app.generation,
            action="install",
            target_snapshot={"slug": app.slug},
        )

    assert (
        Reconciler(repo, runtime=runtime, deployer=BlockingDeployer()).run_once()
        == 1
    )

    with sqlite3.connect(repo.db_path) as connection:
        request_row = connection.execute(
            "SELECT state, error FROM reconciliation_requests WHERE id = ?",
            (request.id,),
        ).fetchone()
        status_row = connection.execute(
            """
            SELECT level, reconciliation, reason, message, observed_generation
            FROM status_snapshots
            WHERE resource_type = ? AND resource_id = ?
            """,
            ("app_instance", app.id),
        ).fetchone()

    assert request_row == ("blocked", "Binding database.uri is not available.")
    assert status_row == (
        "blocked",
        "blocked",
        "runtime_mapping_source_missing",
        "Binding database.uri is not available.",
        1,
    )


def test_binding_reconcile_materializes_binding_secret_and_succeeds(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    runtime = FakeRuntime()
    values = {
        "host": "postgres.svc",
        "port": "5432",
        "database": "paperless",
        "username": "paperless",
        "password": "secret",
        "uri": "postgres://paperless:secret@postgres.svc:5432/paperless",
    }
    with repo.transaction() as tx:
        service = tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path="catalog/services/postgres/service.yaml",
            manifest_digest="sha256:postgres",
        )
        app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(_write_routeless_app(tmp_path)),
            manifest_digest="sha256:paperless",
        )
        binding = tx.create_binding(
            app_instance_id=app.id,
            service_instance_id=service.id,
            alias="database",
            capability="postgres",
            output_summary={
                "target": "app-secret",
                "secretName": "nephos-bind-database",
                "namespace": "app-paperless",
                "keys": ["redacted"],
                "redacted": True,
                "values": values,
            },
        )
        request = tx.create_reconciliation_request(
            target_type="binding",
            target_id=binding.id,
            target_generation=binding.generation,
            action="reconcile",
            target_snapshot={"id": binding.id, "alias": binding.alias},
        )

    assert Reconciler(repo, runtime=runtime).run_once() == 1

    assert runtime.namespaces == [("app_instance", "paperless")]
    assert runtime.binding_secrets == [
        {
            "app_slug": "paperless",
            "service_slug": "postgres",
            "alias": "database",
            "capability": "postgres",
            "values": values,
        }
    ]
    _assert_reconciled_binding_status(repo, request.id, binding.id)


def test_binding_reconcile_blocks_when_binding_output_values_are_missing(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    runtime = FakeRuntime()
    with repo.transaction() as tx:
        service = tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path="catalog/services/postgres/service.yaml",
            manifest_digest="sha256:postgres",
        )
        app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(_write_routeless_app(tmp_path)),
            manifest_digest="sha256:paperless",
        )
        binding = tx.create_binding(
            app_instance_id=app.id,
            service_instance_id=service.id,
            alias="database",
            capability="postgres",
            output_summary={
                "target": "app-secret",
                "secretName": "nephos-bind-database",
                "namespace": "app-paperless",
                "keys": ["redacted"],
                "redacted": True,
            },
        )
        request = tx.create_reconciliation_request(
            target_type="binding",
            target_id=binding.id,
            target_generation=binding.generation,
            action="reconcile",
            target_snapshot={"id": binding.id, "alias": binding.alias},
        )

    assert Reconciler(repo, runtime=runtime).run_once() == 1

    assert runtime.binding_secrets == []
    with sqlite3.connect(repo.db_path) as connection:
        request_row = connection.execute(
            "SELECT state, error FROM reconciliation_requests WHERE id = ?",
            (request.id,),
        ).fetchone()
        status_row = connection.execute(
            """
            SELECT level, reconciliation, reason, message, observed_generation
            FROM status_snapshots
            WHERE resource_type = 'binding' AND resource_id = ?
            """,
            (binding.id,),
        ).fetchone()
    assert request_row == ("blocked", "Binding output values are not available.")
    assert status_row == (
        "blocked",
        "blocked",
        "binding_output_unavailable",
        "Binding output values are not available.",
        1,
    )


def test_binding_reconcile_uses_provisioner_without_persisting_secret_values(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    runtime = FakeRuntime()
    values = {
        "host": "postgres.svc",
        "port": "5432",
        "database": "paperless",
        "username": "paperless",
        "password": "secret",
        "uri": "postgres://paperless:secret@postgres.svc:5432/paperless",
    }
    provisioner = FakeProvisioner(values)
    with repo.transaction() as tx:
        service = tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path="catalog/services/postgres/service.yaml",
            manifest_digest="sha256:postgres",
        )
        app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(_write_routeless_app(tmp_path)),
            manifest_digest="sha256:paperless",
        )
        binding = tx.create_binding(
            app_instance_id=app.id,
            service_instance_id=service.id,
            alias="database",
            capability="postgres",
            output_summary={
                "target": "app-secret",
                "secretName": "nephos-bind-database",
                "namespace": "app-paperless",
                "keys": ["redacted"],
                "redacted": True,
            },
        )
        request = tx.create_reconciliation_request(
            target_type="binding",
            target_id=binding.id,
            target_generation=binding.generation,
            action="reconcile",
            target_snapshot={"id": binding.id, "alias": binding.alias},
        )

    assert Reconciler(repo, runtime=runtime, provisioner=provisioner).run_once() == 1

    assert provisioner.contexts == [
        BindingProvisioningContext(
            binding_id=binding.id,
            app_slug="paperless",
            service_slug="postgres",
            alias="database",
            capability="postgres",
        )
    ]
    assert runtime.binding_secrets[0]["values"] == values
    row = repo.get_binding_row(binding.id)
    assert row is not None
    assert row["output_summary_json"] == (
        '{"keys": ["database", "host", "password", "port", "uri", "username"], '
        '"namespace": "app-paperless", "redacted": true, '
        '"secretName": "nephos-bind-database", "target": "app-secret"}'
    )
    _assert_reconciled_binding_status(repo, request.id, binding.id)


def test_binding_reconcile_persists_protocol_in_redacted_summary(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    runtime = FakeRuntime()
    values = {
        "issuerUrl": "https://zitadel.example",
        "clientId": "client-1",
        "clientSecret": "secret-client",
        "redirectUris": '["https://paperless.example/callback"]',
    }
    provisioner = FakeProvisioner(values)
    with repo.transaction() as tx:
        service = tx.create_service_instance(
            slug="zitadel",
            catalog_name="zitadel",
            catalog_source_id="default",
            catalog_source_path="catalog/services/zitadel/service.yaml",
            manifest_digest="sha256:zitadel",
        )
        app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(_write_routeless_app(tmp_path)),
            manifest_digest="sha256:paperless",
        )
        binding = tx.create_binding(
            app_instance_id=app.id,
            service_instance_id=service.id,
            alias="auth",
            capability="oidc",
            protocol="oidc",
            output_summary={
                "target": "app-secret",
                "secretName": "nephos-bind-auth",
                "namespace": "app-paperless",
                "keys": ["redacted"],
                "redacted": True,
            },
        )
        request = tx.create_reconciliation_request(
            target_type="binding",
            target_id=binding.id,
            target_generation=binding.generation,
            action="reconcile",
            target_snapshot={"id": binding.id, "alias": binding.alias},
        )

    assert Reconciler(repo, runtime=runtime, provisioner=provisioner).run_once() == 1

    assert provisioner.contexts == [
        BindingProvisioningContext(
            binding_id=binding.id,
            app_slug="paperless",
            service_slug="zitadel",
            alias="auth",
            capability="oidc",
            protocol="oidc",
        )
    ]
    assert runtime.binding_secrets == [
        {
            "app_slug": "paperless",
            "service_slug": "zitadel",
            "alias": "auth",
            "capability": "oidc",
            "protocol": "oidc",
            "values": values,
        }
    ]
    row = repo.get_binding_row(binding.id)
    assert row is not None
    summary = json.loads(str(row["output_summary_json"]))
    assert summary == {
        "target": "app-secret",
        "secretName": "nephos-bind-auth",
        "namespace": "app-paperless",
        "capability": "oidc",
        "protocol": "oidc",
        "keys": ["clientId", "clientSecret", "issuerUrl", "redirectUris"],
        "redacted": True,
    }
    assert "secret-client" not in str(row["output_summary_json"])
    _assert_reconciled_binding_status(repo, request.id, binding.id)


def test_binding_reconcile_skips_runtime_materialization_for_removed_app(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    runtime = FakeRuntime()
    values = {
        "host": "postgres.svc",
        "port": "5432",
        "database": "paperless",
        "username": "paperless",
        "password": "secret",
        "uri": "postgres://paperless:secret@postgres.svc:5432/paperless",
    }
    provisioner = FakeProvisioner(values)
    with repo.transaction() as tx:
        service = tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path="catalog/services/postgres/service.yaml",
            manifest_digest="sha256:postgres",
        )
        app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(_write_routeless_app(tmp_path)),
            manifest_digest="sha256:paperless",
            lifecycle="removed",
        )
        binding = tx.create_binding(
            app_instance_id=app.id,
            service_instance_id=service.id,
            alias="database",
            capability="postgres",
        )
        request = tx.create_reconciliation_request(
            target_type="binding",
            target_id=binding.id,
            target_generation=binding.generation,
            action="reconcile",
            target_snapshot={"id": binding.id, "alias": binding.alias},
        )

    assert Reconciler(repo, runtime=runtime, provisioner=provisioner).run_once() == 1

    assert provisioner.contexts == []
    assert runtime.namespaces == []
    assert runtime.binding_secrets == []
    _assert_binding_consumer_inactive_status(repo, request.id, binding.id)


def test_binding_reconcile_skips_runtime_materialization_for_pending_destroy_app(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    runtime = FakeRuntime()
    values = {
        "host": "postgres.svc",
        "port": "5432",
        "database": "paperless",
        "username": "paperless",
        "password": "secret",
        "uri": "postgres://paperless:secret@postgres.svc:5432/paperless",
    }
    provisioner = FakeProvisioner(values)
    with repo.transaction() as tx:
        service = tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path="catalog/services/postgres/service.yaml",
            manifest_digest="sha256:postgres",
        )
        app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(_write_routeless_app(tmp_path)),
            manifest_digest="sha256:paperless",
        )
        tx.mark_app_delete_requested(slug=app.slug)
        binding = tx.create_binding(
            app_instance_id=app.id,
            service_instance_id=service.id,
            alias="database",
            capability="postgres",
        )
        request = tx.create_reconciliation_request(
            target_type="binding",
            target_id=binding.id,
            target_generation=binding.generation,
            action="reconcile",
            target_snapshot={"id": binding.id, "alias": binding.alias},
        )

    assert Reconciler(repo, runtime=runtime, provisioner=provisioner).run_once() == 1

    assert provisioner.contexts == []
    assert runtime.namespaces == []
    assert runtime.binding_secrets == []
    _assert_binding_consumer_inactive_status(repo, request.id, binding.id)


def test_binding_reconcile_enqueues_app_reconcile_after_secret_materialization(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    runtime = FakeRuntime()
    values = {
        "host": "postgres.svc",
        "port": "5432",
        "database": "paperless",
        "username": "paperless",
        "password": "secret",
        "uri": "postgres://paperless:secret@postgres.svc:5432/paperless",
    }
    provisioner = FakeProvisioner(values)
    with repo.transaction() as tx:
        service = tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path="catalog/services/postgres/service.yaml",
            manifest_digest="sha256:postgres",
        )
        app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(_write_routeless_app(tmp_path)),
            manifest_digest="sha256:paperless",
        )
        binding = tx.create_binding(
            app_instance_id=app.id,
            service_instance_id=service.id,
            alias="database",
            capability="postgres",
            output_summary={
                "target": "app-secret",
                "secretName": "nephos-bind-database",
                "namespace": "app-paperless",
                "keys": ["redacted"],
                "redacted": True,
            },
        )
        tx.create_reconciliation_request(
            target_type="binding",
            target_id=binding.id,
            target_generation=binding.generation,
            action="reconcile",
            target_snapshot={"id": binding.id, "alias": binding.alias},
        )

    assert Reconciler(repo, runtime=runtime, provisioner=provisioner).run_once() == 1

    with sqlite3.connect(repo.db_path) as connection:
        app_reconcile = connection.execute(
            """
            SELECT target_type, target_id, target_generation, action, state,
                target_snapshot_json
            FROM reconciliation_requests
            WHERE target_type = 'app_instance'
            """
        ).fetchone()

    assert app_reconcile is not None
    assert app_reconcile[:5] == (
        "app_instance",
        app.id,
        app.generation,
        "reconcile",
        "pending",
    )
    assert json.loads(app_reconcile[5]) == {"slug": "paperless"}


def _assert_reconciled_namespace_status(
    repo: DesiredStateRepository,
    *,
    request_id: str,
    resource_type: str,
    resource_id: str,
) -> None:
    with sqlite3.connect(repo.db_path) as connection:
        request_row = connection.execute(
            "SELECT state, error FROM reconciliation_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        status_row = connection.execute(
            """
            SELECT level, reconciliation, reason, message, observed_generation
            FROM status_snapshots
            WHERE resource_type = ? AND resource_id = ?
            """,
            (resource_type, resource_id),
        ).fetchone()

    assert request_row == ("succeeded", None)
    assert status_row == (
        "healthy",
        "succeeded",
        "runtime_namespace_ready",
        "Kubernetes namespace is present and owned by Nephos.",
        1,
    )


def _assert_request_succeeded(repo: DesiredStateRepository, request_id: str) -> None:
    with sqlite3.connect(repo.db_path) as connection:
        request_row = connection.execute(
            "SELECT state, error FROM reconciliation_requests WHERE id = ?",
            (request_id,),
        ).fetchone()

    assert request_row == ("succeeded", None)


def _assert_reconciled_binding_status(
    repo: DesiredStateRepository,
    request_id: str,
    binding_id: str,
) -> None:
    with sqlite3.connect(repo.db_path) as connection:
        request_row = connection.execute(
            "SELECT state, error FROM reconciliation_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        status_row = connection.execute(
            """
            SELECT level, reconciliation, reason, message, observed_generation
            FROM status_snapshots
            WHERE resource_type = 'binding' AND resource_id = ?
            """,
            (binding_id,),
        ).fetchone()

    assert request_row == ("succeeded", None)
    assert status_row == (
        "healthy",
        "succeeded",
        "binding_secret_ready",
        "Binding Secret is present and owned by Nephos.",
        1,
    )


def _assert_binding_consumer_inactive_status(
    repo: DesiredStateRepository,
    request_id: str,
    binding_id: str,
) -> None:
    with sqlite3.connect(repo.db_path) as connection:
        request_row = connection.execute(
            "SELECT state, error FROM reconciliation_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        status_row = connection.execute(
            """
            SELECT level, reconciliation, reason, message, observed_generation
            FROM status_snapshots
            WHERE resource_type = 'binding' AND resource_id = ?
            """,
            (binding_id,),
        ).fetchone()

    assert request_row == ("succeeded", None)
    assert status_row == (
        "not_applicable",
        "succeeded",
        "binding_consumer_inactive",
        "Binding consumer App is not active.",
        1,
    )


def _assert_platform_domain_reconciled_status(
    repo: DesiredStateRepository,
    request_id: str,
    domain_id: str,
) -> None:
    with sqlite3.connect(repo.db_path) as connection:
        request_row = connection.execute(
            "SELECT state, error FROM reconciliation_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        status_row = connection.execute(
            """
            SELECT level, reconciliation, reason, message, observed_generation
            FROM status_snapshots
            WHERE resource_type = 'platform_domain' AND resource_id = ?
            """,
            (domain_id,),
        ).fetchone()

    assert request_row == ("succeeded", None)
    assert status_row == (
        "healthy",
        "succeeded",
        "platform_domain_reconciled",
        (
            "Platform domain desired state is recorded; "
            "App route reconciliation is queued."
        ),
        1,
    )


def _assert_reconciled_deployment_status(
    repo: DesiredStateRepository,
    request_id: str,
    resource_id: str,
) -> None:
    with sqlite3.connect(repo.db_path) as connection:
        request_row = connection.execute(
            "SELECT state, error FROM reconciliation_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        status_row = connection.execute(
            """
            SELECT level, reconciliation, reason, message, observed_generation
            FROM status_snapshots
            WHERE resource_id = ?
            """,
            (resource_id,),
        ).fetchone()

    assert request_row == ("succeeded", None)
    assert status_row == (
        "healthy",
        "succeeded",
        "runtime_deployed",
        "Runtime deployment is present and owned by Nephos.",
        1,
    )


def _assert_runtime_stopped_status(
    repo: DesiredStateRepository,
    request_id: str,
    resource_id: str,
) -> None:
    with sqlite3.connect(repo.db_path) as connection:
        request_row = connection.execute(
            "SELECT state, error FROM reconciliation_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        status_row = connection.execute(
            """
            SELECT level, reconciliation, reason, message, observed_generation
            FROM status_snapshots
            WHERE resource_id = ?
            """,
            (resource_id,),
        ).fetchone()

    assert request_row == ("succeeded", None)
    assert status_row == (
        "stopped",
        "succeeded",
        "runtime_stopped",
        "Runtime workloads are scaled to zero.",
        1,
    )


def _assert_runtime_removed_status(
    repo: DesiredStateRepository,
    request_id: str,
    resource_id: str,
) -> None:
    with sqlite3.connect(repo.db_path) as connection:
        request_row = connection.execute(
            "SELECT state, error FROM reconciliation_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        status_row = connection.execute(
            """
            SELECT level, reconciliation, reason, message, observed_generation
            FROM status_snapshots
            WHERE resource_id = ?
            """,
            (resource_id,),
        ).fetchone()

    assert request_row == ("succeeded", None)
    assert status_row == (
        "not_applicable",
        "succeeded",
        "runtime_removed",
        "Runtime deployment is removed while desired state is preserved.",
        1,
    )


def _write_routeless_app(tmp_path: Path) -> Path:
    path = tmp_path / "catalog" / "apps" / "paperless-routeless" / "app.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
apiVersion: nephos.pro/v1alpha1
kind: App
metadata:
  name: paperless-routeless
spec:
  runtime:
    type: helm
    chart:
      repository: https://charts.example.test
      name: paperless
      version: "1.0.0"
    values:
      mappings: []
""".strip()
    )
    return path
