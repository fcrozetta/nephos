from collections.abc import Iterable, Iterator, Mapping
from dataclasses import replace

from nephos_api.provisioners.base import (
    BindingProvisioner,
    BindingProvisioningContext,
)
from nephos_api.runtime_errors import RuntimeBlockedError
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


class EngineRoutingBindingProvisioner:
    """Dispatch a binding to its registry-declared provisioning engine.

    ADR 20260718: the service manifest declares which capability-typed engine
    provisions its bindings (surfaced as ``context.provisioning_engine``). The
    named engine must be registered; a binding that declares no engine, or one
    whose declared engine is not registered, blocks loudly rather than being
    handed to the wrong backend. (The strangler back-compat fallback to legacy
    ``(capability, protocol)`` dispatch was removed once the postgres/zitadel
    manifests declared their engines.)
    """

    def __init__(self, engines: Mapping[str, BindingProvisioner]) -> None:
        self._engines = dict(engines)

    def provision_binding(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str] | None:
        engine = self._resolve_engine(context)
        self._assert_entitlements_recognized(context, engine)
        return engine.provision_binding(context)

    def deprovision_binding(self, context: BindingProvisioningContext) -> None:
        # Teardown stays best-effort; do not block deprovision on entitlements.
        self._resolve_engine(context).deprovision_binding(context)

    @staticmethod
    def _assert_entitlements_recognized(
        context: BindingProvisioningContext,
        engine: BindingProvisioner,
    ) -> None:
        # ADR 20260721: an engine blocks loudly on an entitlement it does not
        # recognize rather than silently ignoring the grant. Recognition is
        # engine-declared data (``recognized_entitlements``); the router enforces
        # it uniformly so every engine, not just postgres, is covered.
        recognized = getattr(engine, "recognized_entitlements", frozenset())
        unknown = context.entitlements - recognized
        if unknown:
            raise RuntimeBlockedError(
                reason="binding_entitlement_unknown",
                message=(
                    f"Binding requests entitlement(s) {sorted(unknown)} not "
                    f"recognized by engine '{context.provisioning_engine}'."
                ),
            )

    def _resolve_engine(
        self,
        context: BindingProvisioningContext,
    ) -> BindingProvisioner:
        name = context.provisioning_engine
        if name is None:
            raise RuntimeBlockedError(
                reason="provisioning_engine_missing",
                message=(
                    "Binding reached provisioning with no declared "
                    "provisioning.engine; the service manifest must declare one."
                ),
            )
        try:
            return self._engines[name]
        except KeyError as exc:
            raise RuntimeBlockedError(
                reason="provisioning_engine_unknown",
                message=f"No provisioning engine registered for '{name}'.",
            ) from exc


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
