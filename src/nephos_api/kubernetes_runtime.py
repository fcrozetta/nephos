from __future__ import annotations

import base64
import time
from typing import Literal

from kubernetes import client
from kubernetes.client.rest import ApiException

from nephos_api.domain import validate_machine_identifier
from nephos_api.routing import service_portal_host
from nephos_api.runtime_errors import RuntimeBlockedError

ResourceType = Literal["app_instance", "service_instance"]

MANAGED_BY_LABEL = "app.kubernetes.io/managed-by"
APP_INSTANCE_LABEL = "nephos.pro/app-instance"
SERVICE_INSTANCE_LABEL = "nephos.pro/service-instance"
CAPABILITY_LABEL = "nephos.pro/capability"
PROTOCOL_LABEL = "nephos.pro/protocol"
BINDING_ALIAS_LABEL = "nephos.pro/binding-alias"
ROUTE_LABEL = "nephos.pro/route"
# Set by every Service runtime provider on the resources it creates, carrying the
# runtime release name (`svc-<slug>`). Portal ingress resolves its backend Service
# through this rather than assuming the Service is named after the release.
RUNTIME_NAME_LABEL = "nephos.pro/runtime-name"


class KubernetesRuntimeSafetyError(RuntimeBlockedError):
    def __init__(self, message: str) -> None:
        super().__init__(reason="runtime_safety_blocked", message=message)


