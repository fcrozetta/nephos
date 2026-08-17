from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from nephos_api.providers import ProviderContext
from nephos_api.providers.kubernetes import (
    PulumiKubernetesProvider,
    PulumiKubernetesProviderConfig,
    PulumiKubernetesWorkloadSpec,
    _arcadedb_service,
    _cloudflared_service,
    _openbao_persistent_service,
    _openbao_service,
    _postgres_service,
    _pulumi_program,
    _seaweedfs_service,
    _zitadel_service,
)
from nephos_api.runtime_errors import RuntimeBlockedError


class RecordingRunner:
    def __init__(self) -> None:
        self.ups: list[PulumiKubernetesWorkloadSpec] = []
        self.destroys: list[PulumiKubernetesWorkloadSpec] = []

    def up(self, spec: PulumiKubernetesWorkloadSpec) -> None:
        self.ups.append(spec)

    def destroy(self, spec: PulumiKubernetesWorkloadSpec) -> None:
        self.destroys.append(spec)


class RecordingResource:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, name: str, **kwargs: object) -> None:
        self.calls.append({"name": name, **kwargs})


class RecordingKubernetes:
    def __init__(self) -> None:
        self.secret = RecordingResource()
        self.config_map = RecordingResource()
        self.service = RecordingResource()
        self.ingress = RecordingResource()
        self.network_policy = RecordingResource()
        self.deployment = RecordingResource()
        self.stateful_set = RecordingResource()
        self.core = type(
            "Core",
            (),
            {
                "v1": type(
                    "CoreV1",
                    (),
                    {
                        "Secret": self.secret,
                        "ConfigMap": self.config_map,
                        "Service": self.service,
                    },
                )()
            },
        )()
        self.apps = type(
            "Apps",
            (),
            {
                "v1": type(
                    "AppsV1",
                    (),
                    {
                        "Deployment": self.deployment,
                        "StatefulSet": self.stateful_set,
                    },
                )()
            },
        )()
        self.networking = type(
            "Networking",
            (),
            {
                "v1": type(
                    "NetworkingV1",
                    (),
                    {
                        "Ingress": self.ingress,
                        "NetworkPolicy": self.network_policy,
                    },
                )()
            },
        )()


def test_pulumi_kubernetes_provider_maps_context_to_stack_spec(
    tmp_path: Path,
) -> None:
    runner = RecordingRunner()
    provider = PulumiKubernetesProvider(
        config=PulumiKubernetesProviderConfig(
            work_dir=tmp_path / "workspaces",
            state_dir=tmp_path / "state",
            kubeconfig=tmp_path / "kubeconfig",
            kube_context="docker-desktop",
        ),
        workload="postgres-service",
        runner=runner,
    )
    context = ProviderContext(
        target_type="service_instance",
        slug="postgres",
        runtime_name="svc-postgres",
        manifest=None,
        chart=None,
        values={},
        provider_name="postgres",
    )

    provider.deploy(context)
    provider.uninstall(context)

    assert runner.ups == [
        PulumiKubernetesWorkloadSpec(
            project_name="nephos-api",
            stack_name="svc-postgres",
            work_dir=tmp_path / "workspaces" / "svc-postgres",
            state_dir=tmp_path / "state",
            kubeconfig=tmp_path / "kubeconfig",
            kube_context="docker-desktop",
            runtime_name="svc-postgres",
            namespace="svc-postgres",
            workload="postgres-service",
            values={},
        )
    ]
    assert runner.destroys == runner.ups


def test_pulumi_kubernetes_program_blocks_unknown_workload() -> None:
    spec = PulumiKubernetesWorkloadSpec(
        project_name="nephos-api",
        stack_name="svc-unknown",
        work_dir=Path("/tmp/workspaces/svc-unknown"),
        state_dir=Path("/tmp/state"),
        kubeconfig=None,
        kube_context=None,
        runtime_name="svc-unknown",
        namespace="svc-unknown",
        workload="missing-service",
        values={},
    )

    try:
        _pulumi_program(spec)
    except RuntimeBlockedError as exc:
        assert exc.reason == "runtime_provider_unknown"
    else:
        raise AssertionError("expected unknown workload to block")


def test_postgres_service_uses_persistent_volume_claim_template() -> None:
    k8s = RecordingKubernetes()
    spec = PulumiKubernetesWorkloadSpec(
        project_name="nephos-api",
        stack_name="svc-postgres",
        work_dir=Path("/tmp/workspaces/svc-postgres"),
        state_dir=Path("/tmp/state"),
        kubeconfig=None,
        kube_context=None,
        runtime_name="svc-postgres",
        namespace="svc-postgres",
        workload="postgres-service",
        values={"adminPassword": "admin-secret"},
    )

    _postgres_service(spec, k8s=k8s, opts=None)

    service = cast(dict[str, Any], k8s.service.calls[0])
    assert service["metadata"]["annotations"] == {"pulumi.com/skipAwait": "true"}
    stateful_set_spec = k8s.stateful_set.calls[0]["spec"]
    pod_spec = stateful_set_spec["template"]["spec"]
    assert "volumes" not in pod_spec
    assert stateful_set_spec["volumeClaimTemplates"] == [
        {
            "metadata": {
                "name": "data",
                "labels": {
                    "app.kubernetes.io/managed-by": "nephos",
                    "app.kubernetes.io/part-of": "nephos-dev-reference",
                    "nephos.pro/runtime-name": "svc-postgres",
                },
            },
            "spec": {
                "accessModes": ["ReadWriteOnce"],
                "resources": {"requests": {"storage": "1Gi"}},
            },
        }
    ]


