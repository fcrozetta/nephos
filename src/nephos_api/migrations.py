from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from nephos_api.config import Settings
from nephos_api.db import connect
from nephos_api.domain import utc_now

SCHEMA_MIGRATIONS_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class MigrationResult:
    applied: tuple[str, ...]
    db_path: Path


def migration_files(migrations_dir: Path = Path("migrations")) -> tuple[Path, ...]:
    if not migrations_dir.exists():
        raise RuntimeError(f"migrations directory not found: {migrations_dir}")
    return tuple(sorted(migrations_dir.glob("*.sql"), key=lambda path: path.name))


def _ensure_schema_migrations(connection: sqlite3.Connection) -> None:
    connection.execute(SCHEMA_MIGRATIONS_SQL)


def _applied_versions(connection: sqlite3.Connection) -> tuple[str, ...]:
    rows = connection.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    return tuple(row["version"] for row in rows)


def _sql_statements(script: str) -> tuple[str, ...]:
    statements: list[str] = []
    buffer: list[str] = []
    for line in script.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buffer.append(line)
        candidate = "\n".join(buffer)
        if sqlite3.complete_statement(candidate):
            statements.append(candidate)
            buffer.clear()
    if buffer:
        raise RuntimeError("migration contains incomplete SQL statement")
    return tuple(statements)


def apply_migrations(
    settings: Settings,
    *,
    migrations_dir: Path = Path("migrations"),
) -> MigrationResult:
    files = migration_files(migrations_dir)
    file_versions = tuple(path.stem for path in files)

    with connect(settings.db_path) as connection:
        _ensure_schema_migrations(connection)
        applied_versions = _applied_versions(connection)
        unknown_versions = sorted(set(applied_versions) - set(file_versions))
        if unknown_versions:
            joined = ", ".join(unknown_versions)
            raise RuntimeError(f"database has applied migrations missing locally: {joined}")
        expected_prefix = file_versions[: len(applied_versions)]
        if applied_versions != expected_prefix:
            raise RuntimeError(
                "database migration state is dirty: applied versions are not a local prefix"
            )

        pending_files = files[len(applied_versions) :]
        applied_now: list[str] = []
        for path in pending_files:
            statements = _sql_statements(path.read_text())
            connection.execute("BEGIN;")
            try:
                for statement in statements:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (path.stem, utc_now()),
                )
            except Exception:
                connection.rollback()
                raise
            else:
                connection.commit()
                applied_now.append(path.stem)

    return MigrationResult(applied=tuple(applied_now), db_path=settings.db_path)


def reset_database(settings: Settings, *, force: bool) -> MigrationResult:
    if not force:
        raise RuntimeError("refusing to reset database without --force")
    if str(settings.db_path) != ":memory:":
        for suffix in ("", "-wal", "-shm"):
            path = Path(f"{settings.db_path}{suffix}")
            if path.exists():
                path.unlink()
    return apply_migrations(settings)
