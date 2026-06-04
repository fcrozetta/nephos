from __future__ import annotations

from collections.abc import Mapping

from nephos_api.providers.base import ProviderContext, RuntimeProvider
from nephos_api.runtime_errors import RuntimeBlockedError


class RuntimeProviderRouter:
    def __init__(
        self,
        *,
        helm_provider: RuntimeProvider,
        provider_runtimes: Mapping[str, RuntimeProvider],
    ) -> None:
        self._helm_provider = helm_provider
        self._provider_runtimes = dict(provider_runtimes)

    def deploy(self, context: ProviderContext) -> None:
        self._provider_for(context).deploy(context)

    def uninstall(self, context: ProviderContext) -> None:
        self._provider_for(context).uninstall(context)

    def _provider_for(self, context: ProviderContext) -> RuntimeProvider:
        if context.provider_name is None:
            return self._helm_provider
        provider = self._provider_runtimes.get(context.provider_name)
        if provider is None:
            raise RuntimeBlockedError(
                reason="runtime_provider_unknown",
                message=f"Runtime provider {context.provider_name} is not available.",
            )
        return provider