def test_postgres_service_can_bootstrap_zitadel_database() -> None:
    k8s = RecordingKubernetes()
    spec = PulumiKubernetesWorkloadSpec(
        project_name="nephos-api",
        stack_name="svc-postgres",
        work_dir=Path("/tmp/workspaces/svc-postgres"),
        state_dir=Path("/tmp/state"),
        kubeconfig=None,
        kube_context=None,
        runtime_name="svc-postgres",
        namespace="svc-postgres",
        workload="postgres-service",
        values={
            "image": "postgres:16-alpine",
            "adminPassword": "admin-secret",
            "zitadelDatabase": "zitadel",
            "zitadelUsername": "zitadel",
            "zitadelPassword": "zitadel-secret",
            "storageSize": "8Gi",
        },
    )

    _postgres_service(spec, k8s=k8s, opts=None)

    secret = k8s.secret.calls[0]
    stateful_set = k8s.stateful_set.calls[0]
    container = stateful_set["spec"]["template"]["spec"]["containers"][0]
    pod_spec = stateful_set["spec"]["template"]["spec"]
    init_sql = secret["string_data"]["010-nephos-zitadel.sql"]
    assert secret["string_data"]["postgres-password"] == "admin-secret"
    assert secret["string_data"]["zitadel-password"] == "zitadel-secret"
    assert 'CREATE ROLE "zitadel"' in init_sql
    assert 'CREATE DATABASE "zitadel" OWNER "zitadel"' in init_sql
    assert k8s.config_map.calls == []
    assert container["image"] == "postgres:16-alpine"
    assert {
        "name": "initdb",
        "secret": {
            "secretName": "svc-postgres-postgresql",
            "items": [
                {
                    "key": "010-nephos-zitadel.sql",
                    "path": "010-nephos-zitadel.sql",
                }
            ],
        },
    } in pod_spec["volumes"]
    assert {
        "name": "initdb",
        "mountPath": "/docker-entrypoint-initdb.d",
        "readOnly": True,
    } in container["volumeMounts"]


def test_cloudflared_service_uses_secret_reference_and_configured_route() -> None:
    k8s = RecordingKubernetes()
    spec = PulumiKubernetesWorkloadSpec(
        project_name="nephos-api",
        stack_name="svc-cloudflared",
        work_dir=Path("/tmp/workspaces/svc-cloudflared"),
        state_dir=Path("/tmp/state"),
        kubeconfig=None,
        kube_context=None,
        runtime_name="svc-cloudflared",
        namespace="svc-cloudflared",
        workload="cloudflared-service",
        values={
            "image": "cloudflare/cloudflared:2026.6.1",
            "tunnelName": "nephos",
            "credentialsSecretName": "nephos-cloudflared-credentials",
            "credentialsSecretKey": "credentials.json",
            "hostname": "auth.fcrozetta.app",
            "originServiceUrl": (
                "http://ingress-nginx-controller.ingress-nginx.svc.cluster.local"
            ),
            "originHostHeader": "auth.fcrozetta.app",
        },
    )

    _cloudflared_service(spec, k8s=k8s, opts=None)

    config_map = k8s.config_map.calls[0]
    deployment = k8s.deployment.calls[0]
    pod_spec = deployment["spec"]["template"]["spec"]
    container = pod_spec["containers"][0]
    assert k8s.secret.calls == []
    assert config_map["data"] == {
        "config.yml": (
            "tunnel: nephos\n"
            "credentials-file: /etc/cloudflared/credentials.json\n"
            "metrics: 0.0.0.0:2000\n"
            "no-autoupdate: true\n"
            "ingress:\n"
            "  - hostname: auth.fcrozetta.app\n"
            "    service: "
            "http://ingress-nginx-controller.ingress-nginx.svc.cluster.local\n"
            "    originRequest:\n"
            "      httpHostHeader: auth.fcrozetta.app\n"
            "  - service: http_status:404\n"
        )
    }
    assert container["image"] == "cloudflare/cloudflared:2026.6.1"
    assert container["args"] == [
        "tunnel",
        "--config",
        "/etc/cloudflared/config/config.yml",
        "run",
    ]
    assert container["volumeMounts"] == [
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
    ]
    assert container["readinessProbe"] == {
        "httpGet": {"path": "/ready", "port": 2000},
        "initialDelaySeconds": 5,
        "periodSeconds": 10,
    }
    assert pod_spec["volumes"] == [
        {"name": "config", "configMap": {"name": "svc-cloudflared-cloudflared"}},
        {
            "name": "credentials",
            "secret": {
                "secretName": "nephos-cloudflared-credentials",
                "items": [{"key": "credentials.json", "path": "credentials.json"}],
            },
        },
    ]


