from __future__ import annotations

import json
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
    provider = k8s.Provider("k8s", **provider_kwargs) if provider_kwargs else None
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
    image = _string_value(spec.values, "image", "postgres:16-alpine")
    admin_password = _required_string_value(spec.values, "adminPassword")
    zitadel_database = _string_value(spec.values, "zitadelDatabase", "zitadel")
    zitadel_username = _string_value(spec.values, "zitadelUsername", "zitadel")
    zitadel_password = _optional_string_value(spec.values, "zitadelPassword")
    secret_data = {
        "postgres-password": admin_password,
        **(
            {"zitadel-password": zitadel_password}
            if zitadel_password is not None
            else {}
        ),
        **(
            {
                "010-nephos-zitadel.sql": _postgres_zitadel_init_sql(
                    database=zitadel_database,
                    username=zitadel_username,
                    password=zitadel_password,
                )
            }
            if zitadel_password is not None
            else {}
        ),
    }
    k8s.core.v1.Secret(
        name,
        metadata={
            "name": name,
            "namespace": spec.namespace,
            "labels": labels,
        },
        type="Opaque",
        string_data=secret_data,
        opts=opts,
    )
    k8s.core.v1.Service(
        name,
        metadata={
            "name": name,
            "namespace": spec.namespace,
            "labels": labels,
            "annotations": {"pulumi.com/skipAwait": "true"},
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
    volume_mounts: list[dict[str, object]] = [
        {
            "name": "data",
            "mountPath": "/var/lib/postgresql/data",
        }
    ]
    if zitadel_password is not None:
        volume_mounts.append(
            {
                "name": "initdb",
                "mountPath": "/docker-entrypoint-initdb.d",
                "readOnly": True,
            }
        )
    pod_volumes = []
    if zitadel_password is not None:
        pod_volumes.append(
            {
                "name": "initdb",
                "secret": {
                    "secretName": name,
                    "items": [
                        {
                            "key": "010-nephos-zitadel.sql",
                            "path": "010-nephos-zitadel.sql",
                        }
                    ],
                },
            }
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
                    **({"volumes": pod_volumes} if pod_volumes else {}),
                    "containers": [
                        {
                            "name": "postgresql",
                            "image": image,
                            "ports": [{"name": "postgresql", "containerPort": 5432}],
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
                            "volumeMounts": volume_mounts,
                        }
                    ],
                },
            },
            "volumeClaimTemplates": [_volume_claim_template(spec, labels)],
        },
        opts=opts,
    )


def _postgres_zitadel_init_sql(
    *,
    database: str,
    username: str,
    password: str,
) -> str:
    quoted_database = _postgres_identifier(database)
    quoted_username = _postgres_identifier(username)
    escaped_database = database.replace("'", "''")
    escaped_username = username.replace("'", "''")
    escaped_password = password.replace("'", "''")
    return (
        "DO $$\n"
        "BEGIN\n"
        "  IF NOT EXISTS ("
        f"SELECT FROM pg_roles WHERE rolname = '{escaped_username}'"
        ") THEN\n"
        f"    CREATE ROLE {quoted_username} LOGIN PASSWORD '{escaped_password}';\n"
        "  ELSE\n"
        f"    ALTER ROLE {quoted_username} WITH LOGIN PASSWORD '{escaped_password}';\n"
        "  END IF;\n"
        "END\n"
        "$$;\n"
        f"SELECT 'CREATE DATABASE {quoted_database} OWNER {quoted_username}'\n"
        "WHERE NOT EXISTS ("
        f"SELECT FROM pg_database WHERE datname = '{escaped_database}'"
        ")\\gexec\n"
        f"GRANT ALL PRIVILEGES ON DATABASE {quoted_database} TO {quoted_username};\n"
    )