class KubernetesRuntime:
    def __init__(
        self,
        core_v1_api: client.CoreV1Api,
        apps_v1_api: client.AppsV1Api | None = None,
        networking_v1_api: client.NetworkingV1Api | None = None,
        ingress_class_name: str | None = None,
        namespace_delete_timeout_seconds: float = 60,
        namespace_delete_poll_interval_seconds: float = 1,
    ) -> None:
        self._core_v1_api = core_v1_api
        self._apps_v1_api = apps_v1_api
        self._networking_v1_api = networking_v1_api
        self._configured_ingress_class_name = ingress_class_name
        self._detected_ingress_class_name: str | None | _Unset = _UNSET
        self._namespace_delete_timeout_seconds = namespace_delete_timeout_seconds
        self._namespace_delete_poll_interval_seconds = (
            namespace_delete_poll_interval_seconds
        )

    def ensure_namespace(
        self,
        resource_type: ResourceType,
        slug: str,
    ) -> client.V1Namespace:
        name = namespace_name(resource_type, slug)
        existing = self._read_namespace(name)
        if existing is not None:
            if not _is_owned_namespace(existing, resource_type, slug):
                raise KubernetesRuntimeSafetyError(
                    f"refusing to use unowned namespace {name}"
                )
            if _is_terminating_namespace(existing):
                raise KubernetesRuntimeSafetyError(
                    f"refusing to use terminating namespace {name}"
                )
            return existing

        namespace = client.V1Namespace(
            metadata=client.V1ObjectMeta(
                name=name,
                labels=namespace_labels(resource_type, slug),
            )
        )
        return self._core_v1_api.create_namespace(body=namespace)

    def delete_namespace_if_owned(
        self,
        resource_type: ResourceType,
        slug: str,
    ) -> bool:
        name = namespace_name(resource_type, slug)
        namespace = self._read_namespace(name)
        if namespace is None:
            return False
        if not _is_owned_namespace(namespace, resource_type, slug):
            raise KubernetesRuntimeSafetyError(
                f"refusing to delete unowned namespace {name}"
            )
        self._core_v1_api.delete_namespace(name=name)
        self._wait_until_namespace_absent(name)
        return True

    def ensure_binding_secret(
        self,
        *,
        app_slug: str,
        service_slug: str,
        alias: str,
        capability: str,
        protocol: str | None = None,
        values: dict[str, str],
    ) -> client.V1Secret:
        namespace = namespace_name("app_instance", app_slug)
        self._assert_active_owned_namespace("app_instance", app_slug)
        name = binding_secret_name(alias)
        labels = binding_secret_labels(
            app_slug=app_slug,
            service_slug=service_slug,
            alias=alias,
            capability=capability,
            protocol=protocol,
        )
        secret = client.V1Secret(
            metadata=client.V1ObjectMeta(
                name=name,
                namespace=namespace,
                labels=labels,
            ),
            type="Opaque",
            string_data=values,
        )
        existing = self._read_secret(namespace=namespace, name=name)
        if existing is None:
            return self._core_v1_api.create_namespaced_secret(
                namespace=namespace,
                body=secret,
            )
        if not _is_owned_binding_secret(
            existing,
            app_slug=app_slug,
            service_slug=service_slug,
            alias=alias,
            capability=capability,
            protocol=protocol,
        ):
            raise KubernetesRuntimeSafetyError(
                f"refusing to replace unowned Secret {namespace}/{name}"
            )
        return self._core_v1_api.replace_namespaced_secret(
            name=name,
            namespace=namespace,
            body=secret,
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
        namespace = namespace_name("app_instance", app_slug)
        namespace_resource = self._read_namespace(namespace)
        if namespace_resource is None:
            return False
        _assert_active_namespace(
            namespace_resource,
            resource_type="app_instance",
            slug=app_slug,
            name=namespace,
        )
        name = binding_secret_name(alias)
        existing = self._read_secret(namespace=namespace, name=name)
        if existing is None:
            return False
        if not _is_owned_binding_secret(
            existing,
            app_slug=app_slug,
            service_slug=service_slug,
            alias=alias,
            capability=capability,
            protocol=protocol,
        ):
            raise KubernetesRuntimeSafetyError(
                f"refusing to delete unowned Secret {namespace}/{name}"
            )
        try:
            self._core_v1_api.delete_namespaced_secret(namespace=namespace, name=name)
        except ApiException as exc:
            if exc.status == 404:
                return False
            raise
        self._wait_until_secret_absent(namespace=namespace, name=name)
        return True

    def scale_workloads(
        self,
        resource_type: ResourceType,
        slug: str,
        replicas: int,
    ) -> None:
        if self._apps_v1_api is None:
            raise RuntimeError("AppsV1Api is required to scale workloads")
        namespace_name_ = namespace_name(resource_type, slug)
        namespace = self._read_namespace(namespace_name_)
        if namespace is None or not _is_owned_namespace(namespace, resource_type, slug):
            raise KubernetesRuntimeSafetyError(
                f"refusing to scale workloads in unowned namespace {namespace_name_}"
            )
        if _is_terminating_namespace(namespace):
            raise KubernetesRuntimeSafetyError(
                f"refusing to scale workloads in terminating namespace "
                f"{namespace_name_}"
            )
        body = {"spec": {"replicas": replicas}}
        deployments = self._apps_v1_api.list_namespaced_deployment(
            namespace=namespace_name_,
        )
        for deployment in deployments.items:
            if deployment.metadata is None or deployment.metadata.name is None:
                continue
            self._apps_v1_api.patch_namespaced_deployment_scale(
                name=deployment.metadata.name,
                namespace=namespace_name_,
                body=body,
            )
        stateful_sets = self._apps_v1_api.list_namespaced_stateful_set(
            namespace=namespace_name_,
        )
        for stateful_set in stateful_sets.items:
            if stateful_set.metadata is None or stateful_set.metadata.name is None:
                continue
            self._apps_v1_api.patch_namespaced_stateful_set_scale(
                name=stateful_set.metadata.name,
                namespace=namespace_name_,
                body=body,
            )

    def ensure_app_ingresses(
        self,
        *,
        app_slug: str,
        routes: list[dict[str, object]],
        domains: list[dict[str, object]],
    ) -> None:
        if self._networking_v1_api is None:
            raise RuntimeError("NetworkingV1Api is required to reconcile Ingress")
        namespace = self._assert_active_owned_namespace_for("app_instance", app_slug)
        ingress_class_name = self._resolve_ingress_class_name()
        for index, route in enumerate(routes):
            route_name = str(route["name"])
            ingress_name = ingress_name_for_route(route_name)
            ingress = _app_ingress(
                app_slug=app_slug,
                route=route,
                domains=domains,
                is_default_route=index == 0,
                ingress_class_name=ingress_class_name,
            )
            existing = self._read_ingress(namespace=namespace, name=ingress_name)
            if existing is None:
                self._networking_v1_api.create_namespaced_ingress(
                    namespace=namespace,
                    body=ingress,
                )
            elif _is_owned_app_ingress(
                existing,
                app_slug=app_slug,
                route_name=route_name,
            ):
                self._networking_v1_api.replace_namespaced_ingress(
                    namespace=namespace,
                    name=ingress_name,
                    body=ingress,
                )
            else:
                raise KubernetesRuntimeSafetyError(
                    f"refusing to replace unowned Ingress {namespace}/{ingress_name}"
                )

    def ensure_service_portals(
        self,
        *,
        service_slug: str,
        portals: list[dict[str, object]],
        domains: list[dict[str, object]],
    ) -> None:
        """Reconcile Ingress for a Service's portals (ADR 20260726).

        `domains` must already be filtered to portal-eligible root domains. An
        empty list deletes any previously generated portal Ingress, so revoking a
        domain's eligibility takes effect instead of leaving the surface exposed.
        """
        if self._networking_v1_api is None:
            raise RuntimeError("NetworkingV1Api is required to reconcile Ingress")
        namespace = self._assert_active_owned_namespace_for(
            "service_instance",
            service_slug,
        )
        ingress_class_name = self._resolve_ingress_class_name()
        # Prune first. Iterating only the declared portals leaves an Ingress
        # behind whenever a registry revision removes or renames one, and that
        # orphan keeps serving the admin backend. The desired set is the source of
        # truth for which owned portal Ingresses may exist, so anything owned and
        # not desired goes -- including when the desired set is empty.
        self._prune_service_portals(
            namespace=namespace,
            service_slug=service_slug,
            keep={str(portal["name"]) for portal in portals},
        )
        for index, portal in enumerate(portals):
            portal_name = str(portal["name"])
            ingress_name = ingress_name_for_route(portal_name)
            if not domains:
                self._delete_owned_ingress(
                    namespace=namespace,
                    ingress_name=ingress_name,
                    labels=service_portal_labels(
                        service_slug=service_slug,
                        portal_name=portal_name,
                    ),
                )
                continue
            ingress = _service_portal_ingress(
                service_slug=service_slug,
                portal=portal,
                domains=domains,
                is_first_portal=index == 0,
                ingress_class_name=ingress_class_name,
                backend_service_name=self._resolve_portal_backend_service(
                    namespace=namespace,
                    service_slug=service_slug,
                    portal_name=portal_name,
                    port=portal["target"]["port"],  # type: ignore[index]
                ),
            )
            existing = self._read_ingress(namespace=namespace, name=ingress_name)
            if existing is None:
                self._networking_v1_api.create_namespaced_ingress(
                    namespace=namespace,
                    body=ingress,
                )
            elif _has_labels(
                existing,
                service_portal_labels(
                    service_slug=service_slug,
                    portal_name=portal_name,
                ),
            ):
                self._networking_v1_api.replace_namespaced_ingress(
                    namespace=namespace,
                    name=ingress_name,
                    body=ingress,
                )
            else:
                raise KubernetesRuntimeSafetyError(
                    f"refusing to replace unowned Ingress {namespace}/{ingress_name}"
                )

    def delete_service_portals(self, *, service_slug: str) -> None:
        """Delete every owned portal Ingress for a Service.

        Takes no portal list on purpose. Teardown that trusted the current
        manifest missed an Ingress whose portal a registry revision had already
        removed, leaving an orphan in the preserved namespace after remove.
        """
        if self._networking_v1_api is None:
            raise RuntimeError("NetworkingV1Api is required to reconcile Ingress")
        namespace = namespace_name("service_instance", service_slug)
        namespace_resource = self._read_namespace(namespace)
        if namespace_resource is None:
            return
        if not _is_owned_namespace(
            namespace_resource,
            "service_instance",
            service_slug,
        ):
            raise KubernetesRuntimeSafetyError(
                f"refusing to delete Ingress in unowned namespace {namespace}"
            )
        if _is_terminating_namespace(namespace_resource):
            # Cascading namespace deletion removes these Ingresses anyway, and
            # raising here blocked the request before namespace and desired-state
            # cleanup could run, so a destroy could never complete.
            return
        self._prune_service_portals(
            namespace=namespace,
            service_slug=service_slug,
            keep=set(),
        )

    def _prune_service_portals(
        self,
        *,
        namespace: str,
        service_slug: str,
        keep: set[str],
    ) -> None:
        """Delete owned portal Ingresses whose portal is no longer declared.

        Enumerates by label rather than by the declared list, which is the only
        way to see an Ingress the manifest no longer mentions. `keep` empty is a
        legitimate instruction to remove them all.
        """
        assert self._networking_v1_api is not None
        selector = f"{MANAGED_BY_LABEL}=nephos,{SERVICE_INSTANCE_LABEL}={service_slug}"
        try:
            existing = self._networking_v1_api.list_namespaced_ingress(
                namespace=namespace,
                label_selector=selector,
            ).items
        except ApiException as exc:
            # Do not swallow this. With an empty desired set nothing else in the
            # reconcile can fail, so a transient list error would mark the request
            # succeeded while the obsolete admin Ingress kept serving.
            #
            # ! This surfaces the failure, it does not retry it: the reconciler has
            # ! no retry path, and both `blocked` and `failed` are terminal because
            # ! the worker only claims `pending`. An operator has to re-trigger.
            # ! Visibly blocked still beats silently succeeded.
            raise KubernetesRuntimeSafetyError(
                f"could not list portal Ingresses in {namespace}: {exc.reason}"
            ) from exc
        for ingress in existing:
            metadata = ingress.metadata
            if metadata is None or not metadata.name:
                continue
            portal_name = (metadata.labels or {}).get(ROUTE_LABEL)
            if portal_name is None or portal_name in keep:
                continue
            self._delete_owned_ingress(
                namespace=namespace,
                ingress_name=str(metadata.name),
                labels=service_portal_labels(
                    service_slug=service_slug,
                    portal_name=portal_name,
                ),
            )

    def _resolve_portal_backend_service(
        self,
        *,
        namespace: str,
        service_slug: str,
        portal_name: str,
        port: object,
    ) -> str:
        """The Kubernetes Service a portal Ingress should route to.

        Service providers do not name their Service after the runtime release:
        they append a component suffix (`svc-postgres-postgresql`,
        `svc-arcadedb-arcadedb`, `svc-zitadel-zitadel`). So unlike the App path —
        where the backend name *is* the release name by convention — a portal
        cannot derive it, and hardcoding `svc-<slug>` produces an Ingress that
        resolves to nothing and serves 404.

        Resolve instead by the labels every provider already sets, narrowed to the
        Service actually exposing the portal's target port. Ambiguity and absence
        both fail loudly rather than picking arbitrarily, and neither leaks a
        Kubernetes Service name into the Service manifest.
        """
        selector = f"{MANAGED_BY_LABEL}=nephos,{RUNTIME_NAME_LABEL}={namespace}"
        services = self._core_v1_api.list_namespaced_service(
            namespace=namespace,
            label_selector=selector,
        ).items
        matches = [
            service
            for service in services
            if _service_exposes_port(service, port)
        ]
        if not matches:
            raise KubernetesRuntimeSafetyError(
                f"refusing to reconcile Ingress for portal {portal_name!r} of "
                f"Service {service_slug}: no Nephos-owned Service in {namespace} "
                f"exposes port {port!r}"
            )
        if len(matches) > 1:
            names = ", ".join(
                sorted(
                    service.metadata.name
                    for service in matches
                    if service.metadata is not None
                )
            )
            raise KubernetesRuntimeSafetyError(
                f"refusing to reconcile Ingress for portal {portal_name!r} of "
                f"Service {service_slug}: port {port!r} is exposed by more than "
                f"one Nephos-owned Service in {namespace} ({names})"
            )
        metadata = matches[0].metadata
        if metadata is None or not metadata.name:
            raise KubernetesRuntimeSafetyError(
                f"refusing to reconcile Ingress for portal {portal_name!r} of "
                f"Service {service_slug}: backend Service has no name"
            )
        return str(metadata.name)

    def _assert_active_owned_namespace_for(
        self,
        resource_type: ResourceType,
        slug: str,
    ) -> str:
        namespace = namespace_name(resource_type, slug)
        namespace_resource = self._read_namespace(namespace)
        if namespace_resource is None or not _is_owned_namespace(
            namespace_resource,
            resource_type,
            slug,
        ):
            raise KubernetesRuntimeSafetyError(
                f"refusing to reconcile Ingress in unowned namespace {namespace}"
            )
        if _is_terminating_namespace(namespace_resource):
            raise KubernetesRuntimeSafetyError(
                f"refusing to reconcile Ingress in terminating namespace {namespace}"
            )
        return namespace

    def _delete_owned_ingress(
        self,
        *,
        namespace: str,
        ingress_name: str,
        labels: dict[str, str],
    ) -> None:
        assert self._networking_v1_api is not None
        existing = self._read_ingress(namespace=namespace, name=ingress_name)
        if existing is None:
            return
        if not _has_labels(existing, labels):
            raise KubernetesRuntimeSafetyError(
                f"refusing to delete unowned Ingress {namespace}/{ingress_name}"
            )
        self._networking_v1_api.delete_namespaced_ingress(
            namespace=namespace,
            name=ingress_name,
        )
        self._wait_until_ingress_absent(namespace=namespace, name=ingress_name)

    def delete_app_ingresses(
        self,
        *,
        app_slug: str,
        routes: list[dict[str, object]],
    ) -> None:
        if self._networking_v1_api is None:
            raise RuntimeError("NetworkingV1Api is required to reconcile Ingress")
        namespace = namespace_name("app_instance", app_slug)
        namespace_resource = self._read_namespace(namespace)
        if namespace_resource is None:
            return
        if not _is_owned_namespace(namespace_resource, "app_instance", app_slug):
            raise KubernetesRuntimeSafetyError(
                f"refusing to delete Ingress in unowned namespace {namespace}"
            )
        if _is_terminating_namespace(namespace_resource):
            raise KubernetesRuntimeSafetyError(
                f"refusing to delete Ingress in terminating namespace {namespace}"
            )
        for route in routes:
            route_name = str(route["name"])
            self._delete_owned_ingress(
                namespace=namespace,
                ingress_name=ingress_name_for_route(route_name),
                labels=app_ingress_labels(app_slug=app_slug, route_name=route_name),
            )

    def _read_namespace(self, name: str) -> client.V1Namespace | None:
        try:
            return self._core_v1_api.read_namespace(name=name)
        except ApiException as exc:
            if exc.status == 404:
                return None
            raise

    def _assert_active_owned_namespace(
        self,
        resource_type: ResourceType,
        slug: str,
    ) -> None:
        name = namespace_name(resource_type, slug)
        _assert_active_namespace(
            self._read_namespace(name),
            resource_type=resource_type,
            slug=slug,
            name=name,
        )

    def _wait_until_namespace_absent(self, name: str) -> None:
        deadline = time.monotonic() + self._namespace_delete_timeout_seconds
        while True:
            if self._read_namespace(name) is None:
                return
            if time.monotonic() >= deadline:
                raise TimeoutError(f"timed out waiting for namespace {name} deletion")
            if self._namespace_delete_poll_interval_seconds > 0:
                time.sleep(self._namespace_delete_poll_interval_seconds)

    def _wait_until_ingress_absent(self, *, namespace: str, name: str) -> None:
        deadline = time.monotonic() + self._namespace_delete_timeout_seconds
        while True:
            if self._read_ingress(namespace=namespace, name=name) is None:
                return
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"timed out waiting for Ingress {namespace}/{name} deletion"
                )
            if self._namespace_delete_poll_interval_seconds > 0:
                time.sleep(self._namespace_delete_poll_interval_seconds)

    def _wait_until_secret_absent(self, *, namespace: str, name: str) -> None:
        deadline = time.monotonic() + self._namespace_delete_timeout_seconds
        while True:
            if self._read_secret(namespace=namespace, name=name) is None:
                return
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"timed out waiting for Secret {namespace}/{name} deletion"
                )
            if self._namespace_delete_poll_interval_seconds > 0:
                time.sleep(self._namespace_delete_poll_interval_seconds)

    def _read_secret(self, *, namespace: str, name: str) -> client.V1Secret | None:
        try:
            return self._core_v1_api.read_namespaced_secret(
                namespace=namespace,
                name=name,
            )
        except ApiException as exc:
            if exc.status == 404:
                return None
            raise

    def _read_ingress(self, *, namespace: str, name: str) -> client.V1Ingress | None:
        assert self._networking_v1_api is not None
        try:
            return self._networking_v1_api.read_namespaced_ingress(
                namespace=namespace,
                name=name,
            )
        except ApiException as exc:
            if exc.status == 404:
                return None
            raise

    def _resolve_ingress_class_name(self) -> str | None:
        if self._configured_ingress_class_name:
            return self._configured_ingress_class_name
        if self._detected_ingress_class_name is not _UNSET:
            return self._detected_ingress_class_name
        assert self._networking_v1_api is not None
        self._detected_ingress_class_name = _detect_ingress_class_name(
            self._networking_v1_api
        )
        return self._detected_ingress_class_name