def test_zitadel_service_forwards_values_to_runtime_resources() -> None:
    k8s = RecordingKubernetes()
    spec = PulumiKubernetesWorkloadSpec(
        project_name="nephos-api",
        stack_name="svc-zitadel",
        work_dir=Path("/tmp/workspaces/svc-zitadel"),
        state_dir=Path("/tmp/state"),
        kubeconfig=None,
        kube_context=None,
        runtime_name="svc-zitadel",
        namespace="svc-zitadel",
        workload="zitadel-service",
        values={
            "image": "ghcr.io/zitadel/zitadel:v2.58.0",
            "adminUsername": "root@zitadel.localhost",
            "adminPassword": "Local-secret1!",
            "masterKey": "0123456789abcdef0123456789abcdef",
            "databaseHost": "svc-postgres-postgresql.svc-postgres.svc.cluster.local",
            "databasePort": 5432,
            "databaseName": "zitadel",
            "databaseUsername": "zitadel",
            "databasePassword": "db-secret",
            "databaseSslMode": "disable",
            "externalHost": "login.nephos.localhost",
            "externalPort": 443,
            "externalSecure": True,
            "bootstrapMachineUsername": "nephos-bot",
            "bootstrapMachineName": "Nephos Bot",
            "bootstrapMachineKeyPath": "/var/lib/zitadel-bootstrap/bot.json",
            "bootstrapMachineKeyExpiration": "2037-01-01T00:00:00Z",
            "storageSize": "4Gi",
        },
    )

    _zitadel_service(spec, k8s=k8s, opts=None)

    secret = k8s.secret.calls[0]
    stateful_set = k8s.stateful_set.calls[0]
    service = k8s.service.calls[0]
    stateful_pod_spec = stateful_set["spec"]["template"]["spec"]
    containers = stateful_pod_spec["containers"]
    container = next(item for item in containers if item["name"] == "zitadel")
    bootstrap_reader = next(
        item for item in containers if item["name"] == "bootstrap-reader"
    )
    bootstrap_pvc = next(
        item
        for item in stateful_set["spec"]["volumeClaimTemplates"]
        if item["metadata"]["name"] == "bootstrap"
    )
    env = {item["name"]: item for item in container["env"]}
    assert secret["string_data"] == {
        "admin-username": "root@zitadel.localhost",
        "admin-password": "Local-secret1!",
        "master-key": "0123456789abcdef0123456789abcdef",
        "database-password": "db-secret",
        "database-admin-password": "db-secret",
    }
    assert container["image"] == "ghcr.io/zitadel/zitadel:v2.58.0"
    assert container["args"] == ["start-from-init", "--masterkeyFromEnv"]
    assert env["ZITADEL_EXTERNALDOMAIN"]["value"] == "login.nephos.localhost"
    assert env["ZITADEL_EXTERNALPORT"]["value"] == "443"
    assert env["ZITADEL_EXTERNALSECURE"]["value"] == "true"
    assert env["ZITADEL_TLS_ENABLED"]["value"] == "false"
    assert env["ZITADEL_FIRSTINSTANCE_MACHINEKEYPATH"]["value"] == (
        "/var/lib/zitadel-bootstrap/bot.json"
    )
    assert env["ZITADEL_FIRSTINSTANCE_ORG_MACHINE_MACHINE_USERNAME"]["value"] == (
        "nephos-bot"
    )
    assert env["ZITADEL_FIRSTINSTANCE_ORG_MACHINE_MACHINE_NAME"]["value"] == (
        "Nephos Bot"
    )
    assert env["ZITADEL_FIRSTINSTANCE_ORG_MACHINE_MACHINEKEY_TYPE"]["value"] == "1"
    assert (
        env["ZITADEL_FIRSTINSTANCE_ORG_MACHINE_MACHINEKEY_EXPIRATIONDATE"]["value"]
        == "2037-01-01T00:00:00Z"
    )
    assert container["volumeMounts"] == [
        {"name": "bootstrap", "mountPath": "/var/lib/zitadel-bootstrap"}
    ]
    assert bootstrap_reader["image"] == "busybox:1.36.1"
    assert bootstrap_reader["command"] == [
        "sh",
        "-c",
        "while true; do sleep 3600; done",
    ]
    assert bootstrap_reader["volumeMounts"] == [
        {
            "name": "bootstrap",
            "mountPath": "/var/lib/zitadel-bootstrap",
            "readOnly": True,
        }
    ]
    assert env["ZITADEL_DATABASE_POSTGRES_HOST"]["value"] == (
        "svc-postgres-postgresql.svc-postgres.svc.cluster.local"
    )
    assert env["ZITADEL_DATABASE_POSTGRES_DATABASE"]["value"] == "zitadel"
    assert env["ZITADEL_DATABASE_POSTGRES_USER_USERNAME"]["value"] == "zitadel"
    assert env["ZITADEL_DEFAULTINSTANCE_ORG_HUMAN_USERNAME"]["valueFrom"] == {
        "secretKeyRef": {"name": "svc-zitadel-zitadel", "key": "admin-username"}
    }
    assert env["ZITADEL_DEFAULTINSTANCE_ORG_HUMAN_PASSWORD"]["valueFrom"] == {
        "secretKeyRef": {"name": "svc-zitadel-zitadel", "key": "admin-password"}
    }
    assert env["ZITADEL_DEFAULTINSTANCE_ORG_HUMAN_EMAIL_ADDRESS"]["valueFrom"] == {
        "secretKeyRef": {"name": "svc-zitadel-zitadel", "key": "admin-username"}
    }
    assert env["ZITADEL_FIRSTINSTANCE_ORG_HUMAN_USERNAME"]["valueFrom"] == {
        "secretKeyRef": {"name": "svc-zitadel-zitadel", "key": "admin-username"}
    }
    assert env["ZITADEL_FIRSTINSTANCE_ORG_HUMAN_PASSWORD"]["valueFrom"] == {
        "secretKeyRef": {"name": "svc-zitadel-zitadel", "key": "admin-password"}
    }
    assert env["ZITADEL_FIRSTINSTANCE_ORG_HUMAN_EMAIL_VERIFIED"]["value"] == "true"
    assert env["ZITADEL_MASTERKEY"]["valueFrom"] == {
        "secretKeyRef": {"name": "svc-zitadel-zitadel", "key": "master-key"}
    }
    assert [item["name"] for item in containers] == ["zitadel", "bootstrap-reader"]
    assert bootstrap_pvc["spec"]["resources"]["requests"]["storage"] == "64Mi"
    # h2c is load-bearing, not cosmetic: Zitadel serves gRPC and HTTP on one
    # port, and without it Traefik speaks HTTP/1.1 to the backend and every
    # OIDC binding fails at "failed to create project" with a 404.
    assert service["metadata"]["annotations"] == {
        "pulumi.com/skipAwait": "true",
        "traefik.ingress.kubernetes.io/service.serversscheme": "h2c",
    }
    assert service["spec"]["ports"] == [
        {"name": "http", "port": 8080, "targetPort": "http"}
    ]
    # ADR 20260726: the platform generates portal Ingress from the Service
    # manifest, so the provider must not create one of its own.
    assert k8s.ingress.calls == []


