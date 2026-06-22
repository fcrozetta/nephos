from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class BindingProvisioningContext:
    binding_id: str
    app_slug: str
    service_slug: str
    alias: str
    capability: str
    protocol: str | None = None


class BindingProvisioner(Protocol):
    def provision_binding(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str] | None: ...

    def deprovision_binding(self, context: BindingProvisioningContext) -> None: ...
