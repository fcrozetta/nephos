from collections.abc import Iterable, Iterator, Mapping
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


class _LazyResolvingServiceConfig(Mapping):
    """A Service-config view that resolves ``op://`` refs only when a key is read.

    The reconciler passes the full Service manifest config, which may contain
    ``op://`` references for fields the matched provisioner never reads (for
    example a Postgres binding does not read Zitadel's ``master-key``). Eagerly
    resolving every entry would make an unrelated missing ref (or an unavailable
    1Password CLI/session) block a binding that never needed it. Resolving
    lazily per key means only the fields a provisioner actually looks up hit the
    resolver. Results are cached so a `key in config` followed by `config[key]`
    resolves once.
    """

    def __init__(
        self,
        raw: Mapping[str, object],
        resolver: RuntimeSecretResolver,
    ) -> None:
        self._raw = dict(raw)
        self._resolver = resolver
        self._cache: dict[str, object] = {}

    def __getitem__(self, key: str) -> object:
        if key not in self._raw:
            raise KeyError(key)
        if key not in self._cache:
            self._cache[key] = resolve_runtime_secret_value(
                self._raw[key], self._resolver
            )
        return self._cache[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._raw)

    def __len__(self) -> int:
        return len(self._raw)


class SecretResolvingBindingProvisioner:
    """Resolve ``op://`` references in Service config before delegating.

    The runtime deploy path resolves secret references through the deployer's
    RuntimeSecretResolver, but the binding-provisioning path receives raw
    Service config from the reconciler. Without this, provisioning-relevant
    config values stored as ``op://`` references (for example the Zitadel
    ``external-host``) would reach provisioners unresolved and break derived
    values such as the OIDC issuer URL.

    Resolution is lazy (see :class:`_LazyResolvingServiceConfig`) so only the
    config fields a matched provisioner actually reads are resolved.
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
        return replace(
            context,
            service_config=_LazyResolvingServiceConfig(config, self._resolver),
        )
