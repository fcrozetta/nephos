from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import APIRouter, Request, status
from pydantic import BaseModel, ConfigDict, Field

from nephos_api.api.snapshots import compact_status_snapshot, status_snapshot
from nephos_api.catalog import (
    AppManifest,
    CatalogAmbiguousError,
    CatalogEntryNotFoundError,
    CatalogLoader,
    CatalogSourceNotFoundError,
    CatalogValidationError,
)
from nephos_api.domain import validate_machine_identifier
from nephos_api.errors import NephosError
from nephos_api.repository import DesiredStateRepository

router = APIRouter(tags=["resources"])


class CatalogRef(BaseModel):
    kind: Literal["App", "Service"]
    name: str
    source: str | None = None


class BindingSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    serviceInstance: str


class InstallRequest(BaseModel):
    catalogRef: CatalogRef
    instanceName: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    bindings: dict[str, BindingSelection] = Field(default_factory=dict)


class LifecycleActionBody(BaseModel):
    force: bool = False
    confirm: str | None = None


@router.get("/services")
def list_services(request: Request) -> dict[str, list[dict[str, Any]]]:
    repo = _repo(request)
    return {
        "services": [
            _service_snapshot(request, row) for row in repo.list_service_rows()
        ]
    }


@router.get("/services/{service_instance}")
def get_service(service_instance: str, request: Request) -> dict[str, Any]:
    row = _repo(request).get_service_row(service_instance)
    if row is None:
        raise _not_found("service_not_found", "Service instance was not found.")
    return _service_snapshot(request, row)


@router.post("/services", status_code=status.HTTP_202_ACCEPTED)
def install_service(payload: InstallRequest, request: Request) -> dict[str, Any]:
    if payload.catalogRef.kind != "Service":
        raise NephosError(
            status_code=400,
            code="catalog_kind_mismatch",
            message="Service install requires a Service catalog reference.",
            details={"kind": payload.catalogRef.kind},
        )

    loader = _loader(request)
    catalog_entry = _catalog_or_404(
        lambda: loader.get_service(
            payload.catalogRef.name,
            source=payload.catalogRef.source,
        )
    )
    slug = payload.instanceName or catalog_entry["name"]
    validate_machine_identifier(slug)
    source_path = _catalog_source_path(
        request,
        kind="Service",
        name=catalog_entry["name"],
        source=catalog_entry["source"],
    )
    repo = _repo(request)

    try:
        with repo.transaction() as tx:
            service = tx.create_service_instance(
                slug=slug,
                catalog_name=catalog_entry["name"],
                catalog_version=catalog_entry["version"],
                catalog_source_id=catalog_entry["source"],
                catalog_source_path=str(source_path),
                manifest_digest=catalog_entry["manifestDigest"],
                config=payload.config,
            )
            reconciliation = tx.create_reconciliation_request(
                target_type="service_instance",
                target_id=service.id,
                target_generation=service.generation,
                action="install",
                target_snapshot={"slug": service.slug},
            )
    except sqlite3.IntegrityError as exc:
        raise NephosError(
            status_code=409,
            code="service_instance_conflict",
            message="Service instance already exists.",
            details={"slug": slug},
        ) from exc

    row = repo.get_service_row(service.slug)
    assert row is not None
    return {
        "resource": _service_snapshot(request, row),
        "reconciliation": {"id": reconciliation.id, "state": reconciliation.state},
    }


