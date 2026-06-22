from pathlib import Path

import yaml
from typer.testing import CliRunner

from nephos_api.catalog import CatalogLoader
from nephos_api.cli import app
from nephos_api.config import Settings
from nephos_api.dev_backbone import (
    EXPECTED_BINDING_SECRET_KEYS,
    BackboneSmokeResult,
    _verify_key_only_binding_report,
    run_backbone_smoke,
    write_alpha_backbone_catalog,
)


def test_alpha_backbone_catalog_generator_writes_protocol_aware_entries(
    tmp_path: Path,
) -> None:
    catalog_root = tmp_path / "catalog"

    write_alpha_backbone_catalog(catalog_root)

    loader = CatalogLoader((catalog_root,))
    services = {service["name"]: service for service in loader.list_services()}
    assert set(services) == {"arcadedb", "postgres", "seaweedfs", "zitadel"}
    assert _provided_pairs(services["postgres"]) == {("sql", "postgres")}
    assert _provided_pairs(services["zitadel"]) == {
        ("oidc", "oidc"),
        ("service-account", "jwt"),
    }
    assert _provided_pairs(services["seaweedfs"]) == {("object-storage", "s3")}
    assert _provided_pairs(services["arcadedb"]) == {
        ("sql", "arcadedb"),
        ("opencypher", "bolt"),
        ("opencypher", "n4j"),
    }

    app_entry = loader.get_app("backbone-check")
    assert {
        (requirement["alias"], requirement["capability"], requirement["protocol"])
        for requirement in app_entry["requires"]
    } == {
        ("postgres", "sql", "postgres"),
        ("identity", "oidc", "oidc"),
        ("object-storage", "object-storage", "s3"),
        ("graph", "opencypher", "bolt"),
    }


def test_alpha_backbone_catalog_generator_writes_service_config_mappings(
    tmp_path: Path,
) -> None:
    catalog_root = tmp_path / "catalog"

    write_alpha_backbone_catalog(catalog_root)

    manifests = {
        service_name: yaml.safe_load(
            (catalog_root / "services" / service_name / "service.yaml").read_text()
        )
        for service_name in ("postgres", "zitadel", "seaweedfs", "arcadedb")
    }
    assert _config_option_names(manifests["postgres"]) == {
        "storage-size",
        "storage-class-name",
    }
    assert _runtime_mapping_pairs(manifests["postgres"]) == {
        ("storage-size", "storageSize"),
        ("storage-class-name", "storageClassName"),
    }
    assert _config_option_names(manifests["zitadel"]) == {
        "image",
        "external-host",
        "admin-username",
        "admin-password",
        "master-key",
        "database-password",
        "storage-size",
    }
    assert _runtime_mapping_pairs(manifests["zitadel"]) == {
        ("image", "image"),
        ("external-host", "externalHost"),
        ("admin-username", "adminUsername"),
        ("admin-password", "adminPassword"),
        ("master-key", "masterKey"),
        ("database-password", "databasePassword"),
        ("storage-size", "storageSize"),
    }
    assert _config_option_names(manifests["seaweedfs"]) == {
        "image",
        "storage-size",
        "s3-access-key",
        "s3-secret-key",
    }
    assert _runtime_mapping_pairs(manifests["seaweedfs"]) == {
        ("image", "image"),
        ("storage-size", "storageSize"),
        ("s3-access-key", "s3AccessKey"),
        ("s3-secret-key", "s3SecretKey"),
    }
    assert _config_option_names(manifests["arcadedb"]) == {
        "image",
        "storage-size",
        "root-password",
        "enable-gremlin",
        "enable-mongo",
    }
    assert _runtime_mapping_pairs(manifests["arcadedb"]) == {
        ("image", "image"),
        ("storage-size", "storageSize"),
        ("root-password", "rootPassword"),
        ("enable-gremlin", "enableGremlin"),
        ("enable-mongo", "enableMongo"),
    }


