from __future__ import annotations

import sqlite3

import pytest

from nephos_api.config import Settings
from nephos_api.migrations import apply_migrations, reset_database

pytestmark = pytest.mark.unit


def test_migrate_creates_initial_schema(tmp_path):
    settings = Settings(db_path=tmp_path / "nephos.db")

    result = apply_migrations(settings)

    assert result.applied == ("0000_initial",)
    with sqlite3.connect(settings.db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {
            "app_instances",
            "service_instances",
            "bindings",
            "platform_domains",
            "status_snapshots",
            "reconciliation_requests",
            "schema_migrations",
        } <= tables


def test_migrate_is_idempotent(tmp_path):
    settings = Settings(db_path=tmp_path / "nephos.db")

    first = apply_migrations(settings)
    second = apply_migrations(settings)

    assert first.applied == ("0000_initial",)
    assert second.applied == ()
    with sqlite3.connect(settings.db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    assert count == 1


def test_reset_requires_force(tmp_path):
    settings = Settings(db_path=tmp_path / "nephos.db")

    with pytest.raises(RuntimeError, match="--force"):
        reset_database(settings, force=False)


def test_reset_recreates_database(tmp_path):
    settings = Settings(db_path=tmp_path / "nephos.db")
    apply_migrations(settings)

    result = reset_database(settings, force=True)

    assert result.applied == ("0000_initial",)
    with sqlite3.connect(settings.db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    assert count == 1
