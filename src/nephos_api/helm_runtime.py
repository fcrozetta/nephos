from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import yaml

from nephos_api.catalog import AppManifest, RuntimeMapping, ServiceManifest
from nephos_api.kubernetes_runtime import namespace_name
from nephos_api.repository import DesiredStateRepository
from nephos_api.runtime_errors import RuntimeBlockedError


@dataclass(frozen=True)
class HelmChartRef:
    repository: str
    name: str
    version: str


@dataclass(frozen=True)
class HelmCommand:
    args: list[str]
    env: dict[str, str]


@dataclass(frozen=True)
class HelmRuntimeConfig:
    kubeconfig: Path | None = None
    kube_context: str | None = None
    timeout: str = "5m"


def build_upgrade_install_command(
    *,
    release: str,
    namespace: str,
    chart: HelmChartRef,
    values_file: Path,
    config: HelmRuntimeConfig,
) -> HelmCommand:
    args = [
        "helm",
        "upgrade",
        "--install",
        release,
        chart.name,
        "--repo",
        chart.repository,
        "--version",
        chart.version,
        "--namespace",
        namespace,
        "--create-namespace",
        "--wait",
        "--timeout",
        config.timeout,
        "-f",
        str(values_file),
    ]
    _append_context(args, config)
    return HelmCommand(args=args, env=_helm_env(config))


def build_uninstall_command(
    *,
    release: str,
    namespace: str,
    config: HelmRuntimeConfig,
) -> HelmCommand:
    args = [
        "helm",
        "uninstall",
        release,
        "--namespace",
        namespace,
        "--ignore-not-found",
        "--wait",
        "--timeout",
        config.timeout,
    ]
    _append_context(args, config)
    return HelmCommand(args=args, env=_helm_env(config))


def set_helm_value(
    values: dict[str, object],
    path: str,
    value: object,
) -> None:
    segments = path.split(".")
    if any(segment == "" for segment in segments):
        raise ValueError("invalid Helm value path")

    current = values
    for segment in segments[:-1]:
        existing = current.setdefault(segment, {})
        if not isinstance(existing, dict):
            raise ValueError("invalid Helm value path")
        current = existing
    current[segments[-1]] = value


def runtime_name(kind: str, slug: str) -> str:
    if kind not in {"app_instance", "service_instance"}:
        raise ValueError(f"unsupported Helm runtime kind {kind}")
    return namespace_name(kind, slug)


class HelmRunner:
    def run(self, command: HelmCommand) -> None:
        env = os.environ.copy()
        env.update(command.env)
        subprocess.run(command.args, check=True, env=env)


class HelmRuntime:
    def __init__(
        self,
        *,
        config: HelmRuntimeConfig,
        runner: HelmRunner,
        temp_dir: Path | None = None,
    ) -> None:
        self._config = config
        self._runner = runner
        self._temp_dir = temp_dir

    def upgrade_install(
        self,
        *,
        kind: str,
        slug: str,
        chart: HelmChartRef,
        values: Mapping[str, object],
    ) -> None:
        release = runtime_name(kind, slug)
        values_path = self._write_values_file(values)
        try:
            self._runner.run(
                build_upgrade_install_command(
                    release=release,
                    namespace=release,
                    chart=chart,
                    values_file=values_path,
                    config=self._config,
                )
            )
        finally:
            values_path.unlink(missing_ok=True)

    def uninstall(self, *, kind: str, slug: str) -> None:
        release = runtime_name(kind, slug)
        self._runner.run(
            build_uninstall_command(
                release=release,
                namespace=release,
                config=self._config,
            )
        )

    def _write_values_file(self, values: Mapping[str, object]) -> Path:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            prefix="nephos-helm-values-",
            dir=self._temp_dir,
            delete=False,
        ) as handle:
            yaml.safe_dump(dict(values), handle, sort_keys=True)
            return Path(handle.name)


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


class ManifestBindingValueSource:
    def __init__(self, values: Mapping[tuple[str, str], dict[str, str]]) -> None:
        self._values = values

    def get_binding_values(
        self,
        *,
        app_slug: str,
        service_slug: str,
        alias: str,
        capability: str,
        protocol: str | None = None,
    ) -> dict[str, str] | None:
        return self._values.get((app_slug, alias))


class ManifestHelmDeployer:
    def __init__(
        self,
        *,
        repository: DesiredStateRepository,
        helm_runtime: HelmRuntime,
        binding_value_source: BindingValueSource | None = None,
    ) -> None:
        self._repository = repository
        self._helm_runtime = helm_runtime
        self._binding_value_source = binding_value_source

    def deploy(self, *, target_type: str, slug: str) -> None:
        row = self._instance_row(target_type=target_type, slug=slug)
        manifest = _manifest_from_path(
            target_type=target_type,
            path=Path(str(row["catalog_source_path"])),
        )
        chart = _chart_from_manifest(manifest)
        values = self._values_from_manifest(
            target_type=target_type,
            slug=slug,
            row=row,
            manifest=manifest,
        )
        self._helm_runtime.upgrade_install(
            kind=target_type,
            slug=slug,
            chart=chart,
            values=values,
        )

    def uninstall(self, *, target_type: str, slug: str) -> None:
        self._helm_runtime.uninstall(kind=target_type, slug=slug)

    def _instance_row(self, *, target_type: str, slug: str) -> dict[str, object]:
        if target_type == "app_instance":
            row = self._repository.get_app_row(slug)
        elif target_type == "service_instance":
            row = self._repository.get_service_row(slug)
        else:
            raise ValueError(f"unsupported Helm deploy target type {target_type}")
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
            (
                item
                for item in bindings
                if item["alias"] == source.name
            ),
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
                message=(
                    f"Binding {source.name}.{source.field} is not available."
                ),
            )
        return values[source.field]


def _append_context(args: list[str], config: HelmRuntimeConfig) -> None:
    if config.kube_context is not None:
        args.extend(["--kube-context", config.kube_context])


def _helm_env(config: HelmRuntimeConfig) -> dict[str, str]:
    if config.kubeconfig is None:
        return {}
    return {"KUBECONFIG": str(config.kubeconfig)}


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
    raise ValueError(f"unsupported Helm deploy target type {target_type}")


def _chart_from_manifest(manifest: AppManifest | ServiceManifest) -> HelmChartRef:
    chart = manifest.spec.runtime.chart
    return HelmChartRef(
        repository=chart.repository,
        name=chart.name,
        version=chart.version,
    )


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


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
