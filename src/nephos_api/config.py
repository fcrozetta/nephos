from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DB_PATH = Path(".nephos/state/nephos.db")
DEFAULT_REPO_CATALOG_ROOT = Path("catalog")


@dataclass(frozen=True)
class Settings:
    db_path: Path = DEFAULT_DB_PATH
    repo_catalog_root: Path = DEFAULT_REPO_CATALOG_ROOT
    extra_catalog_roots: tuple[Path, ...] = ()
    kubeconfig: Path | None = None
    kube_context: str | None = None
    runtime_mode: str = "shell"
    helm_timeout: str = "10m"


def _parse_path_list(raw: str | None) -> tuple[Path, ...]:
    if not raw:
        return ()
    return tuple(Path(part) for part in raw.split(os.pathsep) if part)


def get_settings() -> Settings:
    db_path = Path(os.environ.get("NEPHOS_API_DB_PATH", DEFAULT_DB_PATH))
    kubeconfig_raw = os.environ.get("NEPHOS_API_KUBECONFIG")
    return Settings(
        db_path=db_path,
        extra_catalog_roots=_parse_path_list(os.environ.get("NEPHOS_API_CATALOG_ROOTS")),
        kubeconfig=Path(kubeconfig_raw) if kubeconfig_raw else None,
        kube_context=os.environ.get("NEPHOS_API_KUBE_CONTEXT") or None,
        runtime_mode=os.environ.get("NEPHOS_API_RUNTIME_MODE", "shell"),
        helm_timeout=os.environ.get("NEPHOS_API_HELM_TIMEOUT", "10m"),
    )
