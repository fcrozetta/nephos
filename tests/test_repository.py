import sqlite3
from pathlib import Path

import pytest

from nephos_api.db import migrate_database
from nephos_api.repository import DesiredStateRepository


def _migrated_repo(tmp_path: Path) -> DesiredStateRepository:
    db_path = tmp_path / "nephos.db"
    migrate_database(db_path=db_path)
    return DesiredStateRepository(db_path)


def test_repository_transaction_rolls_back_on_error(tmp_path: Path) -> None:
    repo = _migrated_repo(tmp_path)

    with pytest.raises(RuntimeError, match="boom"), repo.transaction() as tx:
        tx.create_service_instance(
            slug="postgres",
            catalog_name="postgres",
            catalog_source_id="default",
            catalog_source_path="catalog/services/postgres/service.yaml",
            manifest_digest="sha256:postgres",
        )
        raise RuntimeError("boom")

    with sqlite3.connect(repo.db_path) as connection:
        count = connection.execute("SELECT count(*) FROM service_instances").fetchone()[
            0
        ]
    assert count == 0


def test_create_service_instance_and_reconciliation_request(tmp_path: Path) -> None:
    repo = _migrated_repo(tmp_path)

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

    assert service.id.startswith("svcinst_")
    assert service.slug == "postgres"
    assert service.lifecycle == "running"
    assert request.id.startswith("reconcile_")
    assert request.state == "pending"

    with sqlite3.connect(repo.db_path) as connection:
        service_rows = connection.execute(
            "SELECT slug, generation FROM service_instances"
        ).fetchall()
        request_rows = connection.execute(
            "SELECT target_type, target_id, target_generation, action, state "
            "FROM reconciliation_requests"
        ).fetchall()
    assert service_rows == [("postgres", 1)]
    assert request_rows == [("service_instance", service.id, 1, "install", "pending")]


def test_create_app_binding_platform_domain_and_status(tmp_path: Path) -> None:
    repo = _migrated_repo(tmp_path)

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
            catalog_source_path="catalog/apps/paperless/app.yaml",
            manifest_digest="sha256:paperless",
        )
        binding = tx.create_binding(
            app_instance_id=app.id,
            service_instance_id=service.id,
            alias="database",
            capability="sql",
            protocol="postgres",
            output_summary={"redacted": True},
        )
        domain = tx.create_platform_domain(
            name="local",
            domain="nephos.local",
            is_default=True,
        )
        status = tx.upsert_status_snapshot(
            resource_type="app_instance",
            resource_id=app.id,
            level="pending",
            lifecycle=app.lifecycle,
            reconciliation="pending",
            reason="install_requested",
            message="Install request is pending reconciliation.",
            evidence=[{"source": "nephos", "subject": app.slug}],
            observed_generation=app.generation,
        )

    assert app.id.startswith("appinst_")
    assert binding.id.startswith("binding_")
    assert domain.id.startswith("domain_")
    assert status.id.startswith("status_")

    with sqlite3.connect(repo.db_path) as connection:
        binding_row = connection.execute(
            "SELECT alias, capability, protocol, output_summary_json FROM bindings"
        ).fetchone()
        domain_row = connection.execute(
            "SELECT name, domain, is_default FROM platform_domains"
        ).fetchone()
        status_row = connection.execute(
            "SELECT level, reason, observed_generation FROM status_snapshots"
        ).fetchone()
    assert binding_row == ("database", "sql", "postgres", '{"redacted": true}')
    assert domain_row == ("local", "nephos.local", 1)
    assert status_row == ("pending", "install_requested", 1)
