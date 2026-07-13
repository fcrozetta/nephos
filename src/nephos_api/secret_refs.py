import json
import os
import secrets
import string
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from nephos_api.runtime_errors import RuntimeBlockedError

# The provider-agnostic scheme. `secrets://<scope>/<name>/<field>` is a logical
# coordinate Nephos owns; it never encodes a provider-native path. See
# docs/adr/20260713-secrets-capability.md.
SECRETS_SCHEME = "secrets://"

# Supported secret-reference schemes. `secrets://` routes through the platform
# secrets capability (read-or-generate). `op://` (1Password CLI) and `bao://`
# (OpenBao KV v2) are legacy read-only schemes kept for back-compat. All are
# materialized at deploy time so desired state stores only references, never
# resolved values.
SECRET_REFERENCE_SCHEMES = (SECRETS_SCHEME, "op://", "bao://")


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


class BaoTokenProvider(Protocol):
    def get_token(self) -> str | None: ...


@dataclass(frozen=True)
class StaticBaoTokenProvider:
    token: str | None

    def get_token(self) -> str | None:
        return self.token or None


@dataclass(frozen=True)
class ChainedBaoTokenProvider:
    """Return the first available token. Ordered k8s-first so a live init token
    wins over a stale static dev token."""

    providers: tuple[BaoTokenProvider, ...]

    def get_token(self) -> str | None:
        for provider in self.providers:
            token = provider.get_token()
            if token:
                return token
        return None


