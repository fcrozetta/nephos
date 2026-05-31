from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from nephos_api.repositories import BindingRepository

router = APIRouter(prefix="/bindings", tags=["bindings"])


def _repository(request: Request) -> BindingRepository:
    return BindingRepository(request.app.state.settings)


@router.get("/{binding_id}")
def get_binding(request: Request, binding_id: str) -> dict[str, Any]:
    return _repository(request).get_binding(binding_id=binding_id)


@router.post("/{binding_id}/actions/reconcile", status_code=status.HTTP_202_ACCEPTED)
def reconcile_binding(request: Request, binding_id: str) -> JSONResponse:
    envelope = _repository(request).reconcile(binding_id=binding_id)
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=envelope)