def test_zitadel_service_can_use_external_postgres() -> None:
    k8s = RecordingKubernetes()
    spec = PulumiKubernetesWorkloadSpec(
        project_name="nephos-api",
        stack_name="svc-zitadel",
        work_dir=Path("/tmp/workspaces/svc-zitadel"),
        state_dir=Path("/tmp/state"),
        kubeconfig=None,
        kube_context=None,
        runtime_name="svc-zitadel",
        namespace="svc-zitadel",
        workload="zitadel-service",
        values={
            "adminPassword": "Local-secret1!",
            "masterKey": "0123456789abcdef0123456789abcdef",
            "externalHost": "zitadel.nephos.lcl",
            "adminUsername": "root@zitadel.nephos.lcl",
            "bootstrapMachineKeyExpiration": "2037-01-01T00:00:00Z",
            "embeddedPostgres": False,
            "databaseHost": "svc-postgres-postgresql.svc-postgres.svc.cluster.local",
            "databasePort": 5432,
            "databaseName": "zitadel",
            "databaseUsername": "zitadel",
            "databasePassword": "zitadel-secret",
            "databaseAdminUsername": "postgres",
            "databaseAdminPassword": "postgres-secret",
            "databaseSslMode": "disable",
        },
    )

    _zitadel_service(spec, k8s=k8s, opts=None)

    stateful_set = k8s.stateful_set.calls[0]
    containers = stateful_set["spec"]["template"]["spec"]["containers"]
    container = next(item for item in containers if item["name"] == "zitadel")
    bootstrap_reader = next(
        item for item in containers if item["name"] == "bootstrap-reader"
    )
    env = {item["name"]: item for item in container["env"]}
    assert {item["name"] for item in containers} == {"zitadel", "bootstrap-reader"}
    volume_claim_names = [
        item["metadata"]["name"]
        for item in stateful_set["spec"]["volumeClaimTemplates"]
    ]
    assert volume_claim_names == ["bootstrap"]
    assert bootstrap_reader["image"] == "busybox:1.36.1"
    assert bootstrap_reader["volumeMounts"] == [
        {
            "name": "bootstrap",
            "mountPath": "/var/lib/zitadel-bootstrap",
            "readOnly": True,
        }
    ]
    assert env["ZITADEL_DATABASE_POSTGRES_HOST"]["value"] == (
        "svc-postgres-postgresql.svc-postgres.svc.cluster.local"
    )
    assert env["ZITADEL_DATABASE_POSTGRES_ADMIN_USERNAME"]["value"] == "postgres"
    assert env["ZITADEL_DATABASE_POSTGRES_ADMIN_PASSWORD"]["valueFrom"] == {
        "secretKeyRef": {
            "name": "svc-zitadel-zitadel",
            "key": "database-admin-password",
        }
    }


def test_zitadel_service_blocks_admin_password_without_symbol() -> None:
    k8s = RecordingKubernetes()
    spec = PulumiKubernetesWorkloadSpec(
        project_name="nephos-api",
        stack_name="svc-zitadel",
        work_dir=Path("/tmp/workspaces/svc-zitadel"),
        state_dir=Path("/tmp/state"),
        kubeconfig=None,
        kube_context=None,
        runtime_name="svc-zitadel",
        namespace="svc-zitadel",
        workload="zitadel-service",
        values={
            "adminPassword": "LocalSecret1",
            "masterKey": "0123456789abcdef0123456789abcdef",
            "externalHost": "zitadel.nephos.lcl",
            "adminUsername": "root@zitadel.nephos.lcl",
            "databasePassword": "db-secret",
            "bootstrapMachineKeyExpiration": "2037-01-01T00:00:00Z",
        },
    )

    try:
        _zitadel_service(spec, k8s=k8s, opts=None)
    except RuntimeBlockedError as exc:
        assert exc.reason == "runtime_config_invalid"
        assert "adminPassword" in str(exc)
        assert "a symbol" in str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("expected Zitadel adminPassword complexity block")