class _Unset:
    pass


_UNSET = _Unset()


class KubernetesSecretBindingValueSource:
    def __init__(self, core_v1_api: client.CoreV1Api) -> None:
        self._core_v1_api = core_v1_api

    def get_binding_values(
        self,
        *,
        app_slug: str,
        service_slug: str,
        alias: str,
        capability: str,
        protocol: str | None = None,
    ) -> dict[str, str] | None:
        namespace = namespace_name("app_instance", app_slug)
        _assert_active_namespace(
            _read_namespace(self._core_v1_api, namespace),
            resource_type="app_instance",
            slug=app_slug,
            name=namespace,
        )
        name = binding_secret_name(alias)
        try:
            secret = self._core_v1_api.read_namespaced_secret(
                namespace=namespace,
                name=name,
            )
        except ApiException as exc:
            if exc.status == 404:
                return None
            raise
        if not _is_owned_binding_secret(
            secret,
            app_slug=app_slug,
            service_slug=service_slug,
            alias=alias,
            capability=capability,
            protocol=protocol,
        ):
            raise KubernetesRuntimeSafetyError(
                f"refusing to read unowned Secret {namespace}/{name}"
            )
        return {
            key: base64.b64decode(value).decode()
            for key, value in (secret.data or {}).items()
        }


