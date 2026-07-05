from collections.abc import Iterable
from dataclasses import replace

from nephos_api.provisioners.base import (
    BindingProvisioner,
    BindingProvisioningContext,
)
from nephos_api.secret_refs import RuntimeSecretResolver, resolve_runtime_secret_value


class CompositeBindingProvisioner:
    def __init__(self, provisioners: Iterable[BindingProvisioner]) -> None:
        self._provisioners = list(provisioners)

    def provision_binding(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str] | None:
        for provisioner in self._provisioners:
            values = provisioner.provision_binding(context)
            if values is not None:
                return values
        return None

    def deprovision_binding(self, context: BindingProvisioningContext) -> None:
        for provisioner in self._provisioners:
            provisioner.deprovision_binding(context)


class SecretResolvingBindingProvisioner:
    """Resolve ``op://`` references in Service config before delegating.

    The runtime deploy path resolves secret references through the deployer's
    RuntimeSecretResolver, but the binding-provisioning path receives raw
    Service config from the reconciler. Without this wrapper, provisioning-
    relevant config values stored as ``op://`` references (for example the
    Zitadel ``external-host``) would reach provisioners unresolved and break
    derived values such as the OIDC issuer URL.
    """

    def __init__(
        self,
        inner: BindingProvisioner,
        *,
        resolver: RuntimeSecretResolver,
    ) -> None:
        self._inner = inner
        self._resolver = resolver

    def provision_binding(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str] | None:
        return self._inner.provision_binding(self._resolve(context))

    def deprovision_binding(self, context: BindingProvisioningContext) -> None:
        self._inner.deprovision_binding(self._resolve(context))

    def _resolve(
        self,
        context: BindingProvisioningContext,
    ) -> BindingProvisioningContext:
        config = context.service_config or {}
        resolved = {
            key: resolve_runtime_secret_value(value, self._resolver)
            for key, value in config.items()
        }
        return replace(context, service_config=resolved)