def test_zitadel_service_never_creates_its_own_ingress() -> None:
    """ADR 20260726: portal Ingress is platform-owned.

    Guards against the provider re-growing a private ingress: legacy
    `ingressEnabled` / `ingressClassName` values must no longer produce one, so a
    stale manifest cannot resurrect a second ingress mechanism competing with the
    platform-generated portal.
    """
    k8s = RecordingKubernetes()
    spec = PulumiKubernetesWorkloadSpec(
        project_name="nephos-api",
        stack_name="svc-zitadel",
        work_dir=Path("/tmp/workspaces/svc-zitadel"),
        state_dir=Path("/tmp/state"),
        kubeconfig=None,
        kube_context=None,
        runtime_name="svc-zitadel",
        namespace="svc-zitadel",
        workload="zitadel-service",
        values={
            "adminPassword": "Local-secret1!",
            "masterKey": "0123456789abcdef0123456789abcdef",
            "externalHost": "console.zitadel.nephos.lcl",
            "adminUsername": "root@zitadel.nephos.lcl",
            "databasePassword": "db-secret",
            "bootstrapMachineKeyExpiration": "2037-01-01T00:00:00Z",
            "ingressEnabled": True,
            "ingressClassName": "nginx",
        },
    )

    _zitadel_service(spec, k8s=k8s, opts=None)

    assert k8s.ingress.calls == []


def _seaweedfs_spec() -> PulumiKubernetesWorkloadSpec:
    return PulumiKubernetesWorkloadSpec(
        project_name="nephos-api",
        stack_name="svc-seaweedfs",
        work_dir=Path("/tmp/workspaces/svc-seaweedfs"),
        state_dir=Path("/tmp/state"),
        kubeconfig=None,
        kube_context=None,
        runtime_name="svc-seaweedfs",
        namespace="svc-seaweedfs",
        workload="seaweedfs-service",
        values={
            "image": "chrislusf/seaweedfs:3.85",
            "storageSize": "2Gi",
            "s3AccessKey": "alpha-access",
            "s3SecretKey": "alpha-secret",
        },
    )


def test_seaweedfs_service_forwards_values_to_runtime_resources() -> None:
    k8s = RecordingKubernetes()

    _seaweedfs_service(_seaweedfs_spec(), k8s=k8s, opts=None)

    stateful_set = k8s.stateful_set.calls[0]
    service = k8s.service.calls[0]
    container = stateful_set["spec"]["template"]["spec"]["containers"][0]
    pvc = stateful_set["spec"]["volumeClaimTemplates"][0]
    env_names = {item["name"] for item in container.get("env", [])}
    assert container["image"] == "chrislusf/seaweedfs:3.85"
    assert "WEED_S3_ACCESS_KEY" not in env_names
    assert "WEED_S3_SECRET_KEY" not in env_names
    assert pvc["spec"]["resources"]["requests"]["storage"] == "2Gi"
    assert service["spec"]["ports"] == [
        {"name": "s3", "port": 8333, "targetPort": "s3"}
    ]


def test_seaweedfs_service_stores_admin_credentials_as_plain_secret_keys() -> None:
    """ADR 20260816: identities live in the filer, so the Secret carries the
    admin credential as data the lifecycle seeder reads -- not as an s3.json
    document mounted into the pod."""
    k8s = RecordingKubernetes()

    _seaweedfs_service(_seaweedfs_spec(), k8s=k8s, opts=None)

    secret = k8s.secret.calls[0]
    assert secret["string_data"] == {
        "access-key": "alpha-access",
        "secret-key": "alpha-secret",
    }


def test_seaweedfs_service_runs_unprivileged() -> None:
    """Verified against chrislusf/seaweedfs:3.85: master, volume, filer and S3 all
    start as uid 1000 with no permission errors, so root buys nothing. fsGroup is
    what keeps the PVC writable once the process is not root."""
    k8s = RecordingKubernetes()

    _seaweedfs_service(_seaweedfs_spec(), k8s=k8s, opts=None)

    pod = k8s.stateful_set.calls[0]["spec"]["template"]["spec"]
    security = pod["securityContext"]
    assert security["runAsNonRoot"] is True
    assert security["runAsUser"] == 1000
    assert security["fsGroup"] == 1000


def test_seaweedfs_service_declares_resources() -> None:
    """Requests on both, a ceiling only on memory. A CPU limit would throttle a
    storage path under exactly the load that needs it, while an unbounded memory
    leak takes the node down with it."""
    k8s = RecordingKubernetes()

    _seaweedfs_service(_seaweedfs_spec(), k8s=k8s, opts=None)

    container = k8s.stateful_set.calls[0]["spec"]["template"]["spec"]["containers"][0]
    resources = container["resources"]
    assert resources["requests"] == {"cpu": "100m", "memory": "256Mi"}
    assert resources["limits"] == {"memory": "1Gi"}
    assert "cpu" not in resources["limits"]