class KubernetesSecretBaoTokenProvider:
    """Read OpenBao's access token from the Nephos-managed init Secret so the
    bao:// resolver authenticates with the live init token rather than a static
    dev token. Returns None (not an error) when the Secret is absent, so a
    ChainedBaoTokenProvider can fall back."""

    def __init__(
        self,
        core_v1_api: client.CoreV1Api,
        *,
        namespace: str,
        secret_name: str = "openbao-init",
        token_key: str = "root-token",
    ) -> None:
        self._core_v1_api = core_v1_api
        self._namespace = namespace
        self._secret_name = secret_name
        self._token_key = token_key

    def get_token(self) -> str | None:
        try:
            secret = self._core_v1_api.read_namespaced_secret(
                name=self._secret_name, namespace=self._namespace
            )
        except ApiException as exc:
            if exc.status == 404:
                return None
            raise
        labels = (secret.metadata.labels or {}) if secret.metadata else {}
        if labels.get(MANAGED_BY_LABEL) != "nephos":
            raise KubernetesRuntimeSafetyError(
                f"refusing to read unowned Secret {self._namespace}/{self._secret_name}"
            )
        raw = (secret.data or {}).get(self._token_key)
        if not raw:
            return None
        return base64.b64decode(raw).decode()


def namespace_name(resource_type: ResourceType, slug: str) -> str:
    validate_machine_identifier(slug)
    prefix = "app" if resource_type == "app_instance" else "svc"
    name = f"{prefix}-{slug}"
    if len(name) > 63:
        raise ValueError(f"{name} exceeds Kubernetes namespace length")
    return name


