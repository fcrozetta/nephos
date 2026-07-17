from pathlib import Path

from catalog_fixtures import write_service

from nephos_api.db import migrate_database
from nephos_api.providers import (
    ProviderContext,
    ProviderRuntimeDeployer,
    PulumiHelmProvider,
    PulumiHelmProviderConfig,
    PulumiHelmReleaseSpec,
)
from nephos_api.providers.pulumi import (
    PulumiAutomationHelmStackRunner,
    _pulumi_release_config,
    _pulumi_workspace_env_vars,
)
from nephos_api.provisioners.base import BindingProvisioningContext
from nephos_api.repository import DesiredStateRepository
from nephos_api.runtime_errors import RuntimeBlockedError
from nephos_api.secret_refs import SecretGenSpec, StaticSecretResolver


class RecordingProvider:
    def __init__(self) -> None:
        self.deployed: list[ProviderContext] = []
        self.uninstalled: list[ProviderContext] = []

    def deploy(self, context: ProviderContext) -> None:
        self.deployed.append(context)

    def uninstall(self, context: ProviderContext) -> None:
        self.uninstalled.append(context)


class RecordingMaterializer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, SecretGenSpec | None]] = []

    def resolve(self, reference: str) -> str:
        return self.materialize(reference, generate=None)

    def materialize(
        self, reference: str, *, generate: SecretGenSpec | None = None
    ) -> str:
        self.calls.append((reference, generate))
        return f"materialized:{reference}"


class RecordingPulumiRunner:
    def __init__(self) -> None:
        self.ups: list[PulumiHelmReleaseSpec] = []
        self.destroys: list[PulumiHelmReleaseSpec] = []

    def up(self, spec: PulumiHelmReleaseSpec) -> None:
        self.ups.append(spec)

    def destroy(self, spec: PulumiHelmReleaseSpec) -> None:
        self.destroys.append(spec)


class RecordingDependencyProvisioner:
    def __init__(self) -> None:
        self.contexts: list[BindingProvisioningContext] = []
        self.deprovisioned: list[BindingProvisioningContext] = []

    def provision_binding(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str] | None:
        self.contexts.append(context)
        return {
            "host": "svc-postgres-postgresql.svc-postgres.svc.cluster.local",
            "port": "5432",
            "database": "nephos_zitadel_database",
            "username": "nephos_zitadel_database",
            "password": "pg-secret",
            "adminUsername": "postgres",
            "adminPassword": "admin-secret",
        }

    def deprovision_binding(self, context: BindingProvisioningContext) -> None:
        self.deprovisioned.append(context)


def test_provider_runtime_deployer_dispatches_services_to_service_provider(
    tmp_path: Path,
) -> None:
    catalog_root = tmp_path / "catalog"
    manifest_path = write_service(catalog_root)
    repo = _repo(tmp_path)
    app_provider = RecordingProvider()
    service_provider = RecordingProvider()
    with repo.transaction() as tx:
        tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path=str(manifest_path),
            manifest_digest="sha256:postgres",
        )

    deployer = ProviderRuntimeDeployer(
        repository=repo,
        app_provider=app_provider,
        service_provider=service_provider,
    )
    deployer.deploy(target_type="service_instance", slug="postgres")

    assert app_provider.deployed == []
    assert len(service_provider.deployed) == 1
    context = service_provider.deployed[0]
    assert context.target_type == "service_instance"
    assert context.slug == "postgres"
    assert context.runtime_name == "svc-postgres"
    assert context.chart.name == "postgresql"
    assert context.chart.repository == "https://charts.example.test"
    assert context.chart.version == "16.0.0"
    assert context.values == {}


