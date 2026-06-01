from __future__ import annotations

import re
import sqlite3
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
_MIGRATION_VERSION_RE = re.compile(r"^[0-9]{4}_[a-z0-9_]+$")


class MigrationStateError(RuntimeError):
    """Raised when migration state cannot be trusted."""


def connect_database(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def migrate_database(
    *,
    db_path: Path,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> None:
    migrations = _migration_files(migrations_dir)
    available_versions = {path.stem for path in migrations}

    with connect_database(db_path) as connection:
        applied_versions = set(_applied_versions(connection))
        unknown_versions = applied_versions - available_versions
        if unknown_versions:
            unknown = ", ".join(sorted(unknown_versions))
            raise MigrationStateError(
                f"unknown applied migration version(s): {unknown}"
            )

        for migration in migrations:
            if migration.stem in applied_versions:
                continue
            _apply_migration(connection, migration)


def reset_database(
    *,
    db_path: Path,
    force: bool,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> None:
    if not force:
        raise ValueError("db reset requires --force")

    sidecar_paths = (
        db_path,
        db_path.with_name(f"{db_path.name}-wal"),
        db_path.with_name(f"{db_path.name}-shm"),
    )
    for path in sidecar_paths:
        if path.exists():
            path.unlink()
    migrate_database(db_path=db_path, migrations_dir=migrations_dir)


def _migration_files(migrations_dir: Path) -> list[Path]:
    if not migrations_dir.exists():
        raise MigrationStateError(
            f"migrations directory does not exist: {migrations_dir}"
        )

    migrations = sorted(migrations_dir.glob("*.sql"))
    if not migrations:
        raise MigrationStateError(f"no SQL migrations found in {migrations_dir}")

    for migration in migrations:
        if not _MIGRATION_VERSION_RE.fullmatch(migration.stem):
            raise MigrationStateError(f"invalid migration filename: {migration.name}")
    return migrations


def _applied_versions(connection: sqlite3.Connection) -> list[str]:
    exists = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = 'schema_migrations'
        """
    ).fetchone()
    if not exists:
        return []

    rows = connection.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()
    return [row["version"] for row in rows]


def _apply_migration(connection: sqlite3.Connection, migration: Path) -> None:
    script = migration.read_text()
    timestamp = utc_now()
    try:
        connection.executescript(
            f"""
            BEGIN;
            {script}
            INSERT INTO schema_migrations(version, applied_at)
            VALUES ('{migration.stem}', '{timestamp}');
            COMMIT;
            """
        )
    except sqlite3.Error as exc:
        with suppress(sqlite3.Error):
            connection.execute("ROLLBACK")
        raise MigrationStateError(
            f"failed to apply migration {migration.name}: {exc}"
        ) from exc


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
