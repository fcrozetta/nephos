from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import uuid4

from nephos_api.errors import NephosError

MACHINE_IDENTIFIER_RE = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
DNS_LABEL_RE = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")

ID_PREFIXES = {
    "app_instance": "appinst",
    "service_instance": "svcinst",
    "binding": "binding",
    "platform_domain": "domain",
    "reconciliation_request": "reconcile",
    "status_snapshot": "status",
}


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id(kind: str) -> str:
    try:
        prefix = ID_PREFIXES[kind]
    except KeyError as exc:
        raise ValueError(f"unknown id kind: {kind}") from exc
    return f"{prefix}_{uuid4().hex}"


def validate_machine_identifier(value: str, *, field: str = "name") -> str:
    if not MACHINE_IDENTIFIER_RE.fullmatch(value):
        raise NephosError(
            "invalid_machine_identifier",
            f"Invalid {field}: {value!r}.",
            status_code=422,
            details={
                "field": field,
                "value": value,
                "pattern": MACHINE_IDENTIFIER_RE.pattern,
            },
        )
    return value


def validate_root_domain(value: str) -> str:
    if ("://" in value) or ("/" in value) or (":" in value) or ("*" in value):
        raise NephosError(
            "invalid_root_domain",
            "Root domain must be a DNS suffix without scheme, wildcard, path, or port.",
            status_code=422,
            details={"domain": value},
        )
    if value.startswith(".") or value.endswith("."):
        raise NephosError(
            "invalid_root_domain",
            "Root domain must not start or end with a dot.",
            status_code=422,
            details={"domain": value},
        )
    if len(value) > 253:
        raise NephosError(
            "invalid_root_domain",
            "Root domain is too long.",
            status_code=422,
            details={"domain": value},
        )

    labels = value.split(".")
    if len(labels) < 2:
        raise NephosError(
            "invalid_root_domain",
            "Root domain must contain at least two DNS labels.",
            status_code=422,
            details={"domain": value},
        )
    for label in labels:
        if len(label) > 63 or not DNS_LABEL_RE.fullmatch(label):
            raise NephosError(
                "invalid_root_domain",
                "Root domain contains an invalid DNS label.",
                status_code=422,
                details={"domain": value, "label": label},
            )
    return value
