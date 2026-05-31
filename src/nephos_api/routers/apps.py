from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from nephos_api.repositories import AppInstanceRepository
from nephos_api.schemas import AppInstallRequest, LifecycleActionRequest

router = APIRouter(prefix="/apps", tags=["apps"])


def _repository(request: Request) -> AppInstanceRepository:
    return AppInstanceRepository(request.app.state.settings)


@router.get("")
def list_apps(request: Request) -> dict[str, Any]:
    return {"items": _repository(request).list_apps()}


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def install_app(request: Request, body: AppInstallRequest) -> JSONResponse:
    envelope = _repository(request).install_app(
        catalog_ref=body.catalog_ref.model_dump(exclude_none=True),
        instance_name=body.instance_name,
        config=body.config,
        bindings=body.bindings,
    )
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=envelope)


@router.get("/{app_instance}")
def get_app(request: Request, app_instance: str) -> dict[str, Any]:
    return _repository(request).get_app(slug=app_instance)


@router.post("/{app_instance}/actions/reconcile", status_code=status.HTTP_202_ACCEPTED)
def reconcile_app(request: Request, app_instance: str) -> JSONResponse:
    envelope = _repository(request).reconcile(slug=app_instance)
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=envelope)


@router.post("/{app_instance}/actions/{action}", status_code=status.HTTP_202_ACCEPTED)
def lifecycle_action(
    request: Request,
    app_instance: str,
    action: str,
    body: LifecycleActionRequest | None = None,
) -> JSONResponse:
    body = body or LifecycleActionRequest()
    envelope = _repository(request).lifecycle_action(
        slug=app_instance,
        action=action,
        confirm=body.confirm,
    )
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=envelope)