def namespace_labels(resource_type: ResourceType, slug: str) -> dict[str, str]:
    validate_machine_identifier(slug)
    relationship_label = (
        APP_INSTANCE_LABEL
        if resource_type == "app_instance"
        else SERVICE_INSTANCE_LABEL
    )
    return {
        MANAGED_BY_LABEL: "nephos",
        relationship_label: slug,
    }


def binding_secret_name(alias: str) -> str:
    validate_machine_identifier(alias)
    name = f"nephos-bind-{alias}"
    if len(name) > 63:
        raise ValueError(f"{name} exceeds Kubernetes Secret name length")
    return name


def ingress_name_for_route(route_name: str) -> str:
    validate_machine_identifier(route_name)
    name = f"nephos-route-{route_name}"
    if len(name) > 63:
        raise ValueError(f"{name} exceeds Kubernetes Ingress name length")
    return name


def binding_secret_labels(
    *,
    app_slug: str,
    service_slug: str,
    alias: str,
    capability: str,
    protocol: str | None = None,
) -> dict[str, str]:
    validate_machine_identifier(app_slug)
    validate_machine_identifier(service_slug)
    validate_machine_identifier(alias)
    validate_machine_identifier(capability)
    labels = {
        MANAGED_BY_LABEL: "nephos",
        APP_INSTANCE_LABEL: app_slug,
        SERVICE_INSTANCE_LABEL: service_slug,
        CAPABILITY_LABEL: capability,
        BINDING_ALIAS_LABEL: alias,
    }
    if protocol is not None:
        validate_machine_identifier(protocol)
        labels[PROTOCOL_LABEL] = protocol
    return labels