def test_provider_runtime_deployer_dispatches_apps_with_mapped_values(
    tmp_path: Path,
) -> None:
    catalog_root = tmp_path / "catalog"
    app_manifest = _write_app_with_runtime_mappings(catalog_root)
    service_manifest = write_service(catalog_root)
    repo = _repo(tmp_path)
    app_provider = RecordingProvider()
    service_provider = RecordingProvider()
    with repo.transaction() as tx:
        service = tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path=str(service_manifest),
            manifest_digest="sha256:postgres",
        )
        app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(app_manifest),
            manifest_digest="sha256:paperless",
            config={"ocr-language": "deu"},
        )
        tx.create_binding(
            app_instance_id=app.id,
            service_instance_id=service.id,
            alias="database",
            capability="postgres",
            output_summary={
                "values": {
                    "uri": "postgresql://paperless:secret@postgres:5432/paperless"
                }
            },
        )

    deployer = ProviderRuntimeDeployer(
        repository=repo,
        app_provider=app_provider,
        service_provider=service_provider,
    )
    deployer.deploy(target_type="app_instance", slug="paperless")

    assert service_provider.deployed == []
    assert len(app_provider.deployed) == 1
    context = app_provider.deployed[0]
    assert context.runtime_name == "app-paperless"
    assert context.chart.name == "paperless"
    assert context.values == {
        "env": {
            "DATABASE_URL": "postgresql://paperless:secret@postgres:5432/paperless"
        },
        "paperless": {"ocr": {"language": "deu"}},
    }


def test_provider_runtime_deployer_passes_provider_runtime_without_chart(
    tmp_path: Path,
) -> None:
    catalog_root = tmp_path / "catalog"
    manifest_path = _write_provider_service(catalog_root)
    repo = _repo(tmp_path)
    app_provider = RecordingProvider()
    service_provider = RecordingProvider()
    with repo.transaction() as tx:
        tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path=str(manifest_path),
            manifest_digest="sha256:postgres",
        )

    deployer = ProviderRuntimeDeployer(
        repository=repo,
        app_provider=app_provider,
        service_provider=service_provider,
    )
    deployer.deploy(target_type="service_instance", slug="postgres")

    context = service_provider.deployed[0]
    assert context.chart is None
    assert context.provider_name == "postgres"


def test_provider_runtime_deployer_maps_service_config_defaults_and_overrides(
    tmp_path: Path,
) -> None:
    catalog_root = tmp_path / "catalog"
    manifest_path = _write_provider_service_with_runtime_mappings(catalog_root)
    repo = _repo(tmp_path)
    app_provider = RecordingProvider()
    service_provider = RecordingProvider()
    with repo.transaction() as tx:
        tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path=str(manifest_path),
            manifest_digest="sha256:postgres",
            config={"storage-size": "8Gi"},
        )

    deployer = ProviderRuntimeDeployer(
        repository=repo,
        app_provider=app_provider,
        service_provider=service_provider,
    )
    deployer.deploy(target_type="service_instance", slug="postgres")

    context = service_provider.deployed[0]
    assert context.values == {
        "image": "postgres:16-alpine",
        "storageSize": "8Gi",
        "debug": {"enabled": False},
    }


def test_provider_runtime_deployer_resolves_onepassword_config_refs(
    tmp_path: Path,
) -> None:
    catalog_root = tmp_path / "catalog"
    manifest_path = _write_provider_service_with_runtime_mappings(catalog_root)
    repo = _repo(tmp_path)
    service_provider = RecordingProvider()
    with repo.transaction() as tx:
        tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path=str(manifest_path),
            manifest_digest="sha256:postgres",
            config={"storage-size": "op://nephos-lcl/postgres-admin/password"},
        )

    deployer = ProviderRuntimeDeployer(
        repository=repo,
        app_provider=RecordingProvider(),
        service_provider=service_provider,
        secret_resolver=StaticSecretResolver(
            {"op://nephos-lcl/postgres-admin/password": "resolved-secret"}
        ),
    )
    deployer.deploy(target_type="service_instance", slug="postgres")

    context = service_provider.deployed[0]
    assert context.values["storageSize"] == "resolved-secret"


