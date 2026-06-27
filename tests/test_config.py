import os
from pathlib import Path

import pytest

from nephos_api.config import (
    DEFAULT_CORE_REGISTRY_URL,
    ManagedCatalogRegistry,
    Settings,
    load_settings,
)


def test_load_settings_uses_default_paths(tmp_path: Path) -> None:
    settings = load_settings(environ={}, cwd=tmp_path)

    assert settings.db_path == tmp_path / ".nephos" / "state" / "nephos.db"
    core_registry_path = tmp_path / ".nephos" / "registries" / "core-registry"
    assert settings.catalog_roots == (core_registry_path,)
    assert settings.managed_catalog_registries == (
        ManagedCatalogRegistry(
            name="core-registry",
            url=DEFAULT_CORE_REGISTRY_URL,
            path=core_registry_path,
        ),
    )
    assert settings.kubeconfig is None
    assert settings.kube_context is None
    assert settings.internal_domain == "nephos.local"
    assert settings.ingress_class is None


def test_load_settings_uses_environment_overrides(tmp_path: Path) -> None:
    first_catalog = tmp_path / "catalog-a"
    second_catalog = tmp_path / "catalog-b"
    db_path = tmp_path / "state" / "custom.db"

    settings = load_settings(
        environ={
            "NEPHOS_API_DB_PATH": str(db_path),
            "NEPHOS_API_CATALOG_ROOTS": f"{first_catalog}:{second_catalog}",
            "NEPHOS_API_KUBECONFIG": str(tmp_path / "kubeconfig"),
            "NEPHOS_API_KUBE_CONTEXT": "nephos-dev",
            "NEPHOS_API_INTERNAL_DOMAIN": "nephos.localhost",
            "NEPHOS_API_INGRESS_CLASS": "nginx",
        },
        cwd=tmp_path,
    )

    assert settings == Settings(
        db_path=db_path,
        catalog_roots=(first_catalog, second_catalog),
        kubeconfig=tmp_path / "kubeconfig",
        kube_context="nephos-dev",
        internal_domain="nephos.localhost",
        ingress_class="nginx",
        managed_catalog_registries=(),
    )


def test_load_settings_reads_dotenv_from_cwd(tmp_path: Path) -> None:
    first_catalog = tmp_path / "catalog-a"
    second_catalog = tmp_path / "catalog-b"
    db_path = tmp_path / "state" / "dotenv.db"
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                f"NEPHOS_API_DB_PATH={db_path}",
                f"NEPHOS_API_CATALOG_ROOTS={first_catalog}:{second_catalog}",
                f"NEPHOS_API_KUBECONFIG={tmp_path / 'kubeconfig'}",
                "NEPHOS_API_KUBE_CONTEXT=docker-desktop",
                "NEPHOS_API_INTERNAL_DOMAIN=nephos.localhost",
                "NEPHOS_API_INGRESS_CLASS=nginx",
                "PULUMI_CONFIG_PASSPHRASE=local-dev",
            ]
        )
    )

    settings = load_settings(environ={}, cwd=tmp_path)

    assert settings == Settings(
        db_path=db_path,
        catalog_roots=(first_catalog, second_catalog),
        kubeconfig=tmp_path / "kubeconfig",
        kube_context="docker-desktop",
        internal_domain="nephos.localhost",
        ingress_class="nginx",
        managed_catalog_registries=(),
    )


def test_environment_overrides_dotenv(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "NEPHOS_API_KUBE_CONTEXT=from-dotenv",
                "NEPHOS_API_DB_PATH=.nephos/from-dotenv.db",
            ]
        )
    )

    settings = load_settings(
        environ={
            "NEPHOS_API_KUBE_CONTEXT": "from-environment",
            "NEPHOS_API_DB_PATH": ".nephos/from-environment.db",
        },
        cwd=tmp_path,
    )

    assert settings.kube_context == "from-environment"
    assert settings.db_path == tmp_path / ".nephos" / "from-environment.db"



def test_configured_catalog_roots_are_the_complete_catalog_dependency_set(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "nephos"
    registry_root = repo_root / "../core-registry"

    settings = load_settings(
        environ={"NEPHOS_API_CATALOG_ROOTS": "../core-registry"},
        cwd=repo_root,
    )

    assert settings.catalog_roots == (registry_root,)
    assert settings.managed_catalog_registries == ()


def test_default_core_registry_url_and_path_can_be_overridden(tmp_path: Path) -> None:
    registry_path = tmp_path / "managed" / "core-registry"

    settings = load_settings(
        environ={
            "NEPHOS_API_CORE_REGISTRY_URL": "https://example.test/core-registry.git",
            "NEPHOS_API_CORE_REGISTRY_PATH": str(registry_path),
        },
        cwd=tmp_path,
    )

    assert settings.catalog_roots == (registry_path,)
    assert settings.managed_catalog_registries == (
        ManagedCatalogRegistry(
            name="core-registry",
            url="https://example.test/core-registry.git",
            path=registry_path,
        ),
    )


def test_load_settings_adds_dotenv_values_to_process_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("PULUMI_CONFIG_PASSPHRASE", raising=False)
    (tmp_path / ".env").write_text("PULUMI_CONFIG_PASSPHRASE=local-dev\n")

    load_settings(cwd=tmp_path)

    assert os.environ["PULUMI_CONFIG_PASSPHRASE"] == "local-dev"
