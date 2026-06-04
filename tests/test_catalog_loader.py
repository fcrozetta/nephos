from pathlib import Path

import pytest
from catalog_fixtures import write_app, write_service

from nephos_api.catalog import (
    CatalogAmbiguousError,
    CatalogLoader,
    CatalogSourceNotFoundError,
    CatalogValidationError,
)


def test_catalog_loader_lists_normalized_app_and_service_summaries(
    tmp_path: Path,
) -> None:
    default_root = tmp_path / "default"
    write_app(default_root)
    write_service(default_root)

    loader = CatalogLoader((default_root,))

    apps = loader.list_apps()
    services = loader.list_services()

    assert apps == [
        {
            "kind": "App",
            "name": "paperless",
            "displayName": "Paperless",
            "description": "Document management",
            "version": "1.0.0",
            "source": "default",
            "manifestDigest": apps[0]["manifestDigest"],
            "requires": [
                {"capability": "postgres", "alias": "database", "provider": None}
            ],
            "routes": [
                {
                    "name": "web",
                    "visibility": "local",
                    "target": {"port": "http"},
                }
            ],
        }
    ]
    assert apps[0]["manifestDigest"].startswith("sha256:")
    assert services == [
        {
            "kind": "Service",
            "name": "postgres",
            "displayName": "PostgreSQL",
            "description": None,
            "version": None,
            "source": "default",
            "manifestDigest": services[0]["manifestDigest"],
            "provides": [
                {
                    "capability": "postgres",
                    "alias": "postgres",
                    "version": "16",
                    "bindingOutputTargets": ["app-secret"],
                }
            ],
        }
    ]


