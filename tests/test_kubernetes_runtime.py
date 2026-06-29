import base64

import pytest
from kubernetes.client import (
    V1Deployment,
    V1Ingress,
    V1IngressClass,
    V1Namespace,
    V1ObjectMeta,
    V1Secret,
    V1StatefulSet,
)
from kubernetes.client.rest import ApiException

from nephos_api.kubernetes_runtime import (
    KubernetesRuntime,
    KubernetesRuntimeSafetyError,
    KubernetesSecretBindingValueSource,
    binding_secret_name,
    namespace_labels,
    namespace_name,
)


class FakeCoreV1Api:
    def __init__(self) -> None:
        self.namespaces: dict[str, V1Namespace] = {}
        self.secrets: dict[tuple[str, str], V1Secret] = {}
        self.created: list[V1Namespace] = []
        self.deleted: list[str] = []
        self.created_secrets: list[V1Secret] = []
        self.replaced_secrets: list[V1Secret] = []
        self.deleted_secrets: list[tuple[str, str]] = []

    def create_namespace(self, body: V1Namespace) -> V1Namespace:
        assert body.metadata is not None
        self.namespaces[body.metadata.name] = body
        self.created.append(body)
        return body

    def read_namespace(self, name: str) -> V1Namespace:
        if name not in self.namespaces:
            raise ApiException(status=404, reason="Not Found")
        return self.namespaces[name]

    def delete_namespace(self, name: str) -> None:
        if name not in self.namespaces:
            raise ApiException(status=404, reason="Not Found")
        self.deleted.append(name)
        del self.namespaces[name]

    def create_namespaced_secret(self, namespace: str, body: V1Secret) -> V1Secret:
        assert body.metadata is not None
        key = (namespace, body.metadata.name)
        self.secrets[key] = body
        self.created_secrets.append(body)
        return body

    def read_namespaced_secret(self, name: str, namespace: str) -> V1Secret:
        key = (namespace, name)
        if key not in self.secrets:
            raise ApiException(status=404, reason="Not Found")
        return self.secrets[key]

    def replace_namespaced_secret(
        self,
        name: str,
        namespace: str,
        body: V1Secret,
    ) -> V1Secret:
        key = (namespace, name)
        if key not in self.secrets:
            raise ApiException(status=404, reason="Not Found")
        self.secrets[key] = body
        self.replaced_secrets.append(body)
        return body

    def delete_namespaced_secret(self, namespace: str, name: str) -> None:
        key = (namespace, name)
        if key not in self.secrets:
            raise ApiException(status=404, reason="Not Found")
        self.deleted_secrets.append(key)
        del self.secrets[key]


class SlowDeletingCoreV1Api(FakeCoreV1Api):
    def __init__(self, reads_before_gone: int) -> None:
        super().__init__()
        self._reads_before_gone = reads_before_gone
        self._deleting_namespaces: set[str] = set()
        self.post_delete_reads: list[str] = []

    def read_namespace(self, name: str) -> V1Namespace:
        if name in self._deleting_namespaces:
            self.post_delete_reads.append(name)
            if len(self.post_delete_reads) > self._reads_before_gone:
                del self.namespaces[name]
                self._deleting_namespaces.remove(name)
                raise ApiException(status=404, reason="Not Found")
        return super().read_namespace(name)

    def delete_namespace(self, name: str) -> None:
        if name not in self.namespaces:
            raise ApiException(status=404, reason="Not Found")
        self.deleted.append(name)
        self._deleting_namespaces.add(name)


