import sqlite3
from pathlib import Path

import uvicorn
from typer.testing import CliRunner

from nephos_api.cli import app
from nephos_api.dev_reference import ReferenceSmokeResult

_MIGRATION_ROWS = [("0000_initial",), ("0001_add_binding_protocol",)]


def test_cli_db_migrate_creates_database(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "nephos.db"
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["db", "migrate"],
        env={"NEPHOS_API_DB_PATH": str(db_path)},
    )

    assert result.exit_code == 0
    assert db_path.exists()
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute("SELECT version FROM schema_migrations").fetchall()
    assert rows == _MIGRATION_ROWS


def test_cli_init_applies_migrations_and_creates_internal_domain(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "state" / "nephos.db"
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["init"],
        env={
            "NEPHOS_API_DB_PATH": str(db_path),
            "NEPHOS_API_INTERNAL_DOMAIN": "nephos.local",
        },
    )

    assert result.exit_code == 0
    assert "Initialized Nephos API state" in result.output
    assert db_path.exists()
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute("SELECT version FROM schema_migrations").fetchall()
        domains = connection.execute(
            "SELECT name, domain, is_default FROM platform_domains"
        ).fetchall()
        reconciliation_count = connection.execute(
            "SELECT count(*) FROM reconciliation_requests"
        ).fetchone()[0]
    assert rows == _MIGRATION_ROWS
    assert domains == [("internal", "nephos.local", 1)]
    assert reconciliation_count == 0


def test_cli_init_accepts_custom_internal_domain(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "nephos.db"
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["init", "--internal-domain", "home.test"],
        env={"NEPHOS_API_DB_PATH": str(db_path)},
    )

    assert result.exit_code == 0
    assert "home.test" in result.output
    with sqlite3.connect(db_path) as connection:
        domains = connection.execute(
            "SELECT name, domain, is_default FROM platform_domains"
        ).fetchall()
    assert domains == [("internal", "home.test", 1)]


def test_cli_init_uses_env_internal_domain_when_option_is_omitted(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "state" / "nephos.db"
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["init"],
        env={
            "NEPHOS_API_DB_PATH": str(db_path),
            "NEPHOS_API_INTERNAL_DOMAIN": "nephos.localhost",
        },
    )

    assert result.exit_code == 0
    assert "nephos.localhost" in result.output
    with sqlite3.connect(db_path) as connection:
        domains = connection.execute(
            "SELECT name, domain, is_default FROM platform_domains"
        ).fetchall()
    assert domains == [("internal", "nephos.localhost", 1)]


def test_cli_init_does_not_replace_existing_platform_domain(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "nephos.db"
    runner = CliRunner()

    first = runner.invoke(
        app,
        ["init", "--internal-domain", "home.test"],
        env={"NEPHOS_API_DB_PATH": str(db_path)},
    )
    second = runner.invoke(
        app,
        ["init", "--internal-domain", "changed.test"],
        env={"NEPHOS_API_DB_PATH": str(db_path)},
    )

    assert first.exit_code == 0
    assert second.exit_code == 0
    with sqlite3.connect(db_path) as connection:
        domains = connection.execute(
            "SELECT name, domain, is_default FROM platform_domains"
        ).fetchall()
    assert domains == [("internal", "home.test", 1)]


def test_cli_init_rejects_invalid_internal_domain(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "nephos.db"
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["init", "--internal-domain", "http://nephos.local"],
        env={"NEPHOS_API_DB_PATH": str(db_path)},
    )

    assert result.exit_code == 1
    assert "invalid internal domain" in result.output


def test_cli_db_reset_requires_force(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "nephos.db"
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["db", "reset"],
        env={"NEPHOS_API_DB_PATH": str(db_path)},
    )

    assert result.exit_code != 0
    assert "requires --force" in result.output
    assert not db_path.exists()


def test_cli_db_reset_force_recreates_database(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "nephos.db"
    runner = CliRunner()

    migrate = runner.invoke(
        app,
        ["db", "migrate"],
        env={"NEPHOS_API_DB_PATH": str(db_path)},
    )
    reset = runner.invoke(
        app,
        ["db", "reset", "--force"],
        env={"NEPHOS_API_DB_PATH": str(db_path)},
    )

    assert migrate.exit_code == 0
    assert reset.exit_code == 0
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute("SELECT version FROM schema_migrations").fetchall()
    assert rows == _MIGRATION_ROWS


def test_cli_serve_starts_worker_enabled_app(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "nephos.db"
    runner = CliRunner()
    captured = {}

    def fake_run(target, *, host: str, port: int) -> None:
        captured["target"] = target
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr(uvicorn, "run", fake_run)

    result = runner.invoke(
        app,
        ["serve", "--host", "127.0.0.2", "--port", "8765"],
        env={"NEPHOS_API_DB_PATH": str(db_path)},
    )

    assert result.exit_code == 0
    assert captured["host"] == "127.0.0.2"
    assert captured["port"] == 8765
    assert captured["target"].state.reconciler_enabled is True
    assert captured["target"].state.deployer_enabled is True
    assert captured["target"].state.provisioner_enabled is True


def test_cli_serve_applies_migrations_before_starting_app(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "state" / "nephos.db"
    runner = CliRunner()

    def fake_run(_target, *, host: str, port: int) -> None:
        assert host == "127.0.0.1"
        assert port == 8000

    monkeypatch.setattr(uvicorn, "run", fake_run)

    result = runner.invoke(
        app,
        ["serve"],
        env={"NEPHOS_API_DB_PATH": str(db_path)},
    )

    assert result.exit_code == 0
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute("SELECT version FROM schema_migrations").fetchall()
    assert rows == _MIGRATION_ROWS


def test_cli_dev_smoke_runs_nephos_owned_reference_flow(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "state" / "nephos.db"
    runner = CliRunner()
    captured = {}

    def fake_smoke(*, settings, timeout_seconds: int, progress) -> ReferenceSmokeResult:
        captured["settings"] = settings
        captured["timeout_seconds"] = timeout_seconds
        captured["progress"] = progress
        return ReferenceSmokeResult(
            app_slug="reference-web-test",
            service_slug="postgres-test",
            canonical_url="http://reference-web-test.nephos.local",
        )

    monkeypatch.setattr("nephos_api.cli.run_reference_smoke", fake_smoke)

    result = runner.invoke(
        app,
        ["dev", "smoke", "--timeout-seconds", "9"],
        env={
            "NEPHOS_API_DB_PATH": str(db_path),
            "NEPHOS_API_KUBE_CONTEXT": "docker-desktop",
            "PULUMI_CONFIG_PASSPHRASE": "local-test",
        },
    )

    assert result.exit_code == 0
    assert captured["settings"].db_path == db_path
    assert captured["settings"].kube_context == "docker-desktop"
    assert captured["timeout_seconds"] == 9
    assert "Reference smoke test passed" in result.output
    assert "reference-web-test" in result.output
