import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CORE_REGISTRY_URL = "https://git.fcrozetta.app/nephos/core-registry.git"
DEFAULT_MYTHOS_REGISTRY_URL = "https://git.fcrozetta.app/nephos/mythos-registry.git"
DEFAULT_COMMUNITY_REGISTRY_URL = (
    "https://git.fcrozetta.app/nephos/community-registry.git"
)


@dataclass(frozen=True)
class ManagedCatalogRegistry:
    name: str
    url: str
    path: Path


@dataclass(frozen=True)
class Settings:
    db_path: Path
    catalog_roots: tuple[Path, ...]
    kubeconfig: Path | None
    kube_context: str | None
    internal_domain: str = "nephos.local"
    ingress_class: str | None = None
    managed_catalog_registries: tuple[ManagedCatalogRegistry, ...] = field(
        default_factory=tuple
    )
    catalog_source_ids: tuple[str, ...] = field(default_factory=tuple)
    # Environment identity (lcl | dev | prd). Defaults fail-closed to prd so that
    # LCL-only behavior (e.g. the insecure dev-mode openbao provider) is never
    # enabled unless the environment is explicitly declared lcl.
    env: str = "prd"
    # Second, explicit opt-in for the dev-mode openbao provider. Even in lcl it
    # stays off unless set, because dev mode ships a static root token.
    allow_dev_mode_openbao: bool = False
    # Deploy-time OpenBao access for the bao:// secret resolver.
    bao_address: str | None = None
    bao_token: str | None = None
    # Persistent (non-dev) openbao core service: StatefulSet + PVC + auto
    # init/unseal. When enabled it supersedes the dev-mode provider.
    openbao_persistent: bool = False
    bao_kv_mount: str = "secret"


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
    configured_catalog_roots = tuple(
        _resolve_path(entry, cwd=base_path)
        for entry in env.get("NEPHOS_API_CATALOG_ROOTS", "").split(os.pathsep)
        if entry
    )
    managed_catalog_registries: tuple[ManagedCatalogRegistry, ...]
    catalog_source_ids: tuple[str, ...]
    if configured_catalog_roots:
        catalog_roots = configured_catalog_roots
        managed_catalog_registries = ()
        catalog_source_ids = ()
    else:
        managed_catalog_registries = _default_managed_catalog_registries(
            env,
            cwd=base_path,
        )
        catalog_roots = tuple(registry.path for registry in managed_catalog_registries)
        catalog_source_ids = tuple(
            registry.name for registry in managed_catalog_registries
        )
    kubeconfig = env.get("NEPHOS_API_KUBECONFIG")

    return Settings(
        db_path=db_path,
        catalog_roots=catalog_roots,
        kubeconfig=_resolve_path(kubeconfig, cwd=base_path) if kubeconfig else None,
        kube_context=env.get("NEPHOS_API_KUBE_CONTEXT") or None,
        internal_domain=env.get("NEPHOS_API_INTERNAL_DOMAIN", "nephos.local"),
        ingress_class=env.get("NEPHOS_API_INGRESS_CLASS") or None,
        managed_catalog_registries=managed_catalog_registries,
        catalog_source_ids=catalog_source_ids,
        env=env.get("NEPHOS_API_ENV", "prd").strip().lower() or "prd",
        allow_dev_mode_openbao=env.get("NEPHOS_API_ALLOW_DEV_MODE_OPENBAO") == "1",
        bao_address=env.get("NEPHOS_API_BAO_ADDR") or None,
        bao_token=env.get("NEPHOS_API_BAO_TOKEN") or None,
        openbao_persistent=env.get("NEPHOS_API_OPENBAO_PERSISTENT") == "1",
        bao_kv_mount=env.get("NEPHOS_API_BAO_KV_MOUNT") or "secret",
    )


def load_environment(
    *,
    environ: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> dict[str, str]:
    base_path = Path.cwd() if cwd is None else cwd
    dotenv_values = (
        {} if environ is not None and cwd is None else _read_dotenv(base_path / ".env")
    )
    process_env = os.environ if environ is None else environ
    env = {**dotenv_values, **dict(process_env)}
    if environ is None:
        for key, value in dotenv_values.items():
            os.environ.setdefault(key, value)
        env = dict(os.environ)
    return env


def _default_managed_catalog_registries(
    env: Mapping[str, str],
    *,
    cwd: Path,
) -> tuple[ManagedCatalogRegistry, ...]:
    registry_defaults = (
        (
            "core-registry",
            "NEPHOS_API_CORE_REGISTRY_URL",
            DEFAULT_CORE_REGISTRY_URL,
            "NEPHOS_API_CORE_REGISTRY_PATH",
            ".nephos/registries/core-registry",
        ),
        (
            "mythos-registry",
            "NEPHOS_API_MYTHOS_REGISTRY_URL",
            DEFAULT_MYTHOS_REGISTRY_URL,
            "NEPHOS_API_MYTHOS_REGISTRY_PATH",
            ".nephos/registries/mythos-registry",
        ),
        (
            "community-registry",
            "NEPHOS_API_COMMUNITY_REGISTRY_URL",
            DEFAULT_COMMUNITY_REGISTRY_URL,
            "NEPHOS_API_COMMUNITY_REGISTRY_PATH",
            ".nephos/registries/community-registry",
        ),
    )
    return tuple(
        ManagedCatalogRegistry(
            name=name,
            url=env.get(url_key, default_url),
            path=_resolve_path(env.get(path_key, default_path), cwd=cwd),
        )
        for name, url_key, default_url, path_key, default_path in registry_defaults
    )


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
