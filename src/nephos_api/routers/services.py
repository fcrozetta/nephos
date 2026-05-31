from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from nephos_api.repositories import ServiceInstanceRepository
from nephos_api.schemas import LifecycleActionRequest, ServiceInstallRequest

router = APIRouter(prefix="/services", tags=["services"])


def _repository(request: Request) -> ServiceInstanceRepository:
    return ServiceInstanceRepository(request.app.state.settings)


@router.get("")
def list_services(request: Request) -> dict[str, Any]:
    return {"items": _repository(request).list_services()}


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def install_service(request: Request, body: ServiceInstallRequest) -> JSONResponse:
    envelope = _repository(request).install_service(
        catalog_ref=body.catalog_ref.model_dump(exclude_none=True),
        instance_name=body.instance_name,
        config=body.config,
    )
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=envelope)


@router.get("/{service_instance}")
def get_service(request: Request, service_instance: str) -> dict[str, Any]:
    return _repository(request).get_service(slug=service_instance)


@router.post("/{service_instance}/actions/reconcile", status_code=status.HTTP_202_ACCEPTED)
def reconcile_service(request: Request, service_instance: str) -> JSONResponse:
    envelope = _repository(request).reconcile(slug=service_instance)
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=envelope)


@router.post("/{service_instance}/actions/{action}", status_code=status.HTTP_202_ACCEPTED)
def lifecycle_action(
    request: Request,
    service_instance: str,
    action: str,
    body: LifecycleActionRequest | None = None,
) -> JSONResponse:
    body = body or LifecycleActionRequest()
    envelope = _repository(request).lifecycle_action(
        slug=service_instance,
        action=action,
        force=body.force,
        confirm=body.confirm,
    )
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=envelope)