class FakeNetworkingV1Api:
    def __init__(self) -> None:
        self.ingresses: dict[tuple[str, str], V1Ingress] = {}
        self.ingress_classes: list[V1IngressClass] = []
        self.created_ingresses: list[V1Ingress] = []
        self.replaced_ingresses: list[V1Ingress] = []
        self.deleted_ingresses: list[tuple[str, str]] = []

    def list_ingress_class(self):
        return type("Result", (), {"items": self.ingress_classes})()

    def read_namespaced_ingress(self, *, namespace: str, name: str) -> V1Ingress:
        ingress = self.ingresses.get((namespace, name))
        if ingress is None:
            raise ApiException(status=404)
        return ingress

    def create_namespaced_ingress(
        self,
        *,
        namespace: str,
        body: V1Ingress,
    ) -> V1Ingress:
        assert body.metadata is not None
        self.ingresses[(namespace, body.metadata.name)] = body
        self.created_ingresses.append(body)
        return body

    def replace_namespaced_ingress(
        self,
        *,
        namespace: str,
        name: str,
        body: V1Ingress,
    ) -> V1Ingress:
        self.ingresses[(namespace, name)] = body
        self.replaced_ingresses.append(body)
        return body

    def delete_namespaced_ingress(self, *, namespace: str, name: str) -> None:
        if (namespace, name) not in self.ingresses:
            raise ApiException(status=404)
        self.deleted_ingresses.append((namespace, name))
        del self.ingresses[(namespace, name)]


class SlowDeletingNetworkingV1Api(FakeNetworkingV1Api):
    def __init__(self, reads_before_gone: int) -> None:
        super().__init__()
        self._reads_before_gone = reads_before_gone
        self._deleting_ingresses: set[tuple[str, str]] = set()
        self.post_delete_reads: list[tuple[str, str]] = []

    def read_namespaced_ingress(self, *, namespace: str, name: str) -> V1Ingress:
        key = (namespace, name)
        if key in self._deleting_ingresses:
            self.post_delete_reads.append(key)
            if len(self.post_delete_reads) > self._reads_before_gone:
                del self.ingresses[key]
                self._deleting_ingresses.remove(key)
                raise ApiException(status=404)
        return super().read_namespaced_ingress(namespace=namespace, name=name)

    def delete_namespaced_ingress(self, *, namespace: str, name: str) -> None:
        key = (namespace, name)
        if key not in self.ingresses:
            raise ApiException(status=404)
        self.deleted_ingresses.append(key)
        self._deleting_ingresses.add(key)


class FakeAppsV1Api:
    def __init__(self) -> None:
        self.deployments: dict[str, list[V1Deployment]] = {}
        self.stateful_sets: dict[str, list[V1StatefulSet]] = {}
        self.deployment_scales: list[tuple[str, str, dict[str, object]]] = []
        self.stateful_set_scales: list[tuple[str, str, dict[str, object]]] = []

    def list_namespaced_deployment(self, namespace: str):
        return type("Result", (), {"items": self.deployments.get(namespace, [])})()

    def list_namespaced_stateful_set(self, namespace: str):
        return type("Result", (), {"items": self.stateful_sets.get(namespace, [])})()

    def patch_namespaced_deployment_scale(
        self,
        *,
        name: str,
        namespace: str,
        body: dict[str, object],
    ) -> None:
        self.deployment_scales.append((namespace, name, body))

    def patch_namespaced_stateful_set_scale(
        self,
        *,
        name: str,
        namespace: str,
        body: dict[str, object],
    ) -> None:
        self.stateful_set_scales.append((namespace, name, body))


def test_namespace_name_uses_accepted_resource_prefixes() -> None:
    assert namespace_name("app_instance", "paperless") == "app-paperless"
    assert namespace_name("service_instance", "postgres") == "svc-postgres"


def test_namespace_name_rejects_values_that_exceed_kubernetes_limit() -> None:
    with pytest.raises(ValueError, match="exceeds Kubernetes namespace length"):
        namespace_name("app_instance", "a" * 61)


def test_binding_secret_name_uses_alias_and_enforces_kubernetes_limit() -> None:
    assert binding_secret_name("database") == "nephos-bind-database"
    with pytest.raises(ValueError, match="exceeds Kubernetes Secret name length"):
        binding_secret_name("a" * 53)


def test_namespace_labels_identify_nephos_owned_app_and_service_namespaces() -> None:
    assert namespace_labels("app_instance", "paperless") == {
        "app.kubernetes.io/managed-by": "nephos",
        "nephos.pro/app-instance": "paperless",
    }
    assert namespace_labels("service_instance", "postgres") == {
        "app.kubernetes.io/managed-by": "nephos",
        "nephos.pro/service-instance": "postgres",
    }