def test_catalog_loader_preserves_numeric_route_target_port(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "default" / "apps" / "paperless" / "app.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        """
apiVersion: nephos.pro/v1alpha1
kind: App
metadata:
  name: paperless
spec:
  routes:
    - name: web
      visibility: local
      target:
        port: 8080
  runtime:
    type: helm
    chart:
      repository: https://charts.example.test
      name: paperless
      version: "1.0.0"
""".strip()
    )
    loader = CatalogLoader((tmp_path / "default",))

    assert loader.list_apps()[0]["routes"] == [
        {
            "name": "web",
            "visibility": "local",
            "target": {"port": 8080},
        }
    ]


def test_catalog_loader_uses_local_source_ids(tmp_path: Path) -> None:
    default_root = tmp_path / "default"
    local_root = tmp_path / "local"
    write_app(local_root, name="paperless")

    loader = CatalogLoader((default_root, local_root))

    assert loader.get_app("paperless", source="local-1")["source"] == "local-1"


def test_catalog_loader_rejects_directory_and_manifest_name_mismatch(
    tmp_path: Path,
) -> None:
    default_root = tmp_path / "default"
    write_app(default_root / "bad-root", name="paperless")
    mismatched = default_root / "apps" / "mismatch" / "app.yaml"
    mismatched.parent.mkdir(parents=True)
    mismatched.write_text(
        """
apiVersion: nephos.pro/v1alpha1
kind: App
metadata:
  name: paperless
spec:
  runtime:
    type: helm
    chart:
      repository: https://charts.example.test
      name: paperless
      version: "1.0.0"
""".strip()
    )

    loader = CatalogLoader((default_root,))

    with pytest.raises(CatalogValidationError, match="directory slug"):
        loader.list_apps()


def test_catalog_loader_rejects_duplicate_app_binding_aliases(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "default" / "apps" / "paperless" / "app.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        """
apiVersion: nephos.pro/v1alpha1
kind: App
metadata:
  name: paperless
spec:
  requires:
    - capability: postgres
    - capability: postgres
  runtime:
    type: helm
    chart:
      repository: https://charts.example.test
      name: paperless
      version: "1.0.0"
""".strip()
    )
    loader = CatalogLoader((tmp_path / "default",))

    with pytest.raises(CatalogValidationError, match="duplicate binding alias"):
        loader.list_apps()


def test_catalog_loader_rejects_invalid_app_route_name(tmp_path: Path) -> None:
    manifest = tmp_path / "default" / "apps" / "paperless" / "app.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        """
apiVersion: nephos.pro/v1alpha1
kind: App
metadata:
  name: paperless
spec:
  routes:
    - name: Web
      visibility: local
      target:
        port: http
  runtime:
    type: helm
    chart:
      repository: https://charts.example.test
      name: paperless
      version: "1.0.0"
""".strip()
    )
    loader = CatalogLoader((tmp_path / "default",))

    with pytest.raises(CatalogValidationError, match="invalid route name"):
        loader.list_apps()


def test_catalog_loader_rejects_unsupported_route_visibility(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "default" / "apps" / "paperless" / "app.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        """
apiVersion: nephos.pro/v1alpha1
kind: App
metadata:
  name: paperless
spec:
  routes:
    - name: web
      visibility: public
      target:
        port: http
  runtime:
    type: helm
    chart:
      repository: https://charts.example.test
      name: paperless
      version: "1.0.0"
""".strip()
    )
    loader = CatalogLoader((tmp_path / "default",))

    with pytest.raises(CatalogValidationError, match="visibility"):
        loader.list_apps()


def test_catalog_loader_rejects_config_default_with_wrong_type(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "default" / "apps" / "paperless" / "app.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        """
apiVersion: nephos.pro/v1alpha1
kind: App
metadata:
  name: paperless
spec:
  config:
    options:
      - name: workers
        type: integer
        default: two
  runtime:
    type: helm
    chart:
      repository: https://charts.example.test
      name: paperless
      version: "1.0.0"
""".strip()
    )
    loader = CatalogLoader((tmp_path / "default",))

    with pytest.raises(CatalogValidationError, match="invalid config default"):
        loader.list_apps()


def test_catalog_loader_rejects_enum_config_without_values(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "default" / "apps" / "paperless" / "app.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        """
apiVersion: nephos.pro/v1alpha1
kind: App
metadata:
  name: paperless
spec:
  config:
    options:
      - name: schedule
        type: enum
        default: daily
  runtime:
    type: helm
    chart:
      repository: https://charts.example.test
      name: paperless
      version: "1.0.0"
""".strip()
    )
    loader = CatalogLoader((tmp_path / "default",))

    with pytest.raises(CatalogValidationError, match="enum config values"):
        loader.list_apps()


def test_catalog_loader_rejects_enum_config_default_outside_values(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "default" / "apps" / "paperless" / "app.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        """
apiVersion: nephos.pro/v1alpha1
kind: App
metadata:
  name: paperless
spec:
  config:
    options:
      - name: schedule
        type: enum
        default: yearly
        values:
          - value: daily
            label: Daily
          - value: weekly
            label: Weekly
  runtime:
    type: helm
    chart:
      repository: https://charts.example.test
      name: paperless
      version: "1.0.0"
""".strip()
    )
    loader = CatalogLoader((tmp_path / "default",))

    with pytest.raises(CatalogValidationError, match="invalid enum default"):
        loader.list_apps()


def test_catalog_loader_accepts_provider_runtime_without_helm_chart(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "default" / "services" / "postgres" / "service.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        """
apiVersion: nephos.pro/v1alpha1
kind: Service
metadata:
  name: postgres
  displayName: PostgreSQL
spec:
  provides:
    - capability: postgres
      as: postgres
      version: "16"
  bindings:
    outputs:
      - name: connection
        target: app-secret
  provisioning:
    mode: app-scoped-resource
  operations: []
  runtime:
    type: provider
    provider:
      name: postgres
""".strip()
    )
    loader = CatalogLoader((tmp_path / "default",))

    assert loader.list_services()[0]["name"] == "postgres"


def test_catalog_loader_rejects_provider_metadata_on_helm_runtime(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "default" / "apps" / "paperless" / "app.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        """
apiVersion: nephos.pro/v1alpha1
kind: App
metadata:
  name: paperless
spec:
  runtime:
    type: helm
    chart:
      repository: https://charts.example.test
      name: paperless
      version: "1.0.0"
    provider:
      name: paperless-provider
""".strip()
    )
    loader = CatalogLoader((tmp_path / "default",))

    with pytest.raises(CatalogValidationError, match="must not define provider"):
        loader.list_apps()


def test_catalog_loader_requires_source_for_ambiguous_duplicates(
    tmp_path: Path,
) -> None:
    default_root = tmp_path / "default"
    local_root = tmp_path / "local"
    write_app(default_root)
    write_app(local_root)

    loader = CatalogLoader((default_root, local_root))

    with pytest.raises(CatalogAmbiguousError) as exc_info:
        loader.get_app("paperless")

    assert exc_info.value.kind == "App"
    assert exc_info.value.name == "paperless"
    assert exc_info.value.sources == ["default", "local-1"]


def test_catalog_loader_rejects_unknown_source(tmp_path: Path) -> None:
    loader = CatalogLoader((tmp_path / "default",))

    with pytest.raises(CatalogSourceNotFoundError) as exc_info:
        loader.get_service("postgres", source="missing")

    assert exc_info.value.source == "missing"
