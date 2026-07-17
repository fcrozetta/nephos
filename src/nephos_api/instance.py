"""Host-side instance profiles for the `nephos` CLI (setup/up/status/down).

LCL-first minimal: a named instance resolves to built-in LCL defaults plus a
kube-context. There is no ~/.nephos/instances.toml yet; DEV/PRD profiles land
with that file later. The one hard invariant is the Pulumi passphrase lifecycle:
the in-cluster Secret is the source of truth and is never overwritten, because a
regenerated PULUMI_CONFIG_PASSPHRASE makes existing Pulumi state undecryptable.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from pathlib import Path

NAMESPACE = "nephos-system"
# The console (BFF) reaches the in-cluster API east-west. FQDN, not the bare
# same-namespace name, because the console pod is not in nephos-system.
API_SERVICE_URL = "http://nephos-api.nephos-system.svc.cluster.local:8099"

_SUPPORTED = ("lcl",)


class UnknownInstanceError(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(
            f"unknown instance '{name}'. Only {list(_SUPPORTED)} is supported in "
            "this version; DEV/PRD profiles arrive with ~/.nephos/instances.toml."
        )
        self.name = name


@dataclass(frozen=True)
class InstanceProfile:
    name: str
    env: str
    kube_context: str
    namespace: str
    internal_domain: str
    ingress_class: str
    image: str
    image_pull_policy: str
    is_local: bool
    k3d_cluster: str | None
    api_service_url: str

    @property
    def passphrase_path(self) -> Path:
        return Path.home() / ".nephos" / "instances" / f"{self.name}.passphrase"

    def render_env(self) -> dict[str, str]:
        """Env values templated into the in-cluster ConfigMap (nephos-api-env)."""
        return {
            "NEPHOS_API_ENV": self.env,
            "NEPHOS_API_INTERNAL_DOMAIN": self.internal_domain,
            "NEPHOS_API_INGRESS_CLASS": self.ingress_class,
        }


def resolve_instance(name: str) -> InstanceProfile:
    key = name.strip().lower()
    if key not in _SUPPORTED:
        raise UnknownInstanceError(name)
    # LCL defaults. The local image is built + imported into k3d, so it must be
    # IfNotPresent (a :dev tag would otherwise ImagePullBackOff on Always).
    return InstanceProfile(
        name=key,
        env="lcl",
        kube_context="k3d-nephos",
        namespace=NAMESPACE,
        internal_domain="nephos.lcl",
        ingress_class="traefik",
        image="nephos-api:dev",
        image_pull_policy="IfNotPresent",
        is_local=True,
        k3d_cluster="nephos",
        api_service_url=API_SERVICE_URL,
    )


# --- Pulumi passphrase: read-existing-else-generate, cluster is authoritative ---


def generate_passphrase() -> str:
    return secrets.token_urlsafe(32)


def read_cached_passphrase(path: Path) -> str | None:
    try:
        value = path.read_text().strip()
    except FileNotFoundError:
        return None
    return value or None


def write_cached_passphrase(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)
    path.chmod(0o600)


def resolve_passphrase(
    profile: InstanceProfile,
    *,
    in_cluster_value: str | None,
) -> tuple[str, bool]:
    """Return (passphrase, generated).

    Precedence: an existing in-cluster Secret (never the placeholder) wins and is
    mirrored to the host cache; else the host cache; else a freshly generated
    value written to the cache. An existing cluster passphrase is never replaced.
    """
    if in_cluster_value and in_cluster_value != "change-me":
        write_cached_passphrase(profile.passphrase_path, in_cluster_value)
        return in_cluster_value, False
    cached = read_cached_passphrase(profile.passphrase_path)
    if cached:
        return cached, False
    generated = generate_passphrase()
    write_cached_passphrase(profile.passphrase_path, generated)
    return generated, True