def test_backbone_smoke_returns_skip_blocker_without_live_config(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "state" / "nephos.db"

    result = run_backbone_smoke(
        settings=Settings(
            db_path=db_path,
            catalog_roots=(),
            kubeconfig=None,
            kube_context=None,
            internal_domain="nephos.localhost",
        ),
        environ={},
        timeout_seconds=1,
    )

    assert result.status == "skipped"
    assert result.blocker_code == "pulumi_passphrase_missing"
    assert "PULUMI_CONFIG_PASSPHRASE" in result.message
    assert not db_path.exists()


def test_cli_dev_backbone_smoke_reports_skip_blocker(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "state" / "nephos.db"
    runner = CliRunner()

    def fake_smoke(*, settings, timeout_seconds: int, progress) -> BackboneSmokeResult:
        assert settings.db_path == db_path
        assert timeout_seconds == 600
        progress("checked live prerequisites")
        return BackboneSmokeResult(
            status="skipped",
            message="PULUMI_CONFIG_PASSPHRASE is required for live backbone smoke.",
            blocker_code="pulumi_passphrase_missing",
        )

    monkeypatch.setattr("nephos_api.cli.run_backbone_smoke", fake_smoke)

    result = runner.invoke(
        app,
        ["dev", "backbone-smoke", "--timeout-seconds", "600"],
        env={"NEPHOS_API_DB_PATH": str(db_path)},
    )

    assert result.exit_code == 0
    assert "- checked live prerequisites" in result.output
    assert "Alpha backbone smoke skipped" in result.output
    assert "pulumi_passphrase_missing" in result.output


def test_key_only_binding_report_redacts_secret_values() -> None:
    secret_values = {
        "host": "postgres.svc.cluster.local",
        "port": "5432",
        "database": "backbone",
        "username": "app",
        "password": "super-secret",
        "uri": "postgres://app:super-secret@postgres/backbone",
    }

    report = _verify_key_only_binding_report(
        alias="postgres",
        expected_keys=EXPECTED_BINDING_SECRET_KEYS["postgres"],
        secret_values=secret_values,
    )

    assert report == {
        "alias": "postgres",
        "keys": ["database", "host", "password", "port", "uri", "username"],
        "redacted": True,
    }
    assert "super-secret" not in str(report)
    assert "postgres://app" not in str(report)


def test_key_only_binding_report_rejects_missing_or_empty_keys() -> None:
    missing = {"host": "postgres", "port": ""}

    try:
        _verify_key_only_binding_report(
            alias="postgres",
            expected_keys=EXPECTED_BINDING_SECRET_KEYS["postgres"],
            secret_values=missing,
        )
    except RuntimeError as exc:
        assert "missing or empty Secret keys" in str(exc)
        assert "database" in str(exc)
        assert "port" in str(exc)
    else:
        raise AssertionError("expected key verification to fail")


def test_backbone_smoke_desired_state_flow_blocks_on_missing_live_clients(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "state" / "nephos.db"

    result = run_backbone_smoke(
        settings=Settings(
            db_path=db_path,
            catalog_roots=(),
            kubeconfig=None,
            kube_context=None,
            internal_domain="nephos.localhost",
        ),
        environ={"PULUMI_CONFIG_PASSPHRASE": "local-test"},
        timeout_seconds=2,
        live=False,
    )

    assert result.status == "blocked"
    assert result.blocker_code == "binding_provisioner_unavailable"
    assert "live external API details" in result.message


def _provided_pairs(service: dict[str, object]) -> set[tuple[str, str | None]]:
    return {
        (provided["capability"], provided["protocol"])
        for provided in service["provides"]
    }


def _config_option_names(manifest: dict[str, object]) -> set[str]:
    options = manifest["spec"]["config"]["options"]
    return {option["name"] for option in options}


def _runtime_mapping_pairs(manifest: dict[str, object]) -> set[tuple[str, str]]:
    mappings = manifest["spec"]["runtime"]["values"]["mappings"]
    return {
        (mapping["from"]["name"], mapping["to"]["helmValue"])
        for mapping in mappings
    }
