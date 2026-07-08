from pathlib import Path

from fastapi.testclient import TestClient

from nephos_api.config import Settings
from nephos_api.db import migrate_database
from nephos_api.main import create_app


def _client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "nephos.db"
    migrate_database(db_path=db_path)
    app = create_app(
        settings=Settings(
            db_path=db_path,
            catalog_roots=(tmp_path / "catalog",),
            kubeconfig=None,
            kube_context=None,
        )
    )
    return TestClient(app)


def test_list_platform_domains_returns_empty_list(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.get("/platform/config/domains")

    assert response.status_code == 200
    assert response.json() == {"domains": []}


def test_add_platform_domain_returns_mutation_envelope(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/platform/config/domains",
        json={"name": "local", "domain": "nephos.local", "default": True},
    )

    body = response.json()
    assert response.status_code == 202
    assert body["resource"]["id"].startswith("domain_")
    assert body["resource"]["name"] == "local"
    assert body["resource"]["domain"] == "nephos.local"
    assert body["resource"]["default"] is True
    assert body["resource"]["generation"] == 1
    assert body["reconciliation"]["id"].startswith("reconcile_")
    assert body["reconciliation"]["state"] == "pending"

    list_response = client.get("/platform/config/domains")
    assert list_response.status_code == 200
    assert list_response.json()["domains"] == [body["resource"]]


def test_first_platform_domain_becomes_default(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/platform/config/domains",
        json={"name": "local", "domain": "nephos.local", "default": False},
    )

    assert response.status_code == 202
    assert response.json()["resource"]["default"] is True


def test_new_default_platform_domain_replaces_existing_default(tmp_path: Path) -> None:
    client = _client(tmp_path)
    first = client.post(
        "/platform/config/domains",
        json={"name": "local", "domain": "nephos.local", "default": True},
    )
    assert first.status_code == 202

    second = client.post(
        "/platform/config/domains",
        json={"name": "public", "domain": "nephos.example", "default": True},
    )

    assert second.status_code == 202
    domains = client.get("/platform/config/domains").json()["domains"]
    defaults = {domain["name"]: domain["default"] for domain in domains}
    assert defaults == {"local": False, "public": True}


def test_invalid_platform_domain_returns_nephos_error(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/platform/config/domains",
        json={"name": "local", "domain": "http://nephos.local", "default": True},
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "invalid_platform_domain",
            "message": "Platform domain must be a DNS suffix.",
            "details": {"domain": "http://nephos.local"},
        }
    }


def test_duplicate_platform_domain_returns_conflict_error(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = client.post(
        "/platform/config/domains",
        json={"name": "local", "domain": "nephos.local", "default": True},
    )
    assert created.status_code == 202

    response = client.post(
        "/platform/config/domains",
        json={"name": "local", "domain": "nephos.local", "default": True},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "platform_domain_conflict"


def test_set_default_platform_domain_action_updates_default(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    assert (
        client.post(
            "/platform/config/domains",
            json={"name": "local", "domain": "nephos.local", "default": True},
        ).status_code
        == 202
    )
    assert (
        client.post(
            "/platform/config/domains",
            json={"name": "public", "domain": "nephos.example", "default": False},
        ).status_code
        == 202
    )

    response = client.post("/platform/config/domains/public/actions/set-default")

    assert response.status_code == 202
    assert response.json()["resource"]["name"] == "public"
    assert response.json()["resource"]["default"] is True
    assert response.json()["reconciliation"]["state"] == "pending"
    domains = client.get("/platform/config/domains").json()["domains"]
    defaults = {domain["name"]: domain["default"] for domain in domains}
    assert defaults == {"local": False, "public": True}


def test_remove_non_default_platform_domain_action_deletes_domain(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    assert (
        client.post(
            "/platform/config/domains",
            json={"name": "local", "domain": "nephos.local", "default": True},
        ).status_code
        == 202
    )
    assert (
        client.post(
            "/platform/config/domains",
            json={"name": "public", "domain": "nephos.example", "default": False},
        ).status_code
        == 202
    )

    response = client.post("/platform/config/domains/public/actions/remove")

    assert response.status_code == 202
    assert response.json()["resource"]["name"] == "public"
    assert response.json()["resource"]["default"] is False
    assert response.json()["reconciliation"]["state"] == "pending"
    domains = client.get("/platform/config/domains").json()["domains"]
    assert [domain["name"] for domain in domains] == ["local"]


def test_remove_default_platform_domain_is_blocked(tmp_path: Path) -> None:
    client = _client(tmp_path)
    assert (
        client.post(
            "/platform/config/domains",
            json={"name": "local", "domain": "nephos.local", "default": True},
        ).status_code
        == 202
    )
    assert (
        client.post(
            "/platform/config/domains",
            json={"name": "public", "domain": "nephos.example", "default": False},
        ).status_code
        == 202
    )

    response = client.post("/platform/config/domains/local/actions/remove")

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "platform_domain_default_required",
            "message": "Cannot remove the default platform domain.",
            "details": {"name": "local"},
        }
    }


def test_platform_domains_reconcile_action_queues_configuration_reconcile(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    created = client.post(
        "/platform/config/domains",
        json={"name": "local", "domain": "nephos.local", "default": True},
    )
    assert created.status_code == 202

    response = client.post("/platform/config/domains/actions/reconcile")

    assert response.status_code == 202
    assert response.json() == {
        "resource": {
            "domains": [created.json()["resource"]],
        },
        "reconciliation": {
            "id": response.json()["reconciliation"]["id"],
            "state": "pending",
        },
    }
    assert response.json()["reconciliation"]["id"].startswith("reconcile_")


def test_platform_domains_reconcile_action_blocks_without_domains(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)

    response = client.post("/platform/config/domains/actions/reconcile")

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "platform_domain_required",
            "message": "At least one platform domain is required.",
        }
    }


def test_platform_domain_actions_return_not_found(tmp_path: Path) -> None:
    client = _client(tmp_path)

    set_default = client.post("/platform/config/domains/missing/actions/set-default")
    remove = client.post("/platform/config/domains/missing/actions/remove")

    assert set_default.status_code == 404
    assert remove.status_code == 404
    assert set_default.json()["error"]["code"] == "platform_domain_not_found"
    assert remove.json()["error"]["code"] == "platform_domain_not_found"
