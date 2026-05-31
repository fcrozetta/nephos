from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from nephos_api.config import Settings
from nephos_api.main import create_app
from nephos_api.migrations import apply_migrations

pytestmark = pytest.mark.unit


def _client(tmp_path) -> tuple[TestClient, Settings]:
    settings = Settings(db_path=tmp_path / "nephos.db")
    apply_migrations(settings)
    return TestClient(create_app(settings)), settings


def test_platform_domain_add_returns_mutation_envelope(tmp_path):
    client, settings = _client(tmp_path)

    response = client.post(
        "/platform/config/domains",
        json={"name": "local", "domain": "nephos.local", "default": True},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["resource"]["name"] == "local"
    assert body["resource"]["domain"] == "nephos.local"
    assert body["resource"]["default"] is True
    assert body["resource"]["generation"] == 1
    assert body["reconciliation"]["state"] == "pending"
    assert body["reconciliation"]["targetType"] == "platform_domain"
    assert body["status"]["level"] == "pending"

    with sqlite3.connect(settings.db_path) as connection:
        request_count = connection.execute(
            "SELECT COUNT(*) FROM reconciliation_requests"
        ).fetchone()[0]
    assert request_count == 1


def test_platform_domain_list_reports_configuration_status(tmp_path):
    client, _settings = _client(tmp_path)

    empty = client.get("/platform/config/domains")
    assert empty.status_code == 200
    assert empty.json() == {"items": [], "configured": False}

    client.post(
        "/platform/config/domains",
        json={"name": "local", "domain": "nephos.local", "default": True},
    )

    listed = client.get("/platform/config/domains")
    assert listed.status_code == 200
    assert listed.json()["configured"] is True
    assert listed.json()["items"][0]["name"] == "local"


def test_platform_domain_set_default_updates_single_default(tmp_path):
    client, _settings = _client(tmp_path)
    client.post(
        "/platform/config/domains",
        json={"name": "local", "domain": "nephos.local", "default": True},
    )
    client.post(
        "/platform/config/domains",
        json={"name": "home", "domain": "home.test", "default": False},
    )

    response = client.post("/platform/config/domains/home/actions/set-default")

    assert response.status_code == 202
    assert response.json()["resource"]["name"] == "home"
    assert response.json()["resource"]["default"] is True
    listed = client.get("/platform/config/domains").json()["items"]
    defaults = [item["name"] for item in listed if item["default"]]
    assert defaults == ["home"]


def test_platform_domain_duplicate_name_returns_domain_error(tmp_path):
    client, _settings = _client(tmp_path)
    client.post(
        "/platform/config/domains",
        json={"name": "local", "domain": "nephos.local", "default": True},
    )

    response = client.post(
        "/platform/config/domains",
        json={"name": "local", "domain": "other.local", "default": False},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "platform_domain_conflict"


def test_platform_domain_invalid_name_uses_nephos_error_shape(tmp_path):
    client, _settings = _client(tmp_path)

    response = client.post(
        "/platform/config/domains",
        json={"name": "Not-Valid", "domain": "nephos.local", "default": True},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_machine_identifier"


def test_platform_domain_remove_deletes_desired_state_and_keeps_request(tmp_path):
    client, settings = _client(tmp_path)
    client.post(
        "/platform/config/domains",
        json={"name": "local", "domain": "nephos.local", "default": True},
    )

    response = client.post("/platform/config/domains/local/actions/remove")

    assert response.status_code == 202
    assert response.json()["resource"]["name"] == "local"
    assert response.json()["reconciliation"]["action"] == "platform_domain.remove"
    assert client.get("/platform/config/domains").json() == {"items": [], "configured": False}
    with sqlite3.connect(settings.db_path) as connection:
        request_count = connection.execute(
            "SELECT COUNT(*) FROM reconciliation_requests"
        ).fetchone()[0]
    assert request_count == 2
