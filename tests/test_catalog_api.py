from pathlib import Path

from catalog_fixtures import write_app, write_service
from fastapi.testclient import TestClient

from nephos_api.config import Settings
from nephos_api.main import create_app


def _client(catalog_roots: tuple[Path, ...]) -> TestClient:
    app = create_app(
        settings=Settings(
            db_path=Path("/tmp/not-used.db"),
            catalog_roots=catalog_roots,
            kubeconfig=None,
            kube_context=None,
        )
    )
    return TestClient(app)


def test_catalog_api_lists_apps_and_services(tmp_path: Path) -> None:
    root = tmp_path / "default"
    write_app(root)
    write_service(root)
    client = _client((root,))

    apps = client.get("/catalog/apps")
    services = client.get("/catalog/services")

    assert apps.status_code == 200
    assert services.status_code == 200
    assert apps.json()["apps"][0]["name"] == "paperless"
    assert services.json()["services"][0]["name"] == "postgres"


def test_catalog_api_exposes_config_options_schema(tmp_path: Path) -> None:
    root = tmp_path / "default"
    path = root / "services" / "widget" / "service.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
apiVersion: nephos.pro/v1alpha1
kind: Service
metadata:
  name: widget
  displayName: Widget
spec:
  provides:
    - capability: sql
      protocol: postgres
      as: postgres
  config:
    options:
      - name: admin-password
        type: string
        required: true
        label: Admin password
      - name: mode
        type: enum
        default: standalone
        values:
          - value: standalone
          - value: replica
  provisioning:
    mode: app-scoped-resource
  operations: []
  runtime:
    type: provider
    provider:
      name: widget
""".strip()
    )
    client = _client((root,))

    response = client.get("/catalog/services/widget")

    assert response.status_code == 200
    options = {o["name"]: o for o in response.json()["config"]["options"]}
    assert options["admin-password"]["type"] == "string"
    assert options["admin-password"]["required"] is True
    assert options["mode"]["type"] == "enum"
    assert options["mode"]["default"] == "standalone"
    assert options["mode"]["values"] == [{"value": "standalone"}, {"value": "replica"}]


def test_catalog_api_returns_selected_detail(tmp_path: Path) -> None:
    default_root = tmp_path / "default"
    local_root = tmp_path / "local"
    write_app(default_root)
    write_app(local_root)
    client = _client((default_root, local_root))

    response = client.get("/catalog/apps/paperless?source=local-1")

    assert response.status_code == 200
    assert response.json()["source"] == "local-1"


def test_catalog_api_returns_invalid_app_name_error(tmp_path: Path) -> None:
    client = _client((tmp_path / "default",))

    response = client.get("/catalog/apps/Bad_Name")

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "catalog_name_invalid",
            "message": "Catalog name is invalid.",
            "details": {"name": "Bad_Name"},
        }
    }


def test_catalog_api_returns_invalid_service_name_error(tmp_path: Path) -> None:
    client = _client((tmp_path / "default",))

    response = client.get("/catalog/services/Bad_Name")

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "catalog_name_invalid",
            "message": "Catalog name is invalid.",
            "details": {"name": "Bad_Name"},
        }
    }


def test_catalog_api_returns_ambiguous_error(tmp_path: Path) -> None:
    default_root = tmp_path / "default"
    local_root = tmp_path / "local"
    write_service(default_root)
    write_service(local_root)
    client = _client((default_root, local_root))

    response = client.get("/catalog/services/postgres")

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


def test_catalog_api_returns_unknown_source_error(tmp_path: Path) -> None:
    client = _client((tmp_path / "default",))

    response = client.get("/catalog/apps/paperless?source=missing")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "catalog_source_not_found",
            "message": "Catalog source was not found.",
            "details": {"source": "missing"},
        }
    }