def app_ingress_labels(*, app_slug: str, route_name: str) -> dict[str, str]:
    validate_machine_identifier(app_slug)
    validate_machine_identifier(route_name)
    return {
        MANAGED_BY_LABEL: "nephos",
        APP_INSTANCE_LABEL: app_slug,
        ROUTE_LABEL: route_name,
    }


def service_portal_labels(*, service_slug: str, portal_name: str) -> dict[str, str]:
    validate_machine_identifier(service_slug)
    validate_machine_identifier(portal_name)
    return {
        MANAGED_BY_LABEL: "nephos",
        SERVICE_INSTANCE_LABEL: service_slug,
        ROUTE_LABEL: portal_name,
    }


def _is_owned_namespace(
    namespace: client.V1Namespace,
    resource_type: ResourceType,
    slug: str,
) -> bool:
    if namespace.metadata is None:
        return False
    labels = namespace.metadata.labels or {}
    expected_labels = namespace_labels(resource_type, slug)
    return all(labels.get(key) == value for key, value in expected_labels.items())


def _read_namespace(
    core_v1_api: client.CoreV1Api,
    name: str,
) -> client.V1Namespace | None:
    try:
        return core_v1_api.read_namespace(name=name)
    except ApiException as exc:
        if exc.status == 404:
            return None
        raise


