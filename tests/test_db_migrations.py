import sqlite3
from importlib import resources
from pathlib import Path

import pytest

from nephos_api.db import MigrationStateError, migrate_database


def _versions(db_path: Path) -> list[str]:
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
    return [row[0] for row in rows]


def _table_names(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    return {row[0] for row in rows}


def test_migrations_are_packaged_resources() -> None:
    migrations_dir = resources.files("nephos_api").joinpath("migrations")

    migration_names = sorted(
        migration.name
        for migration in migrations_dir.iterdir()
        if migration.is_file() and migration.name.endswith(".sql")
    )

    assert migration_names == [
        "0000_initial.sql",
        "0001_add_binding_protocol.sql",
        "0002_add_admin_accounts.sql",
        "0003_add_platform_domain_service_portals.sql",
        "0004_add_admin_tokens.sql",
        "0005_add_reconciliation_attempts.sql",
    ]


def test_migrate_database_applies_initial_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "nephos.db"

    migrate_database(db_path=db_path)

    assert _versions(db_path) == [
        "0000_initial",
        "0001_add_binding_protocol",
        "0002_add_admin_accounts",
        "0003_add_platform_domain_service_portals",
        "0004_add_admin_tokens",
        "0005_add_reconciliation_attempts",
    ]
    assert {
        "app_instances",
        "service_instances",
        "bindings",
        "platform_domains",
        "status_snapshots",
        "reconciliation_requests",
        "admin_accounts",
        "schema_migrations",
    }.issubset(_table_names(db_path))


def test_migrate_database_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "nephos.db"

    migrate_database(db_path=db_path)
    migrate_database(db_path=db_path)

    assert _versions(db_path) == [
        "0000_initial",
        "0001_add_binding_protocol",
        "0002_add_admin_accounts",
        "0003_add_platform_domain_service_portals",
        "0004_add_admin_tokens",
        "0005_add_reconciliation_attempts",
    ]


def test_binding_protocol_migration_adds_nullable_protocol(tmp_path: Path) -> None:
    db_path = tmp_path / "nephos.db"

    migrate_database(db_path=db_path)

    with sqlite3.connect(db_path) as connection:
        columns = {
            row[1]: row[2]
            for row in connection.execute("PRAGMA table_info(bindings)").fetchall()
        }
    assert columns["protocol"] == "TEXT"


def test_service_portal_migration_defaults_existing_domains_to_denied(
    tmp_path: Path,
) -> None:
    # ADR 20260726: applying the migration must not expose a portal that was not
    # already reachable, so the column defaults to 0 for pre-existing rows.
    db_path = tmp_path / "nephos.db"

    migrate_database(db_path=db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO platform_domains(
                id, name, domain, is_default, generation, created_at, updated_at
            )
            VALUES ('domain_1', 'local', 'nephos.lcl', 1, 1, 'now', 'now')
            """
        )
        allows_service_portals = connection.execute(
            "SELECT allows_service_portals FROM platform_domains WHERE id = 'domain_1'"
        ).fetchone()[0]
    assert allows_service_portals == 0


def test_migrate_database_rejects_unknown_applied_versions(tmp_path: Path) -> None:
    db_path = tmp_path / "nephos.db"
    migrate_database(db_path=db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            ("9999_missing", "2026-05-23T00:00:00Z"),
        )

    with pytest.raises(MigrationStateError, match="unknown applied migration"):
        migrate_database(db_path=db_path)


def test_initial_schema_enforces_lifecycle_constraints(tmp_path: Path) -> None:
    db_path = tmp_path / "nephos.db"
    migrate_database(db_path=db_path)

    with (
        sqlite3.connect(db_path) as connection,
        pytest.raises(sqlite3.IntegrityError),
    ):
        connection.execute(
            """
            INSERT INTO app_instances(
                id,
                slug,
                catalog_kind,
                catalog_name,
                catalog_source_id,
                catalog_source_path,
                manifest_digest,
                lifecycle,
                generation,
                config_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "appinst_bad",
                "paperless",
                "App",
                "paperless",
                "default",
                "catalog/apps/paperless/app.yaml",
                "sha256:test",
                "paused",
                1,
                "{}",
                "2026-05-23T00:00:00Z",
                "2026-05-23T00:00:00Z",
            ),
        )
