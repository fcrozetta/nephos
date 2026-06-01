from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from nephos_api.providers.base import ProviderContext
from nephos_api.providers.pulumi import (
    _ensure_pulumi_cli,
    _ensure_pulumi_local_backend_passphrase,
    _pulumi_workspace_env_vars,
)

PulumiKubernetesWorkload = Literal["reference-app", "postgres-service"]


@dataclass(frozen=True)
class PulumiKubernetesProviderConfig:
    work_dir: Path
    state_dir: Path
    kubeconfig: Path | None = None
    kube_context: str | None = None
    project_name: str = "nephos-api"


@dataclass(frozen=True)
class PulumiKubernetesWorkloadSpec:
    project_name: str
    stack_name: str
    work_dir: Path
    state_dir: Path
    kubeconfig: Path | None
    kube_context: str | None
    runtime_name: str
    namespace: str
    workload: PulumiKubernetesWorkload
    values: Mapping[str, object]

    @property
    def backend_url(self) -> str:
        return f"file://{self.state_dir}"


class PulumiKubernetesStackRunner(Protocol):
    def up(self, spec: PulumiKubernetesWorkloadSpec) -> None: ...

    def destroy(self, spec: PulumiKubernetesWorkloadSpec) -> None: ...


class PulumiKubernetesProvider:
    def __init__(
        self,
        *,
        config: PulumiKubernetesProviderConfig,
        workload: PulumiKubernetesWorkload,
        runner: PulumiKubernetesStackRunner | None = None,
    ) -> None:
        self._config = config
        self._workload = workload
        self._runner = runner or PulumiAutomationKubernetesStackRunner()

    def deploy(self, context: ProviderContext) -> None:
        self._runner.up(self._spec(context))

    def uninstall(self, context: ProviderContext) -> None:
        self._runner.destroy(self._spec(context))

    def _spec(self, context: ProviderContext) -> PulumiKubernetesWorkloadSpec:
        return PulumiKubernetesWorkloadSpec(
            project_name=self._config.project_name,
            stack_name=context.runtime_name,
            work_dir=self._config.work_dir / context.runtime_name,
            state_dir=self._config.state_dir,
            kubeconfig=self._config.kubeconfig,
            kube_context=self._config.kube_context,
            runtime_name=context.runtime_name,
            namespace=context.runtime_name,
            workload=self._workload,
            values=context.values,
        )


class PulumiAutomationKubernetesStackRunner:
    def up(self, spec: PulumiKubernetesWorkloadSpec) -> None:
        _ensure_pulumi_cli()
        _ensure_pulumi_local_backend_passphrase()
        stack = _create_or_select_stack(spec)
        stack.up(color="never", suppress_outputs=True)

    def destroy(self, spec: PulumiKubernetesWorkloadSpec) -> None:
        _ensure_pulumi_cli()
        _ensure_pulumi_local_backend_passphrase()
        stack = _create_or_select_stack(spec)
        stack.destroy(color="never", suppress_outputs=True)


def _create_or_select_stack(spec: PulumiKubernetesWorkloadSpec):
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


def _pulumi_program(spec: PulumiKubernetesWorkloadSpec) -> None:
    import pulumi
    import pulumi_kubernetes as k8s

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
    if spec.workload == "reference-app":
        _reference_app(spec, k8s=k8s, opts=opts)
        return
    if spec.workload == "postgres-service":
        _postgres_service(spec, k8s=k8s, opts=opts)
        return
    raise ValueError(f"unsupported Pulumi Kubernetes workload {spec.workload}")


def _reference_app(
    spec: PulumiKubernetesWorkloadSpec,
    *,
    k8s,
    opts,
) -> None:
    labels = _labels(spec)
    selector = {"app.kubernetes.io/name": spec.runtime_name}
    k8s.apps.v1.Deployment(
        spec.runtime_name,
        metadata={
            "name": spec.runtime_name,
            "namespace": spec.namespace,
            "labels": labels,
        },
        spec={
            "replicas": 1,
            "selector": {"matchLabels": selector},
            "template": {
                "metadata": {"labels": {**labels, **selector}},
                "spec": {
                    "containers": [
                        {
                            "name": "web",
                            "image": "nginx:1.27-alpine",
                            "ports": [{"name": "http", "containerPort": 80}],
                        }
                    ]
                },
            },
        },
        opts=opts,
    )
    k8s.core.v1.Service(
        spec.runtime_name,
        metadata={
            "name": spec.runtime_name,
            "namespace": spec.namespace,
            "labels": labels,
        },
        spec={
            "ports": [{"name": "http", "port": 80, "targetPort": "http"}],
            "selector": selector,
        },
        opts=opts,
    )


def _postgres_service(
    spec: PulumiKubernetesWorkloadSpec,
    *,
    k8s,
    opts,
) -> None:
    name = f"{spec.runtime_name}-postgresql"
    labels = _labels(spec)
    selector = {"app.kubernetes.io/name": name}
    storage_size = str(spec.values.get("storageSize", "1Gi"))
    storage_class_name = spec.values.get("storageClassName")
    k8s.core.v1.Secret(
        name,
        metadata={
            "name": name,
            "namespace": spec.namespace,
            "labels": labels,
        },
        type="Opaque",
        string_data={"postgres-password": "nephos-local-postgres"},
        opts=opts,
    )
    k8s.core.v1.Service(
        name,
        metadata={
            "name": name,
            "namespace": spec.namespace,
            "labels": labels,
        },
        spec={
            "ports": [
                {
                    "name": "postgresql",
                    "port": 5432,
                    "targetPort": "postgresql",
                }
            ],
            "selector": selector,
        },
        opts=opts,
    )
    k8s.apps.v1.StatefulSet(
        name,
        metadata={
            "name": name,
            "namespace": spec.namespace,
            "labels": labels,
        },
        spec={
            "serviceName": name,
            "replicas": 1,
            "selector": {"matchLabels": selector},
            "template": {
                "metadata": {"labels": {**labels, **selector}},
                "spec": {
                    "containers": [
                        {
                            "name": "postgresql",
                            "image": "postgres:16-alpine",
                            "ports": [
                                {"name": "postgresql", "containerPort": 5432}
                            ],
                            "env": [
                                {
                                    "name": "POSTGRES_PASSWORD",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": name,
                                            "key": "postgres-password",
                                        }
                                    },
                                },
                                {
                                    "name": "PGDATA",
                                    "value": "/var/lib/postgresql/data/pgdata",
                                },
                            ],
                            "readinessProbe": {
                                "exec": {
                                    "command": [
                                        "pg_isready",
                                        "-U",
                                        "postgres",
                                    ]
                                },
                                "initialDelaySeconds": 5,
                                "periodSeconds": 2,
                            },
                            "volumeMounts": [
                                {
                                    "name": "data",
                                    "mountPath": "/var/lib/postgresql/data",
                                }
                            ],
                        }
                    ],
                },
            },
            "volumeClaimTemplates": [
                {
                    "metadata": {
                        "name": "data",
                        "labels": labels,
                    },
                    "spec": {
                        "accessModes": ["ReadWriteOnce"],
                        "resources": {"requests": {"storage": storage_size}},
                        **(
                            {"storageClassName": str(storage_class_name)}
                            if storage_class_name is not None
                            else {}
                        ),
                    },
                }
            ],
        },
        opts=opts,
    )


def _labels(spec: PulumiKubernetesWorkloadSpec) -> dict[str, str]:
    return {
        "app.kubernetes.io/managed-by": "nephos",
        "app.kubernetes.io/part-of": "nephos-dev-reference",
        "nephos.pro/runtime-name": spec.runtime_name,
    }
