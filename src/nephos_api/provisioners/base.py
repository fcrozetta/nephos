from collections.abc import Mapping
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
    service_config: Mapping[str, object] | None = None
    app_routes: tuple[Mapping[str, object], ...] = ()
    platform_domains: tuple[Mapping[str, object], ...] = ()

    def __post_init__(self) -> None:
        if self.service_config is None:
            object.__setattr__(self, "service_config", {})


class BindingProvisioner(Protocol):
    def provision_binding(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str] | None: ...

    def deprovision_binding(self, context: BindingProvisioningContext) -> None: ...
