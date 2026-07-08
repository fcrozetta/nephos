from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, Field

from nephos_api.domain import (
    InvalidDomainSuffixError,
    InvalidMachineIdentifierError,
    PlatformDomain,
)
from nephos_api.errors import NephosError
from nephos_api.repository import DesiredStateRepository

router = APIRouter(prefix="/platform/config/domains", tags=["platform"])


class PlatformDomainCreate(BaseModel):
    name: str
    domain: str
    default: bool = Field(default=False)


@router.get("")
def list_platform_domains(request: Request) -> dict[str, list[dict[str, Any]]]:
    repo = _repo(request)
    return {
        "domains": [_domain_payload(domain) for domain in repo.list_platform_domains()]
    }


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def add_platform_domain(
    payload: PlatformDomainCreate,
    request: Request,
) -> dict[str, Any]:
    repo = _repo(request)

    try:
        with repo.transaction() as tx:
            is_default = payload.default or tx.count_platform_domains() == 0
            if is_default:
                tx.clear_default_platform_domains()
            domain = tx.create_platform_domain(
                name=payload.name,
                domain=payload.domain,
                is_default=is_default,
            )
            reconciliation = tx.create_reconciliation_request(
                target_type="platform_domain",
                target_id=domain.id,
                target_generation=domain.generation,
                action="create",
                target_snapshot=_domain_payload(domain),
            )
    except InvalidDomainSuffixError as exc:
        raise NephosError(
            status_code=400,
            code="invalid_platform_domain",
            message="Platform domain must be a DNS suffix.",
            details={"domain": payload.domain},
        ) from exc
    except InvalidMachineIdentifierError as exc:
        raise NephosError(
            status_code=400,
            code="invalid_platform_domain_name",
            message="Platform domain name must be a machine identifier.",
            details={"name": payload.name},
        ) from exc
    except sqlite3.IntegrityError as exc:
        raise NephosError(
            status_code=409,
            code="platform_domain_conflict",
            message="Platform domain already exists.",
            details={"name": payload.name, "domain": payload.domain},
        ) from exc

    return {
        "resource": _domain_payload(domain),
        "reconciliation": {
            "id": reconciliation.id,
            "state": reconciliation.state,
        },
    }


@router.post("/{name}/actions/set-default", status_code=status.HTTP_202_ACCEPTED)
def set_default_platform_domain(name: str, request: Request) -> dict[str, Any]:
    repo = _repo(request)
    with repo.transaction() as tx:
        if tx.get_platform_domain_by_name(name) is None:
            raise _not_found(name)
        domain = tx.set_default_platform_domain(name)
        reconciliation = tx.create_reconciliation_request(
            target_type="platform_domain",
            target_id=domain.id,
            target_generation=domain.generation,
            action="set-default",
            target_snapshot=_domain_payload(domain),
        )
    return _mutation_response(domain, reconciliation.id, reconciliation.state)


@router.post("/{name}/actions/remove", status_code=status.HTTP_202_ACCEPTED)
def remove_platform_domain(name: str, request: Request) -> dict[str, Any]:
    repo = _repo(request)
    with repo.transaction() as tx:
        domain = tx.get_platform_domain_by_name(name)
        if domain is None:
            raise _not_found(name)
        if domain.is_default:
            raise NephosError(
                status_code=409,
                code="platform_domain_default_required",
                message="Cannot remove the default platform domain.",
                details={"name": name},
            )
        removed = tx.remove_platform_domain(name)
        reconciliation = tx.create_reconciliation_request(
            target_type="platform_domain",
            target_id=removed.id,
            target_generation=removed.generation,
            action="remove",
            target_snapshot=_domain_payload(removed),
        )
    return _mutation_response(removed, reconciliation.id, reconciliation.state)


@router.post("/actions/reconcile", status_code=status.HTTP_202_ACCEPTED)
def reconcile_platform_domains(request: Request) -> dict[str, Any]:
    repo = _repo(request)
    domains = repo.list_platform_domains()
    if not domains:
        raise NephosError(
            status_code=409,
            code="platform_domain_required",
            message="At least one platform domain is required.",
        )
    target = next((domain for domain in domains if domain.is_default), domains[0])
    with repo.transaction() as tx:
        reconciliation = tx.create_reconciliation_request(
            target_type="platform_domain",
            target_id=target.id,
            target_generation=target.generation,
            action="reconcile",
            target_snapshot={
                "domains": [_domain_payload(domain) for domain in domains],
            },
        )
    return {
        "resource": {
            "domains": [_domain_payload(domain) for domain in domains],
        },
        "reconciliation": {
            "id": reconciliation.id,
            "state": reconciliation.state,
        },
    }


def _repo(request: Request) -> DesiredStateRepository:
    return DesiredStateRepository(request.app.state.settings.db_path)


def _mutation_response(
    domain: PlatformDomain,
    reconciliation_id: str,
    reconciliation_state: str,
) -> dict[str, Any]:
    return {
        "resource": _domain_payload(domain),
        "reconciliation": {
            "id": reconciliation_id,
            "state": reconciliation_state,
        },
    }


def _not_found(name: str) -> NephosError:
    return NephosError(
        status_code=404,
        code="platform_domain_not_found",
        message="Platform domain was not found.",
        details={"name": name},
    )


def _domain_payload(domain: PlatformDomain) -> dict[str, Any]:
    return {
        "id": domain.id,
        "name": domain.name,
        "domain": domain.domain,
        "default": domain.is_default,
        "generation": domain.generation,
        "createdAt": domain.created_at,
        "updatedAt": domain.updated_at,
    }
