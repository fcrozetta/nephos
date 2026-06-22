from typing import Protocol

from nephos_api.provisioners.base import BindingProvisioningContext
from nephos_api.runtime_errors import RuntimeBlockedError


class ZitadelProvisioningClient(Protocol):
    def ensure_oidc_client(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str]: ...

    def ensure_service_account(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str]: ...

    def delete_oidc_client(self, context: BindingProvisioningContext) -> None: ...

    def delete_service_account(self, context: BindingProvisioningContext) -> None: ...


class ZitadelAppScopedProvisioner:
    def __init__(self, client: ZitadelProvisioningClient | None = None) -> None:
        self._client = client

    def provision_binding(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str] | None:
        if _is_oidc(context):
            if self._client is None:
                raise _client_missing("Zitadel")
            return self._client.ensure_oidc_client(context)
        if _is_service_account(context):
            if self._client is None:
                raise _client_missing("Zitadel")
            return self._client.ensure_service_account(context)
        return None

    def deprovision_binding(self, context: BindingProvisioningContext) -> None:
        if self._client is None:
            return
        if _is_oidc(context):
            self._client.delete_oidc_client(context)
        elif _is_service_account(context):
            self._client.delete_service_account(context)


def _is_oidc(context: BindingProvisioningContext) -> bool:
    return context.capability == "oidc" and context.protocol == "oidc"


def _is_service_account(context: BindingProvisioningContext) -> bool:
    return context.capability == "service-account" and context.protocol == "jwt"


def _client_missing(service: str) -> RuntimeBlockedError:
    return RuntimeBlockedError(
        reason="binding_provisioner_unavailable",
        message=(
            f"{service} client is not configured; live external API details "
            "are intentionally blocked until verified."
        ),
    )
