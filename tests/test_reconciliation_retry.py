from pathlib import Path

from nephos_api.db import connect_database, migrate_database, utc_now_minus
from nephos_api.repository import (
    RECONCILE_RETRY_ATTEMPT_CAP,
    DesiredStateRepository,
)


def _repo(tmp_path: Path) -> DesiredStateRepository:
    db_path = tmp_path / "nephos.db"
    migrate_database(db_path=db_path)
    return DesiredStateRepository(db_path)


def _request(repo, *, target_id, action="install"):
    with repo.transaction() as tx:
        return tx.create_reconciliation_request(
            target_type="app_instance",
            target_id=target_id,
            target_generation=1,
            action=action,
            target_snapshot={"slug": target_id},
        )


def _force_blocked(repo, request_id, *, attempts, updated_at):
    """Backdate a blocked request; the public API cannot age one."""
    with connect_database(repo.db_path) as connection:
        connection.execute(
            "UPDATE reconciliation_requests "
            "SET state='blocked', attempts=?, updated_at=? WHERE id=?",
            (attempts, updated_at, request_id),
        )
        connection.commit()


def _attempts(repo, request_id) -> int:
    with connect_database(repo.db_path) as connection:
        row = connection.execute(
            "SELECT attempts FROM reconciliation_requests WHERE id=?",
            (request_id,),
        ).fetchone()
    return int(row["attempts"])


def test_blocked_request_is_reclaimed_after_the_retry_interval(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    request = _request(repo, target_id="appinst_1", action="destroy")
    _force_blocked(repo, request.id, attempts=1, updated_at=utc_now_minus(600))

    claimed = repo.claim_next_reconciliation_request()

    assert claimed is not None
    assert claimed["id"] == request.id
    assert claimed["state"] == "running"


def test_blocked_request_is_not_reclaimed_before_the_retry_interval(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    request = _request(repo, target_id="appinst_1", action="destroy")
    _force_blocked(repo, request.id, attempts=1, updated_at=utc_now_minus(5))

    assert repo.claim_next_reconciliation_request() is None


def test_blocked_request_stops_being_reclaimed_at_the_cap(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    request = _request(repo, target_id="appinst_1", action="destroy")
    _force_blocked(
        repo,
        request.id,
        attempts=RECONCILE_RETRY_ATTEMPT_CAP,
        updated_at=utc_now_minus(600),
    )

    assert repo.claim_next_reconciliation_request() is None


def test_pending_work_is_claimed_ahead_of_a_retry_eligible_blocked_request(
    tmp_path: Path,
) -> None:
    # A permanently blocked request must not starve new work on the single
    # serialized worker while it burns its attempts.
    repo = _repo(tmp_path)
    blocked = _request(repo, target_id="appinst_1", action="destroy")
    _force_blocked(repo, blocked.id, attempts=1, updated_at=utc_now_minus(600))
    pending = _request(repo, target_id="appinst_2")

    claimed = repo.claim_next_reconciliation_request()

    assert claimed["id"] == pending.id


def test_marking_a_request_blocked_increments_attempts(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    request = _request(repo, target_id="appinst_1")

    with repo.transaction() as tx:
        tx.update_reconciliation_request_state(
            request_id=request.id,
            state="blocked",
            error="nope",
            increment_attempts=True,
        )

    assert _attempts(repo, request.id) == 1


def test_marking_a_request_succeeded_leaves_attempts_alone(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    request = _request(repo, target_id="appinst_1")

    with repo.transaction() as tx:
        tx.update_reconciliation_request_state(
            request_id=request.id,
            state="succeeded",
        )

    assert _attempts(repo, request.id) == 0
