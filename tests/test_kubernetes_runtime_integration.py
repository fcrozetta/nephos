import time
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from nephos_api.config import Settings, load_settings
from nephos_api.db import migrate_database
from nephos_api.dev_reference import write_reference_catalog
from nephos_api.kubernetes_client import (
    kubernetes_tests_enabled,
    load_kubernetes_config,
)
from nephos_api.kubernetes_runtime import KubernetesRuntime, namespace_name
from nephos_api.main import (
    create_app,
    default_postgres_provisioner_factory,
    default_provider_deployer_factory,
)

pytestmark = [pytest.mark.integration, pytest.mark.kubernetes]


def test_kubernetes_api_is_reachable_when_explicitly_enabled() -> None:
    if not kubernetes_tests_enabled():
        pytest.skip("set NEPHOS_API_RUN_KUBERNETES_TESTS=1 to run Kubernetes tests")

    from kubernetes import client

    load_kubernetes_config(load_settings())
    version = client.VersionApi().get_code()

    assert version.git_version


def test_kubernetes_runtime_creates_and_deletes_owned_namespace() -> None:
    if not kubernetes_tests_enabled():
        pytest.skip("set NEPHOS_API_RUN_KUBERNETES_TESTS=1 to run Kubernetes tests")

    from uuid import uuid4

    from kubernetes import client

    load_kubernetes_config(load_settings())
    runtime = KubernetesRuntime(client.CoreV1Api())
    slug = f"k8s-test-{uuid4().hex[:8]}"
    namespace = namespace_name("app_instance", slug)

    try:
        created = runtime.ensure_namespace("app_instance", slug)

        assert created.metadata is not None
        assert created.metadata.name == namespace
        assert created.metadata.labels["app.kubernetes.io/managed-by"] == "nephos"
        assert created.metadata.labels["nephos.pro/app-instance"] == slug
    finally:
        runtime.delete_namespace_if_owned("app_instance", slug)


def test_kubernetes_reference_flow_converges_provider_runtime_and_binding_secret(
    tmp_path: Path,
) -> None:
    if not kubernetes_tests_enabled():
        pytest.skip("set NEPHOS_API_RUN_KUBERNETES_TESTS=1 to run Kubernetes tests")

    suffix = uuid4().hex[:8]
    service_slug = f"postgres-{suffix}"
    app_slug = f"reference-web-{suffix}"
    db_path = tmp_path / "nephos.db"
    catalog_root = tmp_path / "catalog"
    write_reference_catalog(catalog_root)
    migrate_database(db_path=db_path)
    base_settings = load_settings()
    settings = Settings(
        db_path=db_path,
        catalog_roots=(catalog_root,),
        kubeconfig=base_settings.kubeconfig,
        kube_context=base_settings.kube_context,
        internal_domain=base_settings.internal_domain,
        ingress_class=base_settings.ingress_class,
    )
    app = create_app(
        settings=settings,
        start_reconciler=True,
        deployer_factory=default_provider_deployer_factory,
        provisioner_factory=default_postgres_provisioner_factory,
        reconciler_interval_seconds=1,
    )

    try:
        with TestClient(app) as api:
            domain = api.post(
                "/platform/config/domains",
                json={
                    "name": "local",
                    "domain": settings.internal_domain,
                    "default": True,
                },
            )
            assert domain.status_code == 202
            service = api.post(
                "/services",
                json={
                    "catalogRef": {"kind": "Service", "name": "postgres"},
                    "instanceName": service_slug,
                },
            )
            assert service.status_code == 202
            created_app = api.post(
                "/apps",
                json={
                    "catalogRef": {"kind": "App", "name": "reference-web"},
                    "instanceName": app_slug,
                },
            )
            assert created_app.status_code == 202
            binding_id = created_app.json()["resource"]["bindings"][0]["id"]
            route = api.get(f"/apps/{app_slug}").json()["routes"][0]
            assert (
                route["canonicalUrl"] == f"http://{app_slug}.{settings.internal_domain}"
            )

            _eventually(
                lambda: (
                    _resource_status_reason(api, f"/services/{service_slug}")
                    == "runtime_deployed"
                    and _resource_status_reason(api, f"/apps/{app_slug}")
                    == "runtime_deployed"
                    and _resource_status_reason(api, f"/bindings/{binding_id}")
                    == "binding_secret_ready"
                ),
                timeout_seconds=180,
            )
            _assert_ingress_host(
                settings,
                app_slug,
                f"{app_slug}.{settings.internal_domain}",
            )
            public_domain = api.post(
                "/platform/config/domains",
                json={
                    "name": "public",
                    "domain": "nephos.example",
                    "default": True,
                },
            )
            assert public_domain.status_code == 202
            _eventually(
                lambda: (
                    f"{app_slug}.nephos.example"
                    in _ingress_hosts(settings, app_slug, "nephos-route-web")
                ),
                timeout_seconds=180,
            )
            route = api.get(f"/apps/{app_slug}").json()["routes"][0]
            assert route["canonicalUrl"] == f"http://{app_slug}.nephos.example"
            blocked_service_stop = api.post(
                f"/services/{service_slug}/actions/stop",
                json={},
            )
            assert blocked_service_stop.status_code == 409

            stop = api.post(f"/apps/{app_slug}/actions/stop", json={})
            assert stop.status_code == 202
            _eventually(
                lambda: (
                    _resource_status_reason(api, f"/apps/{app_slug}")
                    == "runtime_stopped"
                ),
                timeout_seconds=60,
            )
            stopped_reconcile = api.post(
                f"/apps/{app_slug}/actions/reconcile",
                json={},
            )
            assert stopped_reconcile.status_code == 202
            _eventually(
                lambda: (
                    _resource_status_reason(api, f"/apps/{app_slug}")
                    == "runtime_stopped"
                ),
                timeout_seconds=60,
            )

            start = api.post(f"/apps/{app_slug}/actions/start", json={})
            assert start.status_code == 202
            _eventually(
                lambda: (
                    _resource_status_reason(api, f"/apps/{app_slug}")
                    == "runtime_deployed"
                ),
                timeout_seconds=180,
            )

            remove = api.post(f"/apps/{app_slug}/actions/remove", json={})
            assert remove.status_code == 202
            _eventually(
                lambda: (
                    _resource_status_reason(api, f"/apps/{app_slug}")
                    == "runtime_removed"
                ),
                timeout_seconds=120,
            )
            _assert_ingress_absent(settings, app_slug, "nephos-route-web")
            removed_reconcile = api.post(
                f"/apps/{app_slug}/actions/reconcile",
                json={},
            )
            assert removed_reconcile.status_code == 202
            _eventually(
                lambda: (
                    _resource_status_reason(api, f"/apps/{app_slug}")
                    == "runtime_removed"
                ),
                timeout_seconds=120,
            )
            _assert_ingress_absent(settings, app_slug, "nephos-route-web")

            destroy = api.post(
                f"/apps/{app_slug}/actions/destroy",
                json={"confirm": f"destroy {app_slug}"},
            )
            assert destroy.status_code == 202
            _eventually(
                lambda: api.get(f"/apps/{app_slug}").status_code == 404,
                timeout_seconds=120,
            )
            _assert_namespace_absent(settings, "app_instance", app_slug)

            service_destroy = api.post(
                f"/services/{service_slug}/actions/destroy",
                json={"confirm": f"destroy {service_slug}"},
            )
            assert service_destroy.status_code == 202
            _eventually(
                lambda: api.get(f"/services/{service_slug}").status_code == 404,
                timeout_seconds=120,
            )
            _assert_namespace_absent(settings, "service_instance", service_slug)
    finally:
        _delete_owned_namespace_if_present(settings, "app_instance", app_slug)
        _delete_owned_namespace_if_present(settings, "service_instance", service_slug)


