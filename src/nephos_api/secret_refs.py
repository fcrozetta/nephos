import json
import os
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from nephos_api.runtime_errors import RuntimeBlockedError

# Supported secret-reference schemes. `op://` resolves through the 1Password CLI;
# `bao://` resolves through an OpenBao KV v2 store. Both are materialized at
# deploy time so desired state stores only references, never resolved values.
SECRET_REFERENCE_SCHEMES = ("op://", "bao://")


class RuntimeSecretResolver(Protocol):
    def resolve(self, reference: str) -> str: ...


@dataclass(frozen=True)
class StaticSecretResolver:
    values: dict[str, str]

    def resolve(self, reference: str) -> str:
        try:
            return self.values[reference]
        except KeyError as exc:
            raise RuntimeBlockedError(
                reason="secret_ref_unavailable",
                message=f"Secret reference {reference} could not be resolved.",
            ) from exc


@dataclass(frozen=True)
class OnePasswordCliSecretResolver:
    command: str = "op"
    env: dict[str, str] | None = None
    timeout_seconds: float = 30.0

    def resolve(self, reference: str) -> str:
        try:
            completed = subprocess.run(
                [self.command, "read", reference],
                check=False,
                env=self._env(),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise RuntimeBlockedError(
                reason="secret_ref_provider_unavailable",
                message="1Password CLI is not available to resolve secret references.",
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeBlockedError(
                reason="secret_ref_provider_unavailable",
                message=f"Secret reference {reference} resolution timed out.",
            ) from exc

        if completed.returncode != 0:
            raise RuntimeBlockedError(
                reason="secret_ref_unavailable",
                message=f"Secret reference {reference} could not be resolved.",
            )
        return completed.stdout.rstrip("\n")

    def _env(self) -> dict[str, str] | None:
        if self.env is None:
            return None
        resolved = os.environ.copy()
        resolved.update(self.env)
        return resolved


@dataclass(frozen=True)
class BaoSecretResolver:
    """Resolve `bao://<mount>/<path.../<field>` references from an OpenBao KV v2
    store over HTTP. Phase 1 authenticates with a static token; a later phase
    replaces this with a Kubernetes auth method."""

    address: str
    token: str
    timeout_seconds: float = 30.0

    def resolve(self, reference: str) -> str:
        mount, path, field = self._parse(reference)
        url = f"{self.address.rstrip('/')}/v1/{mount}/data/{path}"
        request = urllib.request.Request(
            url,
            headers={"X-Vault-Token": self.token},
            method="GET",
        )
        try:
            with urllib.request.urlopen(  # noqa: S310 - operator-configured URL
                request, timeout=self.timeout_seconds
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeBlockedError(
                reason="secret_ref_provider_unavailable",
                message="OpenBao is not reachable to resolve secret references.",
            ) from exc
        except (ValueError, TimeoutError) as exc:
            raise RuntimeBlockedError(
                reason="secret_ref_unavailable",
                message=f"Secret reference {reference} could not be resolved.",
            ) from exc

        try:
            return str(payload["data"]["data"][field])
        except (KeyError, TypeError) as exc:
            raise RuntimeBlockedError(
                reason="secret_ref_unavailable",
                message=f"Secret reference {reference} has no field {field!r}.",
            ) from exc

    @staticmethod
    def _parse(reference: str) -> tuple[str, str, str]:
        # bao://<mount>/<path...>/<field> -> (mount, path, field)
        parts = reference.removeprefix("bao://").split("/")
        if len(parts) < 3 or not all(parts):
            raise RuntimeBlockedError(
                reason="secret_ref_unavailable",
                message=(
                    f"Secret reference {reference} is not a valid "
                    "bao://<mount>/<path>/<field> reference."
                ),
            )
        return parts[0], "/".join(parts[1:-1]), parts[-1]


@dataclass(frozen=True)
class SchemeRoutingSecretResolver:
    """Route a reference to the resolver registered for its scheme, so `op://`
    and `bao://` references can coexist during the migration off 1Password."""

    resolvers: dict[str, RuntimeSecretResolver]

    def resolve(self, reference: str) -> str:
        for scheme, resolver in self.resolvers.items():
            if reference.startswith(scheme):
                return resolver.resolve(reference)
        raise RuntimeBlockedError(
            reason="secret_ref_provider_unavailable",
            message=f"No secret provider is configured for {reference}.",
        )


def is_secret_reference(value: object) -> bool:
    return isinstance(value, str) and value.startswith(SECRET_REFERENCE_SCHEMES)


def resolve_runtime_secret_value(
    value: object,
    resolver: RuntimeSecretResolver | None,
) -> object:
    if not is_secret_reference(value):
        return value
    if resolver is None:
        raise RuntimeBlockedError(
            reason="secret_ref_provider_unavailable",
            message=f"No secret provider is configured for {value}.",
        )
    return resolver.resolve(str(value))
