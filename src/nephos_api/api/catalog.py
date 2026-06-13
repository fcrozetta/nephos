from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from nephos_api.catalog import (
    CatalogAmbiguousError,
    CatalogEntryNotFoundError,
    CatalogLoader,
    CatalogSourceNotFoundError,
    CatalogValidationError,
)
from nephos_api.domain import InvalidMachineIdentifierError, validate_machine_identifier
from nephos_api.errors import NephosError

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/apps")
def list_apps(request: Request) -> dict[str, list[dict[str, Any]]]:
    return {"apps": _loader(request).list_apps()}


@router.get("/apps/{name}")
def get_app(
    name: str,
    request: Request,
    source: str | None = None,
) -> dict[str, Any]:
    _validate_catalog_name(name)
    return _handle_catalog_errors(lambda: _loader(request).get_app(name, source=source))


@router.get("/services")
def list_services(request: Request) -> dict[str, list[dict[str, Any]]]:
    return {"services": _loader(request).list_services()}


@router.get("/services/{name}")
def get_service(
    name: str,
    request: Request,
    source: str | None = None,
) -> dict[str, Any]:
    _validate_catalog_name(name)
    return _handle_catalog_errors(
        lambda: _loader(request).get_service(name, source=source)
    )


def _loader(request: Request) -> CatalogLoader:
    return CatalogLoader(request.app.state.settings.catalog_roots)


def _validate_catalog_name(name: str) -> None:
    try:
        validate_machine_identifier(name)
    except InvalidMachineIdentifierError as exc:
        raise NephosError(
            status_code=400,
            code="catalog_name_invalid",
            message="Catalog name is invalid.",
            details={"name": name},
        ) from exc


def _handle_catalog_errors(call: Any) -> dict[str, Any]:
    try:
        return call()
    except CatalogAmbiguousError as exc:
        raise NephosError(
            status_code=409,
            code="catalog_entry_ambiguous",
            message="Catalog entry is ambiguous.",
            details={"kind": exc.kind, "name": exc.name, "sources": exc.sources},
        ) from exc
    except CatalogSourceNotFoundError as exc:
        raise NephosError(
            status_code=404,
            code="catalog_source_not_found",
            message="Catalog source was not found.",
            details={"source": exc.source},
        ) from exc
    except CatalogEntryNotFoundError as exc:
        raise NephosError(
            status_code=404,
            code="catalog_entry_not_found",
            message="Catalog entry was not found.",
            details={"kind": exc.kind, "name": exc.name},
        ) from exc
    except CatalogValidationError as exc:
        raise NephosError(
            status_code=400,
            code="catalog_entry_invalid",
            message="Catalog entry is invalid.",
            details={"error": str(exc)},
        ) from exc
