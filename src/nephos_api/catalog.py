from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from nephos_api.domain import (
    InvalidMachineIdentifierError,
    validate_machine_identifier,
)

_KUBERNETES_DNS_LABEL_MAX_LENGTH = 63
_BINDING_SECRET_NAME_PREFIX = "nephos-bind-"
_ROUTE_INGRESS_NAME_PREFIX = "nephos-route-"


class CatalogValidationError(ValueError):
    pass


class CatalogAmbiguousError(ValueError):
    def __init__(self, *, kind: str, name: str, sources: list[str]) -> None:
        self.kind = kind
        self.name = name
        self.sources = sources
        super().__init__(f"{kind} catalog entry {name!r} is ambiguous")


class CatalogSourceNotFoundError(ValueError):
    def __init__(self, *, source: str) -> None:
        self.source = source
        super().__init__(f"catalog source {source!r} was not found")


class CatalogEntryNotFoundError(ValueError):
    def __init__(self, *, kind: str, name: str) -> None:
        self.kind = kind
        self.name = name
        super().__init__(f"{kind} catalog entry {name!r} was not found")


class Metadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    displayName: str | None = None
    description: str | None = None
    version: str | None = None


class CapabilityRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    capability: str
    protocol: str | None = None
    alias: str | None = Field(default=None, alias="as")
    provider: str | None = None


class RouteTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    port: str | int

    @field_validator("port", mode="before")
    @classmethod
    def reject_boolean_port(cls, value: Any) -> Any:
        # ! YAML booleans parse as bool, and bool is an int subclass in Python.
        if type(value) is bool:
            raise ValueError("route target port must be a string name or integer")
        return value


class AppRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    visibility: Literal["local"]
    target: RouteTarget


