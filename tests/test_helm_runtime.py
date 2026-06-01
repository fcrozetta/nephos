from pathlib import Path

import pytest
from catalog_fixtures import write_app, write_service

from nephos_api.db import migrate_database
from nephos_api.helm_runtime import (
    HelmChartRef,
    HelmCommand,
    HelmRuntime,
    HelmRuntimeConfig,
    ManifestBindingValueSource,
    ManifestHelmDeployer,
    build_uninstall_command,
    build_upgrade_install_command,
    runtime_name,
    set_helm_value,
)
from nephos_api.repository import DesiredStateRepository
from nephos_api.runtime_errors import RuntimeBlockedError


class FakeRunner:
    def __init__(self) -> None:
        self.commands: list[HelmCommand] = []
        self.values_content: list[str] = []

    def run(self, command: HelmCommand) -> None:
        self.commands.append(command)
        if "-f" in command.args:
            values_flag = command.args.index("-f")
            self.values_content.append(Path(command.args[values_flag + 1]).read_text())


class FakeBindingValueSource:
    def __init__(self, values: dict[str, dict[str, str]] | None = None) -> None:
        self.values = values or {}

    def get_binding_values(
        self,
        *,
        app_slug: str,
        service_slug: str,
        alias: str,
        capability: str,
    ) -> dict[str, str] | None:
        return self.values.get(alias)


def test_build_upgrade_install_command_uses_argument_list_and_kube_overrides() -> None:
    command = build_upgrade_install_command(
        release="svc-postgres",
        namespace="svc-postgres",
        chart=HelmChartRef(
            repository="https://charts.example.test",
            name="postgresql",
            version="16.0.0",
        ),
        values_file=Path("/tmp/nephos-values.yaml"),
        config=HelmRuntimeConfig(
            kubeconfig=Path("/tmp/kubeconfig"),
            kube_context="k3s-dev",
            timeout="10m",
        ),
    )

    assert command.args == [
        "helm",
        "upgrade",
        "--install",
        "svc-postgres",
        "postgresql",
        "--repo",
        "https://charts.example.test",
        "--version",
        "16.0.0",
        "--namespace",
        "svc-postgres",
        "--create-namespace",
        "--wait",
        "--timeout",
        "10m",
        "-f",
        "/tmp/nephos-values.yaml",
        "--kube-context",
        "k3s-dev",
    ]
    assert command.env == {"KUBECONFIG": "/tmp/kubeconfig"}


def test_build_uninstall_command_uses_wait_timeout_and_context() -> None:
    command = build_uninstall_command(
        release="app-paperless",
        namespace="app-paperless",
        config=HelmRuntimeConfig(kube_context="k3s-dev", timeout="30s"),
    )

    assert command.args == [
        "helm",
        "uninstall",
        "app-paperless",
        "--namespace",
        "app-paperless",
        "--ignore-not-found",
        "--wait",
        "--timeout",
        "30s",
        "--kube-context",
        "k3s-dev",
    ]
    assert command.env == {}


def test_runtime_name_matches_namespace_strategy() -> None:
    assert runtime_name("app_instance", "paperless") == "app-paperless"
    assert runtime_name("service_instance", "postgres") == "svc-postgres"
    with pytest.raises(ValueError, match="unsupported Helm runtime kind"):
        runtime_name("binding", "database")


def test_set_helm_value_expands_dot_path() -> None:
    values: dict[str, object] = {}

    set_helm_value(values, "paperless.env.DATABASE_URL", "postgres://example")
    set_helm_value(values, "paperless.ocr.language", "eng")

    assert values == {
        "paperless": {
            "env": {"DATABASE_URL": "postgres://example"},
            "ocr": {"language": "eng"},
        }
    }


def test_set_helm_value_rejects_empty_path_segments() -> None:
    with pytest.raises(ValueError, match="invalid Helm value path"):
        set_helm_value({}, "paperless..language", "eng")


