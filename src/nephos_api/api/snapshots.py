from __future__ import annotations

import json
from typing import Any

from nephos_api.repository import DesiredStateRepository


def status_snapshot(
    repo: DesiredStateRepository,
    *,
    resource_type: str,
    resource_id: str,
) -> dict[str, Any] | None:
    row = repo.get_status_snapshot(
        resource_type=resource_type,
        resource_id=resource_id,
    )
    if row is None:
        return None
    return {
        "level": row["level"],
        "lifecycle": row["lifecycle"],
        "reconciliation": row["reconciliation"],
        "reason": row["reason"],
        "message": row["message"],
        "evidence": _json_list(row["evidence_json"]),
        "observedAt": row["observed_at"],
    }


def compact_status_snapshot(
    repo: DesiredStateRepository,
    *,
    resource_type: str,
    resource_id: str,
) -> dict[str, Any] | None:
    snapshot = status_snapshot(
        repo,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    if snapshot is None:
        return None
    return {
        "level": snapshot["level"],
        "reason": snapshot["reason"],
        "message": snapshot["message"],
        "observedAt": snapshot["observedAt"],
    }


def _json_list(value: object) -> list[Any]:
    if not isinstance(value, str):
        return []
    decoded = json.loads(value)
    return decoded if isinstance(decoded, list) else []