def test_seaweedfs_service_seeds_the_admin_identity_before_s3_can_serve() -> None:
    """An unconfigured SeaweedFS answers `GET /` with 200. The lifecycle
    provisioner closes that seconds after deploy, which still leaves a window on
    a fresh volume -- and the NetworkPolicy admits 8333 from anywhere, so the
    window is reachable.

    An init container seeds the identity into the filer store on the PVC before
    the serving container ever starts, so S3's first response is already 403.
    Verified end to end against chrislusf/seaweedfs:3.85: seed, clean filer
    shutdown, then the main container's first-ever response was 403 with the
    identity intact and no leveldb corruption.

    It must fail closed. A seeder that exits 0 without seeding would leave S3
    open while looking fixed, which is exactly what a first attempt at this did.
    """
    k8s = RecordingKubernetes()

    _seaweedfs_service(_seaweedfs_spec(), k8s=k8s, opts=None)

    pod = k8s.stateful_set.calls[0]["spec"]["template"]["spec"]
    init_containers = pod["initContainers"]
    assert len(init_containers) == 1
    seeder = init_containers[0]
    assert seeder["image"] == "chrislusf/seaweedfs:3.85"
    # Same PVC as the serving container, or it seeds a store nobody reads.
    assert {"name": "data", "mountPath": "/data"} in seeder["volumeMounts"]
    # Credentials come from the Service Secret, never from the manifest.
    env = {item["name"]: item for item in seeder["env"]}
    assert env["NEPHOS_S3_ACCESS_KEY"]["valueFrom"]["secretKeyRef"] == {
        "name": "svc-seaweedfs-seaweedfs",
        "key": "access-key",
    }
    assert env["NEPHOS_S3_SECRET_KEY"]["valueFrom"]["secretKeyRef"] == {
        "name": "svc-seaweedfs-seaweedfs",
        "key": "secret-key",
    }
    script = seeder["command"][-1]
    # Overriding the entrypoint is required: the image's entrypoint is `weed`.
    assert seeder["command"][0] == "sh"
    # The filer does not start unless asked; `weed server` alone is master+volume.
    assert "-filer" in script
    # Readiness must key on a positive marker. Matching the shell prompt passes
    # while the command underneath is erroring.
    assert '"identities"' in script
    # Fail closed: read back and exit non-zero if the identity is not there.
    assert "exit 1" in script


def test_seaweedfs_service_restricts_ingress_to_the_s3_port() -> None:
    """`weed server` runs master, volume, filer and S3 in one process and binds
    every component to the pod IP, but only S3 authenticates. Verified live from
    an unprivileged pod in another namespace with no credentials: the filer
    serves /etc/iam/identity.json (every S3 credential, admin included) and
    accepts PUT/GET/DELETE against any bucket -- so per-binding S3 scoping is an
    S3-protocol boundary and nothing more.

    There is no in-pod fix: `weed server` exposes a single global -ip.bind with no
    per-component override, so the filer cannot be confined to loopback while S3
    stays reachable. A NetworkPolicy is the only place to draw the line.
    """
    k8s = RecordingKubernetes()

    _seaweedfs_service(_seaweedfs_spec(), k8s=k8s, opts=None)

    assert len(k8s.network_policy.calls) == 1
    policy = k8s.network_policy.calls[0]
    assert policy["metadata"]["namespace"] == "svc-seaweedfs"
    spec = policy["spec"]
    assert spec["podSelector"] == {
        "matchLabels": {"app.kubernetes.io/name": "svc-seaweedfs-seaweedfs"}
    }
    assert spec["policyTypes"] == ["Ingress"]
    # Exactly one rule, exactly the S3 port. Numeric rather than the named port
    # because 8333 is what was verified enforced on k3d.
    assert spec["ingress"] == [{"ports": [{"protocol": "TCP", "port": 8333}]}]
    # The ports that answer unauthenticated must not be reachable.
    reachable = {
        port["port"]
        for rule in spec["ingress"]
        for port in rule.get("ports", [])
    }
    for unauthenticated in (9333, 8888, 18888, 8080, 18080):
        assert unauthenticated not in reachable


def test_seaweedfs_service_gates_readiness_on_the_s3_port() -> None:
    """Without a readiness probe the pod is Ready the instant the process starts,
    Pulumi's await returns immediately, and binding provisioning races SeaweedFS
    startup -- observed live as `dial tcp [::1]:18888: connect: connection
    refused` 21s after container start. Because a blocked binding is terminal,
    that one race permanently blocks the App.

    The probe is tcpSocket, not httpGet, on purpose: once the admin identity is
    seeded, `GET /` answers 403, which httpGet scores as a failure and would flap
    the pod out of Ready forever after.

    SeaweedFS starts the S3 listener only after it has connected to the filer, so
    the S3 port accepting TCP is a sound proxy for "filer gRPC is reachable".
    """
    k8s = RecordingKubernetes()

    _seaweedfs_service(_seaweedfs_spec(), k8s=k8s, opts=None)

    container = k8s.stateful_set.calls[0]["spec"]["template"]["spec"]["containers"][0]
    probe = container.get("readinessProbe")
    assert probe is not None, "no readiness probe: provisioning will race startup"
    assert probe["tcpSocket"] == {"port": "s3"}
    assert "httpGet" not in probe


