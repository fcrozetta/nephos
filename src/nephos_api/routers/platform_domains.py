from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from nephos_api.repositories import PlatformDomainRepository
from nephos_api.schemas import PlatformDomainCreate

router = APIRouter(prefix="/platform/config/domains", tags=["platform-domains"])


def _repository(request: Request) -> PlatformDomainRepository:
    return PlatformDomainRepository(request.app.state.settings)


@router.get("")
def list_domains(request: Request) -> dict[str, Any]:
    items = _repository(request).list_domains()
    return {
        "items": items,
        "configured": bool(items) and any(item["default"] for item in items),
    }


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def add_domain(request: Request, body: PlatformDomainCreate) -> JSONResponse:
    envelope = _repository(request).add_domain(
        name=body.name,
        domain=body.domain,
        is_default=body.is_default,
    )
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=envelope)


@router.post("/actions/reconcile", status_code=status.HTTP_202_ACCEPTED)
def reconcile_domains(request: Request) -> JSONResponse:
    envelope = _repository(request).reconcile()
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=envelope)


@router.post("/{name}/actions/set-default", status_code=status.HTTP_202_ACCEPTED)
def set_default_domain(request: Request, name: str) -> JSONResponse:
    envelope = _repository(request).set_default(name=name)
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=envelope)


@router.post("/{name}/actions/remove", status_code=status.HTTP_202_ACCEPTED)
def remove_domain(request: Request, name: str) -> JSONResponse:
    envelope = _repository(request).remove(name=name)
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=envelope)