def test_runtime_creates_namespace_with_nephos_labels() -> None:
    api = FakeCoreV1Api()
    runtime = KubernetesRuntime(api)

    namespace = runtime.ensure_namespace("app_instance", "paperless")

    assert namespace.metadata is not None
    assert namespace.metadata.name == "app-paperless"
    assert namespace.metadata.labels == {
        "app.kubernetes.io/managed-by": "nephos",
        "nephos.pro/app-instance": "paperless",
    }
    assert api.created == [namespace]


def test_runtime_reuses_existing_namespace() -> None:
    api = FakeCoreV1Api()
    runtime = KubernetesRuntime(api)
    created = runtime.ensure_namespace("service_instance", "postgres")

    reused = runtime.ensure_namespace("service_instance", "postgres")

    assert reused == created
    assert len(api.created) == 1


def test_runtime_refuses_to_reuse_unowned_existing_namespace() -> None:
    api = FakeCoreV1Api()
    runtime = KubernetesRuntime(api)
    namespace = runtime.ensure_namespace("service_instance", "postgres")
    assert namespace.metadata is not None
    namespace.metadata.labels = {}

    with pytest.raises(KubernetesRuntimeSafetyError):
        runtime.ensure_namespace("service_instance", "postgres")


def test_runtime_refuses_to_reuse_terminating_namespace() -> None:
    api = FakeCoreV1Api()
    runtime = KubernetesRuntime(api)
    namespace = runtime.ensure_namespace("service_instance", "postgres")
    assert namespace.metadata is not None
    namespace.metadata.deletion_timestamp = "2026-05-23T00:00:00Z"

    with pytest.raises(KubernetesRuntimeSafetyError, match="terminating namespace"):
        runtime.ensure_namespace("service_instance", "postgres")


def test_runtime_refuses_to_create_binding_secret_in_unowned_namespace() -> None:
    api = FakeCoreV1Api()
    runtime = KubernetesRuntime(api)
    namespace = runtime.ensure_namespace("app_instance", "paperless")
    assert namespace.metadata is not None
    namespace.metadata.labels = {}

    with pytest.raises(KubernetesRuntimeSafetyError, match="unowned namespace"):
        runtime.ensure_binding_secret(
            app_slug="paperless",
            service_slug="postgres",
            alias="database",
            capability="postgres",
            values={"uri": "postgresql://example"},
        )


def test_runtime_refuses_to_create_binding_secret_in_terminating_namespace() -> None:
    api = FakeCoreV1Api()
    runtime = KubernetesRuntime(api)
    namespace = runtime.ensure_namespace("app_instance", "paperless")
    assert namespace.metadata is not None
    namespace.metadata.deletion_timestamp = "2026-05-23T00:00:00Z"

    with pytest.raises(KubernetesRuntimeSafetyError, match="terminating namespace"):
        runtime.ensure_binding_secret(
            app_slug="paperless",
            service_slug="postgres",
            alias="database",
            capability="postgres",
            values={"uri": "postgresql://example"},
        )


def test_runtime_deletes_only_nephos_owned_namespace() -> None:
    api = FakeCoreV1Api()
    runtime = KubernetesRuntime(api)
    runtime.ensure_namespace("app_instance", "paperless")

    assert runtime.delete_namespace_if_owned("app_instance", "paperless") is True
    assert api.deleted == ["app-paperless"]
    assert runtime.delete_namespace_if_owned("app_instance", "paperless") is False


def test_runtime_waits_until_deleted_namespace_is_absent() -> None:
    api = SlowDeletingCoreV1Api(reads_before_gone=2)
    runtime = KubernetesRuntime(
        api,
        namespace_delete_timeout_seconds=1,
        namespace_delete_poll_interval_seconds=0,
    )
    runtime.ensure_namespace("app_instance", "paperless")

    assert runtime.delete_namespace_if_owned("app_instance", "paperless") is True

    assert api.deleted == ["app-paperless"]
    assert api.post_delete_reads == [
        "app-paperless",
        "app-paperless",
        "app-paperless",
    ]
    assert "app-paperless" not in api.namespaces


def test_runtime_refuses_to_delete_unowned_namespace() -> None:
    api = FakeCoreV1Api()
    runtime = KubernetesRuntime(api)
    namespace = runtime.ensure_namespace("app_instance", "paperless")
    assert namespace.metadata is not None
    namespace.metadata.labels = {}

    with pytest.raises(KubernetesRuntimeSafetyError):
        runtime.delete_namespace_if_owned("app_instance", "paperless")