def test_seaweedfs_service_does_not_pass_static_s3_config() -> None:
    """-s3.config disables the filer /etc/ subscription, which would make every
    runtime-provisioned identity invisible (InvalidAccessKeyId)."""
    k8s = RecordingKubernetes()

    _seaweedfs_service(_seaweedfs_spec(), k8s=k8s, opts=None)

    stateful_set = k8s.stateful_set.calls[0]
    pod_spec = stateful_set["spec"]["template"]["spec"]
    container = pod_spec["containers"][0]
    assert not any(str(arg).startswith("-s3.config") for arg in container["args"])
    mount_paths = {mount["mountPath"] for mount in container["volumeMounts"]}
    assert "/etc/seaweedfs" not in mount_paths
    assert pod_spec.get("volumes", []) == []


def test_arcadedb_service_forwards_values_to_raw_statefulset() -> None:
    k8s = RecordingKubernetes()
    spec = PulumiKubernetesWorkloadSpec(
        project_name="nephos-api",
        stack_name="svc-arcadedb",
        work_dir=Path("/tmp/workspaces/svc-arcadedb"),
        state_dir=Path("/tmp/state"),
        kubeconfig=None,
        kube_context=None,
        runtime_name="svc-arcadedb",
        namespace="svc-arcadedb",
        workload="arcadedb-service",
        values={
            "image": "arcadedata/arcadedb:26.5.1",
            "storageSize": "3Gi",
            "rootPassword": "arcade-secret",
            "enableGremlin": True,
            "enableMongo": True,
        },
    )

    _arcadedb_service(spec, k8s=k8s, opts=None)

    secret = k8s.secret.calls[0]
    stateful_set = k8s.stateful_set.calls[0]
    service = k8s.service.calls[0]
    container = stateful_set["spec"]["template"]["spec"]["containers"][0]
    assert secret["string_data"] == {"root-password": "arcade-secret"}
    assert container["image"] == "arcadedata/arcadedb:26.5.1"
    assert container["command"] == ["/bin/sh", "-ec"]
    assert (
        'root_password="$(cat /run/secrets/arcadedb/root-password)"'
        in (container["args"][0])
    )
    assert "-Darcadedb.server.rootPassword=${root_password}" in container["args"][0]
    assert (
        "-Darcadedb.server.plugins="
        "Bolt:com.arcadedb.bolt.BoltProtocolPlugin,"
        "GremlinServer:com.arcadedb.server.gremlin.GremlinServerPlugin,"
        "MongoDB:com.arcadedb.mongo.MongoDBProtocolPlugin"
    ) in container["args"][0]
    assert "rootPasswordFile" not in container["args"][0]
    assert service["spec"]["ports"] == [
        {"name": "http", "port": 2480, "targetPort": "http"},
        {"name": "binary", "port": 2424, "targetPort": "binary"},
        {"name": "bolt", "port": 7687, "targetPort": "bolt"},
        {"name": "gremlin", "port": 8182, "targetPort": "gremlin"},
        {"name": "mongo", "port": 27017, "targetPort": "mongo"},
    ]
    assert {"name": "bolt", "containerPort": 7687} in container["ports"]


def test_arcadedb_service_uses_image_server_sh_path() -> None:
    k8s = RecordingKubernetes()
    spec = PulumiKubernetesWorkloadSpec(
        project_name="nephos-api",
        stack_name="svc-arcadedb",
        work_dir=Path("/tmp/workspaces/svc-arcadedb"),
        state_dir=Path("/tmp/state"),
        kubeconfig=None,
        kube_context=None,
        runtime_name="svc-arcadedb",
        namespace="svc-arcadedb",
        workload="arcadedb-service",
        values={
            "image": "arcadedata/arcadedb:26.5.1",
            "rootPassword": "arcade-secret",
        },
    )

    _arcadedb_service(spec, k8s=k8s, opts=None)

    container = k8s.stateful_set.calls[0]["spec"]["template"]["spec"]["containers"][0]
    entrypoint = container["args"][0]
    # The arcadedata/arcadedb image ships server.sh under /home/arcadedb/bin,
    # not /opt/arcadedb; the wrong path exits 127 and CrashLoops.
    assert "exec /home/arcadedb/bin/server.sh " in entrypoint
    assert "/opt/arcadedb" not in entrypoint


def test_arcadedb_service_blocks_digest_only_images() -> None:
    k8s = RecordingKubernetes()
    spec = PulumiKubernetesWorkloadSpec(
        project_name="nephos-api",
        stack_name="svc-arcadedb",
        work_dir=Path("/tmp/workspaces/svc-arcadedb"),
        state_dir=Path("/tmp/state"),
        kubeconfig=None,
        kube_context=None,
        runtime_name="svc-arcadedb",
        namespace="svc-arcadedb",
        workload="arcadedb-service",
        values={
            "image": (
                "arcadedata/arcadedb@sha256:"
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            ),
            "rootPassword": "arcade-secret",
        },
    )

    try:
        _arcadedb_service(spec, k8s=k8s, opts=None)
    except RuntimeBlockedError as exc:
        assert exc.reason == "runtime_config_unsupported"
        assert "versioned image tag" in str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("expected digest-only ArcadeDB image block")


