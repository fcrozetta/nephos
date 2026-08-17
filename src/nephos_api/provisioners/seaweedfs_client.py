"""Live SeaweedFS S3 provisioning over `weed shell` (ADR 20260816).

One bucket and one bucket-scoped identity per binding. Credentials are cached in
an owned Secret in the Service namespace so a reconcile re-reads rather than
rotates -- an App holding a working key must never have it changed underneath it.
"""

import base64
import hashlib
import secrets
import string
from collections.abc import Callable

from kubernetes import client
from kubernetes.client.rest import ApiException

from nephos_api.kubernetes_runtime import (
    KubernetesRuntimeSafetyError,
    binding_secret_labels,
    namespace_labels,
)
from nephos_api.providers.seaweedfs_lifecycle import (
    KubernetesSeaweedShellRunner,
    SeaweedShellRunner,
    assert_shell_succeeded,
    s3_configure_command,
    seaweedfs_runtime,
)
from nephos_api.provisioners.base import BindingProvisioningContext

REGION = "us-east-1"
S3_PORT = 8333
BINDING_ACTIONS = "Read,Write,List,Tagging"
_ALPHABET = string.ascii_letters + string.digits


def _generate_key(length: int) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


class KubernetesSeaweedFSProvisioningClient:
    def __init__(
        self,
        *,
        core_v1_api: client.CoreV1Api,
        exec_runner: SeaweedShellRunner | None = None,
        key_factory: Callable[[int], str] | None = None,
    ) -> None:
        self._core_v1_api = core_v1_api
        self._exec_runner = exec_runner or KubernetesSeaweedShellRunner()
        self._key_factory = key_factory or _generate_key

    def ensure_s3_binding(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str]:
        namespace, pod_name, _ = seaweedfs_runtime(context.service_slug)
        _assert_active_owned_service_namespace(
            self._core_v1_api,
            service_slug=context.service_slug,
            namespace=namespace,
        )
        bucket = _bucket_name(context)
        credentials = self._ensure_credential_secret(context, namespace=namespace)
        self._core_v1_api.read_namespaced_pod(namespace=namespace, name=pod_name)
        self._shell(
            namespace=namespace,
            pod_name=pod_name,
            commands=[
                f"s3.bucket.create -name {bucket}",
                s3_configure_command(
                    user=bucket,
                    access_key=credentials["accessKeyId"],
                    secret_key=credentials["secretAccessKey"],
                    actions=BINDING_ACTIONS,
                    bucket=bucket,
                ),
            ],
        )
        return {
            "endpointUrl": _endpoint_url(context.service_slug),
            "bucket": bucket,
            "accessKeyId": credentials["accessKeyId"],
            "secretAccessKey": credentials["secretAccessKey"],
            "region": REGION,
        }

    def delete_s3_binding(self, context: BindingProvisioningContext) -> None:
        namespace, pod_name, _ = seaweedfs_runtime(context.service_slug)
        _assert_active_owned_service_namespace(
            self._core_v1_api,
            service_slug=context.service_slug,
            namespace=namespace,
        )
        name = _credential_secret_name(context)
        existing = _read_optional_secret(
            self._core_v1_api, namespace=namespace, name=name
        )
        if existing is None:
            # Nothing was provisioned (or it is already gone). Deleting the
            # bucket anyway could destroy data a differently-named binding owns.
            return
        _assert_owned_credential_secret(existing, context=context, name=name)
        bucket = _bucket_name(context)
        self._core_v1_api.read_namespaced_pod(namespace=namespace, name=pod_name)
        self._shell(
            namespace=namespace,
            pod_name=pod_name,
            commands=[
                f"s3.configure -user {bucket} -delete -apply",
                f"s3.bucket.delete -name {bucket}",
            ],
        )
        self._core_v1_api.delete_namespaced_secret(namespace=namespace, name=name)

    def _shell(self, *, namespace: str, pod_name: str, commands: list[str]) -> str:
        output = self._exec_runner.run(
            core_v1_api=self._core_v1_api,
            namespace=namespace,
            pod_name=pod_name,
            commands=commands,
        )
        assert_shell_succeeded(output, reason="seaweedfs_provisioning_failed")
        return output

    def _ensure_credential_secret(
        self,
        context: BindingProvisioningContext,
        *,
        namespace: str,
    ) -> dict[str, str]:
        name = _credential_secret_name(context)
        existing = _read_optional_secret(
            self._core_v1_api, namespace=namespace, name=name
        )
        if existing is not None:
            _assert_owned_credential_secret(existing, context=context, name=name)
            return {
                "accessKeyId": _decode_secret_key(existing, "accessKeyId"),
                "secretAccessKey": _decode_secret_key(existing, "secretAccessKey"),
            }
        credentials = {
            "accessKeyId": self._key_factory(20),
            "secretAccessKey": self._key_factory(40),
        }
        self._core_v1_api.create_namespaced_secret(
            namespace=namespace,
            body=client.V1Secret(
                metadata=client.V1ObjectMeta(
                    name=name,
                    namespace=namespace,
                    labels=binding_secret_labels(
                        app_slug=context.app_slug,
                        service_slug=context.service_slug,
                        alias=context.alias,
                        capability=context.capability,
                        protocol=context.protocol,
                    ),
                ),
                type="Opaque",
                string_data=credentials,
            ),
        )
        return credentials