def test_runtime_creates_binding_secret_with_redacted_relationship_labels() -> None:
    api = FakeCoreV1Api()
    runtime = KubernetesRuntime(api)
    runtime.ensure_namespace("app_instance", "paperless")

    secret = runtime.ensure_binding_secret(
        app_slug="paperless",
        service_slug="postgres",
        alias="database",
        capability="sql",
        protocol="postgres",
        values={
            "host": "postgres.svc",
            "port": "5432",
            "database": "paperless",
            "username": "paperless",
            "password": "secret",
            "uri": "postgres://paperless:secret@postgres.svc:5432/paperless",
        },
    )

    assert secret.metadata is not None
    assert secret.metadata.name == "nephos-bind-database"
    assert secret.metadata.labels == {
        "app.kubernetes.io/managed-by": "nephos",
        "nephos.pro/app-instance": "paperless",
        "nephos.pro/service-instance": "postgres",
        "nephos.pro/capability": "sql",
        "nephos.pro/protocol": "postgres",
        "nephos.pro/binding-alias": "database",
    }
    assert secret.metadata.annotations is None
    assert secret.string_data == {
        "host": "postgres.svc",
        "port": "5432",
        "database": "paperless",
        "username": "paperless",
        "password": "secret",
        "uri": "postgres://paperless:secret@postgres.svc:5432/paperless",
    }
    assert api.created_secrets == [secret]


def test_runtime_keeps_binding_secret_name_alias_based_with_protocol() -> None:
    api = FakeCoreV1Api()
    runtime = KubernetesRuntime(api)
    runtime.ensure_namespace("app_instance", "paperless")

    secret = runtime.ensure_binding_secret(
        app_slug="paperless",
        service_slug="arcadedb",
        alias="graph",
        capability="opencypher",
        protocol="bolt",
        values={"uri": "bolt://arcadedb"},
    )

    assert secret.metadata is not None
    assert secret.metadata.name == "nephos-bind-graph"
    assert secret.metadata.labels == {
        "app.kubernetes.io/managed-by": "nephos",
        "nephos.pro/app-instance": "paperless",
        "nephos.pro/service-instance": "arcadedb",
        "nephos.pro/capability": "opencypher",
        "nephos.pro/protocol": "bolt",
        "nephos.pro/binding-alias": "graph",
    }


def test_runtime_replaces_owned_binding_secret() -> None:
    api = FakeCoreV1Api()
    runtime = KubernetesRuntime(api)
    runtime.ensure_namespace("app_instance", "paperless")
    runtime.ensure_binding_secret(
        app_slug="paperless",
        service_slug="postgres",
        alias="database",
        capability="postgres",
        values={"uri": "old"},
    )

    secret = runtime.ensure_binding_secret(
        app_slug="paperless",
        service_slug="postgres",
        alias="database",
        capability="postgres",
        values={"uri": "new"},
    )

    assert secret.string_data == {"uri": "new"}
    assert api.replaced_secrets == [secret]


def test_runtime_refuses_to_replace_unowned_binding_secret() -> None:
    api = FakeCoreV1Api()
    runtime = KubernetesRuntime(api)
    namespace = namespace_name("app_instance", "paperless")
    secret_name = binding_secret_name("database")
    api.secrets[(namespace, secret_name)] = V1Secret()

    with pytest.raises(KubernetesRuntimeSafetyError):
        runtime.ensure_binding_secret(
            app_slug="paperless",
            service_slug="postgres",
            alias="database",
            capability="postgres",
            values={"uri": "new"},
        )


def test_runtime_deletes_owned_binding_secret() -> None:
    api = FakeCoreV1Api()
    runtime = KubernetesRuntime(api)
    runtime.ensure_namespace("app_instance", "paperless")
    runtime.ensure_binding_secret(
        app_slug="paperless",
        service_slug="postgres",
        alias="database",
        capability="postgres",
        values={"uri": "postgresql://example"},
    )

    assert runtime.delete_binding_secret_if_owned(
        app_slug="paperless",
        service_slug="postgres",
        alias="database",
        capability="postgres",
    ) is True

    assert api.deleted_secrets == [("app-paperless", "nephos-bind-database")]
    assert ("app-paperless", "nephos-bind-database") not in api.secrets