def test_provider_runtime_deployer_materializes_secrets_refs_with_genspec(
    tmp_path: Path,
) -> None:
    catalog_root = tmp_path / "catalog"
    manifest_path = _write_service_with_secrets_config(catalog_root)
    repo = _repo(tmp_path)
    service_provider = RecordingProvider()
    with repo.transaction() as tx:
        tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path=str(manifest_path),
            manifest_digest="sha256:postgres",
            config={
                "master-key": "secrets://svc/postgres/master/key",
                "api-token": "secrets://svc/postgres/api/token",
            },
        )

    materializer = RecordingMaterializer()
    deployer = ProviderRuntimeDeployer(
        repository=repo,
        app_provider=RecordingProvider(),
        service_provider=service_provider,
        secrets_materializer=materializer,
    )
    deployer.deploy(target_type="service_instance", slug="postgres")

    context = service_provider.deployed[0]
    assert (
        context.values["masterKey"] == "materialized:secrets://svc/postgres/master/key"
    )
    assert context.values["apiToken"] == "materialized:secrets://svc/postgres/api/token"
    # master-key declares a generation policy; api-token does not (read-only).
    master_spec = SecretGenSpec(kind="password", length=40)
    assert set(materializer.calls) == {
        ("secrets://svc/postgres/master/key", master_spec),
        ("secrets://svc/postgres/api/token", None),
    }


def test_provider_runtime_deployer_synthesizes_ref_for_generated_option(
    tmp_path: Path,
) -> None:
    catalog_root = tmp_path / "catalog"
    manifest_path = _write_service_with_secrets_config(catalog_root)
    repo = _repo(tmp_path)
    service_provider = RecordingProvider()
    with repo.transaction() as tx:
        # master-key is generated and NOT supplied by the user (hidden in the
        # install form); api-token is a plain value.
        tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path=str(manifest_path),
            manifest_digest="sha256:postgres",
            config={"api-token": "plain-token"},
        )

    materializer = RecordingMaterializer()
    deployer = ProviderRuntimeDeployer(
        repository=repo,
        app_provider=RecordingProvider(),
        service_provider=service_provider,
        secrets_materializer=materializer,
    )
    deployer.deploy(target_type="service_instance", slug="postgres")

    context = service_provider.deployed[0]
    # Nephos synthesized secrets://svc/postgres/master-key/value and materialized it.
    synthesized = "secrets://svc/postgres/master-key/value"
    assert context.values["masterKey"] == f"materialized:{synthesized}"
    assert context.values["apiToken"] == "plain-token"
    spec = SecretGenSpec(kind="password", length=40)
    assert (synthesized, spec) in materializer.calls


def test_provider_runtime_deployer_blocks_secrets_refs_without_provider(
    tmp_path: Path,
) -> None:
    catalog_root = tmp_path / "catalog"
    manifest_path = _write_service_with_secrets_config(catalog_root)
    repo = _repo(tmp_path)
    with repo.transaction() as tx:
        tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path=str(manifest_path),
            manifest_digest="sha256:postgres",
            config={
                "master-key": "secrets://svc/postgres/master/key",
                "api-token": "plain",
            },
        )

    deployer = ProviderRuntimeDeployer(
        repository=repo,
        app_provider=RecordingProvider(),
        service_provider=RecordingProvider(),
    )

    try:
        deployer.deploy(target_type="service_instance", slug="postgres")
    except RuntimeBlockedError as exc:
        assert exc.reason == "secret_ref_provider_unavailable"
    else:
        raise AssertionError("expected missing secrets provider to block")


def test_provider_runtime_deployer_blocks_onepassword_refs_without_provider(
    tmp_path: Path,
) -> None:
    catalog_root = tmp_path / "catalog"
    manifest_path = _write_provider_service_with_runtime_mappings(catalog_root)
    repo = _repo(tmp_path)
    with repo.transaction() as tx:
        tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path=str(manifest_path),
            manifest_digest="sha256:postgres",
            config={"storage-size": "op://nephos-lcl/postgres-admin/password"},
        )

    deployer = ProviderRuntimeDeployer(
        repository=repo,
        app_provider=RecordingProvider(),
        service_provider=RecordingProvider(),
    )

    try:
        deployer.deploy(target_type="service_instance", slug="postgres")
    except RuntimeBlockedError as exc:
        assert exc.reason == "secret_ref_provider_unavailable"
    else:
        raise AssertionError("expected missing secret provider to block")


