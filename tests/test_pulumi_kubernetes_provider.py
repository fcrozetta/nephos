from pathlib import Path

from nephos_api.providers import ProviderContext
from nephos_api.providers.kubernetes import (
    PulumiKubernetesProvider,
    PulumiKubernetesProviderConfig,
    PulumiKubernetesWorkloadSpec,
    _postgres_service,
)


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
        self.service = RecordingResource()
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
