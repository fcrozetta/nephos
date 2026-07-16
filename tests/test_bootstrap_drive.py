import json

import httpx
import pytest

from nephos_api.bootstrap_drive import BootstrapDriveError, drive_bootstrap


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("nephos_api.bootstrap_drive.time.sleep", lambda *_: None)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://api")


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
                200, json={"resource": {"status": {"level": "ready"}}}
            )
        return httpx.Response(404)

    drive_bootstrap(
        "http://api",
        domain_name="lcl",
        domain="nephos.lcl",
        api_service_url="http://svc:8099",
        client=_client(handler),
    )

    assert ("POST", "/services") in seen
    assert ("POST", "/apps") in seen
    assert console_config["api-url"] == "http://svc:8099"


def test_drive_treats_already_installed_409_as_done() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/healthz":
            return httpx.Response(200, json={})
        if request.method == "POST" and path == "/platform/config/domains":
            return httpx.Response(409, json={})
        if request.method == "POST" and path in ("/services", "/apps"):
            return httpx.Response(409, json={})
        if path == "/services/openbao":
            return httpx.Response(
                200, json={"resource": {"status": {"level": "ready"}}}
            )
        if path == "/apps/console":
            return httpx.Response(
                200, json={"resource": {"status": {"level": "healthy"}}}
            )
        return httpx.Response(404)

    drive_bootstrap(
        "http://api",
        domain_name="lcl",
        domain="nephos.lcl",
        api_service_url="http://svc:8099",
        client=_client(handler),
    )


def test_drive_raises_when_resource_reports_failed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/healthz":
            return httpx.Response(200, json={})
        if request.method == "POST":
            return httpx.Response(202, json={})
        if path == "/services/openbao":
            return httpx.Response(
                200, json={"resource": {"status": {"level": "failed"}}}
            )
        return httpx.Response(404)

    with pytest.raises(BootstrapDriveError, match="openbao failed"):
        drive_bootstrap(
            "http://api",
            domain_name="lcl",
            domain="nephos.lcl",
            api_service_url="http://svc:8099",
            timeout_seconds=1.0,
            client=_client(handler),
        )


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
        drive_bootstrap(
            "http://api",
            domain_name="lcl",
            domain="nephos.lcl",
            api_service_url="http://svc:8099",
            client=_client(handler),
        )
