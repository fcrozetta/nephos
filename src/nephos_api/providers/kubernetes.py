from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from nephos_api.providers.base import ProviderContext
from nephos_api.providers.pulumi import (
    _ensure_pulumi_cli,
    _ensure_pulumi_local_backend_passphrase,
    _pulumi_workspace_env_vars,
)
from nephos_api.runtime_errors import RuntimeBlockedError

PulumiKubernetesWorkload = str
PulumiKubernetesProgram = Callable[..., None]


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
    workload_program = _workload_program(spec.workload)

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
    workload_program(spec, k8s=k8s, opts=opts)


def _workload_program(workload: str) -> PulumiKubernetesProgram:
    try:
        return _WORKLOAD_PROGRAMS[workload]
    except KeyError as exc:
        raise RuntimeBlockedError(
            reason="runtime_provider_unknown",
            message=f"Pulumi Kubernetes workload {workload} is not available.",
        ) from exc


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


def _zitadel_service(
    spec: PulumiKubernetesWorkloadSpec,
    *,
    k8s,
    opts,
) -> None:
    name = f"{spec.runtime_name}-zitadel"
    labels = _labels(spec)
    selector = {"app.kubernetes.io/name": name}
    image = _string_value(spec.values, "image", "ghcr.io/zitadel/zitadel:v2.58.0")
    external_host = _string_value(
        spec.values,
        "externalHost",
        f"{spec.runtime_name}.nephos.localhost",
    )
    admin_username = _string_value(
        spec.values,
        "adminUsername",
        "root@zitadel.nephos.localhost",
    )
    admin_password = _string_value(
        spec.values,
        "adminPassword",
        "nephos-local-zitadel",
    )
    k8s.core.v1.Secret(
        name,
        metadata={
            "name": name,
            "namespace": spec.namespace,
            "labels": labels,
        },
        type="Opaque",
        string_data={
            "admin-username": admin_username,
            "admin-password": admin_password,
        },
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
            "ports": [{"name": "http", "port": 8080, "targetPort": "http"}],
            "selector": selector,
        },
        opts=opts,
    )
    k8s.apps.v1.Deployment(
        name,
        metadata={
            "name": name,
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
                            "name": "zitadel",
                            "image": image,
                            "args": [
                                "start-from-init",
                                "--masterkeyFromEnv",
                            ],
                            "ports": [
                                {"name": "http", "containerPort": 8080}
                            ],
                            "env": [
                                {
                                    "name": "ZITADEL_EXTERNALDOMAIN",
                                    "value": external_host,
                                },
                                {
                                    "name": "ZITADEL_FIRSTINSTANCE_ORG_HUMAN_USERNAME",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": name,
                                            "key": "admin-username",
                                        }
                                    },
                                },
                                {
                                    "name": "ZITADEL_FIRSTINSTANCE_ORG_HUMAN_PASSWORD",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": name,
                                            "key": "admin-password",
                                        }
                                    },
                                },
                            ],
                        }
                    ]
                },
            },
        },
        opts=opts,
    )


def _seaweedfs_service(
    spec: PulumiKubernetesWorkloadSpec,
    *,
    k8s,
    opts,
) -> None:
    name = f"{spec.runtime_name}-seaweedfs"
    labels = _labels(spec)
    selector = {"app.kubernetes.io/name": name}
    image = _string_value(spec.values, "image", "chrislusf/seaweedfs:3.85")
    access_key = _string_value(spec.values, "s3AccessKey", "nephos-local-seaweedfs")
    secret_key = _string_value(spec.values, "s3SecretKey", "nephos-local-seaweedfs")
    k8s.core.v1.Secret(
        name,
        metadata={
            "name": name,
            "namespace": spec.namespace,
            "labels": labels,
        },
        type="Opaque",
        string_data={
            "s3-access-key": access_key,
            "s3-secret-key": secret_key,
        },
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
            "ports": [{"name": "s3", "port": 8333, "targetPort": "s3"}],
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
                            "name": "seaweedfs",
                            "image": image,
                            "args": [
                                "server",
                                "-s3",
                                "-s3.port=8333",
                                "-dir=/data",
                            ],
                            "ports": [
                                {"name": "s3", "containerPort": 8333}
                            ],
                            "env": [
                                {
                                    "name": "WEED_S3_ACCESS_KEY",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": name,
                                            "key": "s3-access-key",
                                        }
                                    },
                                },
                                {
                                    "name": "WEED_S3_SECRET_KEY",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": name,
                                            "key": "s3-secret-key",
                                        }
                                    },
                                },
                            ],
                            "volumeMounts": [
                                {"name": "data", "mountPath": "/data"}
                            ],
                        }
                    ]
                },
            },
            "volumeClaimTemplates": [_volume_claim_template(spec, labels)],
        },
        opts=opts,
    )


