from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from nephos_api import __version__
from nephos_api.api.auth import router as auth_router
from nephos_api.api.bindings import router as bindings_router
from nephos_api.api.catalog import router as catalog_router
from nephos_api.api.platform import router as platform_router
from nephos_api.api.resources import router as resources_router
from nephos_api.config import Settings, load_settings
from nephos_api.errors import NephosError, nephos_error_response
from nephos_api.kubernetes_client import load_kubernetes_config
from nephos_api.kubernetes_runtime import KubernetesRuntime, ResourceType
from nephos_api.providers import (
    ProviderRuntimeDeployer,
    PulumiHelmProvider,
    PulumiHelmProviderConfig,
    PulumiKubernetesProvider,
    PulumiKubernetesProviderConfig,
    RuntimeProviderRouter,
)
from nephos_api.provisioning import BindingProvisioner, BindingProvisioningContext
from nephos_api.reconciler import Reconciler, RuntimeAdapter, RuntimeDeployer
from nephos_api.reconciler_worker import ReconcilerWorker
from nephos_api.registries import ensure_managed_catalog_registries
from nephos_api.repository import DesiredStateRepository
from nephos_api.secret_refs import (
    BaoSecretResolver,
    BaoTokenProvider,
    ChainedBaoTokenProvider,
    OnePasswordCliSecretResolver,
    OpenBaoSecretsProvider,
    RuntimeSecretResolver,
    SchemeRoutingSecretResolver,
    SecretsMaterializer,
    StaticBaoTokenProvider,
)

RuntimeFactory = Callable[[Settings], RuntimeAdapter]
DeployerFactory = Callable[[Settings, DesiredStateRepository], RuntimeDeployer]
ProvisionerFactory = Callable[[Settings], BindingProvisioner]