def test_runtime_delete_binding_secret_returns_false_when_secret_is_absent() -> None:
    api = FakeCoreV1Api()
    runtime = KubernetesRuntime(api)
    runtime.ensure_namespace("app_instance", "paperless")

    assert runtime.delete_binding_secret_if_owned(
        app_slug="paperless",
        service_slug="postgres",
        alias="database",
        capability="postgres",
    ) is False


def test_runtime_refuses_to_delete_unowned_binding_secret() -> None:
    api = FakeCoreV1Api()
    runtime = KubernetesRuntime(api)
    runtime.ensure_namespace("app_instance", "paperless")
    namespace = namespace_name("app_instance", "paperless")
    secret_name = binding_secret_name("database")
    api.secrets[(namespace, secret_name)] = V1Secret(
        metadata=V1ObjectMeta(name=secret_name, namespace=namespace, labels={})
    )

    with pytest.raises(KubernetesRuntimeSafetyError, match="unowned Secret"):
        runtime.delete_binding_secret_if_owned(
            app_slug="paperless",
            service_slug="postgres",
            alias="database",
            capability="postgres",
        )


def test_runtime_scales_deployments_and_statefulsets_in_owned_namespace() -> None:
    core = FakeCoreV1Api()
    apps = FakeAppsV1Api()
    runtime = KubernetesRuntime(core, apps_v1_api=apps)
    runtime.ensure_namespace("app_instance", "paperless")
    apps.deployments["app-paperless"] = [
        V1Deployment(metadata=V1ObjectMeta(name="paperless-web"))
    ]
    apps.stateful_sets["app-paperless"] = [
        V1StatefulSet(metadata=V1ObjectMeta(name="paperless-worker"))
    ]

    runtime.scale_workloads("app_instance", "paperless", 0)

    assert apps.deployment_scales == [
        ("app-paperless", "paperless-web", {"spec": {"replicas": 0}})
    ]
    assert apps.stateful_set_scales == [
        ("app-paperless", "paperless-worker", {"spec": {"replicas": 0}})
    ]


def test_runtime_refuses_to_scale_workloads_in_unowned_namespace() -> None:
    core = FakeCoreV1Api()
    apps = FakeAppsV1Api()
    runtime = KubernetesRuntime(core, apps_v1_api=apps)
    namespace = runtime.ensure_namespace("app_instance", "paperless")
    assert namespace.metadata is not None
    namespace.metadata.labels = {}

    with pytest.raises(KubernetesRuntimeSafetyError):
        runtime.scale_workloads("app_instance", "paperless", 0)


def test_runtime_refuses_to_scale_workloads_in_terminating_namespace() -> None:
    core = FakeCoreV1Api()
    apps = FakeAppsV1Api()
    runtime = KubernetesRuntime(core, apps_v1_api=apps)
    namespace = runtime.ensure_namespace("app_instance", "paperless")
    assert namespace.metadata is not None
    namespace.metadata.deletion_timestamp = "2026-05-23T00:00:00Z"

    with pytest.raises(KubernetesRuntimeSafetyError, match="terminating namespace"):
        runtime.scale_workloads("app_instance", "paperless", 0)


def test_runtime_creates_app_ingress_for_configured_route_hosts() -> None:
    core = FakeCoreV1Api()
    networking = FakeNetworkingV1Api()
    runtime = KubernetesRuntime(core, networking_v1_api=networking)
    runtime.ensure_namespace("app_instance", "paperless")

    runtime.ensure_app_ingresses(
        app_slug="paperless",
        routes=[
            {"name": "web", "target": {"port": "http"}},
            {"name": "metrics", "target": {"port": 9090}},
        ],
        domains=[
            {"domain": "nephos.local", "default": True},
            {"domain": "nephos.example", "default": False},
        ],
    )

    assert len(networking.created_ingresses) == 2
    web = networking.created_ingresses[0]
    assert web.metadata is not None
    assert web.metadata.name == "nephos-route-web"
    assert web.metadata.labels == {
        "app.kubernetes.io/managed-by": "nephos",
        "nephos.pro/app-instance": "paperless",
        "nephos.pro/route": "web",
    }
    assert [rule.host for rule in web.spec.rules] == [
        "paperless.nephos.local",
        "paperless.nephos.example",
    ]
    backend = web.spec.rules[0].http.paths[0].backend.service
    assert backend.name == "app-paperless"
    assert backend.port.name == "http"
    metrics = networking.created_ingresses[1]
    assert [rule.host for rule in metrics.spec.rules] == [
        "metrics.paperless.nephos.local",
        "metrics.paperless.nephos.example",
    ]
    assert metrics.spec.rules[0].http.paths[0].backend.service.port.number == 9090


