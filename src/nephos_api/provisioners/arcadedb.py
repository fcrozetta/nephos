from collections.abc import Iterable
from typing import Protocol

from nephos_api.provisioners.base import BindingProvisioningContext
from nephos_api.runtime_errors import RuntimeBlockedError

_CORE_PROTOCOLS = {
    ("sql", "arcadedb"),
    ("opencypher", "bolt"),
    ("opencypher", "n4j"),
}
_OPTIONAL_PROTOCOLS = {
    ("gremlin", "gremlin"),
    ("mongo", "mongo"),
}


class ArcadeDBProvisioningClient(Protocol):
    def ensure_database_user(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str]: ...

    def delete_database_user(self, context: BindingProvisioningContext) -> None: ...


class ArcadeDBAppScopedProvisioner:
    def __init__(
        self,
        client: ArcadeDBProvisioningClient | None = None,
        enabled_optional_protocols: Iterable[tuple[str, str]] = (),
    ) -> None:
        self._client = client
        self._enabled_optional_protocols = set(enabled_optional_protocols)

    def provision_binding(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str] | None:
        selector = _selector(context)
        if selector is None:
            return None
        if (
            selector in _OPTIONAL_PROTOCOLS
            and selector not in self._enabled_optional_protocols
        ):
            raise RuntimeBlockedError(
                reason="binding_provisioner_unavailable",
                message=(
                    f"ArcadeDB protocol {selector[0]}/{selector[1]} is not enabled."
                ),
            )
        if self._client is None:
            raise RuntimeBlockedError(
                reason="binding_provisioner_unavailable",
                message=(
                    "ArcadeDB client is not configured; live external API details "
                    "are intentionally blocked until verified."
                ),
            )
        return self._client.ensure_database_user(context)

    def deprovision_binding(self, context: BindingProvisioningContext) -> None:
        selector = _selector(context)
        if (
            self._client is not None
            and selector is not None
            and (
                selector in _CORE_PROTOCOLS
                or selector in self._enabled_optional_protocols
            )
        ):
            self._client.delete_database_user(context)


def _selector(context: BindingProvisioningContext) -> tuple[str, str] | None:
    if context.protocol is None:
        return None
    selector = (context.capability, context.protocol)
    if selector in _CORE_PROTOCOLS or selector in _OPTIONAL_PROTOCOLS:
        return selector
    return None
