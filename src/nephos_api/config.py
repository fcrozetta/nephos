from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    db_path: Path
    catalog_roots: tuple[Path, ...]
    kubeconfig: Path | None
    kube_context: str | None
    internal_domain: str = "nephos.local"
    ingress_class: str | None = None


def load_settings(
    *,
    environ: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> Settings:
    base_path = Path.cwd() if cwd is None else cwd
    env = load_environment(environ=environ, cwd=base_path)

    db_path = _resolve_path(
        env.get("NEPHOS_API_DB_PATH", ".nephos/state/nephos.db"),
        cwd=base_path,
    )
    catalog_roots = (base_path / "catalog",) + tuple(
        _resolve_path(entry, cwd=base_path)
        for entry in env.get("NEPHOS_API_CATALOG_ROOTS", "").split(os.pathsep)
        if entry
    )
    kubeconfig = env.get("NEPHOS_API_KUBECONFIG")

    return Settings(
        db_path=db_path,
        catalog_roots=catalog_roots,
        kubeconfig=_resolve_path(kubeconfig, cwd=base_path) if kubeconfig else None,
        kube_context=env.get("NEPHOS_API_KUBE_CONTEXT") or None,
        internal_domain=env.get("NEPHOS_API_INTERNAL_DOMAIN", "nephos.local"),
        ingress_class=env.get("NEPHOS_API_INGRESS_CLASS") or None,
    )


def load_environment(
    *,
    environ: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> dict[str, str]:
    base_path = Path.cwd() if cwd is None else cwd
    dotenv_values = (
        {}
        if environ is not None and cwd is None
        else _read_dotenv(base_path / ".env")
    )
    process_env = os.environ if environ is None else environ
    env = {**dotenv_values, **dict(process_env)}
    if environ is None:
        for key, value in dotenv_values.items():
            os.environ.setdefault(key, value)
        env = dict(os.environ)
    return env


def _resolve_path(value: str, *, cwd: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return cwd / path


def _read_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text().splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        if "=" not in line:
            raise ValueError(f"invalid .env line {line_number}: missing '='")
        key, value = line.split("=", 1)
        key = key.strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) is None:
            raise ValueError(f"invalid .env line {line_number}: invalid key")
        values[key] = _dotenv_value(value.strip())
    return values


def _dotenv_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
