import sqlite3
from pathlib import Path

from catalog_fixtures import write_app, write_service
from fastapi.testclient import TestClient

from nephos_api.config import Settings
from nephos_api.db import migrate_database
from nephos_api.main import create_app


def _client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "nephos.db"
    catalog_root = tmp_path / "catalog"
    write_app(catalog_root)
    write_service(catalog_root)
    return _client_with_catalog_roots(db_path, (catalog_root,))


def _client_with_catalog_roots(
    db_path: Path,
    catalog_roots: tuple[Path, ...],
) -> TestClient:
    migrate_database(db_path=db_path)
    app = create_app(
        settings=Settings(
            db_path=db_path,
            catalog_roots=catalog_roots,
            kubeconfig=None,
            kube_context=None,
        )
    )
    return TestClient(app)


def test_install_service_from_catalog_creates_desired_state(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/services",
        json={"catalogRef": {"kind": "Service", "name": "postgres"}},
    )

    body = response.json()
    assert response.status_code == 202
    assert body["resource"]["id"].startswith("svcinst_")
    assert body["resource"]["slug"] == "postgres"
    assert body["resource"]["kind"] == "Service"
    assert body["resource"]["lifecycle"] == "running"
    assert body["resource"]["catalogRef"] == {
        "kind": "Service",
        "name": "postgres",
        "source": "default",
        "version": None,
        "manifestDigest": body["resource"]["catalogRef"]["manifestDigest"],
    }
    assert body["resource"]["provides"] == [
        {
            "capability": "postgres",
            "alias": "postgres",
            "version": "16",
            "bindingOutputTargets": ["app-secret"],
        }
    ]
    assert body["resource"]["dependents"] == []
    assert body["reconciliation"]["id"].startswith("reconcile_")
    assert body["reconciliation"]["state"] == "pending"

    list_response = client.get("/services")
    assert list_response.status_code == 200
    assert list_response.json()["services"][0]["slug"] == "postgres"


def test_install_app_auto_binds_single_eligible_service(tmp_path: Path) -> None:
    client = _client(tmp_path)
    service = client.post(
        "/services",
        json={"catalogRef": {"kind": "Service", "name": "postgres"}},
    )
    assert service.status_code == 202

    response = client.post(
        "/apps",
        json={"catalogRef": {"kind": "App", "name": "paperless"}},
    )

    body = response.json()
    assert response.status_code == 202
    assert body["resource"]["slug"] == "paperless"
    assert body["resource"]["kind"] == "App"
    assert body["resource"]["bindings"][0]["id"].startswith("binding_")
    assert body["resource"]["bindings"][0]["alias"] == "database"
    assert body["resource"]["bindings"][0]["capability"] == "postgres"
    assert body["resource"]["bindings"][0]["serviceInstance"]["slug"] == "postgres"
    assert body["reconciliation"]["state"] == "pending"

    service_detail = client.get("/services/postgres").json()
    assert service_detail["dependents"] == [
        {
            "appInstance": "paperless",
            "bindingId": body["resource"]["bindings"][0]["id"],
            "bindingAlias": "database",
            "capability": "postgres",
            "lifecycle": "running",
            "status": None,
        }
    ]
    db_path = client.app.state.settings.db_path
    with sqlite3.connect(db_path) as connection:
        binding_requests = connection.execute(
            """
            SELECT target_type, target_id, action, state
            FROM reconciliation_requests
            WHERE target_type = 'binding'
            """
        ).fetchall()
    assert binding_requests == [
        (
            "binding",
            body["resource"]["bindings"][0]["id"],
            "reconcile",
            "pending",
        )
    ]


def test_install_app_uses_explicit_binding_provider_selection(
    tmp_path: Path,
) -> None:
    catalog_root = tmp_path / "catalog"
    write_app(catalog_root)
    write_service(catalog_root, name="postgres-main")
    write_service(catalog_root, name="postgres-lab")
    client = _client_with_catalog_roots(tmp_path / "nephos.db", (catalog_root,))
    assert client.post(
        "/services",
        json={"catalogRef": {"kind": "Service", "name": "postgres-main"}},
    ).status_code == 202
    assert client.post(
        "/services",
        json={"catalogRef": {"kind": "Service", "name": "postgres-lab"}},
    ).status_code == 202

    response = client.post(
        "/apps",
        json={
            "catalogRef": {"kind": "App", "name": "paperless"},
            "bindings": {
                "database": {
                    "serviceInstance": "postgres-lab",
                }
            },
        },
    )

    body = response.json()
    assert response.status_code == 202
    assert body["resource"]["bindings"][0]["alias"] == "database"
    assert body["resource"]["bindings"][0]["serviceInstance"]["slug"] == (
        "postgres-lab"
    )


def test_install_app_returns_unavailable_when_no_eligible_binding_provider(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/apps",
        json={"catalogRef": {"kind": "App", "name": "paperless"}},
    )

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "binding_provider_unavailable",
            "message": "No eligible Service provider exposes the required capability.",
            "details": {
                "alias": "database",
                "capability": "postgres",
                "eligibleProviders": [],
            },
        }
    }