def _postgres_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _cloudflared_service(
    spec: PulumiKubernetesWorkloadSpec,
    *,
    k8s,
    opts,
) -> None:
    name = f"{spec.runtime_name}-cloudflared"
    labels = _labels(spec)
    selector = {"app.kubernetes.io/name": name}
    image = _string_value(spec.values, "image", "cloudflare/cloudflared:2026.6.1")
    tunnel_name = _required_string_value(spec.values, "tunnelName")
    credentials_secret_name = _required_string_value(
        spec.values,
        "credentialsSecretName",
    )
    credentials_secret_key = _string_value(
        spec.values,
        "credentialsSecretKey",
        "credentials.json",
    )
    hostname = _required_string_value(spec.values, "hostname")
    origin_service_url = _required_string_value(spec.values, "originServiceUrl")
    origin_host_header = _optional_string_value(spec.values, "originHostHeader")
    config = _cloudflared_config(
        tunnel_name=tunnel_name,
        hostname=hostname,
        origin_service_url=origin_service_url,
        origin_host_header=origin_host_header,
    )
    k8s.core.v1.ConfigMap(
        name,
        metadata={
            "name": name,
            "namespace": spec.namespace,
            "labels": labels,
        },
        data={"config.yml": config},
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
                            "name": "cloudflared",
                            "image": image,
                            "args": [
                                "tunnel",
                                "--config",
                                "/etc/cloudflared/config/config.yml",
                                "run",
                            ],
                            "ports": [{"name": "metrics", "containerPort": 2000}],
                            "readinessProbe": {
                                "httpGet": {"path": "/ready", "port": 2000},
                                "initialDelaySeconds": 5,
                                "periodSeconds": 10,
                            },
                            "livenessProbe": {
                                "httpGet": {"path": "/ready", "port": 2000},
                                "initialDelaySeconds": 15,
                                "periodSeconds": 20,
                            },
                            "volumeMounts": [
                                {
                                    "name": "config",
                                    "mountPath": "/etc/cloudflared/config",
                                    "readOnly": True,
                                },
                                {
                                    "name": "credentials",
                                    "mountPath": "/etc/cloudflared/credentials.json",
                                    "subPath": "credentials.json",
                                    "readOnly": True,
                                },
                            ],
                        }
                    ],
                    "volumes": [
                        {"name": "config", "configMap": {"name": name}},
                        {
                            "name": "credentials",
                            "secret": {
                                "secretName": credentials_secret_name,
                                "items": [
                                    {
                                        "key": credentials_secret_key,
                                        "path": "credentials.json",
                                    }
                                ],
                            },
                        },
                    ],
                },
            },
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
    external_port = _int_value(spec.values, "externalPort", 8080)
    external_secure = _bool_value(spec.values, "externalSecure", False)
    admin_username = _string_value(
        spec.values,
        "adminUsername",
        "root@zitadel.nephos.localhost",
    )
    admin_password = _required_string_value(spec.values, "adminPassword")
    _validate_zitadel_admin_password(admin_password)
    master_key = _zitadel_master_key(spec.values)
    database_password = _required_string_value(spec.values, "databasePassword")
    database_host = _string_value(spec.values, "databaseHost", "127.0.0.1")
    database_port = _int_value(spec.values, "databasePort", 5432)
    database_name = _string_value(spec.values, "databaseName", "zitadel")
    database_username = _string_value(spec.values, "databaseUsername", "zitadel")
    database_admin_username = _string_value(
        spec.values,
        "databaseAdminUsername",
        database_username,
    )
    database_admin_password = _string_value(
        spec.values,
        "databaseAdminPassword",
        database_password,
    )
    database_ssl_mode = _string_value(spec.values, "databaseSslMode", "disable")
    embedded_postgres = _bool_value(spec.values, "embeddedPostgres", False)
    bootstrap_machine_username = _string_value(
        spec.values,
        "bootstrapMachineUsername",
        "nephos-provisioner",
    )
    bootstrap_machine_name = _string_value(
        spec.values,
        "bootstrapMachineName",
        "Nephos Provisioner",
    )
    bootstrap_machine_key_path = _string_value(
        spec.values,
        "bootstrapMachineKeyPath",
        "/var/lib/zitadel-bootstrap/nephos-provisioner-key.json",
    )
    bootstrap_machine_key_expiration = _required_string_value(
        spec.values,
        "bootstrapMachineKeyExpiration",
    )
    ingress_enabled = _bool_value(spec.values, "ingressEnabled", False)
    ingress_class_name = _optional_string_value(spec.values, "ingressClassName")
    bootstrap_mount_path = bootstrap_machine_key_path.rsplit("/", 1)[0]
    bootstrap_reader_image = _string_value(
        spec.values,
        "bootstrapReaderImage",
        "busybox:1.36.1",
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
            "master-key": master_key,
            "database-password": database_password,
            "database-admin-password": database_admin_password,
        },
        opts=opts,
    )
    k8s.core.v1.Service(
        name,
        metadata={
            "name": name,
            "namespace": spec.namespace,
            "labels": labels,
            "annotations": {"pulumi.com/skipAwait": "true"},
        },
        spec={
            "ports": [{"name": "http", "port": 8080, "targetPort": "http"}],
            "selector": selector,
        },
        opts=opts,
    )
    if ingress_enabled:
        _service_ingress(
            name=name,
            namespace=spec.namespace,
            labels=labels,
            host=external_host,
            service_name=name,
            service_port=8080,
            ingress_class_name=ingress_class_name,
            k8s=k8s,
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
                            "name": "zitadel",
                            "image": image,
                            "args": [
                                "start-from-init",
                                "--masterkeyFromEnv",
                            ],
                            "ports": [{"name": "http", "containerPort": 8080}],
                            "env": [
                                {
                                    "name": "ZITADEL_EXTERNALDOMAIN",
                                    "value": external_host,
                                },
                                {
                                    "name": "ZITADEL_EXTERNALPORT",
                                    "value": str(external_port),
                                },
                                {
                                    "name": "ZITADEL_EXTERNALSECURE",
                                    "value": str(external_secure).lower(),
                                },
                                {
                                    "name": "ZITADEL_TLS_ENABLED",
                                    "value": "false",
                                },
                                {
                                    "name": "ZITADEL_FIRSTINSTANCE_MACHINEKEYPATH",
                                    "value": bootstrap_machine_key_path,
                                },
                                {
                                    "name": (
                                        "ZITADEL_FIRSTINSTANCE_ORG_MACHINE_"
                                        "MACHINE_USERNAME"
                                    ),
                                    "value": bootstrap_machine_username,
                                },
                                {
                                    "name": (
                                        "ZITADEL_FIRSTINSTANCE_ORG_MACHINE_MACHINE_NAME"
                                    ),
                                    "value": bootstrap_machine_name,
                                },
                                {
                                    "name": (
                                        "ZITADEL_FIRSTINSTANCE_ORG_MACHINE_"
                                        "MACHINEKEY_TYPE"
                                    ),
                                    "value": "1",
                                },
                                {
                                    "name": (
                                        "ZITADEL_FIRSTINSTANCE_ORG_MACHINE_"
                                        "MACHINEKEY_EXPIRATIONDATE"
                                    ),
                                    "value": bootstrap_machine_key_expiration,
                                },
                                {
                                    "name": "ZITADEL_MASTERKEY",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": name,
                                            "key": "master-key",
                                        }
                                    },
                                },
                                {
                                    "name": (
                                        "ZITADEL_DEFAULTINSTANCE_ORG_HUMAN_USERNAME"
                                    ),
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": name,
                                            "key": "admin-username",
                                        }
                                    },
                                },
                                {
                                    "name": (
                                        "ZITADEL_DEFAULTINSTANCE_ORG_HUMAN_EMAIL_ADDRESS"
                                    ),
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": name,
                                            "key": "admin-username",
                                        }
                                    },
                                },
                                {
                                    "name": (
                                        "ZITADEL_DEFAULTINSTANCE_ORG_HUMAN_EMAIL_VERIFIED"
                                    ),
                                    "value": "true",
                                },
                                {
                                    "name": (
                                        "ZITADEL_DEFAULTINSTANCE_ORG_HUMAN_PASSWORD"
                                    ),
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": name,
                                            "key": "admin-password",
                                        }
                                    },
                                },
                                {
                                    "name": (
                                        "ZITADEL_DEFAULTINSTANCE_ORG_HUMAN_"
                                        "PASSWORDCHANGEREQUIRED"
                                    ),
                                    "value": "false",
                                },
                                {
                                    "name": (
                                        "ZITADEL_FIRSTINSTANCE_ORG_HUMAN_USERNAME"
                                    ),
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": name,
                                            "key": "admin-username",
                                        }
                                    },
                                },
                                {
                                    "name": (
                                        "ZITADEL_FIRSTINSTANCE_ORG_HUMAN_EMAIL_ADDRESS"
                                    ),
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": name,
                                            "key": "admin-username",
                                        }
                                    },
                                },
                                {
                                    "name": (
                                        "ZITADEL_FIRSTINSTANCE_ORG_HUMAN_EMAIL_VERIFIED"
                                    ),
                                    "value": "true",
                                },
                                {
                                    "name": (
                                        "ZITADEL_FIRSTINSTANCE_ORG_HUMAN_PASSWORD"
                                    ),
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": name,
                                            "key": "admin-password",
                                        }
                                    },
                                },
                                {
                                    "name": (
                                        "ZITADEL_FIRSTINSTANCE_ORG_HUMAN_"
                                        "PASSWORDCHANGEREQUIRED"
                                    ),
                                    "value": "false",
                                },
                                {
                                    "name": "ZITADEL_DATABASE_POSTGRES_HOST",
                                    "value": database_host,
                                },
                                {
                                    "name": "ZITADEL_DATABASE_POSTGRES_PORT",
                                    "value": str(database_port),
                                },
                                {
                                    "name": "ZITADEL_DATABASE_POSTGRES_DATABASE",
                                    "value": database_name,
                                },
                                {
                                    "name": "ZITADEL_DATABASE_POSTGRES_USER_USERNAME",
                                    "value": database_username,
                                },
                                {
                                    "name": "ZITADEL_DATABASE_POSTGRES_USER_PASSWORD",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": name,
                                            "key": "database-password",
                                        }
                                    },
                                },
                                {
                                    "name": "ZITADEL_DATABASE_POSTGRES_USER_SSL_MODE",
                                    "value": database_ssl_mode,
                                },
                                {
                                    "name": "ZITADEL_DATABASE_POSTGRES_ADMIN_USERNAME",
                                    "value": database_admin_username,
                                },
                                {
                                    "name": "ZITADEL_DATABASE_POSTGRES_ADMIN_PASSWORD",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": name,
                                            "key": "database-admin-password",
                                        }
                                    },
                                },
                                {
                                    "name": "ZITADEL_DATABASE_POSTGRES_ADMIN_SSL_MODE",
                                    "value": database_ssl_mode,
                                },
                            ],
                            "volumeMounts": [
                                {
                                    "name": "bootstrap",
                                    "mountPath": bootstrap_mount_path,
                                }
                            ],
                        },
                        {
                            "name": "bootstrap-reader",
                            "image": bootstrap_reader_image,
                            "command": [
                                "sh",
                                "-c",
                                "while true; do sleep 3600; done",
                            ],
                            "volumeMounts": [
                                {
                                    "name": "bootstrap",
                                    "mountPath": bootstrap_mount_path,
                                    "readOnly": True,
                                }
                            ],
                        },
                        *(
                            [
                                {
                                    "name": "postgres",
                                    "image": "postgres:16-alpine",
                                    "ports": [
                                        {
                                            "name": "postgresql",
                                            "containerPort": 5432,
                                        }
                                    ],
                                    "env": [
                                        {
                                            "name": "POSTGRES_DB",
                                            "value": database_name,
                                        },
                                        {
                                            "name": "POSTGRES_USER",
                                            "value": database_username,
                                        },
                                        {
                                            "name": "POSTGRES_PASSWORD",
                                            "valueFrom": {
                                                "secretKeyRef": {
                                                    "name": name,
                                                    "key": "database-password",
                                                }
                                            },
                                        },
                                        {
                                            "name": "PGDATA",
                                            "value": "/var/lib/postgresql/data/pgdata",
                                        },
                                    ],
                                    "volumeMounts": [
                                        {
                                            "name": "data",
                                            "mountPath": "/var/lib/postgresql/data",
                                        },
                                    ],
                                }
                            ]
                            if embedded_postgres
                            else []
                        ),
                    ]
                },
            },
            "volumeClaimTemplates": [
                *([_volume_claim_template(spec, labels)] if embedded_postgres else []),
                _named_volume_claim_template(
                    name="bootstrap",
                    storage_size="64Mi",
                    labels=labels,
                    storage_class_name=_optional_string_value(
                        spec.values,
                        "storageClassName",
                    ),
                ),
            ],
        },
        opts=opts,
    )


