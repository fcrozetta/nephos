"""Drive greenfield backbone bring-up over the in-cluster API.

setup port-forwards the nephos-api Service and POSTs the same desired-state the
console/API expose: set the default platform domain, install OpenBao (the core
secrets backend), wait for it, then install the console pointed at the in-cluster
API. The drive is convergent -- already-installed resources (409) are treated as
done -- so an interrupted setup is fixed by re-running it. The port-forward is
bootstrap-only, not a runtime dependency.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

# The reconciler emits "healthy" on success and "degraded" on a hard failure;
# a RuntimeBlockedError yields "blocked", which can be transient (e.g. a
# secrets:// ref waiting on OpenBao), so we keep polling on it. "ready"/"failed"
# are never emitted today but kept as harmless synonyms.
READY_LEVELS = {"healthy", "ready"}
FAILED_LEVELS = {"degraded", "failed"}
_ALREADY_INSTALLED_CODES = {"service_instance_conflict", "app_instance_conflict"}

Progress = Callable[[str], None]


class BootstrapDriveError(RuntimeError):
    pass


def _noop(_: str) -> None:
    return None


def drive_bootstrap(
    base_url: str,
    *,
    domain_name: str,
    domain: str,
    api_service_url: str,
    console_image: str | None = None,
    timeout_seconds: float = 300.0,
    healthz_timeout: float = 90.0,
    poll_interval: float = 3.0,
    progress: Progress = _noop,
    client: httpx.Client | None = None,
) -> None:
    owns_client = client is None
    client = client or httpx.Client(base_url=base_url, timeout=30.0)
    try:
        _wait_healthz(
            client, timeout_seconds=healthz_timeout, poll_interval=poll_interval
        )

        progress(f"setting default platform domain {domain}")
        _set_default_domain(client, name=domain_name, domain=domain)

        progress("installing OpenBao (core secrets backend)")
        _ensure_installed(
            client,
            "/services",
            "/services/openbao",
            kind="Service",
            name="openbao",
            config={},
        )
        _wait_ready(
            client,
            "/services/openbao",
            label="openbao",
            timeout_seconds=timeout_seconds,
            poll_interval=poll_interval,
            progress=progress,
        )

        console_config: dict[str, Any] = {"api-url": api_service_url}
        if console_image:
            console_config["image"] = console_image
        progress("installing console")
        _ensure_installed(
            client,
            "/apps",
            "/apps/console",
            kind="App",
            name="console",
            config=console_config,
        )
        _wait_ready(
            client,
            "/apps/console",
            label="console",
            timeout_seconds=timeout_seconds,
            poll_interval=poll_interval,
            progress=progress,
        )
    finally:
        if owns_client:
            client.close()


def _ensure_installed(
    client: httpx.Client,
    collection_path: str,
    item_path: str,
    *,
    kind: str,
    name: str,
    config: dict[str, Any],
) -> None:
    resp = client.post(
        collection_path,
        json={"catalogRef": {"kind": kind, "name": name}, "config": config},
    )
    if resp.status_code < 400:
        return
    # Only an instance-conflict means "already installed". Re-issue a reconcile
    # so a previously blocked/failed converge is retried (those requests are
    # otherwise terminal) -- that is what makes a re-run genuinely convergent.
    # Any other 409 (e.g. catalog_entry_ambiguous) is a real error.
    if resp.status_code == 409 and _error_code(resp) in _ALREADY_INSTALLED_CODES:
        retry = client.post(f"{item_path}/actions/reconcile", json={})
        if retry.status_code >= 400:
            raise BootstrapDriveError(
                f"reconcile {name} failed: {retry.status_code} {retry.text}"
            )
        return
    raise BootstrapDriveError(f"install {name} failed: {resp.status_code} {resp.text}")


def _error_code(resp: httpx.Response) -> str | None:
    try:
        return resp.json().get("code")
    except (ValueError, AttributeError):
        return None


def _set_default_domain(client: httpx.Client, *, name: str, domain: str) -> None:
    resp = client.post(
        "/platform/config/domains",
        json={"name": name, "domain": domain, "default": True},
    )
    if resp.status_code == 409:
        return  # domain already present
    if resp.status_code >= 400:
        raise BootstrapDriveError(
            f"set default domain failed: {resp.status_code} {resp.text}"
        )


def _status_fields(
    resource: dict[str, Any],
) -> tuple[str | None, str | None, str | None]:
    for candidate in (resource.get("status"), resource):
        if isinstance(candidate, dict) and isinstance(candidate.get("level"), str):
            return (
                candidate.get("level"),
                candidate.get("reason"),
                candidate.get("message"),
            )
    return None, None, None


def _detail(reason: str | None, message: str | None) -> str:
    joined = " ".join(part for part in (reason, message) if part)
    return f": {joined}" if joined else ""


def _wait_ready(
    client: httpx.Client,
    path: str,
    *,
    label: str,
    timeout_seconds: float,
    poll_interval: float,
    progress: Progress,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last: str | None = None
    last_detail = ""
    while time.monotonic() < deadline:
        resp = client.get(path)
        if resp.status_code == 200:
            body = resp.json()
            resource = body.get("resource", body)
            level, reason, message = _status_fields(resource)
            last_detail = _detail(reason, message) or last_detail
            if level != last:
                progress(f"{label}: {level}")
                last = level
            if level in READY_LEVELS:
                return
            if level in FAILED_LEVELS:
                raise BootstrapDriveError(
                    f"{label} failed to reconcile ({level}){_detail(reason, message)}"
                )
        time.sleep(poll_interval)
    raise BootstrapDriveError(
        f"{label} not ready within {timeout_seconds:.0f}s "
        f"(last level: {last}{last_detail})"
    )


def _wait_healthz(
    client: httpx.Client,
    *,
    timeout_seconds: float,
    poll_interval: float,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            if client.get("/healthz").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(poll_interval)
    raise BootstrapDriveError("API /healthz did not become ready")