def test_install_app_does_not_auto_bind_removed_service_provider(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    assert client.post(
        "/services",
        json={"catalogRef": {"kind": "Service", "name": "postgres"}},
    ).status_code == 202
    removed = client.post("/services/postgres/actions/remove", json={})

    response = client.post(
        "/apps",
        json={"catalogRef": {"kind": "App", "name": "paperless"}},
    )

    assert removed.status_code == 202
    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "binding_provider_unavailable",
            "message": "No eligible Service provider exposes the required capability.",
            "details": {
                "alias": "database",
                "capability": "postgres",
                "eligibleProviders": [],
            },
        }
    }


def test_install_app_rejects_removed_binding_provider_selection(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    assert client.post(
        "/services",
        json={"catalogRef": {"kind": "Service", "name": "postgres"}},
    ).status_code == 202
    removed = client.post("/services/postgres/actions/remove", json={})

    response = client.post(
        "/apps",
        json={
            "catalogRef": {"kind": "App", "name": "paperless"},
            "bindings": {
                "database": {
                    "serviceInstance": "postgres",
                }
            },
        },
    )

    assert removed.status_code == 202
    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "binding_provider_unavailable",
            "message": "Selected binding provider is not available.",
            "details": {
                "alias": "database",
                "capability": "postgres",
                "reason": "service_not_running",
                "lifecycle": "removed",
                "serviceInstance": "postgres",
            },
        }
    }


def test_install_app_rejects_pending_destroy_binding_provider_selection(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    assert client.post(
        "/services",
        json={"catalogRef": {"kind": "Service", "name": "postgres"}},
    ).status_code == 202
    destroyed = client.post(
        "/services/postgres/actions/destroy",
        json={"confirm": "destroy postgres"},
    )

    response = client.post(
        "/apps",
        json={
            "catalogRef": {"kind": "App", "name": "paperless"},
            "bindings": {
                "database": {
                    "serviceInstance": "postgres",
                }
            },
        },
    )

    assert destroyed.status_code == 202
    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "binding_provider_unavailable",
            "message": "Selected binding provider is not available.",
            "details": {
                "alias": "database",
                "capability": "postgres",
                "reason": "destroy_already_requested",
                "serviceInstance": "postgres",
            },
        }
    }


def test_install_app_returns_not_found_for_missing_explicit_binding_provider(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/apps",
        json={
            "catalogRef": {"kind": "App", "name": "paperless"},
            "bindings": {
                "database": {
                    "serviceInstance": "postgres-missing",
                }
            },
        },
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "binding_provider_not_found",
            "message": "Selected binding provider was not found.",
            "details": {
                "alias": "database",
                "serviceInstance": "postgres-missing",
            },
        }
    }


def test_install_app_rejects_ineligible_explicit_binding_provider(
    tmp_path: Path,
) -> None:
    catalog_root = tmp_path / "catalog"
    write_app(catalog_root)
    write_service(catalog_root, name="redis", capability="redis", version="7")
    client = _client_with_catalog_roots(tmp_path / "nephos.db", (catalog_root,))
    assert client.post(
        "/services",
        json={"catalogRef": {"kind": "Service", "name": "redis"}},
    ).status_code == 202

    response = client.post(
        "/apps",
        json={
            "catalogRef": {"kind": "App", "name": "paperless"},
            "bindings": {
                "database": {
                    "serviceInstance": "redis",
                }
            },
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "binding_provider_ineligible",
            "message": (
                "Selected binding provider does not expose the required "
                "capability."
            ),
            "details": {
                "alias": "database",
                "capability": "postgres",
                "serviceInstance": "redis",
                "eligibleProviders": [],
            },
        }
    }


def test_install_app_rejects_unknown_explicit_binding_alias(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/apps",
        json={
            "catalogRef": {"kind": "App", "name": "paperless"},
            "bindings": {
                "cache": {
                    "serviceInstance": "postgres",
                }
            },
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "binding_requirement_unknown",
            "message": "Binding selection does not match an App requirement.",
            "details": {
                "aliases": ["cache"],
            },
        }
    }


def test_install_app_rejects_unknown_config_keys(tmp_path: Path) -> None:
    catalog_root = tmp_path / "catalog"
    _write_configured_app(catalog_root)
    write_service(catalog_root)
    client = _client_with_catalog_roots(tmp_path / "nephos.db", (catalog_root,))
    assert client.post(
        "/services",
        json={"catalogRef": {"kind": "Service", "name": "postgres"}},
    ).status_code == 202

    response = client.post(
        "/apps",
        json={
            "catalogRef": {"kind": "App", "name": "paperless"},
            "config": {
                "unknown": "value",
            },
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "app_config_unknown",
            "message": "App config contains unknown option keys.",
            "details": {"keys": ["unknown"]},
        }
    }


