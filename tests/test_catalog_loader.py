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
                {
                    "capability": "postgres",
                    "protocol": None,
                    "alias": "database",
                    "provider": None,
                }
            ],
            "routes": [
                {
                    "name": "web",
                    "visibility": "local",
                    "target": {"port": "http"},
                }
            ],
            "config": {"options": []},
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
            "requires": [],
            "provides": [
                {
                    "capability": "postgres",
                    "protocol": None,
                    "alias": "postgres",
                    "version": "16",
                    "bindingOutputTargets": ["app-secret"],
                }
            ],
            "config": {"options": []},
        }
    ]


def test_catalog_loader_exposes_protocol_and_defaults_alias_from_capability_protocol(
    tmp_path: Path,
) -> None:
    default_root = tmp_path / "default"
    write_app(default_root, capability="sql", protocol="postgres", alias=None)
    write_service(
        default_root,
        capability="sql",
        protocol="postgres",
        alias=None,
    )

    loader = CatalogLoader((default_root,))

    app = loader.get_app("paperless")
    service = loader.get_service("postgres")

    assert app["requires"] == [
        {
            "capability": "sql",
            "protocol": "postgres",
            "alias": "sql-postgres",
            "provider": None,
        }
    ]
    assert service["provides"] == [
        {
            "capability": "sql",
            "protocol": "postgres",
            "alias": "sql-postgres",
            "version": "16",
            "bindingOutputTargets": ["app-secret"],
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


@pytest.mark.parametrize("target_port", [0, -1, 65536, 70000])
def test_catalog_loader_rejects_invalid_numeric_route_target_port(
    tmp_path: Path,
    target_port: int,
) -> None:
    manifest = tmp_path / "default" / "apps" / "paperless" / "app.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        f"""
apiVersion: nephos.pro/v1alpha1
kind: App
metadata:
  name: paperless
spec:
  routes:
    - name: web
      visibility: local
      target:
        port: {target_port}
  runtime:
    type: helm
    chart:
      repository: https://charts.example.test
      name: paperless
      version: "1.0.0"
""".strip()
    )
    loader = CatalogLoader((tmp_path / "default",))

    with pytest.raises(CatalogValidationError, match="route target port"):
        loader.list_apps()


def test_catalog_loader_rejects_boolean_route_target_port(
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
        port: true
  runtime:
    type: helm
    chart:
      repository: https://charts.example.test
      name: paperless
      version: "1.0.0"
""".strip()
    )
    loader = CatalogLoader((tmp_path / "default",))

    with pytest.raises(CatalogValidationError, match="route target port"):
        loader.list_apps()


def test_catalog_loader_uses_local_source_ids(tmp_path: Path) -> None:
    default_root = tmp_path / "default"
    local_root = tmp_path / "local"
    write_app(local_root, name="paperless")

    loader = CatalogLoader((default_root, local_root))

    assert loader.get_app("paperless", source="local-1")["source"] == "local-1"


def test_catalog_loader_accepts_named_source_ids(tmp_path: Path) -> None:
    core_root = tmp_path / "core-registry"
    mythos_root = tmp_path / "mythos-registry"
    write_service(core_root, name="postgres")
    write_service(mythos_root, name="mythos-mail-ingress")

    loader = CatalogLoader(
        (core_root, mythos_root),
        source_ids=("core-registry", "mythos-registry"),
    )

    assert (
        loader.get_service("postgres", source="core-registry")["source"]
        == "core-registry"
    )
    assert (
        loader.get_service(
            "mythos-mail-ingress",
            source="mythos-registry",
        )["source"]
        == "mythos-registry"
    )


def test_catalog_loader_rejects_source_id_count_mismatch(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="source id count"):
        CatalogLoader(
            (tmp_path / "core-registry",),
            source_ids=("core-registry", "extra"),
        )


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


def test_catalog_loader_rejects_app_requirement_entitlements(
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
      entitlements: [admin-credentials]
  runtime:
    type: helm
    chart:
      repository: https://charts.example.test
      name: paperless
      version: "1.0.0"
""".strip()
    )
    loader = CatalogLoader((tmp_path / "default",))

    with pytest.raises(CatalogValidationError, match="entitlements"):
        loader.list_apps()


def test_catalog_loader_allows_same_capability_with_distinct_protocol_aliases(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "default" / "apps" / "graph-app" / "app.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        """
apiVersion: nephos.pro/v1alpha1
kind: App
metadata:
  name: graph-app
spec:
  requires:
    - capability: opencypher
      protocol: bolt
    - capability: opencypher
      protocol: n4j
  runtime:
    type: helm
    chart:
      repository: https://charts.example.test
      name: graph-app
      version: "1.0.0"
""".strip()
    )
    loader = CatalogLoader((tmp_path / "default",))

    assert loader.get_app("graph-app")["requires"] == [
        {
            "capability": "opencypher",
            "protocol": "bolt",
            "alias": "opencypher-bolt",
            "provider": None,
        },
        {
            "capability": "opencypher",
            "protocol": "n4j",
            "alias": "opencypher-n4j",
            "provider": None,
        },
    ]


def test_catalog_loader_allows_same_provided_capability_with_distinct_protocol_aliases(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "default" / "services" / "arcadedb" / "service.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        """
apiVersion: nephos.pro/v1alpha1
kind: Service
metadata:
  name: arcadedb
spec:
  provides:
    - capability: opencypher
      protocol: bolt
    - capability: opencypher
      protocol: n4j
  provisioning:
    mode: app-scoped-resource
  runtime:
    type: provider
    provider:
      name: arcadedb
""".strip()
    )
    loader = CatalogLoader((tmp_path / "default",))

    assert loader.get_service("arcadedb")["provides"] == [
        {
            "capability": "opencypher",
            "protocol": "bolt",
            "alias": "opencypher-bolt",
            "version": None,
            "bindingOutputTargets": [],
        },
        {
            "capability": "opencypher",
            "protocol": "n4j",
            "alias": "opencypher-n4j",
            "version": None,
            "bindingOutputTargets": [],
        },
    ]


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


def test_catalog_loader_rejects_binding_alias_that_exceeds_secret_name_limit(
    tmp_path: Path,
) -> None:
    alias = "a" * 52
    manifest = tmp_path / "default" / "apps" / "paperless" / "app.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        f"""
apiVersion: nephos.pro/v1alpha1
kind: App
metadata:
  name: paperless
spec:
  requires:
    - capability: postgres
      as: {alias}
  runtime:
    type: helm
    chart:
      repository: https://charts.example.test
      name: paperless
      version: "1.0.0"
""".strip()
    )
    loader = CatalogLoader((tmp_path / "default",))

    with pytest.raises(CatalogValidationError, match="binding alias"):
        loader.list_apps()


def test_catalog_loader_rejects_route_name_that_exceeds_ingress_name_limit(
    tmp_path: Path,
) -> None:
    route_name = "r" * 51
    manifest = tmp_path / "default" / "apps" / "paperless" / "app.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        f"""
apiVersion: nephos.pro/v1alpha1
kind: App
metadata:
  name: paperless
spec:
  routes:
    - name: {route_name}
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

    with pytest.raises(CatalogValidationError, match="route name"):
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


def test_catalog_loader_accepts_service_config_options(
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
spec:
  provides:
    - capability: sql
      protocol: postgres
  config:
    options:
      - name: storage-size
        type: string
        default: 1Gi
      - name: enable-backups
        type: boolean
        default: false
      - name: profile
        type: enum
        default: dev
        values:
          - value: dev
            label: Development
          - value: prod
            label: Production
  provisioning:
    mode: app-scoped-resource
  runtime:
    type: provider
    provider:
      name: postgres
""".strip()
    )
    loader = CatalogLoader((tmp_path / "default",))

    assert loader.get_service("postgres")["provides"][0]["capability"] == "sql"


def test_catalog_loader_rejects_service_config_default_with_wrong_type(
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
spec:
  provides:
    - capability: sql
      protocol: postgres
  config:
    options:
      - name: replicas
        type: integer
        default: two
  provisioning:
    mode: app-scoped-resource
  runtime:
    type: provider
    provider:
      name: postgres
""".strip()
    )
    loader = CatalogLoader((tmp_path / "default",))

    with pytest.raises(CatalogValidationError, match="invalid config default"):
        loader.list_services()


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


def test_catalog_loader_rejects_generate_on_non_string_option(
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
        generate:
          kind: password
          length: 32
  runtime:
    type: helm
    chart:
      repository: https://charts.example.test
      name: paperless
      version: "1.0.0"
""".strip()
    )
    loader = CatalogLoader((tmp_path / "default",))

    with pytest.raises(CatalogValidationError, match="not a string"):
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