class ConfigOption(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str
    type_: Literal["string", "integer", "boolean", "enum"] = Field(alias="type")
    label: str | None = None
    description: str | None = None
    default: str | int | bool | None = None
    required: bool = False
    values: list[dict[str, str]] | None = None


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    options: list[ConfigOption] = Field(default_factory=list)


class HelmChart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository: str
    name: str
    version: str


class RuntimeProvider(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str


class MappingSource(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    kind: Literal["config", "binding"]
    name: str
    field: str | None = None


class MappingTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    helmValue: str


class RuntimeMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: MappingSource = Field(alias="from")
    to: MappingTarget


class RuntimeValues(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mappings: list[RuntimeMapping] = Field(default_factory=list)


class RuntimeRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["helm", "provider"]
    chart: HelmChart | None = None
    provider: RuntimeProvider | None = None
    values: RuntimeValues = Field(default_factory=RuntimeValues)

    @model_validator(mode="after")
    def validate_runtime_reference(self) -> RuntimeRef:
        if self.type == "helm" and self.chart is None:
            raise ValueError("helm runtime requires chart")
        if self.type == "helm" and self.provider is not None:
            raise ValueError("helm runtime must not define provider")
        if self.type == "provider" and self.provider is None:
            raise ValueError("provider runtime requires provider")
        if self.type == "provider" and self.chart is not None:
            raise ValueError("provider runtime must not define chart")
        return self


class AppSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requires: list[CapabilityRequirement] = Field(default_factory=list)
    routes: list[AppRoute] = Field(default_factory=list)
    config: AppConfig = Field(default_factory=AppConfig)
    runtime: RuntimeRef


class ProvidedCapability(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    capability: str
    protocol: str | None = None
    alias: str | None = Field(default=None, alias="as")
    version: str | None = None


class BindingOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    target: Literal["app-secret"]


class BindingOutputs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outputs: list[BindingOutput] = Field(default_factory=list)


class Provisioning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["app-scoped-resource", "none"]


class ServiceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provides: list[ProvidedCapability] = Field(min_length=1)
    requires: list[CapabilityRequirement] = Field(default_factory=list)
    bindings: BindingOutputs | None = None
    config: AppConfig = Field(default_factory=AppConfig)
    provisioning: Provisioning
    operations: list[dict[str, Any]] = Field(default_factory=list)
    runtime: RuntimeRef


class AppManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    api_version: Literal["nephos.pro/v1alpha1"] = Field(alias="apiVersion")
    kind: Literal["App"]
    metadata: Metadata
    spec: AppSpec


class ServiceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    api_version: Literal["nephos.pro/v1alpha1"] = Field(alias="apiVersion")
    kind: Literal["Service"]
    metadata: Metadata
    spec: ServiceSpec


class CatalogLoader:
    def __init__(
        self,
        catalog_roots: tuple[Path, ...],
        *,
        source_ids: tuple[str, ...] | None = None,
    ) -> None:
        resolved_source_ids = source_ids or tuple(_source_ids(len(catalog_roots)))
        if len(resolved_source_ids) != len(catalog_roots):
            raise ValueError("catalog source id count must match catalog root count")
        self._sources = tuple(
            (source_id, root)
            for source_id, root in zip(
                resolved_source_ids,
                catalog_roots,
                strict=True,
            )
        )

    def list_apps(self) -> list[dict[str, Any]]:
        return sorted(
            self._load_entries(kind="App", source=None),
            key=lambda entry: (entry["name"], entry["source"]),
        )

    def list_services(self) -> list[dict[str, Any]]:
        return sorted(
            self._load_entries(kind="Service", source=None),
            key=lambda entry: (entry["name"], entry["source"]),
        )

    def get_app(self, name: str, source: str | None = None) -> dict[str, Any]:
        return self._get(kind="App", name=name, source=source)

    def get_service(self, name: str, source: str | None = None) -> dict[str, Any]:
        return self._get(kind="Service", name=name, source=source)

    def _get(self, *, kind: str, name: str, source: str | None) -> dict[str, Any]:
        validate_machine_identifier(name)
        entries = [
            entry
            for entry in self._load_entries(kind=kind, source=source)
            if entry["name"] == name
        ]
        if source is None and len(entries) > 1:
            raise CatalogAmbiguousError(
                kind=kind,
                name=name,
                sources=[entry["source"] for entry in entries],
            )
        if not entries:
            raise CatalogEntryNotFoundError(kind=kind, name=name)
        return entries[0]

    def _load_entries(self, *, kind: str, source: str | None) -> list[dict[str, Any]]:
        sources = self._selected_sources(source)
        entries: list[dict[str, Any]] = []
        for source_id, root in sources:
            if not root.exists():
                continue
            entries.extend(
                _load_source_entries(kind=kind, source_id=source_id, root=root)
            )
        return entries

    def _selected_sources(self, source: str | None) -> tuple[tuple[str, Path], ...]:
        if source is None:
            return self._sources
        for source_id, root in self._sources:
            if source_id == source:
                return ((source_id, root),)
        raise CatalogSourceNotFoundError(source=source)


def _load_source_entries(
    *,
    kind: str,
    source_id: str,
    root: Path,
) -> list[dict[str, Any]]:
    base = root / ("apps" if kind == "App" else "services")
    filename = "app.yaml" if kind == "App" else "service.yaml"
    if not base.exists():
        return []
    return [
        _load_manifest(kind=kind, source_id=source_id, path=path)
        for path in sorted(base.glob(f"*/{filename}"))
    ]


def _load_manifest(*, kind: str, source_id: str, path: Path) -> dict[str, Any]:
    content = path.read_bytes()
    try:
        raw = yaml.safe_load(content)
        manifest = (
            AppManifest.model_validate(raw)
            if kind == "App"
            else ServiceManifest.model_validate(raw)
        )
    except ValidationError as exc:
        raise CatalogValidationError(f"invalid {kind} manifest {path}: {exc}") from exc

    if manifest.metadata.name != path.parent.name:
        raise CatalogValidationError(
            f"catalog directory slug {path.parent.name!r} must match "
            f"metadata.name {manifest.metadata.name!r}"
        )

    _validate_manifest_semantics(kind=kind, path=path, manifest=manifest)
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    return (
        _app_summary(manifest, source_id=source_id, digest=digest)
        if kind == "App"
        else _service_summary(manifest, source_id=source_id, digest=digest)
    )


def _validate_manifest_semantics(
    *,
    kind: str,
    path: Path,
    manifest: AppManifest | ServiceManifest,
) -> None:
    try:
        validate_machine_identifier(manifest.metadata.name)
    except InvalidMachineIdentifierError as exc:
        raise CatalogValidationError(
            f"invalid {kind} manifest {path}: invalid metadata.name"
        ) from exc
    _validate_runtime_reference(path=path, manifest=manifest)
    if isinstance(manifest, AppManifest):
        _validate_app_manifest(path=path, manifest=manifest)
    else:
        _validate_service_manifest(path=path, manifest=manifest)


def _validate_runtime_reference(
    *,
    path: Path,
    manifest: AppManifest | ServiceManifest,
) -> None:
    runtime = manifest.spec.runtime
    if runtime.provider is not None:
        _validate_catalog_identifier(
            path=path,
            label="runtime provider",
            value=runtime.provider.name,
        )


def _validate_app_manifest(*, path: Path, manifest: AppManifest) -> None:
    aliases: set[str] = set()
    for requirement in manifest.spec.requires:
        _validate_catalog_identifier(
            path=path,
            label="capability",
            value=requirement.capability,
        )
        if requirement.protocol is not None:
            _validate_catalog_identifier(
                path=path,
                label="protocol",
                value=requirement.protocol,
            )
        alias = requirement.alias or _default_capability_alias(
            requirement.capability,
            requirement.protocol,
        )
        _validate_catalog_identifier(
            path=path,
            label="binding alias",
            value=alias,
        )
        _validate_generated_kubernetes_name(
            path=path,
            label="binding alias",
            value=alias,
            prefix=_BINDING_SECRET_NAME_PREFIX,
            resource_kind="Secret",
        )
        if alias in aliases:
            raise CatalogValidationError(
                f"invalid App manifest {path}: duplicate binding alias {alias!r}"
            )
        aliases.add(alias)
        if requirement.provider is not None:
            _validate_catalog_identifier(
                path=path,
                label="provider",
                value=requirement.provider,
            )

    route_names: set[str] = set()
    for route in manifest.spec.routes:
        _validate_catalog_identifier(
            path=path,
            label="route name",
            value=route.name,
        )
        _validate_generated_kubernetes_name(
            path=path,
            label="route name",
            value=route.name,
            prefix=_ROUTE_INGRESS_NAME_PREFIX,
            resource_kind="Ingress",
        )
        _validate_route_target_port(path=path, route=route)
        if route.name in route_names:
            raise CatalogValidationError(
                f"invalid App manifest {path}: duplicate route name {route.name!r}"
            )
        route_names.add(route.name)

    _validate_config_options(
        kind="App",
        path=path,
        options=manifest.spec.config.options,
    )


def _validate_service_manifest(*, path: Path, manifest: ServiceManifest) -> None:
    aliases: set[str] = set()
    requirement_aliases: set[str] = set()
    for requirement in manifest.spec.requires:
        _validate_catalog_identifier(
            path=path,
            label="capability",
            value=requirement.capability,
        )
        if requirement.protocol is not None:
            _validate_catalog_identifier(
                path=path,
                label="protocol",
                value=requirement.protocol,
            )
        alias = requirement.alias or _default_capability_alias(
            requirement.capability,
            requirement.protocol,
        )
        _validate_catalog_identifier(
            path=path,
            label="required alias",
            value=alias,
        )
        if alias in requirement_aliases:
            raise CatalogValidationError(
                f"invalid Service manifest {path}: duplicate required alias {alias!r}"
            )
        requirement_aliases.add(alias)
    for provided in manifest.spec.provides:
        _validate_catalog_identifier(
            path=path,
            label="capability",
            value=provided.capability,
        )
        if provided.protocol is not None:
            _validate_catalog_identifier(
                path=path,
                label="protocol",
                value=provided.protocol,
            )
        alias = provided.alias or _default_capability_alias(
            provided.capability,
            provided.protocol,
        )
        _validate_catalog_identifier(
            path=path,
            label="provided alias",
            value=alias,
        )
        if alias in aliases:
            raise CatalogValidationError(
                f"invalid Service manifest {path}: duplicate provided alias {alias!r}"
            )
        aliases.add(alias)
    if manifest.spec.bindings is not None:
        output_names: set[str] = set()
        for output in manifest.spec.bindings.outputs:
            _validate_catalog_identifier(
                path=path,
                label="binding output name",
                value=output.name,
            )
            if output.name in output_names:
                raise CatalogValidationError(
                    f"invalid Service manifest {path}: "
                    f"duplicate binding output name {output.name!r}"
                )
            output_names.add(output.name)
    _validate_config_options(
        kind="Service",
        path=path,
        options=manifest.spec.config.options,
    )


def _validate_config_options(
    *,
    kind: str,
    path: Path,
    options: list[ConfigOption],
) -> None:
    for option in options:
        _validate_catalog_identifier(
            path=path,
            label="config option name",
            value=option.name,
        )
        if option.default is not None and not _config_value_matches_type(
            option.default,
            option.type_,
        ):
            raise CatalogValidationError(
                f"invalid {kind} manifest {path}: invalid config default "
                f"for {option.name!r}"
            )
        if option.type_ == "enum":
            allowed_values = [enum_value["value"] for enum_value in option.values or []]
            if not allowed_values:
                raise CatalogValidationError(
                    f"invalid {kind} manifest {path}: enum config values "
                    f"are required for {option.name!r}"
                )
            if option.default is not None and option.default not in allowed_values:
                raise CatalogValidationError(
                    f"invalid {kind} manifest {path}: invalid enum default "
                    f"for {option.name!r}"
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


def _default_capability_alias(capability: str, protocol: str | None) -> str:
    if protocol is None:
        return capability
    return f"{capability}-{protocol}"


def _validate_catalog_identifier(*, path: Path, label: str, value: str) -> None:
    try:
        validate_machine_identifier(value)
    except InvalidMachineIdentifierError as exc:
        raise CatalogValidationError(
            f"invalid manifest {path}: invalid {label} {value!r}"
        ) from exc


def _validate_generated_kubernetes_name(
    *,
    path: Path,
    label: str,
    value: str,
    prefix: str,
    resource_kind: str,
) -> None:
    name = f"{prefix}{value}"
    if len(name) > _KUBERNETES_DNS_LABEL_MAX_LENGTH:
        raise CatalogValidationError(
            f"invalid App manifest {path}: {label} {value!r} creates "
            f"Kubernetes {resource_kind} name {name!r} longer than "
            f"{_KUBERNETES_DNS_LABEL_MAX_LENGTH} characters"
        )


def _validate_route_target_port(*, path: Path, route: AppRoute) -> None:
    port = route.target.port
    if isinstance(port, int) and not 1 <= port <= 65535:
        raise CatalogValidationError(
            f"invalid App manifest {path}: route target port {port!r} "
            "must be between 1 and 65535"
        )


def _app_summary(
    manifest: AppManifest,
    *,
    source_id: str,
    digest: str,
) -> dict[str, Any]:
    return {
        "kind": "App",
        "name": manifest.metadata.name,
        "displayName": manifest.metadata.displayName,
        "description": manifest.metadata.description,
        "version": manifest.metadata.version,
        "source": source_id,
        "manifestDigest": digest,
        "requires": [
            {
                "capability": requirement.capability,
                "protocol": requirement.protocol,
                "alias": requirement.alias
                or _default_capability_alias(
                    requirement.capability,
                    requirement.protocol,
                ),
                "provider": requirement.provider,
            }
            for requirement in manifest.spec.requires
        ],
        "routes": [
            {
                "name": route.name,
                "visibility": route.visibility,
                "target": {"port": route.target.port},
            }
            for route in manifest.spec.routes
        ],
    }


def _service_summary(
    manifest: ServiceManifest,
    *,
    source_id: str,
    digest: str,
) -> dict[str, Any]:
    output_targets = (
        [output.target for output in manifest.spec.bindings.outputs]
        if manifest.spec.bindings
        else []
    )
    return {
        "kind": "Service",
        "name": manifest.metadata.name,
        "displayName": manifest.metadata.displayName,
        "description": manifest.metadata.description,
        "version": manifest.metadata.version,
        "source": source_id,
        "manifestDigest": digest,
        "requires": [
            {
                "capability": requirement.capability,
                "protocol": requirement.protocol,
                "alias": requirement.alias
                or _default_capability_alias(
                    requirement.capability,
                    requirement.protocol,
                ),
                "provider": requirement.provider,
            }
            for requirement in manifest.spec.requires
        ],
        "provides": [
            {
                "capability": provided.capability,
                "protocol": provided.protocol,
                "alias": provided.alias
                or _default_capability_alias(
                    provided.capability,
                    provided.protocol,
                ),
                "version": provided.version,
                "bindingOutputTargets": output_targets,
            }
            for provided in manifest.spec.provides
        ],
    }


def _source_ids(count: int) -> list[str]:
    if count == 0:
        return []
    return ["default"] + [f"local-{index}" for index in range(1, count)]