@router.post("/services/{service_instance}/actions/{action}", status_code=202)
def service_action(
    service_instance: str,
    action: Literal["start", "stop", "remove", "destroy", "reconcile"],
    payload: LifecycleActionBody,
    request: Request,
) -> dict[str, Any]:
    repo = _repo(request)
    row = repo.get_service_row(service_instance)
    if row is None:
        raise _not_found("service_not_found", "Service instance was not found.")

    _reject_lifecycle_mutation_after_destroy_requested(
        slug=service_instance,
        action=action,
        row=row,
    )
    if action in {"stop", "remove", "destroy"} and not _service_action_is_noop(
        row,
        action,
    ):
        dependents = repo.list_dependents_for_service(str(row["id"]))
        if dependents and not payload.force:
            raise _dependency_blocked(dependents)
    if action == "destroy":
        _require_destroy_confirmation(service_instance, payload)

    with repo.transaction() as tx:
        updated = _apply_service_action(tx, service_instance, action, row)
        reconciliation = tx.create_reconciliation_request(
            target_type="service_instance",
            target_id=str(updated["id"]),
            target_generation=int(updated["generation"]),
            action=action,
            target_snapshot={"slug": updated["slug"]},
        )

    return {
        "resource": _service_snapshot(request, updated),
        "reconciliation": {"id": reconciliation.id, "state": reconciliation.state},
    }


@router.get("/apps")
def list_apps(request: Request) -> dict[str, list[dict[str, Any]]]:
    repo = _repo(request)
    return {"apps": [_app_snapshot(request, row) for row in repo.list_app_rows()]}


@router.get("/apps/{app_instance}")
def get_app(app_instance: str, request: Request) -> dict[str, Any]:
    row = _repo(request).get_app_row(app_instance)
    if row is None:
        raise _not_found("app_not_found", "App instance was not found.")
    return _app_snapshot(request, row)


@router.post("/apps", status_code=status.HTTP_202_ACCEPTED)
def install_app(payload: InstallRequest, request: Request) -> dict[str, Any]:
    if payload.catalogRef.kind != "App":
        raise NephosError(
            status_code=400,
            code="catalog_kind_mismatch",
            message="App install requires an App catalog reference.",
            details={"kind": payload.catalogRef.kind},
        )

    loader = _loader(request)
    catalog_entry = _catalog_or_404(
        lambda: loader.get_app(
            payload.catalogRef.name,
            source=payload.catalogRef.source,
        )
    )
    slug = payload.instanceName or catalog_entry["name"]
    validate_machine_identifier(slug)
    source_path = _catalog_source_path(
        request,
        kind="App",
        name=catalog_entry["name"],
        source=catalog_entry["source"],
    )
    _validate_app_config(_load_app_manifest(source_path), payload.config)
    providers = _resolve_binding_providers(
        request,
        catalog_entry,
        selections=payload.bindings,
    )
    repo = _repo(request)

    try:
        with repo.transaction() as tx:
            app = tx.create_app_instance(
                slug=slug,
                catalog_name=catalog_entry["name"],
                catalog_version=catalog_entry["version"],
                catalog_source_id=catalog_entry["source"],
                catalog_source_path=str(source_path),
                manifest_digest=catalog_entry["manifestDigest"],
                config=payload.config,
            )
            for requirement in catalog_entry["requires"]:
                service_row = providers[requirement["alias"]]
                binding = tx.create_binding(
                    app_instance_id=app.id,
                    service_instance_id=str(service_row["id"]),
                    alias=requirement["alias"],
                    capability=requirement["capability"],
                    output_summary={
                        "target": "app-secret",
                        "secretName": f"nephos-bind-{requirement['alias']}",
                        "namespace": f"app-{app.slug}",
                        "keys": ["redacted"],
                        "redacted": True,
                    },
                )
                tx.create_reconciliation_request(
                    target_type="binding",
                    target_id=binding.id,
                    target_generation=binding.generation,
                    action="reconcile",
                    target_snapshot={
                        "id": binding.id,
                        "alias": binding.alias,
                    },
                )
            reconciliation = tx.create_reconciliation_request(
                target_type="app_instance",
                target_id=app.id,
                target_generation=app.generation,
                action="install",
                target_snapshot={"slug": app.slug},
            )
    except sqlite3.IntegrityError as exc:
        raise NephosError(
            status_code=409,
            code="app_instance_conflict",
            message="App instance already exists.",
            details={"slug": slug},
        ) from exc

    row = repo.get_app_row(app.slug)
    assert row is not None
    return {
        "resource": _app_snapshot(request, row),
        "reconciliation": {"id": reconciliation.id, "state": reconciliation.state},
    }