def test_helm_runtime_upgrade_install_writes_temporary_values_and_cleans_up(
    tmp_path: Path,
) -> None:
    runner = FakeRunner()
    runtime = HelmRuntime(
        config=HelmRuntimeConfig(kube_context="k3s-dev", timeout="1m"),
        runner=runner,
        temp_dir=tmp_path,
    )

    runtime.upgrade_install(
        kind="service_instance",
        slug="postgres",
        chart=HelmChartRef(
            repository="https://charts.example.test",
            name="postgresql",
            version="16.0.0",
        ),
        values={"auth": {"database": "paperless"}},
    )

    command = runner.commands[0]
    assert command.args[:5] == [
        "helm",
        "upgrade",
        "--install",
        "svc-postgres",
        "postgresql",
    ]
    assert "--kube-context" in command.args
    assert runner.values_content == ["auth:\n  database: paperless\n"]
    assert list(tmp_path.iterdir()) == []


def test_helm_runtime_uninstall_uses_runtime_name() -> None:
    runner = FakeRunner()
    runtime = HelmRuntime(config=HelmRuntimeConfig(), runner=runner)

    runtime.uninstall(kind="app_instance", slug="paperless")

    assert runner.commands[0].args == [
        "helm",
        "uninstall",
        "app-paperless",
        "--namespace",
        "app-paperless",
        "--ignore-not-found",
        "--wait",
        "--timeout",
        "5m",
    ]


def test_manifest_helm_deployer_deploys_installed_service_chart(
    tmp_path: Path,
) -> None:
    catalog_root = tmp_path / "catalog"
    db_path = tmp_path / "nephos.db"
    manifest_path = write_service(catalog_root)
    migrate_database(db_path=db_path)
    repo = DesiredStateRepository(db_path)
    runner = FakeRunner()
    helm = HelmRuntime(config=HelmRuntimeConfig(), runner=runner, temp_dir=tmp_path)
    deployer = ManifestHelmDeployer(repository=repo, helm_runtime=helm)
    with repo.transaction() as tx:
        tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path=str(manifest_path),
            manifest_digest="sha256:postgres",
        )

    deployer.deploy(target_type="service_instance", slug="postgres")

    command = runner.commands[0]
    assert command.args[:11] == [
        "helm",
        "upgrade",
        "--install",
        "svc-postgres",
        "postgresql",
        "--repo",
        "https://charts.example.test",
        "--version",
        "16.0.0",
        "--namespace",
        "svc-postgres",
    ]
    assert runner.values_content == ["{}\n"]


def test_manifest_helm_deployer_deploys_installed_app_chart(
    tmp_path: Path,
) -> None:
    catalog_root = tmp_path / "catalog"
    db_path = tmp_path / "nephos.db"
    manifest_path = write_app(catalog_root)
    migrate_database(db_path=db_path)
    repo = DesiredStateRepository(db_path)
    runner = FakeRunner()
    helm = HelmRuntime(config=HelmRuntimeConfig(), runner=runner, temp_dir=tmp_path)
    deployer = ManifestHelmDeployer(repository=repo, helm_runtime=helm)
    with repo.transaction() as tx:
        tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(manifest_path),
            manifest_digest="sha256:paperless",
        )

    deployer.deploy(target_type="app_instance", slug="paperless")

    command = runner.commands[0]
    assert command.args[:11] == [
        "helm",
        "upgrade",
        "--install",
        "app-paperless",
        "paperless",
        "--repo",
        "https://charts.example.test",
        "--version",
        "1.0.0",
        "--namespace",
        "app-paperless",
    ]


def test_manifest_helm_deployer_maps_app_config_and_binding_values(
    tmp_path: Path,
) -> None:
    catalog_root = tmp_path / "catalog"
    db_path = tmp_path / "nephos.db"
    manifest_path = _write_app_with_runtime_mappings(catalog_root)
    service_path = write_service(catalog_root)
    migrate_database(db_path=db_path)
    repo = DesiredStateRepository(db_path)
    runner = FakeRunner()
    helm = HelmRuntime(config=HelmRuntimeConfig(), runner=runner, temp_dir=tmp_path)
    deployer = ManifestHelmDeployer(
        repository=repo,
        helm_runtime=helm,
        binding_value_source=FakeBindingValueSource(
            {
                "database": {
                    "uri": "postgresql://paperless:secret@postgres:5432/paperless"
                }
            }
        ),
    )
    with repo.transaction() as tx:
        service = tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path=str(service_path),
            manifest_digest="sha256:postgres",
        )
        app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(manifest_path),
            manifest_digest="sha256:paperless",
            config={"ocr-language": "deu"},
        )
        tx.create_binding(
            app_instance_id=app.id,
            service_instance_id=service.id,
            alias="database",
            capability="postgres",
            output_summary={
                "target": "app-secret",
                "secretName": "nephos-bind-database",
                "namespace": "app-paperless",
                "keys": ["database", "host", "password", "port", "uri", "username"],
                "redacted": True,
            },
        )

    deployer.deploy(target_type="app_instance", slug="paperless")

    assert runner.values_content == [
        "env:\n"
        "  DATABASE_URL: postgresql://paperless:secret@postgres:5432/paperless\n"
        "paperless:\n"
        "  ocr:\n"
        "    language: deu\n"
    ]


