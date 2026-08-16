from typing import Protocol

from nephos_api.provisioners.base import BindingProvisioningContext
from nephos_api.runtime_errors import RuntimeBlockedError


class SeaweedFSProvisioningClient(Protocol):
    def ensure_s3_binding(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str]: ...

    def delete_s3_binding(self, context: BindingProvisioningContext) -> None: ...


class SeaweedFSS3Provisioner:
    # ADR 20260721 + ADR 20260816: the object-storage engine grants no elevated
    # entitlements. There is no cross-bucket admin grant for S3 -- that would
    # undo the per-binding scoping this engine exists to provide.
    recognized_entitlements = frozenset()

    def __init__(self, client: SeaweedFSProvisioningClient | None = None) -> None:
        self._client = client

    def provision_binding(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str] | None:
        if not _is_s3(context):
            return None
        if self._client is None:
            raise RuntimeBlockedError(
                reason="binding_provisioner_unavailable",
                message=(
                    "SeaweedFS client is not configured; live external API details "
                    "are intentionally blocked until verified."
                ),
            )
        return self._client.ensure_s3_binding(context)

    def deprovision_binding(self, context: BindingProvisioningContext) -> None:
        if self._client is not None and _is_s3(context):
            self._client.delete_s3_binding(context)


def _is_s3(context: BindingProvisioningContext) -> bool:
    return context.capability == "object-storage" and context.protocol == "s3"