@dataclass(frozen=True)
class BaoSecretResolver:
    """Resolve `bao://<mount>/<path.../<field>` references from an OpenBao KV v2
    store over HTTP. The access token is fetched at resolve time from a
    BaoTokenProvider (Kubernetes-managed init token, or a static dev token)."""

    address: str
    token_provider: BaoTokenProvider
    timeout_seconds: float = 30.0

    @classmethod
    def from_static(
        cls, *, address: str, token: str, timeout_seconds: float = 30.0
    ) -> "BaoSecretResolver":
        return cls(
            address=address,
            token_provider=StaticBaoTokenProvider(token),
            timeout_seconds=timeout_seconds,
        )

    def resolve(self, reference: str) -> str:
        mount, path, field = self._parse(reference)
        token = self.token_provider.get_token()
        if not token:
            raise RuntimeBlockedError(
                reason="secret_ref_provider_unavailable",
                message="No OpenBao token is available to resolve secret references.",
            )
        url = f"{self.address.rstrip('/')}/v1/{mount}/data/{path}"
        request = urllib.request.Request(
            url,
            headers={"X-Vault-Token": token},
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


# --------------------------------------------------------------------------
# secrets:// capability — provider-agnostic read-or-generate.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SecretGenSpec:
    """Nephos-owned generation policy for a `secrets://` value. Absent means
    gen=none: the value must already exist or resolution fails closed."""

    kind: str = "password"
    length: int = 32


@dataclass(frozen=True)
class SecretRead:
    """A secret read from a provider, with the version needed for CAS writes."""

    fields: dict[str, str]
    version: int


class SecretCASConflictError(Exception):
    """Raised by a provider when a versioned write loses to a concurrent one.

    Internal control-flow only (drives a materializer retry); never surfaced.
    """


class SecretsProvider(Protocol):
    """A value store behind the `secrets` capability. The provider owns the
    store; Nephos owns generation policy and the no-lockout rule (see the
    SecretsMaterializer)."""

    def read_secret(self, path: str) -> SecretRead | None: ...

    def write_secret(
        self, path: str, fields: dict[str, str], *, expected_version: int
    ) -> None: ...

    def capability_ready(self) -> bool: ...


@dataclass(frozen=True)
class OpenBaoSecretsProvider:
    """`SecretsProvider` backed by OpenBao KV v2, with CAS writes.

    `expected_version=0` means create-only (fails if the path exists);
    `expected_version=N` means update only if the current version is N.
    """

    address: str
    token_provider: BaoTokenProvider
    mount: str = "secret"
    timeout_seconds: float = 30.0

    def read_secret(self, path: str) -> SecretRead | None:
        url = f"{self.address.rstrip('/')}/v1/{self.mount}/data/{path}"
        request = urllib.request.Request(
            url, headers={"X-Vault-Token": self._token()}, method="GET"
        )
        try:
            payload = self._send(request)
        except _HttpStatusError as exc:
            if exc.code == 404:
                return None
            raise self._blocked(exc) from exc
        try:
            data = payload["data"]
            return SecretRead(
                fields={str(k): str(v) for k, v in data["data"].items()},
                version=int(data["metadata"]["version"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeBlockedError(
                reason="secret_ref_unavailable",
                message=f"OpenBao returned an unexpected shape for {path!r}.",
            ) from exc

    def write_secret(
        self, path: str, fields: dict[str, str], *, expected_version: int
    ) -> None:
        url = f"{self.address.rstrip('/')}/v1/{self.mount}/data/{path}"
        body = json.dumps(
            {"options": {"cas": expected_version}, "data": fields}
        ).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "X-Vault-Token": self._token(),
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            self._send(request)
        except _HttpStatusError as exc:
            # With cas always set, a 400 is a check-and-set version mismatch.
            if exc.code == 400:
                raise SecretCASConflictError(path) from exc
            raise self._blocked(exc) from exc

    def capability_ready(self) -> bool:
        if not self.token_provider.get_token():
            return False
        url = f"{self.address.rstrip('/')}/v1/sys/health"
        request = urllib.request.Request(url, method="GET")
        try:
            self._send(request)
            return True
        except _HttpStatusError as exc:
            # 429 = unsealed standby; still usable for reads/writes via active.
            return exc.code == 429
        except RuntimeBlockedError:
            return False

    def _token(self) -> str:
        token = self.token_provider.get_token()
        if not token:
            raise RuntimeBlockedError(
                reason="secret_ref_provider_unavailable",
                message="No OpenBao token is available for the secrets provider.",
            )
        return token

    def _send(self, request: urllib.request.Request) -> dict[str, object]:
        try:
            with urllib.request.urlopen(  # noqa: S310 - operator-configured URL
                request, timeout=self.timeout_seconds
            ) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise _HttpStatusError(exc.code) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeBlockedError(
                reason="secret_ref_provider_unavailable",
                message="OpenBao is not reachable for the secrets provider.",
            ) from exc
        return json.loads(raw) if raw else {}

    @staticmethod
    def _blocked(exc: "_HttpStatusError") -> RuntimeBlockedError:
        return RuntimeBlockedError(
            reason="secret_ref_provider_unavailable",
            message=f"OpenBao rejected a secrets request (status {exc.code}).",
        )


class _HttpStatusError(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class SecretsMaterializer:
    """Owns generate-if-absent and the no-lockout rule over a SecretsProvider.

    Implements `RuntimeSecretResolver` (read-only via `resolve`) so `secrets://`
    can be routed like any other scheme; `materialize` adds the generation path
    used where a config option declares a generation policy.
    """

    provider: SecretsProvider
    path_prefix: str = "nephos"
    max_attempts: int = 3

    def resolve(self, reference: str) -> str:
        return self.materialize(reference, generate=None)

    def materialize(
        self, reference: str, *, generate: SecretGenSpec | None = None
    ) -> str:
        scope, name, field = self._parse(reference)
        path = f"{self.path_prefix}/{scope}/{name}"
        for _ in range(self.max_attempts):
            existing = self.provider.read_secret(path)
            if existing is not None and field in existing.fields:
                return existing.fields[field]  # no-lockout: never regenerate
            if generate is None:
                raise RuntimeBlockedError(
                    reason="secret_ref_unavailable",
                    message=(
                        f"Secret reference {reference} has no value and no "
                        "generation policy."
                    ),
                )
            value = _generate_value(generate, reference=reference)
            fields = dict(existing.fields) if existing is not None else {}
            fields[field] = value
            expected_version = existing.version if existing is not None else 0
            try:
                self.provider.write_secret(
                    path, fields, expected_version=expected_version
                )
            except SecretCASConflictError:
                continue  # a concurrent write landed; re-read and merge
            # Read back so the returned value is the one now stored.
            readback = self.provider.read_secret(path)
            if readback is not None and field in readback.fields:
                return readback.fields[field]
            return value
        raise RuntimeBlockedError(
            reason="secret_ref_provider_unavailable",
            message=f"Secret reference {reference} could not be materialized.",
        )

    @staticmethod
    def _parse(reference: str) -> tuple[str, str, str]:
        # secrets://<scope>/<name>/<field>; scope is svc/<slug>, app/<slug>,
        # or platform, so field/name are the last two segments and scope is
        # everything before them.
        parts = reference.removeprefix(SECRETS_SCHEME).split("/")
        if len(parts) < 3 or not all(parts):
            raise _invalid_secrets_reference(reference)
        scope_parts, name, field = parts[:-2], parts[-2], parts[-1]
        head = scope_parts[0]
        if head in ("svc", "app"):
            if len(scope_parts) != 2:
                raise _invalid_secrets_reference(reference)
        elif head == "platform":
            if len(scope_parts) != 1:
                raise _invalid_secrets_reference(reference)
        else:
            raise _invalid_secrets_reference(reference)
        return "/".join(scope_parts), name, field


def _invalid_secrets_reference(reference: str) -> RuntimeBlockedError:
    return RuntimeBlockedError(
        reason="secret_ref_unavailable",
        message=(
            f"Secret reference {reference} is not a valid "
            "secrets://<scope>/<name>/<field> reference."
        ),
    )


_PASSWORD_ALPHABET = string.ascii_letters + string.digits


def _generate_value(spec: SecretGenSpec, *, reference: str) -> str:
    if spec.kind == "password":
        return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(spec.length))
    raise RuntimeBlockedError(
        reason="secret_ref_unavailable",
        message=f"Unsupported generation kind {spec.kind!r} for {reference}.",
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
