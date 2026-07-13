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


def test_auth_state_reports_no_admin_initially(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.get("/auth/state")

    assert response.status_code == 200
    assert response.json() == {"adminExists": False}


def test_first_run_admin_creation_and_state_flip(tmp_path: Path) -> None:
    client = _client(tmp_path)

    created = client.post(
        "/admin/accounts",
        json={"username": "admin", "password": "P@ssw0rd"},
    )

    assert created.status_code == 201
    resource = created.json()["resource"]
    assert resource["id"].startswith("admin_")
    assert resource["username"] == "admin"
    assert "password" not in resource
    assert "passwordHash" not in resource

    assert client.get("/auth/state").json() == {"adminExists": True}


def test_second_admin_creation_is_rejected(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.post("/admin/accounts", json={"username": "admin", "password": "P@ssw0rd"})

    second = client.post(
        "/admin/accounts",
        json={"username": "someone-else", "password": "P@ssw0rd"},
    )

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "admin_already_exists"


def test_admin_creation_rejects_invalid_username(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/admin/accounts",
        json={"username": "bad name!", "password": "P@ssw0rd"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "admin_username_invalid"


def test_admin_creation_rejects_short_password(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/admin/accounts",
        json={"username": "admin", "password": "short"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "admin_password_invalid"


def test_login_succeeds_with_correct_credentials(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.post("/admin/accounts", json={"username": "admin", "password": "P@ssw0rd"})

    response = client.post(
        "/auth/login",
        json={"username": "admin", "password": "P@ssw0rd"},
    )

    assert response.status_code == 200
    assert response.json() == {"authenticated": True, "subject": "admin"}


def test_login_rejects_wrong_password(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.post("/admin/accounts", json={"username": "admin", "password": "P@ssw0rd"})

    response = client.post(
        "/auth/login",
        json={"username": "admin", "password": "nope-nope-nope"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_login_rejects_unknown_user(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/auth/login",
        json={"username": "ghost", "password": "P@ssw0rd"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"