def test_provider_runtime_deployer_provisions_service_dependencies(
    tmp_path: Path,
) -> None:
    catalog_root = tmp_path / "catalog"
    postgres_manifest = write_service(
        catalog_root,
        name="postgres",
        capability="sql",
        protocol="postgres",
        alias="postgres",
    )
    zitadel_manifest = _write_service_with_dependency_runtime_mappings(catalog_root)
    repo = _repo(tmp_path)
    app_provider = RecordingProvider()
    service_provider = RecordingProvider()
    provisioner = RecordingDependencyProvisioner()
    with repo.transaction() as tx:
        postgres = tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path=str(postgres_manifest),
            manifest_digest="sha256:postgres",
        )
        tx.create_service_instance(
            slug="zitadel",
            catalog_name="zitadel",
            catalog_source_id="default",
            catalog_source_path=str(zitadel_manifest),
            manifest_digest="sha256:zitadel",
        )
        _mark_service_runtime_deployed(tx, postgres.id, postgres.generation)

    deployer = ProviderRuntimeDeployer(
        repository=repo,
        app_provider=app_provider,
        service_provider=service_provider,
        service_dependency_provisioner=provisioner,
    )
    deployer.deploy(target_type="service_instance", slug="zitadel")

    context = service_provider.deployed[0]
    assert context.values == {
        "databaseHost": "svc-postgres-postgresql.svc-postgres.svc.cluster.local",
        "databasePort": "5432",
        "databaseName": "nephos_zitadel_database",
        "databaseUsername": "nephos_zitadel_database",
        "databasePassword": "pg-secret",
        "databaseAdminUsername": "postgres",
        "databaseAdminPassword": "admin-secret",
    }
    assert len(provisioner.contexts) == 1
    provision_context = provisioner.contexts[0]
    assert provision_context.app_slug == "zitadel"
    assert provision_context.service_slug == "postgres"
    assert provision_context.alias == "database"
    assert provision_context.capability == "sql"
    assert provision_context.protocol == "postgres"
    assert provisioner.deprovisioned == []


def test_provider_runtime_deployer_blocks_service_dependency_until_provider_deployed(
    tmp_path: Path,
) -> None:
    catalog_root = tmp_path / "catalog"
    postgres_manifest = write_service(
        catalog_root,
        name="postgres",
        capability="sql",
        protocol="postgres",
        alias="postgres",
    )
    zitadel_manifest = _write_service_with_dependency_runtime_mappings(catalog_root)
    repo = _repo(tmp_path)
    service_provider = RecordingProvider()
    provisioner = RecordingDependencyProvisioner()
    with repo.transaction() as tx:
        tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path=str(postgres_manifest),
            manifest_digest="sha256:postgres",
        )
        tx.create_service_instance(
            slug="zitadel",
            catalog_name="zitadel",
            catalog_source_id="default",
            catalog_source_path=str(zitadel_manifest),
            manifest_digest="sha256:zitadel",
        )

    deployer = ProviderRuntimeDeployer(
        repository=repo,
        app_provider=RecordingProvider(),
        service_provider=service_provider,
        service_dependency_provisioner=provisioner,
    )

    try:
        deployer.deploy(target_type="service_instance", slug="zitadel")
    except RuntimeBlockedError as exc:
        assert exc.reason == "service_dependency_provider_unavailable"
    else:
        raise AssertionError("expected undeployed dependency provider to block")

    assert provisioner.contexts == []
    assert service_provider.deployed == []


def test_provider_runtime_deployer_deprovisions_service_dependencies_on_uninstall(
    tmp_path: Path,
) -> None:
    catalog_root = tmp_path / "catalog"
    postgres_manifest = write_service(
        catalog_root,
        name="postgres",
        capability="sql",
        protocol="postgres",
        alias="postgres",
    )
    zitadel_manifest = _write_service_with_dependency_runtime_mappings(catalog_root)
    repo = _repo(tmp_path)
    app_provider = RecordingProvider()
    service_provider = RecordingProvider()
    provisioner = RecordingDependencyProvisioner()
    with repo.transaction() as tx:
        postgres = tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path=str(postgres_manifest),
            manifest_digest="sha256:postgres",
        )
        tx.create_service_instance(
            slug="zitadel",
            catalog_name="zitadel",
            catalog_source_id="default",
            catalog_source_path=str(zitadel_manifest),
            manifest_digest="sha256:zitadel",
        )
        _mark_service_runtime_deployed(tx, postgres.id, postgres.generation)

    deployer = ProviderRuntimeDeployer(
        repository=repo,
        app_provider=app_provider,
        service_provider=service_provider,
        service_dependency_provisioner=provisioner,
    )
    deployer.uninstall(target_type="service_instance", slug="zitadel")

    assert provisioner.contexts == []
    assert len(provisioner.deprovisioned) == 1
    context = provisioner.deprovisioned[0]
    assert context.binding_id == "service-zitadel-database"
    assert context.app_slug == "zitadel"
    assert context.service_slug == "postgres"
    assert context.alias == "database"
    assert context.capability == "sql"
    assert context.protocol == "postgres"
    assert len(service_provider.uninstalled) == 1
    assert service_provider.uninstalled[0].slug == "zitadel"
    assert service_provider.uninstalled[0].values == {}