def _assert_active_namespace(
    namespace: client.V1Namespace | None,
    *,
    resource_type: ResourceType,
    slug: str,
    name: str,
) -> None:
    if namespace is None or not _is_owned_namespace(namespace, resource_type, slug):
        raise KubernetesRuntimeSafetyError(f"refusing to use unowned namespace {name}")
    if _is_terminating_namespace(namespace):
        raise KubernetesRuntimeSafetyError(
            f"refusing to use terminating namespace {name}"
        )


def _is_terminating_namespace(namespace: client.V1Namespace) -> bool:
    if namespace.metadata is None:
        return False
    return namespace.metadata.deletion_timestamp is not None


def _is_owned_binding_secret(
    secret: client.V1Secret,
    *,
    app_slug: str,
    service_slug: str,
    alias: str,
    capability: str,
    protocol: str | None = None,
) -> bool:
    if secret.metadata is None:
        return False
    labels = secret.metadata.labels or {}
    expected_labels = binding_secret_labels(
        app_slug=app_slug,
        service_slug=service_slug,
        alias=alias,
        capability=capability,
        protocol=protocol,
    )
    return all(labels.get(key) == value for key, value in expected_labels.items())


def _is_owned_app_ingress(
    ingress: client.V1Ingress,
    *,
    app_slug: str,
    route_name: str,
) -> bool:
    return _has_labels(
        ingress,
        app_ingress_labels(app_slug=app_slug, route_name=route_name),
    )


def _has_labels(ingress: client.V1Ingress, expected_labels: dict[str, str]) -> bool:
    if ingress.metadata is None:
        return False
    labels = ingress.metadata.labels or {}
    return all(labels.get(key) == value for key, value in expected_labels.items())


def _service_exposes_port(service: client.V1Service, port: object) -> bool:
    ports = (service.spec.ports or []) if service.spec is not None else []
    if isinstance(port, int):
        return any(item.port == port for item in ports)
    return any(item.name == str(port) for item in ports)