@router.post("/apps/{app_instance}/actions/{action}", status_code=202)
def app_action(
    app_instance: str,
    action: Literal["start", "stop", "remove", "destroy", "reconcile"],
    payload: LifecycleActionBody,
    request: Request,
) -> dict[str, Any]:
    repo = _repo(request)
    row = repo.get_app_row(app_instance)
    if row is None:
        raise _not_found("app_not_found", "App instance was not found.")
    _reject_lifecycle_mutation_after_destroy_requested(
        slug=app_instance,
        action=action,
        row=row,
    )
    if action == "destroy":
        _require_destroy_confirmation(app_instance, payload)

    with repo.transaction() as tx:
        updated = _apply_app_action(tx, app_instance, action, row)
        reconciliation = tx.create_reconciliation_request(
            target_type="app_instance",
            target_id=str(updated["id"]),
            target_generation=int(updated["generation"]),
            action=action,
            target_snapshot={"slug": updated["slug"]},
        )

    return {
        "resource": _app_snapshot(request, updated),
        "reconciliation": {"id": reconciliation.id, "state": reconciliation.state},
    }


def _resolve_binding_providers(
    request: Request,
    app_catalog_entry: dict[str, Any],
    *,
    selections: dict[str, BindingSelection],
) -> dict[str, dict[str, object]]:
    repo = _repo(request)
    loader = _loader(request)
    service_rows = repo.list_service_rows()
    requirements = {
        requirement["alias"]: requirement
        for requirement in app_catalog_entry["requires"]
    }
    unknown_aliases = sorted(set(selections) - set(requirements))
    if unknown_aliases:
        raise NephosError(
            status_code=400,
            code="binding_requirement_unknown",
            message="Binding selection does not match an App requirement.",
            details={"aliases": unknown_aliases},
        )

    providers: dict[str, dict[str, object]] = {}
    for requirement in app_catalog_entry["requires"]:
        alias = requirement["alias"]
        capable = _capability_provider_rows(
            loader=loader,
            service_rows=service_rows,
            capability=requirement["capability"],
        )
        eligible = [
            service_row
            for service_row in capable
            if _binding_provider_is_available(service_row)
        ]
        selection = selections.get(alias)
        if selection is not None:
            selected = next(
                (
                    service_row
                    for service_row in service_rows
                    if service_row["slug"] == selection.serviceInstance
                ),
                None,
            )
            if selected is None:
                raise NephosError(
                    status_code=404,
                    code="binding_provider_not_found",
                    message="Selected binding provider was not found.",
                    details={
                        "alias": alias,
                        "serviceInstance": selection.serviceInstance,
                    },
                )
            if str(selected["id"]) not in {str(row["id"]) for row in capable}:
                raise NephosError(
                    status_code=409,
                    code="binding_provider_ineligible",
                    message=(
                        "Selected binding provider does not expose the "
                        "required capability."
                    ),
                    details={
                        "alias": alias,
                        "capability": requirement["capability"],
                        "serviceInstance": selection.serviceInstance,
                        "eligibleProviders": [row["slug"] for row in eligible],
                    },
                )
            if selected["delete_requested_at"] is not None:
                raise NephosError(
                    status_code=409,
                    code="binding_provider_unavailable",
                    message="Selected binding provider is not available.",
                    details={
                        "alias": alias,
                        "capability": requirement["capability"],
                        "reason": "destroy_already_requested",
                        "serviceInstance": selection.serviceInstance,
                    },
                )
            if selected["lifecycle"] != "running":
                raise NephosError(
                    status_code=409,
                    code="binding_provider_unavailable",
                    message="Selected binding provider is not available.",
                    details={
                        "alias": alias,
                        "capability": requirement["capability"],
                        "reason": "service_not_running",
                        "lifecycle": selected["lifecycle"],
                        "serviceInstance": selection.serviceInstance,
                    },
                )
            providers[alias] = selected
            continue
        if not eligible:
            raise NephosError(
                status_code=409,
                code="binding_provider_unavailable",
                message="No eligible Service provider exposes the required capability.",
                details={
                    "alias": alias,
                    "capability": requirement["capability"],
                    "eligibleProviders": [],
                },
            )
        if len(eligible) > 1:
            raise NephosError(
                status_code=409,
                code="binding_provider_selection_required",
                message="Required capability needs explicit provider selection.",
                details={
                    "alias": alias,
                    "capability": requirement["capability"],
                    "eligibleProviders": [row["slug"] for row in eligible],
                },
            )
        providers[alias] = eligible[0]
    return providers


