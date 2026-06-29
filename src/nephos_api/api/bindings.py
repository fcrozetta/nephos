from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request

from nephos_api.api.snapshots import status_snapshot
from nephos_api.errors import NephosError
from nephos_api.repository import DesiredStateRepository

router = APIRouter(prefix="/bindings", tags=["bindings"])


@router.get("")
def list_bindings(request: Request) -> dict[str, list[dict[str, Any]]]:
    repo = _repo(request)
    return {
        "bindings": [
            _binding_snapshot(request, row) for row in repo.list_binding_rows()
        ]
    }


@router.get("/{binding_id}")
def get_binding(binding_id: str, request: Request) -> dict[str, Any]:
    row = _require_binding(request, binding_id)
    return _binding_snapshot(request, row)


@router.post("/{binding_id}/actions/reconcile", status_code=202)
def reconcile_binding(binding_id: str, request: Request) -> dict[str, Any]:
    repo = _repo(request)
    row = _require_binding(request, binding_id)
    with repo.transaction() as tx:
        reconciliation = tx.create_reconciliation_request(
            target_type="binding",
            target_id=binding_id,
            target_generation=int(row["generation"]),
            action="reconcile",
            target_snapshot={"id": binding_id, "alias": row["alias"]},
        )
    return {
        "resource": _binding_snapshot(request, row),
        "reconciliation": {
            "id": reconciliation.id,
            "state": reconciliation.state,
        },
    }


def _require_binding(request: Request, binding_id: str) -> dict[str, object]:
    row = _repo(request).get_binding_row(binding_id)
    if row is None:
        raise NephosError(
            status_code=404,
            code="binding_not_found",
            message="Binding was not found.",
            details={"id": binding_id},
        )
    return row


def _binding_snapshot(request: Request, row: dict[str, object]) -> dict[str, Any]:
    repo = _repo(request)
    return {
        "id": row["id"],
        "alias": row["alias"],
        "capability": row["capability"],
        "protocol": row["protocol"],
        "appInstance": {
            "id": row["app_instance_id"],
            "slug": row["app_instance_slug"],
        },
        "serviceInstance": {
            "id": row["service_instance_id"],
            "slug": row["service_instance_slug"],
        },
        "output": _json_dict(row["output_summary_json"]),
        "status": status_snapshot(
            repo,
            resource_type="binding",
            resource_id=str(row["id"]),
        ),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def _repo(request: Request) -> DesiredStateRepository:
    return DesiredStateRepository(request.app.state.settings.db_path)


def _json_dict(value: object) -> dict[str, Any]:
    if not isinstance(value, str):
        return {}
    return json.loads(value)
