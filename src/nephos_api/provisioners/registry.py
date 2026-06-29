from collections.abc import Iterable

from nephos_api.provisioners.base import (
    BindingProvisioner,
    BindingProvisioningContext,
)


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