def _binding_provider_is_available(service_row: dict[str, object]) -> bool:
    return (
        service_row["delete_requested_at"] is None
        and service_row["lifecycle"] == "running"
    )


def _capability_provider_rows(
    *,
    loader: CatalogLoader,
    service_rows: list[dict[str, object]],
    capability: str,
) -> list[dict[str, object]]:
    eligible = []
    for service_row in service_rows:
        catalog_name = str(service_row["catalog_name"])
        catalog_source_id = str(service_row["catalog_source_id"])
        service_catalog = _catalog_or_404(
            lambda catalog_name=catalog_name,
            catalog_source_id=catalog_source_id: loader.get_service(
                catalog_name,
                source=catalog_source_id,
            ),
        )
        if any(
            provided["capability"] == capability
            for provided in service_catalog["provides"]
        ):
            eligible.append(service_row)
    return eligible


def _service_snapshot(request: Request, row: dict[str, object]) -> dict[str, Any]:
    repo = _repo(request)
    catalog_entry = _loader(request).get_service(
        str(row["catalog_name"]),
        source=str(row["catalog_source_id"]),
    )
    dependents = repo.list_dependents_for_service(str(row["id"]))
    return {
        "id": row["id"],
        "slug": row["slug"],
        "kind": "Service",
        "lifecycle": row["lifecycle"],
        "catalogRef": _catalog_ref(row),
        "config": _json_dict(row["config_json"]),
        "provides": catalog_entry["provides"],
        "dependents": [
            {
                "appInstance": dependent["app_instance_slug"],
                "bindingId": dependent["binding_id"],
                "bindingAlias": dependent["binding_alias"],
                "capability": dependent["capability"],
                "lifecycle": dependent["app_lifecycle"],
                "status": compact_status_snapshot(
                    repo,
                    resource_type="binding",
                    resource_id=str(dependent["binding_id"]),
                ),
            }
            for dependent in dependents
        ],
        "status": status_snapshot(
            repo,
            resource_type="service_instance",
            resource_id=str(row["id"]),
        ),
        "deleteRequestedAt": row["delete_requested_at"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def _load_app_manifest(path: Path) -> AppManifest:
    return AppManifest.model_validate(yaml.safe_load(path.read_text()))


def _validate_app_config(
    manifest: AppManifest,
    config: dict[str, Any],
) -> None:
    options = {option.name: option for option in manifest.spec.config.options}
    unknown_keys = sorted(set(config) - set(options))
    if unknown_keys:
        raise NephosError(
            status_code=400,
            code="app_config_unknown",
            message="App config contains unknown option keys.",
            details={"keys": unknown_keys},
        )

    missing_required = sorted(
        option.name
        for option in options.values()
        if option.required and option.default is None and option.name not in config
    )
    if missing_required:
        raise NephosError(
            status_code=400,
            code="app_config_required",
            message="App config is missing required option values.",
            details={"keys": missing_required},
        )

    for key, value in config.items():
        option = options[key]
        expected_type = option.type_
        if not _config_value_matches_type(value, expected_type):
            raise NephosError(
                status_code=400,
                code="app_config_invalid",
                message="App config value does not match the declared type.",
                details={
                    "key": key,
                    "expectedType": expected_type,
                },
            )
        if expected_type == "enum":
            allowed_values = [
                enum_value["value"]
                for enum_value in option.values or []
            ]
            if value not in allowed_values:
                raise NephosError(
                    status_code=400,
                    code="app_config_invalid",
                    message="App config enum value is not allowed.",
                    details={
                        "key": key,
                        "allowedValues": allowed_values,
                    },
                )


def _config_value_matches_type(value: object, expected_type: str) -> bool:
    if expected_type in {"string", "enum"}:
        return isinstance(value, str)
    if expected_type == "integer":
        return type(value) is int
    if expected_type == "boolean":
        return type(value) is bool
    return False


def _app_snapshot(request: Request, row: dict[str, object]) -> dict[str, Any]:
    catalog_entry = _loader(request).get_app(
        str(row["catalog_name"]),
        source=str(row["catalog_source_id"]),
    )
    repo = _repo(request)
    bindings = repo.list_bindings_for_app(str(row["id"]))
    return {
        "id": row["id"],
        "slug": row["slug"],
        "kind": "App",
        "lifecycle": row["lifecycle"],
        "catalogRef": _catalog_ref(row),
        "config": _json_dict(row["config_json"]),
        "bindings": [
            {
                "id": binding["id"],
                "alias": binding["alias"],
                "capability": binding["capability"],
                "serviceInstance": {
                    "id": binding["service_instance_id"],
                    "slug": binding["service_instance_slug"],
                },
                "status": compact_status_snapshot(
                    repo,
                    resource_type="binding",
                    resource_id=str(binding["id"]),
                ),
            }
            for binding in bindings
        ],
        "routes": _route_snapshots(
            request,
            app_slug=str(row["slug"]),
            app_instance_id=str(row["id"]),
            routes=catalog_entry["routes"],
        ),
        "status": status_snapshot(
            repo,
            resource_type="app_instance",
            resource_id=str(row["id"]),
        ),
        "deleteRequestedAt": row["delete_requested_at"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def _route_snapshots(
    request: Request,
    *,
    app_slug: str,
    app_instance_id: str,
    routes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    repo = _repo(request)
    domains = repo.list_platform_domains()
    default_domain = next((domain for domain in domains if domain.is_default), None)
    alias_domains = [domain for domain in domains if not domain.is_default]
    route_status = compact_status_snapshot(
        repo,
        resource_type="app_instance",
        resource_id=app_instance_id,
    )
    snapshots = []
    for index, route in enumerate(routes):
        host_prefix = app_slug if index == 0 else f"{route['name']}.{app_slug}"
        snapshots.append(
            {
                "name": route["name"],
                "visibility": route["visibility"],
                "target": route["target"],
                "canonicalUrl": (
                    f"http://{host_prefix}.{default_domain.domain}"
                    if default_domain is not None
                    else None
                ),
                "aliases": [
                    f"http://{host_prefix}.{domain.domain}"
                    for domain in alias_domains
                ],
                "status": route_status,
            }
        )
    return snapshots


def _catalog_ref(row: dict[str, object]) -> dict[str, Any]:
    return {
        "kind": row["catalog_kind"],
        "name": row["catalog_name"],
        "source": row["catalog_source_id"],
        "version": row["catalog_version"],
        "manifestDigest": row["manifest_digest"],
    }


def _catalog_source_path(
    request: Request,
    *,
    kind: Literal["App", "Service"],
    name: str,
    source: str,
) -> Path:
    roots = request.app.state.settings.catalog_roots
    index = 0 if source == "default" else int(source.removeprefix("local-"))
    root = roots[index]
    if kind == "App":
        return root / "apps" / name / "app.yaml"
    return root / "services" / name / "service.yaml"


def _loader(request: Request) -> CatalogLoader:
    return CatalogLoader(request.app.state.settings.catalog_roots)


def _repo(request: Request) -> DesiredStateRepository:
    return DesiredStateRepository(request.app.state.settings.db_path)


def _not_found(code: str, message: str) -> NephosError:
    return NephosError(status_code=404, code=code, message=message)


def _dependency_blocked(dependents: list[dict[str, object]]) -> NephosError:
    return NephosError(
        status_code=409,
        code="dependency_blocked",
        message="Service has dependent Apps.",
        details={
            "requiresForce": True,
            "dependents": [
                {
                    "appInstance": dependent["app_instance_slug"],
                    "bindingId": dependent["binding_id"],
                    "bindingAlias": dependent["binding_alias"],
                    "capability": dependent["capability"],
                }
                for dependent in dependents
            ],
        },
    )


def _require_destroy_confirmation(
    slug: str,
    payload: LifecycleActionBody,
) -> None:
    expected = f"destroy {slug}"
    if payload.confirm != expected:
        raise NephosError(
            status_code=400,
            code="destructive_confirmation_required",
            message="Destroy requires explicit confirmation.",
            details={"confirm": expected},
        )


def _reject_lifecycle_mutation_after_destroy_requested(
    *,
    slug: str,
    action: str,
    row: dict[str, object],
) -> None:
    if (
        action not in {"start", "stop", "remove"}
        or row["delete_requested_at"] is None
    ):
        return
    raise NephosError(
        status_code=409,
        code="destroy_already_requested",
        message="Destroy has already been requested.",
        details={
            "action": action,
            "deleteRequestedAt": row["delete_requested_at"],
            "slug": slug,
        },
    )


def _service_action_is_noop(row: dict[str, object], action: str) -> bool:
    desired_lifecycle = {
        "start": "running",
        "stop": "stopped",
        "remove": "removed",
    }.get(action)
    if desired_lifecycle is not None:
        return row["lifecycle"] == desired_lifecycle
    if action == "destroy":
        return row["delete_requested_at"] is not None
    return False


def _apply_service_action(
    tx: Any,
    slug: str,
    action: str,
    current: dict[str, object],
) -> dict[str, object]:
    if action == "start":
        if current["lifecycle"] == "running":
            return current
        return tx.update_service_lifecycle(slug=slug, lifecycle="running")
    if action == "stop":
        if current["lifecycle"] == "stopped":
            return current
        return tx.update_service_lifecycle(slug=slug, lifecycle="stopped")
    if action == "remove":
        if current["lifecycle"] == "removed":
            return current
        return tx.update_service_lifecycle(slug=slug, lifecycle="removed")
    if action == "destroy":
        if current["delete_requested_at"] is not None:
            return current
        return tx.mark_service_delete_requested(slug=slug)
    return current


def _apply_app_action(
    tx: Any,
    slug: str,
    action: str,
    current: dict[str, object],
) -> dict[str, object]:
    if action == "start":
        if current["lifecycle"] == "running":
            return current
        return tx.update_app_lifecycle(slug=slug, lifecycle="running")
    if action == "stop":
        if current["lifecycle"] == "stopped":
            return current
        return tx.update_app_lifecycle(slug=slug, lifecycle="stopped")
    if action == "remove":
        if current["lifecycle"] == "removed":
            return current
        return tx.update_app_lifecycle(slug=slug, lifecycle="removed")
    if action == "destroy":
        if current["delete_requested_at"] is not None:
            return current
        return tx.mark_app_delete_requested(slug=slug)
    return current


def _catalog_or_404(call: Any) -> dict[str, Any]:
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


def _json_dict(value: object) -> dict[str, Any]:
    import json

    if not isinstance(value, str):
        return {}
    return json.loads(value)