def _service_portal_ingress(
    *,
    service_slug: str,
    portal: dict[str, object],
    domains: list[dict[str, object]],
    is_first_portal: bool,
    ingress_class_name: str | None,
    backend_service_name: str,
) -> client.V1Ingress:
    portal_name = str(portal["name"])
    return client.V1Ingress(
        metadata=client.V1ObjectMeta(
            name=ingress_name_for_route(portal_name),
            namespace=namespace_name("service_instance", service_slug),
            labels=service_portal_labels(
                service_slug=service_slug,
                portal_name=portal_name,
            ),
        ),
        spec=client.V1IngressSpec(
            ingress_class_name=ingress_class_name,
            rules=[
                client.V1IngressRule(
                    host=service_portal_host(
                        service_slug=service_slug,
                        portal_name=portal_name,
                        domain=str(domain["domain"]),
                        is_first_portal=is_first_portal,
                    ),
                    http=client.V1HTTPIngressRuleValue(
                        paths=[
                            client.V1HTTPIngressPath(
                                path="/",
                                path_type="Prefix",
                                backend=client.V1IngressBackend(
                                    service=client.V1IngressServiceBackend(
                                        name=backend_service_name,
                                        port=_service_backend_port(
                                            portal["target"]["port"]  # type: ignore[index]
                                        ),
                                    )
                                ),
                            )
                        ]
                    ),
                )
                for domain in domains
            ],
        ),
    )


def _app_ingress(
    *,
    app_slug: str,
    route: dict[str, object],
    domains: list[dict[str, object]],
    is_default_route: bool,
    ingress_class_name: str | None,
) -> client.V1Ingress:
    route_name = str(route["name"])
    return client.V1Ingress(
        metadata=client.V1ObjectMeta(
            name=ingress_name_for_route(route_name),
            namespace=namespace_name("app_instance", app_slug),
            labels=app_ingress_labels(app_slug=app_slug, route_name=route_name),
        ),
        spec=client.V1IngressSpec(
            ingress_class_name=ingress_class_name,
            rules=[
                client.V1IngressRule(
                    host=_route_host(
                        app_slug=app_slug,
                        route_name=route_name,
                        domain=str(domain["domain"]),
                        is_default_route=is_default_route,
                    ),
                    http=client.V1HTTPIngressRuleValue(
                        paths=[
                            client.V1HTTPIngressPath(
                                path="/",
                                path_type="Prefix",
                                backend=client.V1IngressBackend(
                                    service=client.V1IngressServiceBackend(
                                        name=namespace_name("app_instance", app_slug),
                                        port=_service_backend_port(
                                            route["target"]["port"]  # type: ignore[index]
                                        ),
                                    )
                                ),
                            )
                        ]
                    ),
                )
                for domain in domains
            ],
        ),
    )


def _route_host(
    *,
    app_slug: str,
    route_name: str,
    domain: str,
    is_default_route: bool,
) -> str:
    prefix = app_slug if is_default_route else f"{route_name}.{app_slug}"
    return f"{prefix}.{domain}"


def _service_backend_port(port: object) -> client.V1ServiceBackendPort:
    if isinstance(port, int):
        return client.V1ServiceBackendPort(number=port)
    return client.V1ServiceBackendPort(name=str(port))


def _detect_ingress_class_name(networking_v1_api: client.NetworkingV1Api) -> str | None:
    try:
        ingress_classes = networking_v1_api.list_ingress_class().items
    except ApiException:
        return None

    default_classes = [
        ingress_class
        for ingress_class in ingress_classes
        if _is_default_ingress_class(ingress_class)
    ]
    if len(default_classes) == 1:
        metadata = default_classes[0].metadata
        return metadata.name if metadata is not None else None
    if len(ingress_classes) == 1:
        metadata = ingress_classes[0].metadata
        return metadata.name if metadata is not None else None
    return None


def _is_default_ingress_class(ingress_class: client.V1IngressClass) -> bool:
    if ingress_class.metadata is None:
        return False
    annotations = ingress_class.metadata.annotations or {}
    return annotations.get("ingressclass.kubernetes.io/is-default-class") == "true"
