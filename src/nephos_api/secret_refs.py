import os
import subprocess
from dataclasses import dataclass
from typing import Protocol

from nephos_api.runtime_errors import RuntimeBlockedError


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


def is_secret_reference(value: object) -> bool:
    return isinstance(value, str) and value.startswith("op://")


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
