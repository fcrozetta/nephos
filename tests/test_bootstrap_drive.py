import json

import httpx
import pytest

from nephos_api.bootstrap_drive import BootstrapDriveError, drive_bootstrap


@pytest.fixture(autouse=True)
def _fast_clock(monkeypatch):
    # No real sleeping, and a monotonic clock that advances deterministically so
    # timeout loops terminate instantly instead of burning wall-clock.
    ticks = {"t": 0.0}

    def fake_monotonic() -> float:
        ticks["t"] += 0.1
        return ticks["t"]

    monkeypatch.setattr("nephos_api.bootstrap_drive.time.sleep", lambda *_: None)
    monkeypatch.setattr("nephos_api.bootstrap_drive.time.monotonic", fake_monotonic)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://api")


def _run(handler) -> None:
    drive_bootstrap(
        "http://api",
        domain_name="lcl",
        domain="nephos.lcl",
        api_service_url="http://svc:8099",
        timeout_seconds=5.0,
        client=_client(handler),
    )


def test_drive_installs_openbao_then_console_with_apiurl() -> None:
    seen: list[tuple[str, str]] = []
    console_config: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        seen.append((request.method, path))
        if path == "/healthz":
            return httpx.Response(200, json={})
        if request.method == "POST" and path == "/platform/config/domains":
            return httpx.Response(202, json={})
        if request.method == "POST" and path == "/services":
            return httpx.Response(202, json={})
        if path == "/services/openbao":
            return httpx.Response(
                200, json={"resource": {"status": {"level": "healthy"}}}
            )
        if request.method == "POST" and path == "/apps":
            console_config.update(json.loads(request.content)["config"])
            return httpx.Response(202, json={})
        if path == "/apps/console":
            return httpx.Response(
                200, json={"resource": {"status": {"level": "healthy"}}}
            )
        return httpx.Response(404)

    _run(handler)
    assert ("POST", "/services") in seen
    assert ("POST", "/apps") in seen
    assert console_config["api-url"] == "http://svc:8099"


def test_drive_reconciles_on_already_installed_conflict() -> None:
    """A re-run: install returns the instance-conflict 409, so the drive must
    re-issue a reconcile (blocked/failed requests are otherwise terminal)."""
    reconciled: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/healthz":
            return httpx.Response(200, json={})
        if request.method == "POST" and path == "/platform/config/domains":
            return httpx.Response(409, json={})
        if request.method == "POST" and path == "/services":
            return httpx.Response(
                409, json={"error": {"code": "service_instance_conflict"}}
            )
        if request.method == "POST" and path == "/apps":
            return httpx.Response(
                409, json={"error": {"code": "app_instance_conflict"}}
            )
        if path.endswith("/actions/reconcile"):
            reconciled.append(path)
            return httpx.Response(202, json={})
        if path == "/services/openbao":
            return httpx.Response(
                200, json={"resource": {"status": {"level": "ready"}}}
            )
        if path == "/apps/console":
            return httpx.Response(
                200, json={"resource": {"status": {"level": "healthy"}}}
            )
        return httpx.Response(404)

    _run(handler)
    assert "/services/openbao/actions/reconcile" in reconciled
    assert "/apps/console/actions/reconcile" in reconciled


def test_drive_raises_on_non_conflict_409() -> None:
    """A 409 that is not an instance-conflict (e.g. ambiguous catalog) is a real
    error, not 'already installed'."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/healthz":
            return httpx.Response(200, json={})
        if request.method == "POST" and path == "/platform/config/domains":
            return httpx.Response(202, json={})
        if request.method == "POST" and path == "/services":
            return httpx.Response(
                409, json={"error": {"code": "catalog_entry_ambiguous"}}
            )
        return httpx.Response(404)

    with pytest.raises(BootstrapDriveError, match="install openbao failed"):
        _run(handler)


def test_drive_keeps_polling_on_blocked_then_succeeds() -> None:
    """'blocked' is transient (e.g. secrets:// waiting on OpenBao); the drive
    must keep polling, not fail."""
    polls = {"openbao": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/healthz":
            return httpx.Response(200, json={})
        if request.method == "POST":
            return httpx.Response(202, json={})
        if path == "/services/openbao":
            polls["openbao"] += 1
            level = "blocked" if polls["openbao"] < 2 else "healthy"
            return httpx.Response(200, json={"resource": {"status": {"level": level}}})
        if path == "/apps/console":
            return httpx.Response(
                200, json={"resource": {"status": {"level": "healthy"}}}
            )
        return httpx.Response(404)

    _run(handler)
    assert polls["openbao"] >= 2


def test_drive_fails_fast_and_surfaces_reason_on_degraded() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/healthz":
            return httpx.Response(200, json={})
        if request.method == "POST":
            return httpx.Response(202, json={})
        if path == "/services/openbao":
            return httpx.Response(
                200,
                json={
                    "resource": {
                        "status": {
                            "level": "degraded",
                            "reason": "helm_failed",
                            "message": "chart pull error",
                        }
                    }
                },
            )
        return httpx.Response(404)

    with pytest.raises(BootstrapDriveError, match="helm_failed.*chart pull error"):
        _run(handler)


def test_drive_times_out_when_never_ready() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/healthz":
            return httpx.Response(200, json={})
        if request.method == "POST":
            return httpx.Response(202, json={})
        if path == "/services/openbao":
            return httpx.Response(
                200, json={"resource": {"status": {"level": "blocked"}}}
            )
        return httpx.Response(404)

    with pytest.raises(BootstrapDriveError, match="openbao not ready within"):
        _run(handler)


def test_drive_raises_on_install_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/healthz":
            return httpx.Response(200, json={})
        if request.method == "POST" and path == "/platform/config/domains":
            return httpx.Response(202, json={})
        if request.method == "POST" and path == "/services":
            return httpx.Response(500, text="boom")
        return httpx.Response(404)

    with pytest.raises(BootstrapDriveError, match="install openbao failed"):
        _run(handler)


def test_wait_healthz_retries_then_raises_on_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/healthz":
            raise httpx.ConnectError("api still starting")
        return httpx.Response(404)

    with pytest.raises(BootstrapDriveError, match="/healthz did not become ready"):
        drive_bootstrap(
            "http://api",
            domain_name="lcl",
            domain="nephos.lcl",
            api_service_url="http://svc:8099",
            timeout_seconds=5.0,
            healthz_timeout=1.0,
            client=_client(handler),
        )