def test_pulumi_helm_provider_maps_context_to_local_stack_operations(
    tmp_path: Path,
) -> None:
    runner = RecordingPulumiRunner()
    provider = PulumiHelmProvider(
        config=PulumiHelmProviderConfig(
            work_dir=tmp_path / "workspaces",
            state_dir=tmp_path / "state",
            kubeconfig=tmp_path / "kubeconfig",
            kube_context="k3s-dev",
        ),
        runner=runner,
    )
    context = ProviderContext(
        target_type="app_instance",
        slug="paperless",
        runtime_name="app-paperless",
        manifest=None,
        chart=ProviderContext.Chart(
            repository="https://charts.example.test",
            name="paperless",
            version="1.0.0",
        ),
        values={"paperless": {"ocr": {"language": "eng"}}},
    )

    provider.deploy(context)
    provider.uninstall(context)

    assert runner.ups == [
        PulumiHelmReleaseSpec(
            project_name="nephos-api",
            stack_name="app-paperless",
            work_dir=tmp_path / "workspaces" / "app-paperless",
            state_dir=tmp_path / "state",
            kubeconfig=tmp_path / "kubeconfig",
            kube_context="k3s-dev",
            release_name="app-paperless",
            namespace="app-paperless",
            chart_repository="https://charts.example.test",
            chart_name="paperless",
            chart_version="1.0.0",
            values={"paperless": {"ocr": {"language": "eng"}}},
        )
    ]
    assert runner.destroys == runner.ups


def test_pulumi_helm_provider_blocks_provider_runtime_without_chart(
    tmp_path: Path,
) -> None:
    provider = PulumiHelmProvider(
        config=PulumiHelmProviderConfig(
            work_dir=tmp_path / "workspaces",
            state_dir=tmp_path / "state",
        ),
        runner=RecordingPulumiRunner(),
    )
    context = ProviderContext(
        target_type="service_instance",
        slug="postgres",
        runtime_name="svc-postgres",
        manifest=None,
        chart=None,
        values={},
        provider_name="postgres",
    )

    try:
        provider.deploy(context)
    except RuntimeBlockedError as exc:
        assert exc.reason == "runtime_chart_missing"
    else:
        raise AssertionError("expected Helm provider to require a chart")


def test_pulumi_automation_runner_blocks_when_pulumi_cli_is_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("nephos_api.providers.pulumi.shutil.which", lambda _: None)
    spec = PulumiHelmReleaseSpec(
        project_name="nephos-api",
        stack_name="app-paperless",
        work_dir=tmp_path / "workspaces" / "app-paperless",
        state_dir=tmp_path / "state",
        kubeconfig=None,
        kube_context=None,
        release_name="app-paperless",
        namespace="app-paperless",
        chart_repository="https://charts.example.test",
        chart_name="paperless",
        chart_version="1.0.0",
        values={},
    )

    runner = PulumiAutomationHelmStackRunner()

    try:
        runner.up(spec)
    except RuntimeBlockedError as exc:
        assert exc.reason == "pulumi_cli_missing"
        assert "Pulumi CLI is required" in str(exc)
    else:
        raise AssertionError("expected missing Pulumi CLI to block")


