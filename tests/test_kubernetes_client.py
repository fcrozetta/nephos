from pathlib import Path

import pytest

from nephos_api.config import Settings
from nephos_api.kubernetes_client import (
    KubernetesConfigError,
    kubernetes_tests_enabled,
    load_kubernetes_config,
)


class FakeConfigLoader:
    def __init__(self) -> None:
        self.calls: list[tuple[str | None, str | None]] = []
        self.incluster_calls = 0

    def load_kube_config(
        self,
        *,
        config_file: str | None = None,
        context: str | None = None,
    ) -> None:
        self.calls.append((config_file, context))

    def load_incluster_config(self) -> None:
        self.incluster_calls += 1


class KubeconfigFailureInclusterSuccessLoader(FakeConfigLoader):
    def load_kube_config(self, **_kwargs: object) -> None:
        raise RuntimeError("kubeconfig unavailable")


def _settings(
    *,
    kubeconfig: Path | None = None,
    kube_context: str | None = None,
) -> Settings:
    return Settings(
        db_path=Path("/tmp/nephos.db"),
        catalog_roots=(Path("/tmp/catalog"),),
        kubeconfig=kubeconfig,
        kube_context=kube_context,
        internal_domain="nephos.local",
    )


def test_load_kubernetes_config_uses_normal_resolution_by_default() -> None:
    loader = FakeConfigLoader()

    load_kubernetes_config(_settings(), config_loader=loader)

    assert loader.calls == [(None, None)]
    assert loader.incluster_calls == 0


def test_load_kubernetes_config_uses_env_override_settings(tmp_path: Path) -> None:
    loader = FakeConfigLoader()
    kubeconfig = tmp_path / "kubeconfig"

    load_kubernetes_config(
        _settings(kubeconfig=kubeconfig, kube_context="nephos-dev"),
        config_loader=loader,
    )

    assert loader.calls == [(str(kubeconfig), "nephos-dev")]
    assert loader.incluster_calls == 0


def test_load_kubernetes_config_falls_back_to_incluster_without_overrides() -> None:
    loader = KubeconfigFailureInclusterSuccessLoader()

    load_kubernetes_config(_settings(), config_loader=loader)

    assert loader.incluster_calls == 1


def test_load_kubernetes_config_does_not_fallback_when_overrides_fail(
    tmp_path: Path,
) -> None:
    loader = KubeconfigFailureInclusterSuccessLoader()

    with pytest.raises(KubernetesConfigError, match="kubeconfig unavailable"):
        load_kubernetes_config(
            _settings(kubeconfig=tmp_path / "kubeconfig"),
            config_loader=loader,
        )

    assert loader.incluster_calls == 0


def test_load_kubernetes_config_wraps_loader_errors() -> None:
    class BrokenConfigLoader:
        def load_kube_config(self, **_kwargs: object) -> None:
            raise RuntimeError("not reachable")

        def load_incluster_config(self) -> None:
            raise RuntimeError("incluster not reachable")

    with pytest.raises(KubernetesConfigError, match="incluster not reachable"):
        load_kubernetes_config(_settings(), config_loader=BrokenConfigLoader())


def test_kubernetes_tests_require_explicit_opt_in() -> None:
    assert kubernetes_tests_enabled({}) is False
    assert kubernetes_tests_enabled({"NEPHOS_API_RUN_KUBERNETES_TESTS": "0"}) is False
    assert kubernetes_tests_enabled({"NEPHOS_API_RUN_KUBERNETES_TESTS": "1"}) is True


def test_kubernetes_tests_accept_legacy_k3s_opt_in_alias() -> None:
    assert kubernetes_tests_enabled({"NEPHOS_API_RUN_K3S_TESTS": "1"}) is True


def test_kubernetes_tests_read_explicit_opt_in_from_dotenv(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("NEPHOS_API_RUN_KUBERNETES_TESTS=1\n")

    assert kubernetes_tests_enabled({}, cwd=tmp_path) is True
