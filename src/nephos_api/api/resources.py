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
    ServiceManifest,
)
from nephos_api.domain import InvalidMachineIdentifierError, validate_machine_identifier
from nephos_api.errors import NephosError
from nephos_api.kubernetes_runtime import ResourceType, namespace_name
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
    _require_catalog_kind(payload.catalogRef.kind, expected="Service")

    catalog_entry, slug, source_path = _install_catalog_entry(
        payload,
        request,
        kind="Service",
    )
    _validate_service_config(_load_service_manifest(source_path), payload.config)
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
    if action in {"stop", "remove", "destroy"} and not _lifecycle_action_is_noop(
        row,
        action,
    ):
        dependents = repo.list_dependents_for_service(str(row["id"]))
        if dependents and not payload.force:
            raise _dependency_blocked(dependents)
    if action == "destroy":
        _require_destroy_confirmation(service_instance, payload)

    with repo.transaction() as tx:
        updated = _apply_lifecycle_action(
            tx,
            target_type="service_instance",
            slug=service_instance,
            action=action,
            current=row,
        )
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
    _require_catalog_kind(payload.catalogRef.kind, expected="App")

    catalog_entry, slug, source_path = _install_catalog_entry(
        payload,
        request,
        kind="App",
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
                    protocol=requirement["protocol"],
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
        updated = _apply_lifecycle_action(
            tx,
            target_type="app_instance",
            slug=app_instance,
            action=action,
            current=row,
        )
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


def _require_catalog_kind(
    actual: Literal["App", "Service"],
    *,
    expected: Literal["App", "Service"],
) -> None:
    if actual == expected:
        return
    article = "an" if expected == "App" else "a"
    raise NephosError(
        status_code=400,
        code="catalog_kind_mismatch",
        message=f"{expected} install requires {article} {expected} catalog reference.",
        details={"kind": actual},
    )


def _install_catalog_entry(
    payload: InstallRequest,
    request: Request,
    *,
    kind: Literal["App", "Service"],
) -> tuple[dict[str, Any], str, Path]:
    # * Shared install preflight: resolve catalog identity before mutating state.
    _validate_catalog_name(payload.catalogRef.name)
    loader = _loader(request)
    get_entry = loader.get_app if kind == "App" else loader.get_service
    catalog_entry = _catalog_or_404(
        lambda: get_entry(
            payload.catalogRef.name,
            source=payload.catalogRef.source,
        )
    )
    slug = payload.instanceName or str(catalog_entry["name"])
    resource_type: ResourceType = (
        "app_instance" if kind == "App" else "service_instance"
    )
    _validate_runtime_namespace_slug(resource_type, slug)
    source_path = _catalog_source_path(
        request,
        kind=kind,
        name=str(catalog_entry["name"]),
        source=str(catalog_entry["source"]),
    )
    return catalog_entry, slug, source_path


def _validate_runtime_namespace_slug(resource_type: ResourceType, slug: str) -> None:
    try:
        namespace_name(resource_type, slug)
    except ValueError as exc:
        label = "App" if resource_type == "app_instance" else "Service"
        prefix = "app-" if resource_type == "app_instance" else "svc-"
        raise NephosError(
            status_code=400,
            code="runtime_namespace_name_invalid",
            message=(
                f"{label} instance name is not valid for the generated "
                "Kubernetes namespace."
            ),
            details={
                "instanceName": slug,
                "namespacePrefix": prefix,
                "maxInstanceNameLength": 63 - len(prefix),
                "reason": str(exc),
            },
        ) from exc


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


def _resolve_binding_providers(
    request: Request,
    app_catalog_entry: dict[str, Any],
    *,
    selections: dict[str, BindingSelection],
) -> dict[str, dict[str, object]]:
    repo = _repo(request)
    loader = _loader(request)
    service_rows = repo.list_service_rows()
    requirements = _requirements_by_alias(app_catalog_entry)
    # ! Error precedence is part of the API contract; keep this before selection.
    _reject_unknown_binding_aliases(selections, requirements)

    providers: dict[str, dict[str, object]] = {}
    for requirement in app_catalog_entry["requires"]:
        alias = requirement["alias"]
        capability = requirement["capability"]
        protocol = requirement.get("protocol")
        capable = _matching_provider_rows(
            loader=loader,
            service_rows=service_rows,
            capability=capability,
            protocol=protocol,
        )
        providers[alias] = _select_binding_provider(
            alias=alias,
            capability=capability,
            protocol=protocol,
            service_rows=service_rows,
            capable=capable,
            selection=selections.get(alias),
        )
    return providers


def _requirements_by_alias(
    app_catalog_entry: dict[str, Any],
) -> dict[str, dict[str, object]]:
    return {
        requirement["alias"]: requirement
        for requirement in app_catalog_entry["requires"]
    }


def _reject_unknown_binding_aliases(
    selections: dict[str, BindingSelection],
    requirements: dict[str, dict[str, object]],
) -> None:
    unknown_aliases = sorted(set(selections) - set(requirements))
    if not unknown_aliases:
        return
    raise NephosError(
        status_code=400,
        code="binding_requirement_unknown",
        message="Binding selection does not match an App requirement.",
        details={"aliases": unknown_aliases},
    )


def _select_binding_provider(
    *,
    alias: str,
    capability: str,
    protocol: object,
    service_rows: list[dict[str, object]],
    capable: list[dict[str, object]],
    selection: BindingSelection | None,
) -> dict[str, object]:
    eligible = [
        service_row
        for service_row in capable
        if _binding_provider_is_available(service_row)
    ]
    if selection is not None:
        return _selected_binding_provider(
            alias=alias,
            capability=capability,
            protocol=protocol,
            service_rows=service_rows,
            capable=capable,
            eligible=eligible,
            selection=selection,
        )
    return _automatic_binding_provider(
        alias=alias,
        capability=capability,
        protocol=protocol,
        eligible=eligible,
    )


def _selected_binding_provider(
    *,
    alias: str,
    capability: str,
    protocol: object,
    service_rows: list[dict[str, object]],
    capable: list[dict[str, object]],
    eligible: list[dict[str, object]],
    selection: BindingSelection,
) -> dict[str, object]:
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
    _reject_ineligible_binding_provider(
        alias=alias,
        capability=capability,
        protocol=protocol,
        capable=capable,
        eligible=eligible,
        selected=selected,
        selection=selection,
    )
    _reject_unavailable_binding_provider(
        alias=alias,
        capability=capability,
        protocol=protocol,
        selected=selected,
        selection=selection,
    )
    return selected


def _reject_ineligible_binding_provider(
    *,
    alias: str,
    capability: str,
    protocol: object,
    capable: list[dict[str, object]],
    eligible: list[dict[str, object]],
    selected: dict[str, object],
    selection: BindingSelection,
) -> None:
    if str(selected["id"]) in {str(row["id"]) for row in capable}:
        return
    raise NephosError(
        status_code=409,
        code="binding_provider_ineligible",
        message="Selected binding provider does not expose the required capability.",
        details={
            **_binding_requirement_details(
                alias=alias,
                capability=capability,
                protocol=protocol,
            ),
            "serviceInstance": selection.serviceInstance,
            "eligibleProviders": [row["slug"] for row in eligible],
        },
    )


def _reject_unavailable_binding_provider(
    *,
    alias: str,
    capability: str,
    protocol: object,
    selected: dict[str, object],
    selection: BindingSelection,
) -> None:
    if selected["delete_requested_at"] is not None:
        raise NephosError(
            status_code=409,
            code="binding_provider_unavailable",
            message="Selected binding provider is not available.",
            details={
                **_binding_requirement_details(
                    alias=alias,
                    capability=capability,
                    protocol=protocol,
                ),
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
                **_binding_requirement_details(
                    alias=alias,
                    capability=capability,
                    protocol=protocol,
                ),
                "reason": "service_not_running",
                "lifecycle": selected["lifecycle"],
                "serviceInstance": selection.serviceInstance,
            },
        )


def _automatic_binding_provider(
    *,
    alias: str,
    capability: str,
    protocol: object,
    eligible: list[dict[str, object]],
) -> dict[str, object]:
    if not eligible:
        raise NephosError(
            status_code=409,
            code="binding_provider_unavailable",
            message="No eligible Service provider exposes the required capability.",
            details={
                **_binding_requirement_details(
                    alias=alias,
                    capability=capability,
                    protocol=protocol,
                ),
                "eligibleProviders": [],
            },
        )
    if len(eligible) > 1:
        raise NephosError(
            status_code=409,
            code="binding_provider_selection_required",
            message="Required capability needs explicit provider selection.",
            details={
                **_binding_requirement_details(
                    alias=alias,
                    capability=capability,
                    protocol=protocol,
                ),
                "eligibleProviders": [row["slug"] for row in eligible],
            },
        )
    return eligible[0]


def _binding_provider_is_available(service_row: dict[str, object]) -> bool:
    return (
        service_row["delete_requested_at"] is None
        and service_row["lifecycle"] == "running"
    )


def _binding_requirement_details(
    *,
    alias: str,
    capability: str,
    protocol: object,
) -> dict[str, object]:
    details: dict[str, object] = {
        "alias": alias,
        "capability": capability,
    }
    if protocol is not None:
        details["protocol"] = protocol
    return details


def _matching_provider_rows(
    *,
    loader: CatalogLoader,
    service_rows: list[dict[str, object]],
    capability: str,
    protocol: object,
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
            and (protocol is None or provided["protocol"] == protocol)
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
        "config": _redacted_config(_json_dict(row["config_json"])),
        "provides": catalog_entry["provides"],
        "dependents": [
            {
                "appInstance": dependent["app_instance_slug"],
                "bindingId": dependent["binding_id"],
                "bindingAlias": dependent["binding_alias"],
                "capability": dependent["capability"],
                "protocol": dependent["protocol"],
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


def _load_service_manifest(path: Path) -> ServiceManifest:
    return ServiceManifest.model_validate(yaml.safe_load(path.read_text()))


def _validate_app_config(
    manifest: AppManifest,
    config: dict[str, Any],
) -> None:
    _validate_manifest_config(
        options={option.name: option for option in manifest.spec.config.options},
        config=config,
        code_prefix="app_config",
        label="App",
    )


def _validate_service_config(
    manifest: ServiceManifest,
    config: dict[str, Any],
) -> None:
    _validate_manifest_config(
        options={option.name: option for option in manifest.spec.config.options},
        config=config,
        code_prefix="service_config",
        label="Service",
    )


def _validate_manifest_config(
    *,
    options: dict[str, Any],
    config: dict[str, Any],
    code_prefix: str,
    label: str,
) -> None:
    unknown_keys = sorted(set(config) - set(options))
    if unknown_keys:
        raise NephosError(
            status_code=400,
            code=f"{code_prefix}_unknown",
            message=f"{label} config contains unknown option keys.",
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
            code=f"{code_prefix}_required",
            message=f"{label} config is missing required option values.",
            details={"keys": missing_required},
        )

    for key, value in config.items():
        option = options[key]
        expected_type = option.type_
        if not _config_value_matches_type(value, expected_type):
            raise NephosError(
                status_code=400,
                code=f"{code_prefix}_invalid",
                message=f"{label} config value does not match the declared type.",
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
                    code=f"{code_prefix}_invalid",
                    message=f"{label} config enum value is not allowed.",
                    details={
                        "key": key,
                        "allowedValues": allowed_values,
                    },
                )


def _config_value_matches_type(value: object, expected_type: str) -> bool:
    # ! Keep exact checks here; isinstance(True, int) is True.
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
                "protocol": binding["protocol"],
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


def _lifecycle_action_is_noop(row: dict[str, object], action: str) -> bool:
    desired_lifecycle = _ACTION_LIFECYCLES.get(action)
    if desired_lifecycle is not None:
        return row["lifecycle"] == desired_lifecycle
    if action == "destroy":
        return row["delete_requested_at"] is not None
    return False


_ACTION_LIFECYCLES = {
    "start": "running",
    "stop": "stopped",
    "remove": "removed",
}


def _apply_lifecycle_action(
    tx: Any,
    *,
    target_type: ResourceType,
    slug: str,
    action: str,
    current: dict[str, object],
) -> dict[str, object]:
    desired_lifecycle = _ACTION_LIFECYCLES.get(action)
    if desired_lifecycle is not None:
        if current["lifecycle"] == desired_lifecycle:
            return current
        if target_type == "service_instance":
            return tx.update_service_lifecycle(
                slug=slug,
                lifecycle=desired_lifecycle,
            )
        return tx.update_app_lifecycle(slug=slug, lifecycle=desired_lifecycle)
    if action == "destroy":
        if current["delete_requested_at"] is not None:
            return current
        if target_type == "service_instance":
            return tx.mark_service_delete_requested(slug=slug)
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


def _redacted_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        key: "[REDACTED]" if _is_sensitive_config_key(key) else value
        for key, value in config.items()
    }


def _is_sensitive_config_key(key: str) -> bool:
    lowered = key.lower()
    return any(
        marker in lowered
        for marker in ("password", "secret", "token", "key", "credential")
    )