def test_runtime_uses_configured_ingress_class_name() -> None:
    core = FakeCoreV1Api()
    networking = FakeNetworkingV1Api()
    runtime = KubernetesRuntime(
        core,
        networking_v1_api=networking,
        ingress_class_name="nginx",
    )
    runtime.ensure_namespace("app_instance", "paperless")

    runtime.ensure_app_ingresses(
        app_slug="paperless",
        routes=[{"name": "web", "target": {"port": "http"}}],
        domains=[{"domain": "nephos.localhost", "default": True}],
    )

    ingress = networking.created_ingresses[0]
    assert ingress.spec.ingress_class_name == "nginx"


def test_runtime_auto_detects_single_ingress_class_name() -> None:
    core = FakeCoreV1Api()
    networking = FakeNetworkingV1Api()
    networking.ingress_classes = [V1IngressClass(metadata=V1ObjectMeta(name="nginx"))]
    runtime = KubernetesRuntime(core, networking_v1_api=networking)
    runtime.ensure_namespace("app_instance", "paperless")

    runtime.ensure_app_ingresses(
        app_slug="paperless",
        routes=[{"name": "web", "target": {"port": "http"}}],
        domains=[{"domain": "nephos.localhost", "default": True}],
    )

    ingress = networking.created_ingresses[0]
    assert ingress.spec.ingress_class_name == "nginx"


def test_runtime_prefers_default_ingress_class_name() -> None:
    core = FakeCoreV1Api()
    networking = FakeNetworkingV1Api()
    networking.ingress_classes = [
        V1IngressClass(metadata=V1ObjectMeta(name="nginx")),
        V1IngressClass(
            metadata=V1ObjectMeta(
                name="traefik",
                annotations={"ingressclass.kubernetes.io/is-default-class": "true"},
            )
        ),
    ]
    runtime = KubernetesRuntime(core, networking_v1_api=networking)
    runtime.ensure_namespace("app_instance", "paperless")

    runtime.ensure_app_ingresses(
        app_slug="paperless",
        routes=[{"name": "web", "target": {"port": "http"}}],
        domains=[{"domain": "nephos.localhost", "default": True}],
    )

    ingress = networking.created_ingresses[0]
    assert ingress.spec.ingress_class_name == "traefik"


def test_runtime_leaves_ingress_class_unset_when_ambiguous() -> None:
    core = FakeCoreV1Api()
    networking = FakeNetworkingV1Api()
    networking.ingress_classes = [
        V1IngressClass(metadata=V1ObjectMeta(name="nginx")),
        V1IngressClass(metadata=V1ObjectMeta(name="traefik")),
    ]
    runtime = KubernetesRuntime(core, networking_v1_api=networking)
    runtime.ensure_namespace("app_instance", "paperless")

    runtime.ensure_app_ingresses(
        app_slug="paperless",
        routes=[{"name": "web", "target": {"port": "http"}}],
        domains=[{"domain": "nephos.localhost", "default": True}],
    )

    ingress = networking.created_ingresses[0]
    assert ingress.spec.ingress_class_name is None


def test_runtime_replaces_owned_app_ingress() -> None:
    core = FakeCoreV1Api()
    networking = FakeNetworkingV1Api()
    runtime = KubernetesRuntime(core, networking_v1_api=networking)
    runtime.ensure_namespace("app_instance", "paperless")
    runtime.ensure_app_ingresses(
        app_slug="paperless",
        routes=[{"name": "web", "target": {"port": "http"}}],
        domains=[{"domain": "nephos.local", "default": True}],
    )

    runtime.ensure_app_ingresses(
        app_slug="paperless",
        routes=[{"name": "web", "target": {"port": "web"}}],
        domains=[{"domain": "nephos.example", "default": True}],
    )

    assert len(networking.replaced_ingresses) == 1
    ingress = networking.replaced_ingresses[0]
    assert ingress.spec.rules[0].host == "paperless.nephos.example"
    assert ingress.spec.rules[0].http.paths[0].backend.service.port.name == "web"