def _service_ingress(
    *,
    name: str,
    namespace: str,
    labels: Mapping[str, str],
    host: str,
    service_name: str,
    service_port: int,
    ingress_class_name: str | None,
    k8s,
    opts,
) -> None:
    spec: dict[str, object] = {
        "rules": [
            {
                "host": host,
                "http": {
                    "paths": [
                        {
                            "path": "/",
                            "pathType": "Prefix",
                            "backend": {
                                "service": {
                                    "name": service_name,
                                    "port": {"number": service_port},
                                }
                            },
                        }
                    ]
                },
            }
        ],
    }
    if ingress_class_name is not None:
        spec["ingressClassName"] = ingress_class_name
    k8s.networking.v1.Ingress(
        name,
        metadata={
            "name": name,
            "namespace": namespace,
            "labels": dict(labels),
            "annotations": {"pulumi.com/skipAwait": "true"},
        },
        spec=spec,
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
    access_key = _required_string_value(spec.values, "s3AccessKey")
    secret_key = _required_string_value(spec.values, "s3SecretKey")
    s3_config_json = _seaweedfs_s3_config_json(
        access_key=access_key,
        secret_key=secret_key,
    )
    k8s.core.v1.Secret(
        name,
        metadata={
            "name": name,
            "namespace": spec.namespace,
            "labels": labels,
        },
        type="Opaque",
        string_data={"s3.json": s3_config_json},
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
                                "-s3.config=/etc/seaweedfs/s3.json",
                                "-dir=/data",
                            ],
                            "ports": [{"name": "s3", "containerPort": 8333}],
                            "volumeMounts": [
                                {"name": "data", "mountPath": "/data"},
                                {
                                    "name": "s3-config",
                                    "mountPath": "/etc/seaweedfs",
                                    "readOnly": True,
                                },
                            ],
                        }
                    ],
                    "volumes": [{"name": "s3-config", "secret": {"secretName": name}}],
                },
            },
            "volumeClaimTemplates": [_volume_claim_template(spec, labels)],
        },
        opts=opts,
    )


