from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from nephos_api.config import Settings
from nephos_api.domain import validate_machine_identifier
from nephos_api.errors import NephosError

CatalogKind = Literal["App", "Service"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class CatalogMetadata(StrictModel):
    name: str
    display_name: str | None = Field(default=None, alias="displayName")
    description: str | None = None
    version: str | None = None


class RuntimeChart(StrictModel):
    repository: str
    name: str
    version: str


class RuntimeValues(StrictModel):
    mappings: list[dict[str, Any]] = Field(default_factory=list)


class RuntimeSpec(StrictModel):
    type: Literal["helm"]
    chart: RuntimeChart
    values: RuntimeValues | None = None


class AppRequirement(StrictModel):
    capability: str
    alias: str | None = Field(default=None, alias="as")
    provider: str | None = None


class RouteTarget(StrictModel):
    port: str | int


class AppRoute(StrictModel):
    name: str
    visibility: str
    target: RouteTarget


class ConfigEnumValue(StrictModel):
    value: str
    label: str


class ConfigOption(StrictModel):
    name: str
    type: Literal["string", "integer", "boolean", "enum"]
    label: str | None = None
    description: str | None = None
    default: str | int | bool | None = None
    required: bool = False
    values: list[ConfigEnumValue] | None = None


class AppConfig(StrictModel):
    options: list[ConfigOption] = Field(default_factory=list)


class AppSpec(StrictModel):
    requires: list[AppRequirement] = Field(default_factory=list)
    routes: list[AppRoute] = Field(default_factory=list)
    runtime: RuntimeSpec
    config: AppConfig = Field(default_factory=AppConfig)


class AppManifest(StrictModel):
    api_version: Literal["nephos.pro/v1alpha1"] = Field(alias="apiVersion")
    kind: Literal["App"]
    metadata: CatalogMetadata
    spec: AppSpec


class ServiceProvide(StrictModel):
    capability: str
    alias: str | None = Field(default=None, alias="as")
    version: str | None = None


class BindingOutput(StrictModel):
    name: str
    target: Literal["app-secret"]


class ServiceBindings(StrictModel):
    outputs: list[BindingOutput] = Field(default_factory=list)


class ServiceProvisioning(StrictModel):
    mode: Literal["none", "app-scoped-resource"]


class ServiceSpec(StrictModel):
    provides: list[ServiceProvide]
    bindings: ServiceBindings = Field(default_factory=ServiceBindings)
    provisioning: ServiceProvisioning
    runtime: RuntimeSpec
    operations: list[dict[str, Any]] = Field(default_factory=list)


class ServiceManifest(StrictModel):
    api_version: Literal["nephos.pro/v1alpha1"] = Field(alias="apiVersion")
    kind: Literal["Service"]
    metadata: CatalogMetadata
    spec: ServiceSpec


@dataclass(frozen=True)
class CatalogSource:
    id: str
    root: Path


@dataclass(frozen=True)
class CatalogEntry:
    kind: CatalogKind
    name: str
    source: CatalogSource
    manifest_path: Path
    manifest_digest: str
    manifest: AppManifest | ServiceManifest


@dataclass(frozen=True)
class EntryLocation:
    source: CatalogSource
    path: Path


_KIND_DIRECTORY: dict[CatalogKind, tuple[str, str]] = {
    "App": ("apps", "app.yaml"),
    "Service": ("services", "service.yaml"),
}


def catalog_sources(settings: Settings) -> tuple[CatalogSource, ...]:
    sources = [CatalogSource(id="default", root=settings.repo_catalog_root)]
    for index, root in enumerate(settings.extra_catalog_roots[:3], start=1):
        sources.append(CatalogSource(id=f"local-{index}", root=root))
    return tuple(sources)


class CatalogLoader:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.sources = catalog_sources(settings)

    def list_entries(
        self,
        kind: CatalogKind,
        *,
        source_id: str | None = None,
    ) -> list[dict[str, Any]]:
        entries = [
            self._load_location(kind, location)
            for location in self._locations(kind, source_id)
        ]
        sorted_entries = sorted(entries, key=lambda entry: (entry.name, entry.source.id))
        return [self._summary(entry) for entry in sorted_entries]

    def get_entry(
        self,
        kind: CatalogKind,
        name: str,
        *,
        source_id: str | None = None,
    ) -> dict[str, Any]:
        return self._summary(self.resolve_entry(kind, name, source_id=source_id))

    def resolve_entry(
        self,
        kind: CatalogKind,
        name: str,
        *,
        source_id: str | None = None,
    ) -> CatalogEntry:
        validate_machine_identifier(name, field="name")
        matches = [
            self._load_location(kind, location)
            for location in self._locations(kind, source_id)
            if location.path.parent.name == name
        ]
        if not matches:
            raise NephosError(
                "catalog_entry_not_found",
                "Catalog entry not found.",
                status_code=404,
                details={"kind": kind, "name": name, "source": source_id},
            )
        if source_id is None and len(matches) > 1:
            raise NephosError(
                "catalog_entry_ambiguous",
                "Catalog entry exists in multiple sources; select a source explicitly.",
                status_code=409,
                details={
                    "kind": kind,
                    "name": name,
                    "sources": [entry.source.id for entry in matches],
                },
            )
        return matches[0]

    def _source(self, source_id: str) -> CatalogSource:
        for source in self.sources:
            if source.id == source_id:
                return source
        raise NephosError(
            "catalog_source_not_found",
            "Catalog source not found.",
            status_code=404,
            details={"source": source_id},
        )

    def _locations(self, kind: CatalogKind, source_id: str | None) -> list[EntryLocation]:
        sources = (self._source(source_id),) if source_id else self.sources
        directory_name, manifest_name = _KIND_DIRECTORY[kind]
        locations: list[EntryLocation] = []
        for source in sources:
            catalog_dir = source.root / directory_name
            if not catalog_dir.exists():
                continue
            for entry_dir in sorted(catalog_dir.iterdir()):
                manifest_path = entry_dir / manifest_name
                if entry_dir.is_dir() and manifest_path.exists():
                    locations.append(EntryLocation(source=source, path=manifest_path))
        return locations

    def _load_location(self, kind: CatalogKind, location: EntryLocation) -> CatalogEntry:
        raw = location.path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        try:
            data = yaml.safe_load(raw) or {}
        except yaml.YAMLError as exc:
            raise NephosError(
                "catalog_manifest_invalid",
                "Catalog manifest YAML is invalid.",
                status_code=422,
                details={"path": str(location.path), "error": str(exc)},
            ) from exc

        try:
            manifest: AppManifest | ServiceManifest
            if kind == "App":
                manifest = AppManifest.model_validate(data)
            else:
                manifest = ServiceManifest.model_validate(data)
        except ValidationError as exc:
            raise NephosError(
                "catalog_manifest_invalid",
                "Catalog manifest does not match the accepted Nephos manifest model.",
                status_code=422,
                details={"path": str(location.path), "errors": exc.errors(include_url=False)},
            ) from exc

        self._validate_manifest_identity(kind, location, manifest)
        return CatalogEntry(
            kind=kind,
            name=manifest.metadata.name,
            source=location.source,
            manifest_path=location.path,
            manifest_digest=digest,
            manifest=manifest,
        )

    def _validate_manifest_identity(
        self,
        kind: CatalogKind,
        location: EntryLocation,
        manifest: AppManifest | ServiceManifest,
    ) -> None:
        validate_machine_identifier(manifest.metadata.name, field="metadata.name")
        expected_slug = location.path.parent.name
        if expected_slug != manifest.metadata.name:
            raise NephosError(
                "catalog_manifest_invalid",
                "Catalog directory slug must match manifest metadata.name.",
                status_code=422,
                details={
                    "kind": kind,
                    "path": str(location.path),
                    "directorySlug": expected_slug,
                    "metadataName": manifest.metadata.name,
                },
            )
        if isinstance(manifest, AppManifest):
            requirement_aliases: set[str] = set()
            for requirement in manifest.spec.requires:
                validate_machine_identifier(
                    requirement.capability,
                    field="spec.requires[].capability",
                )
                alias = requirement.alias or requirement.capability
                validate_machine_identifier(alias, field="spec.requires[].as")
                if requirement.provider is not None:
                    validate_machine_identifier(
                        requirement.provider,
                        field="spec.requires[].provider",
                    )
                if alias in requirement_aliases:
                    raise NephosError(
                        "catalog_manifest_invalid",
                        "App requirement aliases must be unique after defaulting.",
                        status_code=422,
                        details={"path": str(location.path), "alias": alias},
                    )
                requirement_aliases.add(alias)
            route_names: set[str] = set()
            for route in manifest.spec.routes:
                validate_machine_identifier(route.name, field="spec.routes[].name")
                if route.name in route_names:
                    raise NephosError(
                        "catalog_manifest_invalid",
                        "App route names must be unique.",
                        status_code=422,
                        details={"path": str(location.path), "route": route.name},
                    )
                route_names.add(route.name)
            for option in manifest.spec.config.options:
                validate_machine_identifier(option.name, field="spec.config.options[].name")
        else:
            if not manifest.spec.provides:
                raise NephosError(
                    "catalog_manifest_invalid",
                    "Service manifests must provide at least one capability.",
                    status_code=422,
                    details={"path": str(location.path)},
                )
            for provide in manifest.spec.provides:
                validate_machine_identifier(provide.capability, field="spec.provides[].capability")
                if provide.alias is not None:
                    validate_machine_identifier(provide.alias, field="spec.provides[].as")

    def _summary(self, entry: CatalogEntry) -> dict[str, Any]:
        metadata = entry.manifest.metadata
        base: dict[str, Any] = {
            "kind": entry.kind,
            "name": entry.name,
            "displayName": metadata.display_name,
            "description": metadata.description,
            "version": metadata.version,
            "source": entry.source.id,
            "manifestDigest": entry.manifest_digest,
        }
        if isinstance(entry.manifest, AppManifest):
            base["requires"] = [
                {
                    "capability": requirement.capability,
                    "alias": requirement.alias or requirement.capability,
                    **({"provider": requirement.provider} if requirement.provider else {}),
                }
                for requirement in entry.manifest.spec.requires
            ]
            base["routes"] = [
                {
                    "name": route.name,
                    "visibility": route.visibility,
                    "target": {"port": route.target.port},
                }
                for route in entry.manifest.spec.routes
            ]
        else:
            output_targets = [output.target for output in entry.manifest.spec.bindings.outputs]
            base["provides"] = [
                {
                    "capability": provide.capability,
                    **({"alias": provide.alias} if provide.alias else {}),
                    **({"version": provide.version} if provide.version else {}),
                    "bindingOutputTargets": output_targets,
                }
                for provide in entry.manifest.spec.provides
            ]
        return base
