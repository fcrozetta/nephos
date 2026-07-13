from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import uuid4

_MACHINE_IDENTIFIER_RE = re.compile(r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")
_DNS_SUFFIX_RE = re.compile(
    r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?"
    r"(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$"
)


class InvalidMachineIdentifierError(ValueError):
    """Raised when a public Nephos machine identifier is invalid."""


class InvalidDomainSuffixError(ValueError):
    """Raised when a configured root domain is not a DNS suffix."""


def validate_machine_identifier(value: str) -> str:
    if not _MACHINE_IDENTIFIER_RE.fullmatch(value):
        raise InvalidMachineIdentifierError(
            "machine identifiers must be DNS-label style lowercase names"
        )
    return value


def validate_dns_suffix(value: str) -> str:
    if (
        "://" in value
        or "/" in value
        or "*" in value
        or ":" in value
        or not _DNS_SUFFIX_RE.fullmatch(value)
        or len(value) > 253
    ):
        raise InvalidDomainSuffixError("platform domain must be a DNS suffix")
    return value


def generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


@dataclass(frozen=True)
class AppInstance:
    id: str
    slug: str
    lifecycle: str
    generation: int


@dataclass(frozen=True)
class ServiceInstance:
    id: str
    slug: str
    lifecycle: str
    generation: int


@dataclass(frozen=True)
class Binding:
    id: str
    alias: str
    capability: str
    protocol: str | None
    generation: int


@dataclass(frozen=True)
class PlatformDomain:
    id: str
    name: str
    domain: str
    is_default: bool
    generation: int
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class AdminAccount:
    id: str
    username: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class StatusSnapshot:
    id: str
    resource_type: str
    resource_id: str
    level: str


@dataclass(frozen=True)
class ReconciliationRequest:
    id: str
    target_type: str
    target_id: str
    target_generation: int
    action: str
    state: str