def _seaweedfs_s3_config_json(*, access_key: str, secret_key: str) -> str:
    return json.dumps(
        {
            "identities": [
                {
                    "name": "nephos-admin",
                    "credentials": [{"accessKey": access_key, "secretKey": secret_key}],
                    "actions": ["Admin", "Read", "List", "Tagging", "Write"],
                }
            ]
        },
        separators=(",", ":"),
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
    image = _string_value(spec.values, "image", "arcadedata/arcadedb:26.5.1")
    _ensure_arcadedb_bolt_supported(image)
    root_password = _required_string_value(spec.values, "rootPassword")
    server_plugins = ["Bolt:com.arcadedb.bolt.BoltProtocolPlugin"]
    ports = [
        {"name": "http", "port": 2480, "targetPort": "http"},
        {"name": "binary", "port": 2424, "targetPort": "binary"},
        {"name": "bolt", "port": 7687, "targetPort": "bolt"},
    ]
    container_ports = [
        {"name": "http", "containerPort": 2480},
        {"name": "binary", "containerPort": 2424},
        {"name": "bolt", "containerPort": 7687},
    ]
    if _bool_value(spec.values, "enableGremlin", False):
        server_plugins.append(
            "GremlinServer:com.arcadedb.server.gremlin.GremlinServerPlugin"
        )
        ports.append({"name": "gremlin", "port": 8182, "targetPort": "gremlin"})
        container_ports.append({"name": "gremlin", "containerPort": 8182})
    if _bool_value(spec.values, "enableMongo", False):
        server_plugins.append("MongoDB:com.arcadedb.mongo.MongoDBProtocolPlugin")
        ports.append({"name": "mongo", "port": 27017, "targetPort": "mongo"})
        container_ports.append({"name": "mongo", "containerPort": 27017})
    server_plugins_value = ",".join(server_plugins)
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
                            "command": ["/bin/sh", "-ec"],
                            "args": [
                                (
                                    'root_password="$(cat '
                                    '/run/secrets/arcadedb/root-password)"\n'
                                    "exec /home/arcadedb/bin/server.sh "
                                    '"-Darcadedb.server.rootPassword='
                                    '${root_password}" '
                                    '"-Darcadedb.server.plugins='
                                    f'{server_plugins_value}"'
                                )
                            ],
                            "ports": container_ports,
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


def _ensure_arcadedb_bolt_supported(image: str) -> None:
    image_without_digest = image.split("@", 1)[0]
    image_name = image_without_digest.rsplit("/", 1)[-1]
    tag = image_name.rsplit(":", 1)[-1] if ":" in image_name else ""
    if not tag:
        if "@" in image:
            raise RuntimeBlockedError(
                reason="runtime_config_unsupported",
                message=(
                    "ArcadeDB opencypher/bolt requires a versioned image tag "
                    "when pinning by digest."
                ),
            )
        return
    if tag == "latest":
        return
    version = _version_tuple(tag)
    if version is None or version >= (26, 2, 1):
        return
    raise RuntimeBlockedError(
        reason="runtime_config_unsupported",
        message=(
            "ArcadeDB opencypher/bolt requires ArcadeDB image version 26.2.1 or newer."
        ),
    )


def _version_tuple(tag: str) -> tuple[int, int, int] | None:
    parts = tag.split("-", 1)[0].split(".")
    if not parts or not all(part.isdigit() for part in parts[:3]):
        return None
    padded = [int(part) for part in parts[:3]]
    while len(padded) < 3:
        padded.append(0)
    major, minor, patch = padded[:3]
    return (major, minor, patch)


def _string_value(
    values: Mapping[str, object],
    name: str,
    default: str,
) -> str:
    value = values.get(name, default)
    return str(value)


def _optional_string_value(
    values: Mapping[str, object],
    name: str,
) -> str | None:
    value = values.get(name)
    if value is None or value == "":
        return None
    return str(value)


def _required_string_value(
    values: Mapping[str, object],
    name: str,
) -> str:
    value = _optional_string_value(values, name)
    if value is None:
        raise RuntimeBlockedError(
            reason="runtime_config_missing",
            message=f"Runtime config value {name} is required.",
        )
    return value


def _cloudflared_config(
    *,
    tunnel_name: str,
    hostname: str,
    origin_service_url: str,
    origin_host_header: str | None,
) -> str:
    lines = [
        f"tunnel: {tunnel_name}",
        "credentials-file: /etc/cloudflared/credentials.json",
        "metrics: 0.0.0.0:2000",
        "no-autoupdate: true",
        "ingress:",
        f"  - hostname: {hostname}",
        f"    service: {origin_service_url}",
    ]
    if origin_host_header is not None:
        lines.extend(
            [
                "    originRequest:",
                f"      httpHostHeader: {origin_host_header}",
            ]
        )
    lines.append("  - service: http_status:404")
    return "\n".join(lines) + "\n"


def _int_value(
    values: Mapping[str, object],
    name: str,
    default: int,
) -> int:
    value = values.get(name, default)
    if type(value) is int:
        return value
    return int(str(value))


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


def _validate_zitadel_admin_password(password: str) -> None:
    missing: list[str] = []
    if len(password) < 8:
        missing.append("at least 8 characters")
    if not any(character.islower() for character in password):
        missing.append("a lowercase letter")
    if not any(character.isupper() for character in password):
        missing.append("an uppercase letter")
    if not any(character.isdigit() for character in password):
        missing.append("a digit")
    if not any(not character.isalnum() for character in password):
        missing.append("a symbol")
    if not missing:
        return
    raise RuntimeBlockedError(
        reason="runtime_config_invalid",
        message=(
            "Zitadel adminPassword does not satisfy the default password "
            f"complexity policy; missing {', '.join(missing)}."
        ),
    )


def _zitadel_master_key(values: Mapping[str, object]) -> str:
    master_key = _required_string_value(values, "masterKey")
    if len(master_key) != 32:
        raise RuntimeBlockedError(
            reason="runtime_config_invalid",
            message="Zitadel masterKey must be exactly 32 characters.",
        )
    return master_key


def _volume_claim_template(
    spec: PulumiKubernetesWorkloadSpec,
    labels: Mapping[str, str],
) -> dict[str, object]:
    storage_size = _string_value(spec.values, "storageSize", "1Gi")
    storage_class_name = _optional_string_value(spec.values, "storageClassName")
    return _named_volume_claim_template(
        name="data",
        storage_size=storage_size,
        labels=labels,
        storage_class_name=storage_class_name,
    )


def _named_volume_claim_template(
    *,
    name: str,
    storage_size: str,
    labels: Mapping[str, str],
    storage_class_name: object,
) -> dict[str, object]:
    return {
        "metadata": {
            "name": name,
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


def _openbao_service(
    spec: PulumiKubernetesWorkloadSpec,
    *,
    k8s,
    opts,
) -> None:
    # ! DEV MODE ONLY. Runs `bao server -dev`: in-memory storage, auto-unsealed,
    # ! with a static root token. This is insecure by design and must never run
    # ! outside LCL; the API refuses to register this provider unless the
    # ! environment is `lcl`. A later phase replaces this with a persistent,
    # ! sealed, Kubernetes-auth OpenBao before openbao can serve non-LCL secrets.
    name = f"{spec.runtime_name}-openbao"
    labels = _labels(spec)
    selector = {"app.kubernetes.io/name": name}
    image = _string_value(spec.values, "image", "openbao/openbao:2.4.1")
    # Static dev-mode token, LCL-only by construction (see the gate in main.py).
    # Phase 2 replaces dev mode with init/unseal + a Kubernetes auth method.
    dev_root_token = _string_value(spec.values, "devRootToken", "root")
    http_port = _int_value(spec.values, "httpPort", 8200)
    k8s.core.v1.Secret(
        name,
        metadata={"name": name, "namespace": spec.namespace, "labels": labels},
        type="Opaque",
        string_data={"dev-root-token": dev_root_token},
        opts=opts,
    )
    k8s.core.v1.Service(
        name,
        metadata={"name": name, "namespace": spec.namespace, "labels": labels},
        spec={
            "ports": [{"name": "http", "port": http_port, "targetPort": "http"}],
            "selector": selector,
        },
        opts=opts,
    )
    k8s.apps.v1.Deployment(
        name,
        metadata={"name": name, "namespace": spec.namespace, "labels": labels},
        spec={
            "replicas": 1,
            "selector": {"matchLabels": selector},
            "template": {
                "metadata": {"labels": {**labels, **selector}},
                "spec": {
                    "containers": [
                        {
                            "name": "openbao",
                            "image": image,
                            "args": ["server", "-dev"],
                            "env": [
                                {
                                    "name": "BAO_DEV_ROOT_TOKEN_ID",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": name,
                                            "key": "dev-root-token",
                                        }
                                    },
                                },
                                {
                                    "name": "BAO_DEV_LISTEN_ADDRESS",
                                    "value": f"0.0.0.0:{http_port}",
                                },
                            ],
                            "ports": [{"name": "http", "containerPort": http_port}],
                            "readinessProbe": {
                                "httpGet": {"path": "/v1/sys/health", "port": "http"},
                                "initialDelaySeconds": 5,
                                "periodSeconds": 5,
                            },
                        }
                    ],
                },
            },
        },
        opts=opts,
    )


_WORKLOAD_PROGRAMS: dict[str, PulumiKubernetesProgram] = {
    "reference-app": _reference_app,
    "postgres-service": _postgres_service,
    "cloudflared-service": _cloudflared_service,
    "zitadel-service": _zitadel_service,
    "seaweedfs-service": _seaweedfs_service,
    "arcadedb-service": _arcadedb_service,
    "openbao-service": _openbao_service,
}
