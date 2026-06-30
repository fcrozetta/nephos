from __future__ import annotations

import json
from contextlib import suppress
from pathlib import Path
from typing import Protocol

import yaml

from nephos_api.catalog import AppManifest, RuntimeMapping, ServiceManifest
from nephos_api.helm_runtime import runtime_name, set_helm_value
from nephos_api.manifest_config import manifest_config_values
from nephos_api.providers.base import ProviderContext, RuntimeProvider
from nephos_api.provisioners.base import BindingProvisioner, BindingProvisioningContext
from nephos_api.repository import DesiredStateRepository
from nephos_api.runtime_errors import RuntimeBlockedError
from nephos_api.secret_refs import RuntimeSecretResolver, resolve_runtime_secret_value


class BindingValueSource(Protocol):
    def get_binding_values(
        self,
        *,
        app_slug: str,
        service_slug: str,
        alias: str,
        capability: str,
        protocol: str | None = None,
    ) -> dict[str, str] | None: ...


class ProviderRuntimeDeployer:
    def __init__(
        self,
        *,
        repository: DesiredStateRepository,
        app_provider: RuntimeProvider,
        service_provider: RuntimeProvider,
        binding_value_source: BindingValueSource | None = None,
        service_dependency_provisioner: BindingProvisioner | None = None,
        secret_resolver: RuntimeSecretResolver | None = None,
    ) -> None:
        self._repository = repository
        self._app_provider = app_provider
        self._service_provider = service_provider
        self._binding_value_source = binding_value_source
        self._service_dependency_provisioner = service_dependency_provisioner
        self._secret_resolver = secret_resolver

    def deploy(self, *, target_type: str, slug: str) -> None:
        context = self._context(target_type=target_type, slug=slug)
        self._provider_for(target_type).deploy(context)

    def uninstall(self, *, target_type: str, slug: str) -> None:
        row = self._instance_row(target_type=target_type, slug=slug)
        manifest = _manifest_from_path(
            target_type=target_type,
            path=Path(str(row["catalog_source_path"])),
        )
        if target_type == "service_instance" and isinstance(manifest, ServiceManifest):
            self._deprovision_service_dependencies(slug=slug, manifest=manifest)
        context = self._context_from_row(
            target_type=target_type,
            slug=slug,
            row=row,
            manifest=manifest,
            include_values=False,
        )
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
        return self._context_from_row(
            target_type=target_type,
            slug=slug,
            row=row,
            manifest=manifest,
            include_values=True,
        )

    def _context_from_row(
        self,
        *,
        target_type: str,
        slug: str,
        row: dict[str, object],
        manifest: AppManifest | ServiceManifest,
        include_values: bool,
    ) -> ProviderContext:
        return ProviderContext(
            target_type=target_type,
            slug=slug,
            runtime_name=runtime_name(target_type, slug),
            manifest=manifest,
            chart=_chart_from_manifest(manifest),
            values=(
                self._values_from_manifest(
                    target_type=target_type,
                    slug=slug,
                    row=row,
                    manifest=manifest,
                )
                if include_values
                else {}
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
        config = manifest_config_values(row, manifest)
        bindings = (
            self._repository.list_bindings_for_app(str(row["id"]))
            if target_type == "app_instance"
            else []
        )
        service_dependency_values = (
            self._service_dependency_values(slug=slug, manifest=manifest)
            if (
                target_type == "service_instance"
                and isinstance(manifest, ServiceManifest)
            )
            else {}
        )
        values: dict[str, object] = {}
        for runtime_mapping in manifest.spec.runtime.values.mappings:
            value = self._runtime_mapping_value(
                mapping=runtime_mapping,
                app_slug=slug,
                config=config,
                bindings=bindings,
                service_dependency_values=service_dependency_values,
            )
            set_helm_value(values, runtime_mapping.to.helmValue, value)
        return values

    def _service_dependency_values(
        self,
        *,
        slug: str,
        manifest: ServiceManifest,
    ) -> dict[str, dict[str, str]]:
        if not manifest.spec.requires:
            return {}
        if self._service_dependency_provisioner is None:
            raise RuntimeBlockedError(
                reason="service_dependency_provisioner_unavailable",
                message="Service dependency provisioning is not configured.",
            )
        values: dict[str, dict[str, str]] = {}
        for context in self._service_dependency_contexts(
            slug=slug,
            manifest=manifest,
            require_ready=True,
        ):
            provisioned = self._service_dependency_provisioner.provision_binding(
                context
            )
            if provisioned is None:
                raise RuntimeBlockedError(
                    reason="service_dependency_output_unavailable",
                    message=(
                        f"Service dependency {context.alias} did not return "
                        "binding values."
                    ),
                )
            values[context.alias] = provisioned
        return values

    def _deprovision_service_dependencies(
        self,
        *,
        slug: str,
        manifest: ServiceManifest,
    ) -> None:
        if not manifest.spec.requires:
            return
        if self._service_dependency_provisioner is None:
            raise RuntimeBlockedError(
                reason="service_dependency_provisioner_unavailable",
                message="Service dependency provisioning is not configured.",
            )
        contexts: list[BindingProvisioningContext] = []
        with suppress(RuntimeBlockedError):
            contexts = self._service_dependency_contexts(
                slug=slug,
                manifest=manifest,
                require_ready=False,
            )
        for context in contexts:
            self._service_dependency_provisioner.deprovision_binding(context)

    def _service_dependency_contexts(
        self,
        *,
        slug: str,
        manifest: ServiceManifest,
        require_ready: bool,
    ) -> list[BindingProvisioningContext]:
        contexts: list[BindingProvisioningContext] = []
        for requirement in manifest.spec.requires:
            alias = requirement.alias or _default_capability_alias(
                requirement.capability,
                requirement.protocol,
            )
            provider_row = self._service_dependency_provider(
                consumer_slug=slug,
                alias=alias,
                capability=requirement.capability,
                protocol=requirement.protocol,
                provider=requirement.provider,
                require_ready=require_ready,
            )
            contexts.append(
                BindingProvisioningContext(
                    binding_id=f"service-{slug}-{alias}",
                    app_slug=slug,
                    service_slug=str(provider_row["slug"]),
                    alias=alias,
                    capability=requirement.capability,
                    protocol=requirement.protocol,
                )
            )
        return contexts

    def _service_dependency_provider(
        self,
        *,
        consumer_slug: str,
        alias: str,
        capability: str,
        protocol: str | None,
        provider: str | None,
        require_ready: bool,
    ) -> dict[str, object]:
        eligible = []
        for row in self._repository.list_service_rows():
            if str(row["slug"]) == consumer_slug:
                continue
            if row["delete_requested_at"] is not None or row["lifecycle"] != "running":
                continue
            if require_ready and not self._service_provider_runtime_ready(row):
                continue
            if provider is not None and provider not in {
                str(row["slug"]),
                str(row["catalog_name"]),
            }:
                continue
            service_manifest = _manifest_from_path(
                target_type="service_instance",
                path=Path(str(row["catalog_source_path"])),
            )
            if not isinstance(service_manifest, ServiceManifest):
                continue
            if any(
                provided.capability == capability and provided.protocol == protocol
                for provided in service_manifest.spec.provides
            ):
                eligible.append(row)
        if len(eligible) == 1:
            return eligible[0]
        if not eligible:
            raise RuntimeBlockedError(
                reason="service_dependency_provider_unavailable",
                message=(
                    f"Service dependency {alias} requires {capability}/{protocol}; "
                    "install and start a matching Service first."
                ),
            )
        raise RuntimeBlockedError(
            reason="service_dependency_provider_selection_required",
            message=(
                f"Service dependency {alias} has multiple eligible providers; "
                "set an explicit provider in the Service catalog requirement."
            ),
        )

    def _service_provider_runtime_ready(self, row: dict[str, object]) -> bool:
        snapshot = self._repository.get_status_snapshot(
            resource_type="service_instance",
            resource_id=str(row["id"]),
        )
        return (
            snapshot is not None
            and snapshot["reconciliation"] == "succeeded"
            and snapshot["reason"] == "runtime_deployed"
        )

    def _runtime_mapping_value(
        self,
        *,
        mapping: RuntimeMapping,
        app_slug: str,
        config: dict[str, object],
        bindings: list[dict[str, object]],
        service_dependency_values: dict[str, dict[str, str]],
    ) -> object:
        source = mapping.from_
        if source.kind == "config":
            if source.name not in config:
                raise RuntimeBlockedError(
                    reason="runtime_mapping_source_missing",
                    message=f"Config value {source.name} is not available.",
                )
            return resolve_runtime_secret_value(
                config[source.name],
                self._secret_resolver,
            )

        if source.field is None:
            raise RuntimeBlockedError(
                reason="runtime_mapping_source_missing",
                message=f"Binding {source.name} field is not specified.",
            )
        if source.name in service_dependency_values:
            values = service_dependency_values[source.name]
            if source.field not in values:
                raise RuntimeBlockedError(
                    reason="runtime_mapping_source_missing",
                    message=f"Binding {source.name}.{source.field} is not available.",
                )
            return values[source.field]
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
                protocol=_optional_str(binding["protocol"]),
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


def _default_capability_alias(capability: str, protocol: str | None) -> str:
    if protocol is None:
        return capability
    return f"{capability}-{protocol}"


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
