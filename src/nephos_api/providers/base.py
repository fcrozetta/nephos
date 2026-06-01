from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from nephos_api.catalog import AppManifest, ServiceManifest


@dataclass(frozen=True)
class ProviderContext:
    @dataclass(frozen=True)
    class Chart:
        repository: str
        name: str
        version: str

    target_type: str
    slug: str
    runtime_name: str
    manifest: AppManifest | ServiceManifest | None
    chart: Chart | None
    values: dict[str, object]
    provider_name: str | None = None


class RuntimeProvider(Protocol):
    def deploy(self, context: ProviderContext) -> None: ...

    def uninstall(self, context: ProviderContext) -> None: ...
