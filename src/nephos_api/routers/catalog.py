from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Request

from nephos_api.catalog import CatalogLoader

router = APIRouter(prefix="/catalog", tags=["catalog"])


def _loader(request: Request) -> CatalogLoader:
    return CatalogLoader(request.app.state.settings)


def _list_entries(
    request: Request,
    kind: Literal["App", "Service"],
    source: str | None,
) -> dict[str, Any]:
    return {"items": _loader(request).list_entries(kind, source_id=source)}


def _get_entry(
    request: Request,
    kind: Literal["App", "Service"],
    name: str,
    source: str | None,
) -> dict[str, Any]:
    return _loader(request).get_entry(kind, name, source_id=source)


@router.get("/apps")
def list_apps(request: Request, source: str | None = None) -> dict[str, Any]:
    return _list_entries(request, "App", source)


@router.get("/apps/{name}")
def get_app(request: Request, name: str, source: str | None = None) -> dict[str, Any]:
    return _get_entry(request, "App", name, source)


@router.get("/services")
def list_services(request: Request, source: str | None = None) -> dict[str, Any]:
    return _list_entries(request, "Service", source)


@router.get("/services/{name}")
def get_service(request: Request, name: str, source: str | None = None) -> dict[str, Any]:
    return _get_entry(request, "Service", name, source)