def test_manifest_helm_deployer_uses_manifest_config_defaults(
    tmp_path: Path,
) -> None:
    catalog_root = tmp_path / "catalog"
    db_path = tmp_path / "nephos.db"
    manifest_path = _write_app_with_runtime_mappings(catalog_root)
    migrate_database(db_path=db_path)
    repo = DesiredStateRepository(db_path)
    runner = FakeRunner()
    helm = HelmRuntime(config=HelmRuntimeConfig(), runner=runner, temp_dir=tmp_path)
    deployer = ManifestHelmDeployer(
        repository=repo,
        helm_runtime=helm,
        binding_value_source=FakeBindingValueSource(
            {
                "database": {
                    "uri": "postgresql://paperless:secret@postgres:5432/paperless"
                }
            }
        ),
    )
    with repo.transaction() as tx:
        service = tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path=str(write_service(catalog_root)),
            manifest_digest="sha256:postgres",
        )
        app = tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(manifest_path),
            manifest_digest="sha256:paperless",
        )
        tx.create_binding(
            app_instance_id=app.id,
            service_instance_id=service.id,
            alias="database",
            capability="postgres",
            output_summary={"target": "app-secret", "redacted": True},
        )

    deployer.deploy(target_type="app_instance", slug="paperless")

    assert "language: eng\n" in runner.values_content[0]


def test_manifest_helm_deployer_blocks_missing_binding_mapping_source(
    tmp_path: Path,
) -> None:
    catalog_root = tmp_path / "catalog"
    db_path = tmp_path / "nephos.db"
    manifest_path = _write_app_with_runtime_mappings(catalog_root)
    migrate_database(db_path=db_path)
    repo = DesiredStateRepository(db_path)
    helm = HelmRuntime(
        config=HelmRuntimeConfig(),
        runner=FakeRunner(),
        temp_dir=tmp_path,
    )
    deployer = ManifestHelmDeployer(repository=repo, helm_runtime=helm)
    with repo.transaction() as tx:
        tx.create_app_instance(
            slug="paperless",
            catalog_name="paperless",
            catalog_source_id="default",
            catalog_source_path=str(manifest_path),
            manifest_digest="sha256:paperless",
        )

    with pytest.raises(RuntimeBlockedError, match="Binding database is not ready"):
        deployer.deploy(target_type="app_instance", slug="paperless")


def test_manifest_binding_value_source_reads_redacted_binding_secret() -> None:
    source = ManifestBindingValueSource(
        {
            ("paperless", "database"): {
                "uri": "postgresql://paperless:secret@postgres:5432/paperless"
            }
        }
    )

    assert source.get_binding_values(
        app_slug="paperless",
        service_slug="postgres",
        alias="database",
        capability="postgres",
    ) == {"uri": "postgresql://paperless:secret@postgres:5432/paperless"}


def test_manifest_helm_deployer_uninstalls_runtime_release() -> None:
    runner = FakeRunner()
    helm = HelmRuntime(config=HelmRuntimeConfig(), runner=runner)
    deployer = ManifestHelmDeployer(
        repository=DesiredStateRepository(Path("/tmp/unused.db")),
        helm_runtime=helm,
    )

    deployer.uninstall(target_type="app_instance", slug="paperless")

    assert runner.commands[0].args[:3] == ["helm", "uninstall", "app-paperless"]


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