def test_pulumi_automation_runner_blocks_when_local_backend_passphrase_is_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "nephos_api.providers.pulumi.shutil.which",
        lambda _: "/opt/homebrew/bin/pulumi",
    )
    monkeypatch.delenv("PULUMI_CONFIG_PASSPHRASE", raising=False)
    monkeypatch.delenv("PULUMI_CONFIG_PASSPHRASE_FILE", raising=False)

    def fail_if_stack_is_created(_spec):
        raise AssertionError("stack creation should be blocked by preflight")

    monkeypatch.setattr(
        "nephos_api.providers.pulumi._create_or_select_stack",
        fail_if_stack_is_created,
    )
    spec = PulumiHelmReleaseSpec(
        project_name="nephos-api",
        stack_name="app-paperless",
        work_dir=tmp_path / "workspaces" / "app-paperless",
        state_dir=tmp_path / "state",
        kubeconfig=None,
        kube_context=None,
        release_name="app-paperless",
        namespace="app-paperless",
        chart_repository="https://charts.example.test",
        chart_name="paperless",
        chart_version="1.0.0",
        values={},
    )

    runner = PulumiAutomationHelmStackRunner()

    try:
        runner.up(spec)
    except RuntimeBlockedError as exc:
        assert exc.reason == "pulumi_passphrase_missing"
        assert "PULUMI_CONFIG_PASSPHRASE" in str(exc)
    else:
        raise AssertionError("expected missing Pulumi passphrase to block")


def test_pulumi_release_config_keeps_helm_release_name_aligned_with_runtime_name(
    tmp_path: Path,
) -> None:
    spec = PulumiHelmReleaseSpec(
        project_name="nephos-api",
        stack_name="svc-postgres",
        work_dir=tmp_path / "workspaces" / "svc-postgres",
        state_dir=tmp_path / "state",
        kubeconfig=None,
        kube_context=None,
        release_name="svc-postgres",
        namespace="svc-postgres",
        chart_repository="https://charts.example.test",
        chart_name="postgresql",
        chart_version="16.0.0",
        values={"primary": {"persistence": {"enabled": False}}},
    )

    config = _pulumi_release_config(spec)

    assert config.name == "svc-postgres"
    assert config.namespace == "svc-postgres"
    assert config.repository == "https://charts.example.test"
    assert config.chart == "postgresql"
    assert config.version == "16.0.0"
    assert config.values == {"primary": {"persistence": {"enabled": False}}}


def test_pulumi_workspace_env_vars_include_local_backend_and_passphrase(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PULUMI_CONFIG_PASSPHRASE", "local-test-passphrase")
    monkeypatch.delenv("PULUMI_CONFIG_PASSPHRASE_FILE", raising=False)
    spec = PulumiHelmReleaseSpec(
        project_name="nephos-api",
        stack_name="svc-postgres",
        work_dir=tmp_path / "workspaces" / "svc-postgres",
        state_dir=tmp_path / "state",
        kubeconfig=tmp_path / "kubeconfig",
        kube_context="k3d-nephos-001",
        release_name="svc-postgres",
        namespace="svc-postgres",
        chart_repository="https://charts.example.test",
        chart_name="postgresql",
        chart_version="18.6.8",
        values={},
    )

    env_vars = _pulumi_workspace_env_vars(spec)

    assert env_vars["PULUMI_BACKEND_URL"] == f"file://{tmp_path / 'state'}"
    assert env_vars["PULUMI_CONFIG_PASSPHRASE"] == "local-test-passphrase"
    assert env_vars["KUBECONFIG"] == str(tmp_path / "kubeconfig")
    assert "PULUMI_CONFIG_PASSPHRASE_FILE" not in env_vars


def _repo(tmp_path: Path) -> DesiredStateRepository:
    db_path = tmp_path / "nephos.db"
    migrate_database(db_path=db_path)
    return DesiredStateRepository(db_path)


def _mark_service_runtime_deployed(tx, service_id: str, generation: int) -> None:
    tx.upsert_status_snapshot(
        resource_type="service_instance",
        resource_id=service_id,
        level="healthy",
        lifecycle="running",
        reconciliation="succeeded",
        reason="runtime_deployed",
        message="Runtime deployment is present and owned by Nephos.",
        evidence=[],
        observed_generation=generation,
    )


def _write_app_with_runtime_mappings(root: Path) -> Path:
    path = root / "apps" / "paperless" / "app.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
apiVersion: nephos.pro/v1alpha1
kind: App
metadata:
  name: paperless
spec:
  requires:
    - capability: postgres
      as: database
  config:
    options:
      - name: ocr-language
        type: string
        default: eng
  runtime:
    type: helm
    chart:
      repository: https://charts.example.test
      name: paperless
      version: "1.0.0"
    values:
      mappings:
        - from:
            kind: config
            name: ocr-language
          to:
            helmValue: paperless.ocr.language
        - from:
            kind: binding
            name: database
            field: uri
          to:
            helmValue: env.DATABASE_URL
""".strip()
    )
    return path


def _write_provider_service(root: Path) -> Path:
    path = root / "services" / "postgres" / "service.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
apiVersion: nephos.pro/v1alpha1
kind: Service
metadata:
  name: postgres
spec:
  provides:
    - capability: postgres
      as: postgres
      version: "16"
  provisioning:
    mode: app-scoped-resource
  runtime:
    type: provider
    provider:
      name: postgres
""".strip()
    )
    return path


