import pytest

from nephos_api.instance import (
    UnknownInstanceError,
    read_cached_passphrase,
    resolve_instance,
    resolve_passphrase,
    write_cached_passphrase,
)


def test_resolve_lcl_defaults() -> None:
    profile = resolve_instance("lcl")
    assert profile.env == "lcl"
    assert profile.kube_context == "k3d-nephos"
    assert profile.namespace == "nephos-system"
    assert profile.internal_domain == "nephos.lcl"
    assert profile.ingress_class == "traefik"
    assert profile.image == "nephos-api:dev"
    assert profile.image_pull_policy == "IfNotPresent"
    assert profile.is_local is True
    assert profile.api_service_url.endswith("svc.cluster.local:8099")


def test_resolve_is_case_insensitive() -> None:
    assert resolve_instance("LCL").name == "lcl"


def test_resolve_unknown_instance_raises() -> None:
    with pytest.raises(UnknownInstanceError):
        resolve_instance("dev")


def test_render_env_maps_profile_to_configmap_keys() -> None:
    env = resolve_instance("lcl").render_env()
    assert env["NEPHOS_API_ENV"] == "lcl"
    assert env["NEPHOS_API_INTERNAL_DOMAIN"] == "nephos.lcl"
    assert env["NEPHOS_API_INGRESS_CLASS"] == "traefik"


def test_passphrase_cluster_value_wins_and_mirrors_cache(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    profile = resolve_instance("lcl")
    value, generated = resolve_passphrase(profile, in_cluster_value="cluster-secret")
    assert value == "cluster-secret"
    assert generated is False
    assert read_cached_passphrase(profile.passphrase_path) == "cluster-secret"


def test_passphrase_placeholder_is_ignored(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    profile = resolve_instance("lcl")
    value, generated = resolve_passphrase(profile, in_cluster_value="change-me")
    assert generated is True
    assert value != "change-me"
    assert read_cached_passphrase(profile.passphrase_path) == value


def test_passphrase_uses_host_cache_when_cluster_empty(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    profile = resolve_instance("lcl")
    write_cached_passphrase(profile.passphrase_path, "cached-value")
    value, generated = resolve_passphrase(profile, in_cluster_value=None)
    assert value == "cached-value"
    assert generated is False


def test_passphrase_generates_and_persists_0600(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    profile = resolve_instance("lcl")
    value, generated = resolve_passphrase(profile, in_cluster_value=None)
    assert generated is True
    assert value
    assert profile.passphrase_path.exists()
    assert (profile.passphrase_path.stat().st_mode & 0o777) == 0o600