def _arcadedb_service(
    spec: PulumiKubernetesWorkloadSpec,
    *,
    k8s,
    opts,
) -> None:
    name = f"{spec.runtime_name}-arcadedb"
    labels = _labels(spec)
    selector = {"app.kubernetes.io/name": name}
    image = _string_value(spec.values, "image", "arcadedata/arcadedb:25.5.1")
    root_password = _string_value(
        spec.values,
        "rootPassword",
        "nephos-local-arcadedb",
    )
    ports = [
        {"name": "http", "port": 2480, "targetPort": "http"},
        {"name": "binary", "port": 2424, "targetPort": "binary"},
    ]
    container_ports = [
        {"name": "http", "containerPort": 2480},
        {"name": "binary", "containerPort": 2424},
    ]
    if _bool_value(spec.values, "enableGremlin", False):
        ports.append({"name": "gremlin", "port": 8182, "targetPort": "gremlin"})
        container_ports.append({"name": "gremlin", "containerPort": 8182})
    if _bool_value(spec.values, "enableMongo", False):
        ports.append({"name": "mongo", "port": 27017, "targetPort": "mongo"})
        container_ports.append({"name": "mongo", "containerPort": 27017})
    k8s.core.v1.Secret(
        name,
        metadata={
            "name": name,
            "namespace": spec.namespace,
            "labels": labels,
        },
        type="Opaque",
        string_data={"root-password": root_password},
        opts=opts,
    )
    k8s.core.v1.Service(
        name,
        metadata={
            "name": name,
            "namespace": spec.namespace,
            "labels": labels,
        },
        spec={"ports": ports, "selector": selector},
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
                            "name": "arcadedb",
                            "image": image,
                            "ports": container_ports,
                            "env": [
                                {
                                    "name": "JAVA_OPTS",
                                    "value": (
                                        "-Darcadedb.server.rootPasswordFile="
                                        "/run/secrets/arcadedb/root-password"
                                    ),
                                }
                            ],
                            "volumeMounts": [
                                {
                                    "name": "data",
                                    "mountPath": "/home/arcadedb/databases",
                                },
                                {
                                    "name": "credentials",
                                    "mountPath": "/run/secrets/arcadedb",
                                    "readOnly": True,
                                },
                            ],
                        }
                    ],
                    "volumes": [
                        {
                            "name": "credentials",
                            "secret": {"secretName": name},
                        }
                    ],
                },
            },
            "volumeClaimTemplates": [_volume_claim_template(spec, labels)],
        },
        opts=opts,
    )


def _string_value(
    values: Mapping[str, object],
    name: str,
    default: str,
) -> str:
    value = values.get(name, default)
    return str(value)


def _bool_value(
    values: Mapping[str, object],
    name: str,
    default: bool,
) -> bool:
    value = values.get(name, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _volume_claim_template(
    spec: PulumiKubernetesWorkloadSpec,
    labels: Mapping[str, str],
) -> dict[str, object]:
    storage_size = _string_value(spec.values, "storageSize", "1Gi")
    storage_class_name = spec.values.get("storageClassName")
    return {
        "metadata": {
            "name": "data",
            "labels": dict(labels),
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


def _labels(spec: PulumiKubernetesWorkloadSpec) -> dict[str, str]:
    return {
        "app.kubernetes.io/managed-by": "nephos",
        "app.kubernetes.io/part-of": "nephos-dev-reference",
        "nephos.pro/runtime-name": spec.runtime_name,
    }


_WORKLOAD_PROGRAMS: dict[str, PulumiKubernetesProgram] = {
    "reference-app": _reference_app,
    "postgres-service": _postgres_service,
    "zitadel-service": _zitadel_service,
    "seaweedfs-service": _seaweedfs_service,
    "arcadedb-service": _arcadedb_service,
}