def create_app(
    *,
    settings: Settings | None = None,
    start_reconciler: bool = False,
    runtime_factory: RuntimeFactory | None = None,
    deployer_factory: DeployerFactory | None = None,
    provisioner: BindingProvisioner | None = None,
    provisioner_factory: ProvisionerFactory | None = None,
    reconciler_interval_seconds: float = 1.0,
    ensure_registries: bool = True,
) -> FastAPI:
    resolved_settings = settings if settings is not None else load_settings()
    lifespan = _lifespan(
        start_reconciler=start_reconciler,
        runtime_factory=runtime_factory or _default_runtime_factory,
        deployer_factory=deployer_factory,
        provisioner=provisioner,
        provisioner_factory=provisioner_factory,
        reconciler_interval_seconds=reconciler_interval_seconds,
        ensure_registries=ensure_registries,
    )
    app = FastAPI(title="Nephos API", version=__version__, lifespan=lifespan)
    app.state.settings = resolved_settings
    app.state.repository = DesiredStateRepository(resolved_settings.db_path)
    app.state.ensure_registries = ensure_registries
    app.state.reconciler_enabled = start_reconciler
    app.state.deployer_enabled = deployer_factory is not None
    app.state.provisioner_enabled = (
        provisioner is not None or provisioner_factory is not None
    )
    app.add_exception_handler(NephosError, nephos_error_response)
    app.include_router(auth_router)
    app.include_router(bindings_router)
    app.include_router(catalog_router)
    app.include_router(platform_router)
    app.include_router(resources_router)

    @app.get("/version")
    def read_version() -> dict[str, str]:
        return {"name": "nephos-api", "version": __version__}

    @app.get("/healthz")
    def read_healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _lifespan(
    *,
    start_reconciler: bool,
    runtime_factory: RuntimeFactory,
    deployer_factory: DeployerFactory | None,
    provisioner: BindingProvisioner | None,
    provisioner_factory: ProvisionerFactory | None,
    reconciler_interval_seconds: float,
    ensure_registries: bool,
) -> Callable[[FastAPI], AsyncIterator[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        task: asyncio.Task[None] | None = None
        worker: ReconcilerWorker | None = None
        if ensure_registries:
            ensure_managed_catalog_registries(app.state.settings)
        if start_reconciler:
            runtime = _LazyRuntimeAdapter(runtime_factory, app.state.settings)
            deployer = (
                _LazyRuntimeDeployer(
                    deployer_factory,
                    app.state.settings,
                    app.state.repository,
                )
                if deployer_factory is not None
                else None
            )
            resolved_provisioner = provisioner
            if resolved_provisioner is None and provisioner_factory is not None:
                resolved_provisioner = _LazyBindingProvisioner(
                    provisioner_factory,
                    app.state.settings,
                )
            worker = ReconcilerWorker(
                Reconciler(
                    app.state.repository,
                    runtime=runtime,
                    provisioner=resolved_provisioner,
                    deployer=deployer,
                ),
                interval_seconds=reconciler_interval_seconds,
            )
            app.state.reconciler_worker = worker
            task = asyncio.create_task(worker.run())
        try:
            yield
        finally:
            if worker is not None:
                await worker.stop()
            if task is not None:
                await task

    return lifespan


def _default_runtime_factory(settings: Settings) -> RuntimeAdapter:
    from kubernetes import client

    load_kubernetes_config(settings)
    return KubernetesRuntime(
        client.CoreV1Api(),
        apps_v1_api=client.AppsV1Api(),
        networking_v1_api=client.NetworkingV1Api(),
        ingress_class_name=settings.ingress_class,
    )


class _LazyRuntimeAdapter:
    def __init__(self, factory: RuntimeFactory, settings: Settings) -> None:
        self._factory = factory
        self._settings = settings
        self._runtime: RuntimeAdapter | None = None

    def ensure_namespace(self, resource_type: ResourceType, slug: str) -> object:
        return self._get().ensure_namespace(resource_type, slug)

    def delete_namespace_if_owned(
        self,
        resource_type: ResourceType,
        slug: str,
    ) -> bool:
        return self._get().delete_namespace_if_owned(resource_type, slug)

    def ensure_binding_secret(
        self,
        *,
        app_slug: str,
        service_slug: str,
        alias: str,
        capability: str,
        protocol: str | None = None,
        values: dict[str, str],
    ) -> object:
        return self._get().ensure_binding_secret(
            app_slug=app_slug,
            service_slug=service_slug,
            alias=alias,
            capability=capability,
            protocol=protocol,
            values=values,
        )

    def delete_binding_secret_if_owned(
        self,
        *,
        app_slug: str,
        service_slug: str,
        alias: str,
        capability: str,
        protocol: str | None = None,
    ) -> bool:
        return self._get().delete_binding_secret_if_owned(
            app_slug=app_slug,
            service_slug=service_slug,
            alias=alias,
            capability=capability,
            protocol=protocol,
        )

    def scale_workloads(
        self,
        resource_type: ResourceType,
        slug: str,
        replicas: int,
    ) -> object:
        return self._get().scale_workloads(resource_type, slug, replicas)

    def ensure_app_ingresses(
        self,
        *,
        app_slug: str,
        routes: list[dict[str, object]],
        domains: list[dict[str, object]],
    ) -> object:
        return self._get().ensure_app_ingresses(
            app_slug=app_slug,
            routes=routes,
            domains=domains,
        )

    def delete_app_ingresses(
        self,
        *,
        app_slug: str,
        routes: list[dict[str, object]],
    ) -> object:
        return self._get().delete_app_ingresses(app_slug=app_slug, routes=routes)

    def _get(self) -> RuntimeAdapter:
        if self._runtime is None:
            self._runtime = self._factory(self._settings)
        return self._runtime


class _LazyRuntimeDeployer:
    def __init__(
        self,
        factory: DeployerFactory,
        settings: Settings,
        repository: DesiredStateRepository,
    ) -> None:
        self._factory = factory
        self._settings = settings
        self._repository = repository
        self._deployer: RuntimeDeployer | None = None

    def deploy(self, *, target_type: str, slug: str) -> None:
        self._get().deploy(target_type=target_type, slug=slug)

    def uninstall(self, *, target_type: str, slug: str) -> None:
        self._get().uninstall(target_type=target_type, slug=slug)

    def _get(self) -> RuntimeDeployer:
        if self._deployer is None:
            self._deployer = self._factory(self._settings, self._repository)
        return self._deployer


class _LazyBindingProvisioner:
    def __init__(self, factory: ProvisionerFactory, settings: Settings) -> None:
        self._factory = factory
        self._settings = settings
        self._provisioner: BindingProvisioner | None = None

    def provision_binding(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str] | None:
        return self._get().provision_binding(context)

    def deprovision_binding(self, context: BindingProvisioningContext) -> None:
        self._get().deprovision_binding(context)

    def _get(self) -> BindingProvisioner:
        if self._provisioner is None:
            self._provisioner = self._factory(self._settings)
        return self._provisioner


def default_provider_deployer_factory(
    settings: Settings,
    repository: DesiredStateRepository,
) -> RuntimeDeployer:
    from kubernetes import client

    from nephos_api.kubernetes_runtime import KubernetesSecretBindingValueSource
    from nephos_api.providers.service_lifecycle import KubernetesOpenBaoLifecycle
    from nephos_api.provisioning import PostgresAppScopedProvisioner

    load_kubernetes_config(settings)
    core_v1_api = client.CoreV1Api()
    pulumi_config = _pulumi_helm_provider_config(settings)
    kubernetes_config = _pulumi_kubernetes_provider_config(settings)
    app_provider = RuntimeProviderRouter(
        helm_provider=PulumiHelmProvider(config=pulumi_config),
        provider_runtimes={
            "reference-web": PulumiKubernetesProvider(
                config=kubernetes_config,
                workload="reference-app",
            ),
        },
    )
    service_runtimes: dict[str, PulumiKubernetesProvider] = {
        "postgres": PulumiKubernetesProvider(
            config=kubernetes_config,
            workload="postgres-service",
        ),
        "zitadel": PulumiKubernetesProvider(
            config=kubernetes_config,
            workload="zitadel-service",
        ),
        "seaweedfs": PulumiKubernetesProvider(
            config=kubernetes_config,
            workload="seaweedfs-service",
        ),
        "arcadedb": PulumiKubernetesProvider(
            config=kubernetes_config,
            workload="arcadedb-service",
        ),
        "cloudflared": PulumiKubernetesProvider(
            config=kubernetes_config,
            workload="cloudflared-service",
        ),
    }
    # OpenBao secret backend. Persistent (StatefulSet + auto init/unseal) takes
    # precedence when enabled. Otherwise the insecure dev-mode provider is only
    # registered in LCL with an explicit opt-in. Anywhere else an openbao install
    # blocks as unknown runtime.
    openbao_lifecycle = None
    if settings.openbao_persistent:
        service_runtimes["openbao"] = PulumiKubernetesProvider(
            config=kubernetes_config,
            workload="openbao-persistent-service",
        )
        # The init Secret name/keys are fixed constants shared by the lifecycle,
        # the unseal sidecar, and the token provider, so they cannot diverge.
        openbao_lifecycle = KubernetesOpenBaoLifecycle(
            core_v1_api=core_v1_api,
            kv_mount=settings.bao_kv_mount,
        )
    elif settings.env == "lcl" and settings.allow_dev_mode_openbao:
        service_runtimes["openbao"] = PulumiKubernetesProvider(
            config=kubernetes_config,
            workload="openbao-service",
        )
    service_provider = RuntimeProviderRouter(
        helm_provider=PulumiHelmProvider(config=pulumi_config),
        provider_runtimes=service_runtimes,
    )
    return ProviderRuntimeDeployer(
        repository=repository,
        app_provider=app_provider,
        service_provider=service_provider,
        binding_value_source=KubernetesSecretBindingValueSource(core_v1_api),
        service_dependency_provisioner=PostgresAppScopedProvisioner(
            core_v1_api=core_v1_api
        ),
        secret_resolver=_build_secret_resolver(settings, core_v1_api=core_v1_api),
        secrets_materializer=_build_secrets_materializer(
            settings, core_v1_api=core_v1_api
        ),
        service_lifecycle=openbao_lifecycle,
    )


def _bao_token_providers(
    settings: Settings, *, core_v1_api: object | None
) -> list[BaoTokenProvider]:
    # Ordered k8s-first so a live init token wins over a stale static dev token.
    token_providers: list[BaoTokenProvider] = []
    if core_v1_api is not None:
        from nephos_api.kubernetes_runtime import (
            KubernetesSecretBaoTokenProvider,
            namespace_name,
        )

        token_providers.append(
            # NOTE: openbao must be installed under the slug "openbao" (single-
            # instance constraint, see the OpenBao ADR); the init Secret
            # name/key are the shared fixed constants.
            KubernetesSecretBaoTokenProvider(
                core_v1_api,
                namespace=namespace_name("service_instance", "openbao"),
            )
        )
    if settings.bao_token:
        token_providers.append(StaticBaoTokenProvider(settings.bao_token))
    return token_providers


def _build_secret_resolver(
    settings: Settings, *, core_v1_api: object | None = None
) -> RuntimeSecretResolver:
    # op:// resolves through the 1Password CLI. bao:// resolves through OpenBao,
    # taking its token from the Nephos-managed init Secret (via the Kubernetes
    # API) and falling back to the static dev token. Both are legacy read-only
    # schemes; new references use secrets:// (see the secrets-capability ADR).
    resolvers: dict[str, RuntimeSecretResolver] = {
        "op://": OnePasswordCliSecretResolver(),
    }
    if settings.bao_address:
        token_providers = _bao_token_providers(settings, core_v1_api=core_v1_api)
        if token_providers:
            resolvers["bao://"] = BaoSecretResolver(
                address=settings.bao_address,
                token_provider=ChainedBaoTokenProvider(tuple(token_providers)),
            )
    return SchemeRoutingSecretResolver(resolvers)


def _build_secrets_materializer(
    settings: Settings, *, core_v1_api: object | None = None
) -> SecretsMaterializer | None:
    # The secrets:// capability, backed by the managed OpenBao (KV v2 with CAS
    # writes). Returns None when OpenBao is not configured, in which case a
    # secrets:// reference fails closed at deploy time.
    if not settings.bao_address:
        return None
    token_providers = _bao_token_providers(settings, core_v1_api=core_v1_api)
    if not token_providers:
        return None
    provider = OpenBaoSecretsProvider(
        address=settings.bao_address,
        token_provider=ChainedBaoTokenProvider(tuple(token_providers)),
        mount=settings.bao_kv_mount,
    )
    return SecretsMaterializer(provider)


def _pulumi_helm_provider_config(settings: Settings) -> PulumiHelmProviderConfig:
    base_dir = _pulumi_base_dir(settings)
    pulumi_dir = base_dir / "pulumi"
    return PulumiHelmProviderConfig(
        work_dir=pulumi_dir / "workspaces",
        state_dir=pulumi_dir / "state",
        kubeconfig=settings.kubeconfig,
        kube_context=settings.kube_context,
    )


def _pulumi_kubernetes_provider_config(
    settings: Settings,
) -> PulumiKubernetesProviderConfig:
    base_dir = _pulumi_base_dir(settings)
    pulumi_dir = base_dir / "pulumi"
    return PulumiKubernetesProviderConfig(
        work_dir=pulumi_dir / "workspaces",
        state_dir=pulumi_dir / "state",
        kubeconfig=settings.kubeconfig,
        kube_context=settings.kube_context,
    )


def _pulumi_base_dir(settings: Settings) -> Path:
    base_dir = (
        settings.db_path.parent.parent
        if settings.db_path.parent.name == "state"
        else settings.db_path.parent
    )
    return base_dir


def default_postgres_provisioner_factory(settings: Settings) -> BindingProvisioner:
    from kubernetes import client

    from nephos_api.provisioning import (
        CompositeBindingProvisioner,
        KubernetesPulumiZitadelProvisioningClient,
        KubernetesZitadelProvisionerConfig,
        PostgresAppScopedProvisioner,
        SecretResolvingBindingProvisioner,
        ZitadelAppScopedProvisioner,
    )

    load_kubernetes_config(settings)
    core_v1_api = client.CoreV1Api()
    pulumi_dir = _pulumi_base_dir(settings) / "pulumi"
    zitadel_client = KubernetesPulumiZitadelProvisioningClient(
        core_v1_api=core_v1_api,
        config=KubernetesZitadelProvisionerConfig(
            work_dir=pulumi_dir / "workspaces",
            state_dir=pulumi_dir / "state",
            kubeconfig=settings.kubeconfig,
            kube_context=settings.kube_context,
        ),
    )
    return SecretResolvingBindingProvisioner(
        CompositeBindingProvisioner(
            [
                PostgresAppScopedProvisioner(core_v1_api=core_v1_api),
                ZitadelAppScopedProvisioner(client=zitadel_client),
            ]
        ),
        resolver=_build_secret_resolver(settings, core_v1_api=core_v1_api),
    )


app = create_app()
