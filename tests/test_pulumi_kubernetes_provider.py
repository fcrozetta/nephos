from pathlib import Path

from nephos_api.providers import ProviderContext
from nephos_api.providers.kubernetes import (
    PulumiKubernetesProvider,
    PulumiKubernetesProviderConfig,
    PulumiKubernetesWorkloadSpec,
    _arcadedb_service,
    _cloudflared_service,
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
                    {"Ingress": self.ingress},
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
        values={},
    )

    _postgres_service(spec, k8s=k8s, opts=None)

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
    config_map = k8s.config_map.calls[0]
    stateful_set = k8s.stateful_set.calls[0]
    container = stateful_set["spec"]["template"]["spec"]["containers"][0]
    pod_spec = stateful_set["spec"]["template"]["spec"]
    assert secret["string_data"] == {
        "postgres-password": "admin-secret",
        "zitadel-password": "zitadel-secret",
    }
    assert "CREATE ROLE \"zitadel\"" in config_map["data"]["010-nephos-zitadel.sql"]
    assert "CREATE DATABASE \"zitadel\" OWNER \"zitadel\"" in config_map["data"][
        "010-nephos-zitadel.sql"
    ]
    assert container["image"] == "postgres:16-alpine"
    assert {
        "name": "initdb",
        "configMap": {"name": "svc-postgres-postgresql-initdb"},
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
                "items": [
                    {"key": "credentials.json", "path": "credentials.json"}
                ],
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
            "adminPassword": "local-secret",
            "masterKey": "0123456789abcdef0123456789abcdef",
            "databasePassword": "db-secret",
            "externalHost": "login.nephos.localhost",
            "externalPort": 443,
            "externalSecure": True,
            "bootstrapMachineUsername": "nephos-bot",
            "bootstrapMachineName": "Nephos Bot",
            "bootstrapMachineKeyPath": "/var/lib/zitadel-bootstrap/bot.json",
            "bootstrapMachineKeyExpiration": "2037-01-01T00:00:00Z",
            "ingressEnabled": True,
            "ingressClassName": "nginx",
            "storageSize": "4Gi",
        },
    )

    _zitadel_service(spec, k8s=k8s, opts=None)

    secret = k8s.secret.calls[0]
    stateful_set = k8s.stateful_set.calls[0]
    service = k8s.service.calls[0]
    ingress = k8s.ingress.calls[0]
    stateful_pod_spec = stateful_set["spec"]["template"]["spec"]
    containers = stateful_pod_spec["containers"]
    container = next(item for item in containers if item["name"] == "zitadel")
    bootstrap_reader = next(
        item for item in containers if item["name"] == "bootstrap-reader"
    )
    postgres = next(item for item in containers if item["name"] == "postgres")
    data_pvc = next(
        item
        for item in stateful_set["spec"]["volumeClaimTemplates"]
        if item["metadata"]["name"] == "data"
    )
    bootstrap_pvc = next(
        item
        for item in stateful_set["spec"]["volumeClaimTemplates"]
        if item["metadata"]["name"] == "bootstrap"
    )
    env = {item["name"]: item for item in container["env"]}
    assert secret["string_data"] == {
        "admin-username": "root@zitadel.localhost",
        "admin-password": "local-secret",
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
    assert env[
        "ZITADEL_FIRSTINSTANCE_ORG_MACHINE_MACHINEKEY_EXPIRATIONDATE"
    ]["value"] == "2037-01-01T00:00:00Z"
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
    assert env["ZITADEL_DATABASE_POSTGRES_HOST"]["value"] == "127.0.0.1"
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
    assert postgres["image"] == "postgres:16-alpine"
    assert {
        "name": "POSTGRES_PASSWORD",
        "valueFrom": {
            "secretKeyRef": {
                "name": "svc-zitadel-zitadel",
                "key": "database-password",
            }
        },
    } in postgres["env"]
    assert {
        "name": "bootstrap",
        "mountPath": "/var/lib/zitadel-bootstrap",
        "readOnly": True,
    } in postgres["volumeMounts"]
    assert data_pvc["spec"]["resources"]["requests"]["storage"] == "4Gi"
    assert bootstrap_pvc["spec"]["resources"]["requests"]["storage"] == "64Mi"
    assert service["spec"]["ports"] == [
        {"name": "http", "port": 8080, "targetPort": "http"}
    ]
    assert ingress["metadata"] == {
        "name": "svc-zitadel-zitadel",
        "namespace": "svc-zitadel",
        "labels": service["metadata"]["labels"],
    }
    assert ingress["spec"] == {
        "ingressClassName": "nginx",
        "rules": [
            {
                "host": "login.nephos.localhost",
                "http": {
                    "paths": [
                        {
                            "path": "/",
                            "pathType": "Prefix",
                            "backend": {
                                "service": {
                                    "name": "svc-zitadel-zitadel",
                                    "port": {"number": 8080},
                                }
                            },
                        }
                    ]
                },
            }
        ],
    }


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


def test_zitadel_service_omits_ingress_by_default() -> None:
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
        values={},
    )

    _zitadel_service(spec, k8s=k8s, opts=None)

    assert k8s.ingress.calls == []


def test_seaweedfs_service_forwards_values_to_runtime_resources() -> None:
    k8s = RecordingKubernetes()
    spec = PulumiKubernetesWorkloadSpec(
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

    _seaweedfs_service(spec, k8s=k8s, opts=None)

    secret = k8s.secret.calls[0]
    stateful_set = k8s.stateful_set.calls[0]
    service = k8s.service.calls[0]
    container = stateful_set["spec"]["template"]["spec"]["containers"][0]
    pvc = stateful_set["spec"]["volumeClaimTemplates"][0]
    env_names = {item["name"] for item in container.get("env", [])}
    assert secret["string_data"] == {
        "s3-access-key": "alpha-access",
        "s3-secret-key": "alpha-secret",
    }
    assert container["image"] == "chrislusf/seaweedfs:3.85"
    assert "WEED_S3_ACCESS_KEY" not in env_names
    assert "WEED_S3_SECRET_KEY" not in env_names
    assert pvc["spec"]["resources"]["requests"]["storage"] == "2Gi"
    assert service["spec"]["ports"] == [
        {"name": "s3", "port": 8333, "targetPort": "s3"}
    ]


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
            "image": "arcadedata/arcadedb:25.5.1",
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
    assert container["image"] == "arcadedata/arcadedb:25.5.1"
    assert container["command"] == ["/bin/sh", "-ec"]
    assert "root_password=\"$(cat /run/secrets/arcadedb/root-password)\"" in (
        container["args"][0]
    )
    assert "-Darcadedb.server.rootPassword=${root_password}" in container["args"][0]
    assert "rootPasswordFile" not in container["args"][0]
    assert service["spec"]["ports"] == [
        {"name": "http", "port": 2480, "targetPort": "http"},
        {"name": "binary", "port": 2424, "targetPort": "binary"},
        {"name": "gremlin", "port": 8182, "targetPort": "gremlin"},
        {"name": "mongo", "port": 27017, "targetPort": "mongo"},
    ]
