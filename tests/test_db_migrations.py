import sqlite3
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


def test_migrate_database_applies_initial_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "nephos.db"

    migrate_database(db_path=db_path)

    assert _versions(db_path) == ["0000_initial"]
    assert {
        "app_instances",
        "service_instances",
        "bindings",
        "platform_domains",
        "status_snapshots",
        "reconciliation_requests",
        "schema_migrations",
    }.issubset(_table_names(db_path))


def test_migrate_database_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "nephos.db"

    migrate_database(db_path=db_path)
    migrate_database(db_path=db_path)

    assert _versions(db_path) == ["0000_initial"]


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
