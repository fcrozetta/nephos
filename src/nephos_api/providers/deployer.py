from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

import yaml

from nephos_api.catalog import AppManifest, RuntimeMapping, ServiceManifest
from nephos_api.helm_runtime import runtime_name, set_helm_value
from nephos_api.providers.base import ProviderContext, RuntimeProvider
from nephos_api.repository import DesiredStateRepository
from nephos_api.runtime_errors import RuntimeBlockedError


class BindingValueSource(Protocol):
    def get_binding_values(
        self,
        *,
        app_slug: str,
        service_slug: str,
        alias: str,
        capability: str,
    ) -> dict[str, str] | None: ...


class ProviderRuntimeDeployer:
    def __init__(
        self,
        *,
        repository: DesiredStateRepository,
        app_provider: RuntimeProvider,
        service_provider: RuntimeProvider,
        binding_value_source: BindingValueSource | None = None,
    ) -> None:
        self._repository = repository
        self._app_provider = app_provider
        self._service_provider = service_provider
        self._binding_value_source = binding_value_source

    def deploy(self, *, target_type: str, slug: str) -> None:
        context = self._context(target_type=target_type, slug=slug)
        self._provider_for(target_type).deploy(context)

    def uninstall(self, *, target_type: str, slug: str) -> None:
        context = self._context(target_type=target_type, slug=slug)
        self._provider_for(target_type).uninstall(context)

    def _provider_for(self, target_type: str) -> RuntimeProvider:
        if target_type == "app_instance":
            return self._app_provider
        if target_type == "service_instance":
            return self._service_provider
        raise ValueError(f"unsupported provider target type {target_type}")

    def _context(self, *, target_type: str, slug: str) -> ProviderContext:
        row = self._instance_row(target_type=target_type, slug=slug)
        manifest = _manifest_from_path(
            target_type=target_type,
            path=Path(str(row["catalog_source_path"])),
        )
        return ProviderContext(
            target_type=target_type,
            slug=slug,
            runtime_name=runtime_name(target_type, slug),
            manifest=manifest,
            chart=_chart_from_manifest(manifest),
            values=self._values_from_manifest(
                target_type=target_type,
                slug=slug,
                row=row,
                manifest=manifest,
            ),
            provider_name=_provider_name_from_manifest(manifest),
        )

    def _instance_row(self, *, target_type: str, slug: str) -> dict[str, object]:
        if target_type == "app_instance":
            row = self._repository.get_app_row(slug)
        elif target_type == "service_instance":
            row = self._repository.get_service_row(slug)
        else:
            raise ValueError(f"unsupported provider deploy target type {target_type}")
        if row is None:
            raise ValueError(f"desired state row not found for {target_type} {slug}")
        return row

    def _values_from_manifest(
        self,
        *,
        target_type: str,
        slug: str,
        row: dict[str, object],
        manifest: AppManifest | ServiceManifest,
    ) -> dict[str, object]:
        config = _manifest_config_values(row, manifest)
        bindings = (
            self._repository.list_bindings_for_app(str(row["id"]))
            if target_type == "app_instance"
            else []
        )
        values: dict[str, object] = {}
        for runtime_mapping in manifest.spec.runtime.values.mappings:
            value = self._runtime_mapping_value(
                mapping=runtime_mapping,
                app_slug=slug,
                config=config,
                bindings=bindings,
            )
            set_helm_value(values, runtime_mapping.to.helmValue, value)
        return values

    def _runtime_mapping_value(
        self,
        *,
        mapping: RuntimeMapping,
        app_slug: str,
        config: dict[str, object],
        bindings: list[dict[str, object]],
    ) -> object:
        source = mapping.from_
        if source.kind == "config":
            if source.name not in config:
                raise RuntimeBlockedError(
                    reason="runtime_mapping_source_missing",
                    message=f"Config value {source.name} is not available.",
                )
            return config[source.name]

        if source.field is None:
            raise RuntimeBlockedError(
                reason="runtime_mapping_source_missing",
                message=f"Binding {source.name} field is not specified.",
            )
        binding = next(
            (item for item in bindings if item["alias"] == source.name),
            None,
        )
        if binding is None:
            raise RuntimeBlockedError(
                reason="runtime_mapping_source_missing",
                message=f"Binding {source.name} is not ready.",
            )
        values = _binding_output_values(binding)
        if values is None and self._binding_value_source is not None:
            values = self._binding_value_source.get_binding_values(
                app_slug=app_slug,
                service_slug=str(binding["service_instance_slug"]),
                alias=str(binding["alias"]),
                capability=str(binding["capability"]),
            )
        if values is None or source.field not in values:
            raise RuntimeBlockedError(
                reason="runtime_mapping_source_missing",
                message=f"Binding {source.name}.{source.field} is not available.",
            )
        return values[source.field]


def _manifest_from_path(
    *,
    target_type: str,
    path: Path,
) -> AppManifest | ServiceManifest:
    raw = yaml.safe_load(path.read_text())
    if target_type == "app_instance":
        return AppManifest.model_validate(raw)
    if target_type == "service_instance":
        return ServiceManifest.model_validate(raw)
    raise ValueError(f"unsupported provider deploy target type {target_type}")


def _chart_from_manifest(
    manifest: AppManifest | ServiceManifest,
) -> ProviderContext.Chart | None:
    chart = manifest.spec.runtime.chart
    if chart is None:
        return None
    return ProviderContext.Chart(
        repository=chart.repository,
        name=chart.name,
        version=chart.version,
    )


def _provider_name_from_manifest(
    manifest: AppManifest | ServiceManifest,
) -> str | None:
    provider = manifest.spec.runtime.provider
    if provider is None:
        return None
    return provider.name


def _manifest_config_values(
    row: dict[str, object],
    manifest: AppManifest | ServiceManifest,
) -> dict[str, object]:
    values: dict[str, object] = {}
    if isinstance(manifest, AppManifest):
        values.update(
            {
                option.name: option.default
                for option in manifest.spec.config.options
                if option.default is not None
            }
        )
    config_json = row.get("config_json")
    if isinstance(config_json, str):
        values.update(json.loads(config_json))
    return values


def _binding_output_values(binding: dict[str, object]) -> dict[str, str] | None:
    output_summary_json = binding.get("output_summary_json")
    if not isinstance(output_summary_json, str):
        return None
    output_summary = json.loads(output_summary_json)
    values = output_summary.get("values")
    if not isinstance(values, dict):
        return None
    if not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in values.items()
    ):
        return None
    return values