def _eventually(check, *, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(1)
    assert check()


def _resource_status_reason(api: TestClient, path: str) -> str | None:
    response = api.get(path)
    if response.status_code != 200:
        return None
    status = response.json()["status"]
    return status["reason"] if status else None


def _delete_owned_namespace_if_present(
    settings: Settings,
    resource_type,
    slug: str,
) -> None:
    from kubernetes import client

    load_kubernetes_config(settings)
    runtime = KubernetesRuntime(client.CoreV1Api())
    runtime.delete_namespace_if_owned(resource_type, slug)


def _assert_ingress_host(settings: Settings, app_slug: str, host: str) -> None:
    from kubernetes import client

    load_kubernetes_config(settings)
    ingress = client.NetworkingV1Api().read_namespaced_ingress(
        namespace=f"app-{app_slug}",
        name="nephos-route-web",
    )

    assert ingress.metadata is not None
    assert ingress.metadata.labels["app.kubernetes.io/managed-by"] == "nephos"
    assert ingress.metadata.labels["nephos.pro/app-instance"] == app_slug
    assert ingress.metadata.labels["nephos.pro/route"] == "web"
    assert ingress.spec is not None
    if settings.ingress_class is not None:
        assert ingress.spec.ingress_class_name == settings.ingress_class
    assert [rule.host for rule in ingress.spec.rules] == [host]


def _ingress_hosts(
    settings: Settings,
    app_slug: str,
    ingress_name: str,
) -> list[str]:
    from kubernetes import client

    load_kubernetes_config(settings)
    ingress = client.NetworkingV1Api().read_namespaced_ingress(
        namespace=f"app-{app_slug}",
        name=ingress_name,
    )

    assert ingress.spec is not None
    return [rule.host for rule in ingress.spec.rules]


def _assert_ingress_absent(
    settings: Settings,
    app_slug: str,
    ingress_name: str,
) -> None:
    from kubernetes import client
    from kubernetes.client.rest import ApiException

    load_kubernetes_config(settings)
    try:
        client.NetworkingV1Api().read_namespaced_ingress(
            namespace=f"app-{app_slug}",
            name=ingress_name,
        )
    except ApiException as exc:
        if exc.status == 404:
            return
        raise
    pytest.fail(f"Ingress app-{app_slug}/{ingress_name} still exists")


def _assert_namespace_absent(
    settings: Settings,
    resource_type,
    slug: str,
) -> None:
    from kubernetes import client
    from kubernetes.client.rest import ApiException

    load_kubernetes_config(settings)
    namespace = namespace_name(resource_type, slug)
    try:
        client.CoreV1Api().read_namespace(name=namespace)
    except ApiException as exc:
        if exc.status == 404:
            return
        raise
    pytest.fail(f"Namespace {namespace} still exists")
