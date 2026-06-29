from nephos_api.providers import ProviderContext, RuntimeProviderRouter
from nephos_api.runtime_errors import RuntimeBlockedError


class RecordingProvider:
    def __init__(self) -> None:
        self.deployed: list[ProviderContext] = []
        self.uninstalled: list[ProviderContext] = []

    def deploy(self, context: ProviderContext) -> None:
        self.deployed.append(context)

    def uninstall(self, context: ProviderContext) -> None:
        self.uninstalled.append(context)


def test_runtime_provider_router_dispatches_provider_runtime_by_name() -> None:
    helm = RecordingProvider()
    postgres = RecordingProvider()
    router = RuntimeProviderRouter(
        helm_provider=helm,
        provider_runtimes={"postgres": postgres},
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

    router.deploy(context)
    router.uninstall(context)

    assert helm.deployed == []
    assert postgres.deployed == [context]
    assert postgres.uninstalled == [context]


def test_runtime_provider_router_blocks_unknown_provider_runtime() -> None:
    router = RuntimeProviderRouter(
        helm_provider=RecordingProvider(),
        provider_runtimes={},
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

    try:
        router.deploy(context)
    except RuntimeBlockedError as exc:
        assert exc.reason == "runtime_provider_unknown"
    else:
        raise AssertionError("expected unknown provider runtime to block")


def test_runtime_provider_router_dispatches_alpha_backbone_service_names() -> None:
    helm = RecordingProvider()
    providers = {
        "postgres": RecordingProvider(),
        "zitadel": RecordingProvider(),
        "seaweedfs": RecordingProvider(),
        "arcadedb": RecordingProvider(),
    }
    router = RuntimeProviderRouter(
        helm_provider=helm,
        provider_runtimes=providers,
    )

    for provider_name, provider in providers.items():
        context = ProviderContext(
            target_type="service_instance",
            slug=provider_name,
            runtime_name=f"svc-{provider_name}",
            manifest=None,
            chart=None,
            values={"marker": provider_name},
            provider_name=provider_name,
        )

        router.deploy(context)

        assert provider.deployed == [context]

    assert helm.deployed == []