def test_install_app_rejects_missing_required_config(tmp_path: Path) -> None:
    catalog_root = tmp_path / "catalog"
    _write_configured_app(catalog_root)
    write_service(catalog_root)
    client = _client_with_catalog_roots(tmp_path / "nephos.db", (catalog_root,))
    assert client.post(
        "/services",
        json={"catalogRef": {"kind": "Service", "name": "postgres"}},
    ).status_code == 202

    response = client.post(
        "/apps",
        json={"catalogRef": {"kind": "App", "name": "paperless"}},
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "app_config_required",
            "message": "App config is missing required option values.",
            "details": {"keys": ["admin-email"]},
        }
    }


def test_install_app_rejects_invalid_config_value_type(tmp_path: Path) -> None:
    catalog_root = tmp_path / "catalog"
    _write_configured_app(catalog_root)
    write_service(catalog_root)
    client = _client_with_catalog_roots(tmp_path / "nephos.db", (catalog_root,))
    assert client.post(
        "/services",
        json={"catalogRef": {"kind": "Service", "name": "postgres"}},
    ).status_code == 202

    response = client.post(
        "/apps",
        json={
            "catalogRef": {"kind": "App", "name": "paperless"},
            "config": {
                "admin-email": "fer@example.test",
                "workers": "two",
            },
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "app_config_invalid",
            "message": "App config value does not match the declared type.",
            "details": {
                "key": "workers",
                "expectedType": "integer",
            },
        }
    }


def test_install_app_rejects_invalid_enum_config_value(tmp_path: Path) -> None:
    catalog_root = tmp_path / "catalog"
    _write_configured_app(catalog_root)
    write_service(catalog_root)
    client = _client_with_catalog_roots(tmp_path / "nephos.db", (catalog_root,))
    assert client.post(
        "/services",
        json={"catalogRef": {"kind": "Service", "name": "postgres"}},
    ).status_code == 202

    response = client.post(
        "/apps",
        json={
            "catalogRef": {"kind": "App", "name": "paperless"},
            "config": {
                "admin-email": "fer@example.test",
                "schedule": "yearly",
            },
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "app_config_invalid",
            "message": "App config enum value is not allowed.",
            "details": {
                "key": "schedule",
                "allowedValues": ["daily", "weekly"],
            },
        }
    }


def test_service_stop_with_dependents_requires_force(tmp_path: Path) -> None:
    client = _client(tmp_path)
    assert client.post(
        "/services",
        json={"catalogRef": {"kind": "Service", "name": "postgres"}},
    ).status_code == 202
    app = client.post(
        "/apps",
        json={"catalogRef": {"kind": "App", "name": "paperless"}},
    )
    assert app.status_code == 202
    binding_id = app.json()["resource"]["bindings"][0]["id"]

    blocked = client.post("/services/postgres/actions/stop", json={})

    assert blocked.status_code == 409
    assert blocked.json() == {
        "error": {
            "code": "dependency_blocked",
            "message": "Service has dependent Apps.",
            "details": {
                "requiresForce": True,
                "dependents": [
                    {
                        "appInstance": "paperless",
                        "bindingId": binding_id,
                        "bindingAlias": "database",
                        "capability": "postgres",
                    }
                ],
            },
        }
    }

    forced = client.post("/services/postgres/actions/stop", json={"force": True})

    assert forced.status_code == 202
    assert forced.json()["resource"]["lifecycle"] == "stopped"
    assert forced.json()["reconciliation"]["state"] == "pending"


def _write_configured_app(root: Path) -> Path:
    path = root / "apps" / "paperless" / "app.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
apiVersion: nephos.pro/v1alpha1
kind: App
metadata:
  name: paperless
spec:
  requires:
    - capability: postgres
      as: database
  config:
    options:
      - name: admin-email
        type: string
        required: true
      - name: workers
        type: integer
        default: 1
      - name: schedule
        type: enum
        default: daily
        values:
          - value: daily
            label: Daily
          - value: weekly
            label: Weekly
      - name: enable-ocr
        type: boolean
        default: true
  runtime:
    type: helm
    chart:
      repository: https://charts.example.test
      name: paperless
      version: "1.0.0"
    values:
      mappings: []
""".strip()
    )
    return path


def test_install_service_returns_ambiguous_catalog_error(tmp_path: Path) -> None:
    default_root = tmp_path / "default"
    local_root = tmp_path / "local"
    write_service(default_root)
    write_service(local_root)
    client = _client_with_catalog_roots(
        tmp_path / "nephos.db",
        (default_root, local_root),
    )

    response = client.post(
        "/services",
        json={"catalogRef": {"kind": "Service", "name": "postgres"}},
    )

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "catalog_entry_ambiguous",
            "message": "Catalog entry is ambiguous.",
            "details": {
                "kind": "Service",
                "name": "postgres",
                "sources": ["default", "local-1"],
            },
        }
    }


def test_install_app_returns_missing_catalog_source_error(tmp_path: Path) -> None:
    catalog_root = tmp_path / "catalog"
    write_app(catalog_root)
    client = _client_with_catalog_roots(tmp_path / "nephos.db", (catalog_root,))

    response = client.post(
        "/apps",
        json={
            "catalogRef": {
                "kind": "App",
                "name": "paperless",
                "source": "local-9",
            }
        },
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "catalog_source_not_found",
            "message": "Catalog source was not found.",
            "details": {"source": "local-9"},
        }
    }