def _write_provider_service_with_runtime_mappings(root: Path) -> Path:
    path = root / "services" / "postgres" / "service.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
apiVersion: nephos.pro/v1alpha1
kind: Service
metadata:
  name: postgres
spec:
  provides:
    - capability: sql
      protocol: postgres
      as: postgres
  config:
    options:
      - name: image
        type: string
        default: postgres:16-alpine
      - name: storage-size
        type: string
        default: 1Gi
      - name: debug-enabled
        type: boolean
        default: false
  provisioning:
    mode: app-scoped-resource
  runtime:
    type: provider
    provider:
      name: postgres
    values:
      mappings:
        - from:
            kind: config
            name: image
          to:
            helmValue: image
        - from:
            kind: config
            name: storage-size
          to:
            helmValue: storageSize
        - from:
            kind: config
            name: debug-enabled
          to:
            helmValue: debug.enabled
""".strip()
    )
    return path


def _write_service_with_secrets_config(root: Path) -> Path:
    path = root / "services" / "postgres" / "service.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
apiVersion: nephos.pro/v1alpha1
kind: Service
metadata:
  name: postgres
spec:
  provides:
    - capability: sql
      protocol: postgres
      as: postgres
  config:
    options:
      - name: master-key
        type: string
        generate:
          kind: password
          length: 40
      - name: api-token
        type: string
  provisioning:
    mode: app-scoped-resource
  runtime:
    type: provider
    provider:
      name: postgres
    values:
      mappings:
        - from:
            kind: config
            name: master-key
          to:
            helmValue: masterKey
        - from:
            kind: config
            name: api-token
          to:
            helmValue: apiToken
""".strip()
    )
    return path


def _write_service_with_dependency_runtime_mappings(root: Path) -> Path:
    path = root / "services" / "zitadel" / "service.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
apiVersion: nephos.pro/v1alpha1
kind: Service
metadata:
  name: zitadel
spec:
  provides:
    - capability: oidc
      protocol: oidc
      as: oidc
  requires:
    - capability: sql
      protocol: postgres
      as: database
  provisioning:
    mode: app-scoped-resource
  runtime:
    type: provider
    provider:
      name: zitadel
    values:
      mappings:
        - from:
            kind: binding
            name: database
            field: host
          to:
            helmValue: databaseHost
        - from:
            kind: binding
            name: database
            field: port
          to:
            helmValue: databasePort
        - from:
            kind: binding
            name: database
            field: database
          to:
            helmValue: databaseName
        - from:
            kind: binding
            name: database
            field: username
          to:
            helmValue: databaseUsername
        - from:
            kind: binding
            name: database
            field: password
          to:
            helmValue: databasePassword
        - from:
            kind: binding
            name: database
            field: adminUsername
          to:
            helmValue: databaseAdminUsername
        - from:
            kind: binding
            name: database
            field: adminPassword
          to:
            helmValue: databaseAdminPassword
""".strip()
    )
    return path
