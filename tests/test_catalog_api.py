from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nephos_api.config import Settings
from nephos_api.main import create_app

pytestmark = pytest.mark.unit


def _client(default_root, *extra_roots) -> TestClient:
    settings = Settings(repo_catalog_root=default_root, extra_catalog_roots=tuple(extra_roots))
    return TestClient(create_app(settings))


def _write_app(root, name="paperless", *, display_name="Paperless"):
    path = root / "apps" / name / "app.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""
apiVersion: nephos.pro/v1alpha1
kind: App
metadata:
  name: {name}
  displayName: {display_name}
  description: Document management for scanned and digital documents.
  version: 0.0.1
spec:
  requires:
    - capability: postgres
      as: database
  routes:
    - name: web
      visibility: local
      target:
        port: http
  runtime:
    type: helm
    chart:
      repository: https://charts.example.invalid/paperless
      name: paperless
      version: 1.2.3
    values:
      mappings: []
  config:
    options: []
""".lstrip()
    )
    return path


def _write_service(root, name="postgres"):
    path = root / "services" / name / "service.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""
apiVersion: nephos.pro/v1alpha1
kind: Service
metadata:
  name: {name}
  displayName: PostgreSQL
  description: Relational database Service exposing the postgres capability.
  version: 0.0.1
spec:
  provides:
    - capability: postgres
      as: database
      version: "16"
  bindings:
    outputs:
      - name: connection
        target: app-secret
  provisioning:
    mode: app-scoped-resource
  runtime:
    type: helm
    chart:
      repository: https://charts.example.invalid/postgres
      name: postgresql
      version: 16.0.0
    values:
      mappings: []
  operations: []
""".lstrip()
    )
    return path


def test_catalog_lists_apps_from_default_source(tmp_path):
    _write_app(tmp_path)
    client = _client(tmp_path)

    response = client.get("/catalog/apps")

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["kind"] == "App"
    assert item["name"] == "paperless"
    assert item["source"] == "default"
    assert item["manifestDigest"]
    assert item["requires"] == [{"capability": "postgres", "alias": "database"}]
    assert item["routes"] == [
        {"name": "web", "visibility": "local", "target": {"port": "http"}}
    ]


def test_catalog_gets_service_summary(tmp_path):
    _write_service(tmp_path)
    client = _client(tmp_path)

    response = client.get("/catalog/services/postgres")

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "Service"
    assert body["name"] == "postgres"
    assert body["source"] == "default"
    assert body["provides"] == [
        {
            "capability": "postgres",
            "alias": "database",
            "version": "16",
            "bindingOutputTargets": ["app-secret"],
        }
    ]


def test_catalog_detail_duplicate_requires_source_selection(tmp_path):
    default_root = tmp_path / "default"
    local_root = tmp_path / "local"
    _write_app(default_root, display_name="Default Paperless")
    _write_app(local_root, display_name="Local Paperless")
    client = _client(default_root, local_root)

    ambiguous = client.get("/catalog/apps/paperless")

    assert ambiguous.status_code == 409
    assert ambiguous.json()["error"]["code"] == "catalog_entry_ambiguous"
    assert ambiguous.json()["error"]["details"]["sources"] == ["default", "local-1"]

    selected = client.get("/catalog/apps/paperless?source=local-1")
    assert selected.status_code == 200
    assert selected.json()["displayName"] == "Local Paperless"
    assert selected.json()["source"] == "local-1"


def test_catalog_list_can_filter_by_source(tmp_path):
    default_root = tmp_path / "default"
    local_root = tmp_path / "local"
    _write_app(default_root, "paperless")
    _write_app(local_root, "immich", display_name="Immich")
    client = _client(default_root, local_root)

    response = client.get("/catalog/apps?source=local-1")

    assert response.status_code == 200
    assert [item["name"] for item in response.json()["items"]] == ["immich"]


def test_catalog_unknown_source_uses_nephos_error(tmp_path):
    client = _client(tmp_path)

    response = client.get("/catalog/apps?source=local-9")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "catalog_source_not_found"


def test_catalog_missing_entry_uses_nephos_error(tmp_path):
    client = _client(tmp_path)

    response = client.get("/catalog/services/postgres")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "catalog_entry_not_found"


def test_catalog_rejects_directory_slug_mismatch(tmp_path):
    path = tmp_path / "apps" / "paperless" / "app.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
apiVersion: nephos.pro/v1alpha1
kind: App
metadata:
  name: not-paperless
spec:
  runtime:
    type: helm
    chart:
      repository: https://charts.example.invalid/paperless
      name: paperless
      version: 1.2.3
""".lstrip()
    )
    client = _client(tmp_path)

    response = client.get("/catalog/apps")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "catalog_manifest_invalid"


def test_catalog_rejects_unknown_manifest_fields(tmp_path):
    path = _write_app(tmp_path)
    path.write_text(path.read_text() + "unexpected: true\n")
    client = _client(tmp_path)

    response = client.get("/catalog/apps/paperless")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "catalog_manifest_invalid"