def test_runtime_refuses_to_replace_unowned_app_ingress() -> None:
    core = FakeCoreV1Api()
    networking = FakeNetworkingV1Api()
    runtime = KubernetesRuntime(core, networking_v1_api=networking)
    runtime.ensure_namespace("app_instance", "paperless")
    networking.ingresses[("app-paperless", "nephos-route-web")] = V1Ingress(
        metadata=V1ObjectMeta(name="nephos-route-web", labels={})
    )

    with pytest.raises(KubernetesRuntimeSafetyError):
        runtime.ensure_app_ingresses(
            app_slug="paperless",
            routes=[{"name": "web", "target": {"port": "http"}}],
            domains=[{"domain": "nephos.local", "default": True}],
        )


def test_runtime_refuses_to_reconcile_ingress_in_terminating_namespace() -> None:
    core = FakeCoreV1Api()
    networking = FakeNetworkingV1Api()
    runtime = KubernetesRuntime(core, networking_v1_api=networking)
    namespace = runtime.ensure_namespace("app_instance", "paperless")
    assert namespace.metadata is not None
    namespace.metadata.deletion_timestamp = "2026-05-23T00:00:00Z"

    with pytest.raises(KubernetesRuntimeSafetyError, match="terminating namespace"):
        runtime.ensure_app_ingresses(
            app_slug="paperless",
            routes=[{"name": "web", "target": {"port": "http"}}],
            domains=[{"domain": "nephos.local", "default": True}],
        )


def test_runtime_deletes_owned_app_ingresses() -> None:
    core = FakeCoreV1Api()
    networking = FakeNetworkingV1Api()
    runtime = KubernetesRuntime(core, networking_v1_api=networking)
    runtime.ensure_namespace("app_instance", "paperless")
    runtime.ensure_app_ingresses(
        app_slug="paperless",
        routes=[{"name": "web", "target": {"port": "http"}}],
        domains=[{"domain": "nephos.local", "default": True}],
    )

    runtime.delete_app_ingresses(app_slug="paperless", routes=[{"name": "web"}])

    assert networking.deleted_ingresses == [("app-paperless", "nephos-route-web")]


def test_runtime_waits_until_deleted_app_ingress_is_absent() -> None:
    core = FakeCoreV1Api()
    networking = SlowDeletingNetworkingV1Api(reads_before_gone=2)
    runtime = KubernetesRuntime(
        core,
        networking_v1_api=networking,
        namespace_delete_timeout_seconds=1,
        namespace_delete_poll_interval_seconds=0,
    )
    runtime.ensure_namespace("app_instance", "paperless")
    runtime.ensure_app_ingresses(
        app_slug="paperless",
        routes=[{"name": "web", "target": {"port": "http"}}],
        domains=[{"domain": "nephos.local", "default": True}],
    )

    runtime.delete_app_ingresses(app_slug="paperless", routes=[{"name": "web"}])

    assert networking.deleted_ingresses == [("app-paperless", "nephos-route-web")]
    assert networking.post_delete_reads == [
        ("app-paperless", "nephos-route-web"),
        ("app-paperless", "nephos-route-web"),
        ("app-paperless", "nephos-route-web"),
    ]
    assert ("app-paperless", "nephos-route-web") not in networking.ingresses


