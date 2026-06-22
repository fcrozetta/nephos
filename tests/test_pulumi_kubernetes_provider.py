from pathlib import Path

from nephos_api.providers import ProviderContext
from nephos_api.providers.kubernetes import (
    PulumiKubernetesProvider,
    PulumiKubernetesProviderConfig,
    PulumiKubernetesWorkloadSpec,
    _arcadedb_service,
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
            "externalHost": "login.nephos.localhost",
        },
    )

    _zitadel_service(spec, k8s=k8s, opts=None)

    secret = k8s.secret.calls[0]
    deployment = k8s.deployment.calls[0]
    service = k8s.service.calls[0]
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert secret["string_data"] == {
        "admin-username": "root@zitadel.localhost",
        "admin-password": "local-secret",
    }
    assert container["image"] == "ghcr.io/zitadel/zitadel:v2.58.0"
    assert {"name": "ZITADEL_EXTERNALDOMAIN", "value": "login.nephos.localhost"} in (
        container["env"]
    )
    assert service["spec"]["ports"] == [
        {"name": "http", "port": 8080, "targetPort": "http"}
    ]


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
    assert secret["string_data"] == {
        "s3-access-key": "alpha-access",
        "s3-secret-key": "alpha-secret",
    }
    assert container["image"] == "chrislusf/seaweedfs:3.85"
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
    assert service["spec"]["ports"] == [
        {"name": "http", "port": 2480, "targetPort": "http"},
        {"name": "binary", "port": 2424, "targetPort": "binary"},
        {"name": "gremlin", "port": 8182, "targetPort": "gremlin"},
        {"name": "mongo", "port": 27017, "targetPort": "mongo"},
    ]
