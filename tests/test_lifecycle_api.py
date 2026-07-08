import sqlite3
from pathlib import Path

from catalog_fixtures import write_app, write_service
from fastapi.testclient import TestClient

from nephos_api.config import Settings
from nephos_api.db import migrate_database
from nephos_api.main import create_app


def _client_with_installed_app(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "nephos.db"
    catalog_root = tmp_path / "catalog"
    write_app(catalog_root)
    write_service(catalog_root)
    migrate_database(db_path=db_path)
    app = create_app(
        settings=Settings(
            db_path=db_path,
            catalog_roots=(catalog_root,),
            kubeconfig=None,
            kube_context=None,
        )
    )
    client = TestClient(app)
    assert (
        client.post(
            "/services",
            json={"catalogRef": {"kind": "Service", "name": "postgres"}},
        ).status_code
        == 202
    )
    assert (
        client.post(
            "/apps",
            json={"catalogRef": {"kind": "App", "name": "paperless"}},
        ).status_code
        == 202
    )
    return client


def _client_with_installed_service(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "nephos.db"
    catalog_root = tmp_path / "catalog"
    write_service(catalog_root)
    migrate_database(db_path=db_path)
    app = create_app(
        settings=Settings(
            db_path=db_path,
            catalog_roots=(catalog_root,),
            kubeconfig=None,
            kube_context=None,
        )
    )
    client = TestClient(app)
    assert (
        client.post(
            "/services",
            json={"catalogRef": {"kind": "Service", "name": "postgres"}},
        ).status_code
        == 202
    )
    return client


def _generation(client: TestClient, *, table: str, slug: str) -> int:
    with sqlite3.connect(client.app.state.settings.db_path) as connection:
        return int(
            connection.execute(
                f"SELECT generation FROM {table} WHERE slug = ?",
                (slug,),
            ).fetchone()[0]
        )


def test_app_stop_start_remove_and_reconcile_create_requests(tmp_path: Path) -> None:
    client = _client_with_installed_app(tmp_path)

    stop = client.post("/apps/paperless/actions/stop", json={})
    start = client.post("/apps/paperless/actions/start", json={})
    remove = client.post("/apps/paperless/actions/remove", json={})
    reconcile = client.post("/apps/paperless/actions/reconcile", json={})

    assert stop.status_code == 202
    assert stop.json()["resource"]["lifecycle"] == "stopped"
    assert start.status_code == 202
    assert start.json()["resource"]["lifecycle"] == "running"
    assert remove.status_code == 202
    assert remove.json()["resource"]["lifecycle"] == "removed"
    assert reconcile.status_code == 202
    assert reconcile.json()["resource"]["lifecycle"] == "removed"
    assert reconcile.json()["reconciliation"]["state"] == "pending"


def test_app_lifecycle_actions_are_idempotent_for_current_desired_state(
    tmp_path: Path,
) -> None:
    client = _client_with_installed_app(tmp_path)
    initial_generation = _generation(client, table="app_instances", slug="paperless")

    already_running = client.post("/apps/paperless/actions/start", json={})
    after_already_running_generation = _generation(
        client,
        table="app_instances",
        slug="paperless",
    )
    stopped = client.post("/apps/paperless/actions/stop", json={})
    stopped_generation = _generation(
        client,
        table="app_instances",
        slug="paperless",
    )
    already_stopped = client.post("/apps/paperless/actions/stop", json={})

    assert already_running.status_code == 202
    assert after_already_running_generation == initial_generation
    assert stopped.status_code == 202
    assert already_stopped.status_code == 202
    assert _generation(client, table="app_instances", slug="paperless") == (
        stopped_generation
    )
    assert already_stopped.json()["resource"]["lifecycle"] == "stopped"


def test_service_lifecycle_actions_are_idempotent_for_current_desired_state(
    tmp_path: Path,
) -> None:
    client = _client_with_installed_service(tmp_path)
    initial_generation = _generation(
        client,
        table="service_instances",
        slug="postgres",
    )

    already_running = client.post("/services/postgres/actions/start", json={})
    after_already_running_generation = _generation(
        client,
        table="service_instances",
        slug="postgres",
    )
    removed = client.post("/services/postgres/actions/remove", json={})
    removed_generation = _generation(
        client,
        table="service_instances",
        slug="postgres",
    )
    already_removed = client.post("/services/postgres/actions/remove", json={})

    assert already_running.status_code == 202
    assert after_already_running_generation == initial_generation
    assert removed.status_code == 202
    assert already_removed.status_code == 202
    assert _generation(client, table="service_instances", slug="postgres") == (
        removed_generation
    )
    assert already_removed.json()["resource"]["lifecycle"] == "removed"


def test_service_repeated_stop_with_dependents_is_idempotent_without_force(
    tmp_path: Path,
) -> None:
    client = _client_with_installed_app(tmp_path)
    stopped = client.post("/services/postgres/actions/stop", json={"force": True})
    stopped_generation = _generation(
        client,
        table="service_instances",
        slug="postgres",
    )

    repeated = client.post("/services/postgres/actions/stop", json={})

    assert stopped.status_code == 202
    assert repeated.status_code == 202
    assert repeated.json()["resource"]["lifecycle"] == "stopped"
    assert _generation(client, table="service_instances", slug="postgres") == (
        stopped_generation
    )


def test_service_repeated_remove_with_dependents_is_idempotent_without_force(
    tmp_path: Path,
) -> None:
    client = _client_with_installed_app(tmp_path)
    removed = client.post("/services/postgres/actions/remove", json={"force": True})
    removed_generation = _generation(
        client,
        table="service_instances",
        slug="postgres",
    )

    repeated = client.post("/services/postgres/actions/remove", json={})

    assert removed.status_code == 202
    assert repeated.status_code == 202
    assert repeated.json()["resource"]["lifecycle"] == "removed"
    assert _generation(client, table="service_instances", slug="postgres") == (
        removed_generation
    )


def test_service_repeated_destroy_with_dependents_is_idempotent_without_force(
    tmp_path: Path,
) -> None:
    client = _client_with_installed_app(tmp_path)
    destroyed = client.post(
        "/services/postgres/actions/destroy",
        json={"confirm": "destroy postgres", "force": True},
    )

    repeated = client.post(
        "/services/postgres/actions/destroy",
        json={"confirm": "destroy postgres"},
    )

    assert destroyed.status_code == 202
    assert repeated.status_code == 202
    assert (
        repeated.json()["resource"]["deleteRequestedAt"]
        == destroyed.json()["resource"]["deleteRequestedAt"]
    )


def test_destroy_requires_confirmation_and_keeps_desired_state_row(
    tmp_path: Path,
) -> None:
    client = _client_with_installed_app(tmp_path)

    missing = client.post("/apps/paperless/actions/destroy", json={})

    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "destructive_confirmation_required"

    destroyed = client.post(
        "/apps/paperless/actions/destroy",
        json={"confirm": "destroy paperless"},
    )

    assert destroyed.status_code == 202
    assert destroyed.json()["resource"]["slug"] == "paperless"
    assert destroyed.json()["resource"]["deleteRequestedAt"] is not None
    assert destroyed.json()["reconciliation"]["state"] == "pending"

    detail = client.get("/apps/paperless")
    assert detail.status_code == 200
    assert (
        detail.json()["deleteRequestedAt"]
        == destroyed.json()["resource"]["deleteRequestedAt"]
    )


def test_app_destroy_request_blocks_later_lifecycle_mutations(
    tmp_path: Path,
) -> None:
    client = _client_with_installed_app(tmp_path)
    destroyed = client.post(
        "/apps/paperless/actions/destroy",
        json={"confirm": "destroy paperless"},
    )

    blocked = client.post("/apps/paperless/actions/start", json={})
    repeated_destroy = client.post(
        "/apps/paperless/actions/destroy",
        json={"confirm": "destroy paperless"},
    )
    detail = client.get("/apps/paperless")

    assert destroyed.status_code == 202
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "destroy_already_requested"
    assert blocked.json()["error"]["details"] == {
        "action": "start",
        "deleteRequestedAt": destroyed.json()["resource"]["deleteRequestedAt"],
        "slug": "paperless",
    }
    assert repeated_destroy.status_code == 202
    assert (
        repeated_destroy.json()["resource"]["deleteRequestedAt"]
        == destroyed.json()["resource"]["deleteRequestedAt"]
    )
    assert detail.json()["lifecycle"] == "running"
    assert (
        detail.json()["deleteRequestedAt"]
        == destroyed.json()["resource"]["deleteRequestedAt"]
    )


def test_service_destroy_request_blocks_later_lifecycle_mutations(
    tmp_path: Path,
) -> None:
    client = _client_with_installed_app(tmp_path)
    destroyed = client.post(
        "/services/postgres/actions/destroy",
        json={"confirm": "destroy postgres", "force": True},
    )

    blocked = client.post("/services/postgres/actions/stop", json={})
    repeated_destroy = client.post(
        "/services/postgres/actions/destroy",
        json={"confirm": "destroy postgres", "force": True},
    )
    detail = client.get("/services/postgres")

    assert destroyed.status_code == 202
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "destroy_already_requested"
    assert blocked.json()["error"]["details"] == {
        "action": "stop",
        "deleteRequestedAt": destroyed.json()["resource"]["deleteRequestedAt"],
        "slug": "postgres",
    }
    assert repeated_destroy.status_code == 202
    assert (
        repeated_destroy.json()["resource"]["deleteRequestedAt"]
        == destroyed.json()["resource"]["deleteRequestedAt"]
    )
    assert detail.json()["lifecycle"] == "running"
    assert (
        detail.json()["deleteRequestedAt"]
        == destroyed.json()["resource"]["deleteRequestedAt"]
    )


def test_service_remove_with_dependents_requires_force(tmp_path: Path) -> None:
    client = _client_with_installed_app(tmp_path)

    blocked = client.post("/services/postgres/actions/remove", json={})
    forced = client.post("/services/postgres/actions/remove", json={"force": True})

    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "dependency_blocked"
    assert forced.status_code == 202
    assert forced.json()["resource"]["lifecycle"] == "removed"