def test_kubernetes_secret_binding_value_source_reads_owned_secret_values() -> None:
    api = FakeCoreV1Api()
    namespace = namespace_name("app_instance", "paperless")
    name = binding_secret_name("database")
    api.namespaces[namespace] = V1Namespace(
        metadata=V1ObjectMeta(
            name=namespace,
            labels=namespace_labels("app_instance", "paperless"),
        )
    )
    api.secrets[(namespace, name)] = V1Secret(
        metadata=type(
            "Meta",
            (),
            {
                "labels": {
                    "app.kubernetes.io/managed-by": "nephos",
                    "nephos.pro/app-instance": "paperless",
                    "nephos.pro/service-instance": "postgres",
                    "nephos.pro/capability": "postgres",
                    "nephos.pro/binding-alias": "database",
                }
            },
        )(),
        data={
            "uri": base64.b64encode(
                b"postgresql://paperless:secret@postgres:5432/paperless"
            ).decode(),
            "database": base64.b64encode(b"paperless").decode(),
        },
    )
    source = KubernetesSecretBindingValueSource(api)

    assert source.get_binding_values(
        app_slug="paperless",
        service_slug="postgres",
        alias="database",
        capability="postgres",
    ) == {
        "uri": "postgresql://paperless:secret@postgres:5432/paperless",
        "database": "paperless",
    }


def test_kubernetes_secret_value_source_refuses_unowned_namespace() -> None:
    api = FakeCoreV1Api()
    namespace = namespace_name("app_instance", "paperless")
    name = binding_secret_name("database")
    api.namespaces[namespace] = V1Namespace(
        metadata=V1ObjectMeta(name=namespace, labels={})
    )
    api.secrets[(namespace, name)] = V1Secret(
        metadata=V1ObjectMeta(
            name=name,
            labels={
                "app.kubernetes.io/managed-by": "nephos",
                "nephos.pro/app-instance": "paperless",
                "nephos.pro/service-instance": "postgres",
                "nephos.pro/capability": "postgres",
                "nephos.pro/binding-alias": "database",
            },
        ),
        data={"uri": base64.b64encode(b"postgresql://example").decode()},
    )
    source = KubernetesSecretBindingValueSource(api)

    with pytest.raises(KubernetesRuntimeSafetyError, match="unowned namespace"):
        source.get_binding_values(
            app_slug="paperless",
            service_slug="postgres",
            alias="database",
            capability="postgres",
        )


def test_kubernetes_secret_value_source_refuses_terminating_namespace() -> None:
    api = FakeCoreV1Api()
    namespace = namespace_name("app_instance", "paperless")
    name = binding_secret_name("database")
    api.namespaces[namespace] = V1Namespace(
        metadata=V1ObjectMeta(
            name=namespace,
            labels=namespace_labels("app_instance", "paperless"),
            deletion_timestamp="2026-05-23T00:00:00Z",
        )
    )
    api.secrets[(namespace, name)] = V1Secret(
        metadata=V1ObjectMeta(
            name=name,
            labels={
                "app.kubernetes.io/managed-by": "nephos",
                "nephos.pro/app-instance": "paperless",
                "nephos.pro/service-instance": "postgres",
                "nephos.pro/capability": "postgres",
                "nephos.pro/binding-alias": "database",
            },
        ),
        data={"uri": base64.b64encode(b"postgresql://example").decode()},
    )
    source = KubernetesSecretBindingValueSource(api)

    with pytest.raises(KubernetesRuntimeSafetyError, match="terminating namespace"):
        source.get_binding_values(
            app_slug="paperless",
            service_slug="postgres",
            alias="database",
            capability="postgres",
        )


def test_kubernetes_secret_value_source_returns_none_for_missing_secret() -> None:
    api = FakeCoreV1Api()
    namespace = namespace_name("app_instance", "paperless")
    api.namespaces[namespace] = V1Namespace(
        metadata=V1ObjectMeta(
            name=namespace,
            labels=namespace_labels("app_instance", "paperless"),
        )
    )
    source = KubernetesSecretBindingValueSource(api)

    assert (
        source.get_binding_values(
            app_slug="paperless",
            service_slug="postgres",
            alias="database",
            capability="postgres",
        )
        is None
    )


def test_kubernetes_secret_binding_value_source_refuses_unowned_secret() -> None:
    api = FakeCoreV1Api()
    namespace = namespace_name("app_instance", "paperless")
    name = binding_secret_name("database")
    api.secrets[(namespace, name)] = V1Secret(metadata=V1ObjectMeta(labels={}))
    source = KubernetesSecretBindingValueSource(api)

    with pytest.raises(KubernetesRuntimeSafetyError):
        source.get_binding_values(
            app_slug="paperless",
            service_slug="postgres",
            alias="database",
            capability="postgres",
        )
