from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from nephos_api.config import Settings, load_environment


class KubernetesConfigError(RuntimeError):
    pass


class KubernetesConfigLoader(Protocol):
    def load_kube_config(
        self,
        *,
        config_file: str | None = None,
        context: str | None = None,
    ) -> None: ...

    def load_incluster_config(self) -> None: ...


def load_kubernetes_config(
    settings: Settings,
    *,
    config_loader: KubernetesConfigLoader | None = None,
) -> None:
    loader = config_loader if config_loader is not None else _default_config_loader()
    try:
        loader.load_kube_config(
            config_file=str(settings.kubeconfig) if settings.kubeconfig else None,
            context=settings.kube_context,
        )
    except Exception as exc:
        if settings.kubeconfig is None and settings.kube_context is None:
            try:
                loader.load_incluster_config()
                return
            except Exception as incluster_exc:
                raise KubernetesConfigError(str(incluster_exc)) from incluster_exc
        raise KubernetesConfigError(str(exc)) from exc


def kubernetes_tests_enabled(
    environ: Mapping[str, str] | None = None,
    *,
    cwd: Path | None = None,
) -> bool:
    env = load_environment(environ=environ, cwd=cwd)
    return (
        env.get("NEPHOS_API_RUN_KUBERNETES_TESTS") == "1"
        or env.get("NEPHOS_API_RUN_K3S_TESTS") == "1"
    )


def k3s_tests_enabled(
    environ: Mapping[str, str] | None = None,
    *,
    cwd: Path | None = None,
) -> bool:
    return kubernetes_tests_enabled(environ=environ, cwd=cwd)


def _default_config_loader() -> KubernetesConfigLoader:
    from kubernetes import config

    return config
