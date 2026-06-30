from fastapi.testclient import TestClient

from nephos_api.config import ManagedCatalogRegistry, Settings
from nephos_api.main import (
    _default_runtime_factory,
    app,
    create_app,
    default_provider_deployer_factory,
)
from nephos_api.repository import DesiredStateRepository


def test_version_endpoint_reports_backend_identity() -> None:
    client = TestClient(app)

    response = client.get("/version")

    assert response.status_code == 200
    assert response.json() == {"name": "nephos-api", "version": "0.0.1"}


def test_create_app_ensures_managed_registries_on_startup(
    monkeypatch,
    tmp_path,
) -> None:
    registry_path = tmp_path / ".nephos" / "registries" / "core-registry"
    settings = Settings(
        db_path=tmp_path / "nephos.db",
        catalog_roots=(registry_path,),
        kubeconfig=None,
        kube_context=None,
        managed_catalog_registries=(
            ManagedCatalogRegistry(
                name="core-registry",
                url="https://example.test/core-registry.git",
                path=registry_path,
            ),
        ),
    )
    calls = []

    def fake_sync(received_settings):
        calls.append(received_settings)

    monkeypatch.setattr("nephos_api.main.ensure_managed_catalog_registries", fake_sync)

    with TestClient(create_app(settings=settings)) as client:
        assert client.get("/version").status_code == 200

    assert calls == [settings]


def test_default_provider_deployer_factory_builds_pulumi_provider_deployer(
    monkeypatch,
    tmp_path,
) -> None:
    captured = {}

    class FakeCoreV1Api:
        pass

    class FakeProviderDeployer:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("kubernetes.client.CoreV1Api", FakeCoreV1Api)
    monkeypatch.setattr(
        "nephos_api.main.load_kubernetes_config",
        lambda _settings: None,
    )
    monkeypatch.setattr(
        "nephos_api.main.ProviderRuntimeDeployer",
        FakeProviderDeployer,
    )

    deployer = default_provider_deployer_factory(
        Settings(
            db_path=tmp_path / "nephos.db",
            catalog_roots=(),
            kubeconfig=None,
            kube_context=None,
        ),
        DesiredStateRepository(tmp_path / "nephos.db"),
    )

    assert isinstance(deployer, FakeProviderDeployer)
    assert captured["binding_value_source"].__class__.__name__ == (
        "KubernetesSecretBindingValueSource"
    )
    assert captured["app_provider"].__class__.__name__ == "RuntimeProviderRouter"
    assert captured["service_provider"].__class__.__name__ == "RuntimeProviderRouter"
    assert captured["secret_resolver"].__class__.__name__ == (
        "OnePasswordCliSecretResolver"
    )


def test_default_runtime_factory_provides_apps_api_for_scaling(
    monkeypatch,
    tmp_path,
) -> None:
    captured = {}

    class FakeCoreV1Api:
        pass

    class FakeAppsV1Api:
        pass

    class FakeNetworkingV1Api:
        pass

    class FakeRuntime:
        def __init__(
            self,
            core_v1_api,
            *,
            apps_v1_api,
            networking_v1_api,
            ingress_class_name,
        ):
            captured["core"] = core_v1_api
            captured["apps"] = apps_v1_api
            captured["networking"] = networking_v1_api
            captured["ingress_class_name"] = ingress_class_name

    monkeypatch.setattr("kubernetes.client.CoreV1Api", FakeCoreV1Api)
    monkeypatch.setattr("kubernetes.client.AppsV1Api", FakeAppsV1Api)
    monkeypatch.setattr("kubernetes.client.NetworkingV1Api", FakeNetworkingV1Api)
    monkeypatch.setattr("nephos_api.main.KubernetesRuntime", FakeRuntime)
    monkeypatch.setattr(
        "nephos_api.main.load_kubernetes_config",
        lambda _settings: None,
    )

    runtime = _default_runtime_factory(
        Settings(
            db_path=tmp_path / "nephos.db",
            catalog_roots=(),
            kubeconfig=None,
            kube_context=None,
            ingress_class="nginx",
        )
    )

    assert isinstance(runtime, FakeRuntime)
    assert isinstance(captured["core"], FakeCoreV1Api)
    assert isinstance(captured["apps"], FakeAppsV1Api)
    assert isinstance(captured["networking"], FakeNetworkingV1Api)
    assert captured["ingress_class_name"] == "nginx"
