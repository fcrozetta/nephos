import os
from pathlib import Path

import pytest

from nephos_api.config import Settings, load_settings


def test_load_settings_uses_default_paths(tmp_path: Path) -> None:
    settings = load_settings(environ={}, cwd=tmp_path)

    assert settings.db_path == tmp_path / ".nephos" / "state" / "nephos.db"
    assert settings.catalog_roots == (tmp_path / "catalog",)
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
        catalog_roots=(tmp_path / "catalog", first_catalog, second_catalog),
        kubeconfig=tmp_path / "kubeconfig",
        kube_context="nephos-dev",
        internal_domain="nephos.localhost",
        ingress_class="nginx",
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
        catalog_roots=(tmp_path / "catalog", first_catalog, second_catalog),
        kubeconfig=tmp_path / "kubeconfig",
        kube_context="docker-desktop",
        internal_domain="nephos.localhost",
        ingress_class="nginx",
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


def test_load_settings_adds_dotenv_values_to_process_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("PULUMI_CONFIG_PASSPHRASE", raising=False)
    (tmp_path / ".env").write_text("PULUMI_CONFIG_PASSPHRASE=local-dev\n")

    load_settings(cwd=tmp_path)

    assert os.environ["PULUMI_CONFIG_PASSPHRASE"] == "local-dev"
