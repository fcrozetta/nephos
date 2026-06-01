import sqlite3
from pathlib import Path

from nephos_api.db import migrate_database
from nephos_api.reconciler import Reconciler
from nephos_api.repository import DesiredStateRepository


def _repo(tmp_path: Path) -> DesiredStateRepository:
    db_path = tmp_path / "nephos.db"
    migrate_database(db_path=db_path)
    return DesiredStateRepository(db_path)


def test_reconciler_returns_zero_when_no_requests_are_pending(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    assert Reconciler(repo).run_once() == 0


def test_reconciler_marks_missing_runtime_handler_as_blocked(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
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

    assert Reconciler(repo).run_once() == 1

    with sqlite3.connect(repo.db_path) as connection:
        request_row = connection.execute(
            "SELECT state, error FROM reconciliation_requests WHERE id = ?",
            (request.id,),
        ).fetchone()
        status_row = connection.execute(
            """
            SELECT level, reconciliation, reason, message, observed_generation
            FROM status_snapshots
            WHERE resource_type = ? AND resource_id = ?
            """,
            ("service_instance", service.id),
        ).fetchone()

    assert request_row == (
        "blocked",
        "No runtime handler is implemented for service_instance install.",
    )
    assert status_row == (
        "blocked",
        "blocked",
        "runtime_handler_missing",
        "No runtime handler is implemented for service_instance install.",
        1,
    )