def _endpoint_url(service_slug: str) -> str:
    namespace, _, name = seaweedfs_runtime(service_slug)
    return f"http://{name}.{namespace}.svc.cluster.local:{S3_PORT}"


_DISCRIMINATOR_LENGTH = 12
_MAX_NAME_LENGTH = 63


def _scoped(base: str, *, binding_id: str) -> str:
    """`base` narrowed to one binding, always.

    The discriminator is unconditional rather than a truncation fallback. App and
    Service slugs are UNIQUE on separate tables and install checks neither against
    the other, while a service dependency passes the consumer slug as `app_slug`
    -- so an App and a Service sharing a slug and alias produce identical names
    *and* identical ownership labels, and the second consumer is handed the first
    one's credentials.

    Derived from `binding_id`, not random: deprovision recomputes these names from
    the context and would otherwise miss.
    """
    suffix = hashlib.sha256(binding_id.encode()).hexdigest()[:_DISCRIMINATOR_LENGTH]
    budget = _MAX_NAME_LENGTH - len(suffix) - 1
    return f"{base[:budget].rstrip('-')}-{suffix}"


def _bucket_name(context: BindingProvisioningContext) -> str:
    # S3 bucket names are DNS labels: lowercase, 3-63 chars, no underscores.
    base = f"nephos-{context.app_slug}-{context.alias}".lower().replace("_", "-")
    return _scoped(base, binding_id=context.binding_id)


def _credential_secret_name(context: BindingProvisioningContext) -> str:
    base = f"nephos-s3-{context.app_slug}-{context.alias}"
    return _scoped(base, binding_id=context.binding_id)


def _read_optional_secret(core_v1_api, *, namespace: str, name: str):
    try:
        return core_v1_api.read_namespaced_secret(namespace=namespace, name=name)
    except ApiException as exc:
        if exc.status == 404:
            return None
        raise


def _decode_secret_key(secret, key: str) -> str:
    data = secret.data or {}
    value = data.get(key)
    if value is None:
        raise RuntimeError(f"Secret {secret.metadata.name} is missing key {key}")
    return base64.b64decode(value).decode()


def _assert_active_owned_service_namespace(
    core_v1_api, *, service_slug: str, namespace: str
) -> None:
    try:
        namespace_resource = core_v1_api.read_namespace(name=namespace)
    except ApiException as exc:
        if exc.status == 404:
            namespace_resource = None
        else:
            raise
    if namespace_resource is None or namespace_resource.metadata is None:
        raise KubernetesRuntimeSafetyError(
            f"refusing to use unowned namespace {namespace}"
        )
    labels = namespace_resource.metadata.labels or {}
    expected = namespace_labels("service_instance", service_slug)
    if not all(labels.get(key) == value for key, value in expected.items()):
        raise KubernetesRuntimeSafetyError(
            f"refusing to use unowned namespace {namespace}"
        )
    if namespace_resource.metadata.deletion_timestamp is not None:
        raise KubernetesRuntimeSafetyError(
            f"refusing to use terminating namespace {namespace}"
        )


def _assert_owned_credential_secret(
    secret, *, context: BindingProvisioningContext, name: str
) -> None:
    if secret.metadata is None:
        raise KubernetesRuntimeSafetyError(f"refusing to use unowned Secret {name}")
    labels = secret.metadata.labels or {}
    expected = binding_secret_labels(
        app_slug=context.app_slug,
        service_slug=context.service_slug,
        alias=context.alias,
        capability=context.capability,
        protocol=context.protocol,
    )
    if not all(labels.get(key) == value for key, value in expected.items()):
        namespace = getattr(secret.metadata, "namespace", "?")
        raise KubernetesRuntimeSafetyError(
            f"refusing to use unowned Secret {namespace}/{name}"
        )