def test_arcadedb_service_blocks_images_without_bolt_support() -> None:
    k8s = RecordingKubernetes()
    spec = PulumiKubernetesWorkloadSpec(
        project_name="nephos-api",
        stack_name="svc-arcadedb",
        work_dir=Path("/tmp/workspaces/svc-arcadedb"),
        state_dir=Path("/tmp/state"),
        kubeconfig=None,
        kube_context=None,
        runtime_name="svc-arcadedb",
        namespace="svc-arcadedb",
        workload="arcadedb-service",
        values={
            "image": (
                "arcadedata/arcadedb:25.5.1@sha256:"
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            ),
            "rootPassword": "arcade-secret",
        },
    )

    try:
        _arcadedb_service(spec, k8s=k8s, opts=None)
    except RuntimeBlockedError as exc:
        assert exc.reason == "runtime_config_unsupported"
        assert "26.2.1" in str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("expected ArcadeDB image version block")


def test_openbao_service_runs_dev_mode_with_secret_token() -> None:
    k8s = RecordingKubernetes()
    spec = PulumiKubernetesWorkloadSpec(
        project_name="nephos-api",
        stack_name="svc-openbao",
        work_dir=Path("/tmp/workspaces/svc-openbao"),
        state_dir=Path("/tmp/state"),
        kubeconfig=None,
        kube_context=None,
        runtime_name="svc-openbao",
        namespace="svc-openbao",
        workload="openbao-service",
        values={},
    )

    _openbao_service(spec, k8s=k8s, opts=None)

    secret = cast(dict[str, Any], k8s.secret.calls[0])
    service = cast(dict[str, Any], k8s.service.calls[0])
    deployment = cast(dict[str, Any], k8s.deployment.calls[0])
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert secret["string_data"] == {"dev-root-token": "root"}
    assert service["spec"]["ports"] == [
        {"name": "http", "port": 8200, "targetPort": "http"}
    ]
    assert container["args"] == ["server", "-dev"]
    token_env = next(
        e for e in container["env"] if e["name"] == "BAO_DEV_ROOT_TOKEN_ID"
    )
    assert token_env["valueFrom"]["secretKeyRef"]["key"] == "dev-root-token"
    listen_env = next(
        e for e in container["env"] if e["name"] == "BAO_DEV_LISTEN_ADDRESS"
    )
    assert listen_env["value"] == "0.0.0.0:8200"


def test_openbao_persistent_service_is_statefulset_with_unseal_sidecar() -> None:
    k8s = RecordingKubernetes()
    spec = PulumiKubernetesWorkloadSpec(
        project_name="nephos-api",
        stack_name="svc-openbao",
        work_dir=Path("/tmp/workspaces/svc-openbao"),
        state_dir=Path("/tmp/state"),
        kubeconfig=None,
        kube_context=None,
        runtime_name="svc-openbao",
        namespace="svc-openbao",
        workload="openbao-persistent-service",
        values={},
    )

    _openbao_persistent_service(spec, k8s=k8s, opts=None)

    sts = cast(dict[str, Any], k8s.stateful_set.calls[0])["spec"]
    pod = sts["template"]["spec"]
    # Persistent = PVC-backed, not the dev-mode in-memory Deployment.
    assert "volumeClaimTemplates" in sts
    assert pod["securityContext"] == {"fsGroup": 1000}
    containers = {c["name"]: c for c in pod["containers"]}
    assert set(containers) == {"openbao", "unseal"}
    assert containers["openbao"]["args"] == ["server"]
    # The unseal sidecar mounts the managed key Secret optionally (absent on the
    # first boot before init creates it).
    volume = pod["volumes"][0]
    assert volume["secret"]["optional"] is True
    assert k8s.deployment.calls == []


def test_seaweedfs_service_rejects_a_credential_weed_shell_cannot_represent() -> None:
    """Caught at render time so a bad override fails the install with a readable
    reason, instead of leaving the pod wedged in Init behind a seeder that
    applied a command storing nothing."""
    k8s = RecordingKubernetes()
    spec = _seaweedfs_spec()
    values = dict(spec.values)
    values["s3AccessKey"] = "has'quote"
    spec = replace(spec, values=values)

    with pytest.raises(RuntimeBlockedError) as excinfo:
        _seaweedfs_service(spec, k8s=k8s, opts=None)

    assert excinfo.value.reason == "seaweedfs_credential_unrepresentable"


def test_seaweedfs_seed_script_quotes_and_verifies_by_credential() -> None:
    k8s = RecordingKubernetes()

    _seaweedfs_service(_seaweedfs_spec(), k8s=k8s, opts=None)

    script = k8s.stateful_set.calls[0]["spec"]["template"]["spec"]["initContainers"][0][
        "command"
    ][-1]
    # Simple single quotes: weed shell honours those, and embedded quotes are
    # rejected before they can reach here.
    assert "-access_key '$NEPHOS_S3_ACCESS_KEY'" in script
    assert "-secret_key '$NEPHOS_S3_SECRET_KEY'" in script
    # Read back by credential, not by identity name: on a reused volume the name
    # is already present, so a name-only check passes with a stale credential.
    assert 'grep -qF "$NEPHOS_S3_ACCESS_KEY"' in script
