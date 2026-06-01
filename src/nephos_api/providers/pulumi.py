from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from nephos_api.providers.base import ProviderContext
from nephos_api.runtime_errors import RuntimeBlockedError


@dataclass(frozen=True)
class PulumiHelmProviderConfig:
    work_dir: Path
    state_dir: Path
    kubeconfig: Path | None = None
    kube_context: str | None = None
    project_name: str = "nephos-api"


@dataclass(frozen=True)
class PulumiHelmReleaseSpec:
    project_name: str
    stack_name: str
    work_dir: Path
    state_dir: Path
    kubeconfig: Path | None
    kube_context: str | None
    release_name: str
    namespace: str
    chart_repository: str
    chart_name: str
    chart_version: str
    values: Mapping[str, object]

    @property
    def backend_url(self) -> str:
        return f"file://{self.state_dir}"


@dataclass(frozen=True)
class PulumiHelmReleaseConfig:
    name: str
    namespace: str
    repository: str
    chart: str
    version: str
    values: dict[str, object]


class PulumiHelmStackRunner(Protocol):
    def up(self, spec: PulumiHelmReleaseSpec) -> None: ...

    def destroy(self, spec: PulumiHelmReleaseSpec) -> None: ...


class PulumiHelmProvider:
    def __init__(
        self,
        *,
        config: PulumiHelmProviderConfig,
        runner: PulumiHelmStackRunner | None = None,
    ) -> None:
        self._config = config
        self._runner = runner or PulumiAutomationHelmStackRunner()

    def deploy(self, context: ProviderContext) -> None:
        self._runner.up(self._spec(context))

    def uninstall(self, context: ProviderContext) -> None:
        self._runner.destroy(self._spec(context))

    def _spec(self, context: ProviderContext) -> PulumiHelmReleaseSpec:
        if context.chart is None:
            raise RuntimeBlockedError(
                reason="runtime_chart_missing",
                message="Helm runtime provider requires chart runtime metadata.",
            )
        return PulumiHelmReleaseSpec(
            project_name=self._config.project_name,
            stack_name=context.runtime_name,
            work_dir=self._config.work_dir / context.runtime_name,
            state_dir=self._config.state_dir,
            kubeconfig=self._config.kubeconfig,
            kube_context=self._config.kube_context,
            release_name=context.runtime_name,
            namespace=context.runtime_name,
            chart_repository=context.chart.repository,
            chart_name=context.chart.name,
            chart_version=context.chart.version,
            values=context.values,
        )


class PulumiAutomationHelmStackRunner:
    def up(self, spec: PulumiHelmReleaseSpec) -> None:
        _ensure_pulumi_cli()
        _ensure_pulumi_local_backend_passphrase()
        stack = _create_or_select_stack(spec)
        stack.up(color="never", suppress_outputs=True)

    def destroy(self, spec: PulumiHelmReleaseSpec) -> None:
        _ensure_pulumi_cli()
        _ensure_pulumi_local_backend_passphrase()
        stack = _create_or_select_stack(spec)
        stack.destroy(color="never", suppress_outputs=True)


def _ensure_pulumi_cli() -> None:
    if shutil.which("pulumi") is None:
        raise RuntimeBlockedError(
            reason="pulumi_cli_missing",
            message="Pulumi CLI is required for the Pulumi provider runtime path.",
        )


def _ensure_pulumi_local_backend_passphrase() -> None:
    if (
        not os.environ.get("PULUMI_CONFIG_PASSPHRASE")
        and not os.environ.get("PULUMI_CONFIG_PASSPHRASE_FILE")
    ):
        raise RuntimeBlockedError(
            reason="pulumi_passphrase_missing",
            message=(
                "PULUMI_CONFIG_PASSPHRASE or PULUMI_CONFIG_PASSPHRASE_FILE "
                "is required for the Pulumi local backend."
            ),
        )


def _pulumi_release_config(spec: PulumiHelmReleaseSpec) -> PulumiHelmReleaseConfig:
    return PulumiHelmReleaseConfig(
        name=spec.release_name,
        namespace=spec.namespace,
        repository=spec.chart_repository,
        chart=spec.chart_name,
        version=spec.chart_version,
        values=dict(spec.values),
    )


def _pulumi_workspace_env_vars(spec: PulumiHelmReleaseSpec) -> dict[str, str]:
    env_vars = {"PULUMI_BACKEND_URL": spec.backend_url}
    if spec.kubeconfig is not None:
        env_vars["KUBECONFIG"] = str(spec.kubeconfig)
    passphrase = os.environ.get("PULUMI_CONFIG_PASSPHRASE")
    if passphrase:
        env_vars["PULUMI_CONFIG_PASSPHRASE"] = passphrase
    passphrase_file = os.environ.get("PULUMI_CONFIG_PASSPHRASE_FILE")
    if passphrase_file:
        env_vars["PULUMI_CONFIG_PASSPHRASE_FILE"] = passphrase_file
    return env_vars


def _create_or_select_stack(spec: PulumiHelmReleaseSpec):
    from pulumi import automation as auto

    spec.work_dir.mkdir(parents=True, exist_ok=True)
    spec.state_dir.mkdir(parents=True, exist_ok=True)
    return auto.create_or_select_stack(
        stack_name=spec.stack_name,
        project_name=spec.project_name,
        program=lambda: _pulumi_program(spec),
        opts=auto.LocalWorkspaceOptions(
            work_dir=str(spec.work_dir),
            env_vars=_pulumi_workspace_env_vars(spec),
            project_settings=auto.ProjectSettings(
                name=spec.project_name,
                runtime="python",
                backend=auto.ProjectBackend(url=spec.backend_url),
            ),
        ),
    )


def _pulumi_program(spec: PulumiHelmReleaseSpec) -> None:
    import pulumi
    import pulumi_kubernetes as k8s
    from pulumi_kubernetes.helm.v3 import (
        Release,
        ReleaseArgs,
        RepositoryOptsArgs,
    )

    provider_kwargs: dict[str, object] = {}
    if spec.kubeconfig is not None:
        provider_kwargs["kubeconfig"] = spec.kubeconfig.read_text()
    if spec.kube_context is not None:
        provider_kwargs["context"] = spec.kube_context
    provider = (
        k8s.Provider("k8s", **provider_kwargs)
        if provider_kwargs
        else None
    )
    opts = pulumi.ResourceOptions(provider=provider) if provider is not None else None
    release = _pulumi_release_config(spec)
    Release(
        release.name,
        ReleaseArgs(
            name=release.name,
            chart=release.chart,
            version=release.version,
            namespace=release.namespace,
            create_namespace=True,
            repository_opts=RepositoryOptsArgs(repo=release.repository),
            values=release.values,
        ),
        opts=opts,
    )
