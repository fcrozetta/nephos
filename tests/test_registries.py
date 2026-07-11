import subprocess
from pathlib import Path

import pytest

from nephos_api.config import ManagedCatalogRegistry, Settings
from nephos_api.registries import RegistrySyncError, ensure_managed_catalog_registries


def _settings(registry: ManagedCatalogRegistry) -> Settings:
    return Settings(
        db_path=registry.path.parent / "nephos.db",
        catalog_roots=(registry.path,),
        kubeconfig=None,
        kube_context=None,
        managed_catalog_registries=(registry,),
    )


def test_ensure_managed_catalog_registries_clones_missing_registry(
    tmp_path: Path,
) -> None:
    registry = ManagedCatalogRegistry(
        name="core-registry",
        url="https://example.test/core-registry.git",
        path=tmp_path / ".nephos" / "registries" / "core-registry",
    )
    commands: list[list[str]] = []

    def fake_runner(command):
        commands.append(list(command))
        registry.path.mkdir(parents=True)
        (registry.path / ".git").mkdir()
        return subprocess.CompletedProcess(command, 0, "", "")

    ensure_managed_catalog_registries(_settings(registry), runner=fake_runner)

    assert commands == [
        ["git", "clone", "--depth", "1", registry.url, str(registry.path)]
    ]


def test_ensure_managed_catalog_registries_clones_missing_shared_parent(
    tmp_path: Path,
) -> None:
    registries = (
        ManagedCatalogRegistry(
            name="core-registry",
            url="https://example.test/core-registry.git",
            path=tmp_path / ".nephos" / "registries" / "core-registry",
        ),
        ManagedCatalogRegistry(
            name="mythos-registry",
            url="https://example.test/mythos-registry.git",
            path=tmp_path / ".nephos" / "registries" / "mythos-registry",
        ),
    )
    settings = Settings(
        db_path=tmp_path / ".nephos" / "state" / "nephos.db",
        catalog_roots=tuple(registry.path for registry in registries),
        kubeconfig=None,
        kube_context=None,
        managed_catalog_registries=registries,
    )
    commands: list[list[str]] = []

    def fake_runner(command):
        commands.append(list(command))
        target_path = Path(command[-1])
        target_path.mkdir(parents=True)
        (target_path / ".git").mkdir()
        return subprocess.CompletedProcess(command, 0, "", "")

    ensure_managed_catalog_registries(settings, runner=fake_runner)

    assert commands == [
        ["git", "clone", "--depth", "1", registries[0].url, str(registries[0].path)],
        ["git", "clone", "--depth", "1", registries[1].url, str(registries[1].path)],
    ]


def test_ensure_managed_catalog_registries_refreshes_existing_checkout(
    tmp_path: Path,
) -> None:
    registry = ManagedCatalogRegistry(
        name="core-registry",
        url="https://example.test/core-registry.git",
        path=tmp_path / ".nephos" / "registries" / "core-registry",
    )
    (registry.path / ".git").mkdir(parents=True)
    commands: list[list[str]] = []

    def fake_runner(command):
        commands.append(list(command))
        if list(command)[-3:] == ["config", "--get-all", "remote.origin.url"]:
            return subprocess.CompletedProcess(command, 0, f"{registry.url}\n", "")
        return subprocess.CompletedProcess(command, 0, "", "")

    ensure_managed_catalog_registries(
        _settings(registry),
        runner=fake_runner,
    )

    assert commands == [
        ["git", "-C", str(registry.path), "config", "--get-all", "remote.origin.url"],
        ["git", "-C", str(registry.path), "status", "--porcelain"],
        ["git", "-C", str(registry.path), "rev-list", "--count", "@{upstream}..HEAD"],
        ["git", "-C", str(registry.path), "pull", "--ff-only"],
    ]


def test_ensure_managed_catalog_registries_blocks_ahead_checkout(
    tmp_path: Path,
) -> None:
    registry = ManagedCatalogRegistry(
        name="core-registry",
        url="https://example.test/core-registry.git",
        path=tmp_path / ".nephos" / "registries" / "core-registry",
    )
    (registry.path / ".git").mkdir(parents=True)

    def fake_runner(command):
        tail = list(command)[-3:]
        if tail == ["config", "--get-all", "remote.origin.url"]:
            return subprocess.CompletedProcess(command, 0, f"{registry.url}\n", "")
        if tail == ["rev-list", "--count", "@{upstream}..HEAD"]:
            return subprocess.CompletedProcess(command, 0, "1\n", "")
        if list(command)[-2:] == ["status", "--porcelain"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError("ahead checkouts should not be pulled")

    with pytest.raises(RegistrySyncError, match="local commits ahead"):
        ensure_managed_catalog_registries(_settings(registry), runner=fake_runner)


def test_ensure_managed_catalog_registries_blocks_dirty_checkout(
    tmp_path: Path,
) -> None:
    registry = ManagedCatalogRegistry(
        name="core-registry",
        url="https://example.test/core-registry.git",
        path=tmp_path / ".nephos" / "registries" / "core-registry",
    )
    (registry.path / ".git").mkdir(parents=True)

    def fake_runner(command):
        if list(command)[-3:] == ["config", "--get-all", "remote.origin.url"]:
            return subprocess.CompletedProcess(command, 0, f"{registry.url}\n", "")
        if list(command)[-2:] == ["status", "--porcelain"]:
            return subprocess.CompletedProcess(command, 0, " M service.yaml\n", "")
        raise AssertionError("dirty checkouts should not be pulled")

    with pytest.raises(RegistrySyncError, match="local changes"):
        ensure_managed_catalog_registries(_settings(registry), runner=fake_runner)


def test_ensure_managed_catalog_registries_blocks_divergent_checkout(
    tmp_path: Path,
) -> None:
    registry = ManagedCatalogRegistry(
        name="core-registry",
        url="https://example.test/core-registry.git",
        path=tmp_path / ".nephos" / "registries" / "core-registry",
    )
    (registry.path / ".git").mkdir(parents=True)

    def fake_runner(command):
        if list(command)[-3:] == ["config", "--get-all", "remote.origin.url"]:
            return subprocess.CompletedProcess(command, 0, f"{registry.url}\n", "")
        if list(command)[-2:] == ["status", "--porcelain"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if list(command)[-3:] == ["rev-list", "--count", "@{upstream}..HEAD"]:
            return subprocess.CompletedProcess(command, 0, "0\n", "")
        raise subprocess.CalledProcessError(
            128,
            command,
            stderr="fatal: Not possible to fast-forward, aborting.",
        )

    with pytest.raises(RegistrySyncError, match="fast-forward"):
        ensure_managed_catalog_registries(_settings(registry), runner=fake_runner)


def test_ensure_managed_catalog_registries_blocks_remote_url_mismatch(
    tmp_path: Path,
) -> None:
    registry = ManagedCatalogRegistry(
        name="core-registry",
        url="https://example.test/core-registry.git",
        path=tmp_path / ".nephos" / "registries" / "core-registry",
    )
    (registry.path / ".git").mkdir(parents=True)

    def fake_runner(command):
        if list(command)[-3:] == ["config", "--get-all", "remote.origin.url"]:
            return subprocess.CompletedProcess(
                command, 0, "https://example.test/foreign-registry.git\n", ""
            )
        raise AssertionError("mismatched-remote checkouts should not be refreshed")

    with pytest.raises(RegistrySyncError, match="do not match configured"):
        ensure_managed_catalog_registries(_settings(registry), runner=fake_runner)


def test_ensure_managed_catalog_registries_blocks_multiple_origin_urls(
    tmp_path: Path,
) -> None:
    registry = ManagedCatalogRegistry(
        name="core-registry",
        url="https://example.test/core-registry.git",
        path=tmp_path / ".nephos" / "registries" / "core-registry",
    )
    (registry.path / ".git").mkdir(parents=True)

    def fake_runner(command):
        # foreign first (what `git fetch` uses), configured last (what a scalar
        # `config --get` read would return); the guard must reject the ambiguity.
        if list(command)[-3:] == ["config", "--get-all", "remote.origin.url"]:
            return subprocess.CompletedProcess(
                command,
                0,
                f"https://example.test/foreign-registry.git\n{registry.url}\n",
                "",
            )
        raise AssertionError("multi-url origins should not be refreshed")

    with pytest.raises(RegistrySyncError, match="do not match configured"):
        ensure_managed_catalog_registries(_settings(registry), runner=fake_runner)


def test_ensure_managed_catalog_registries_skips_when_no_managed_registries(
    tmp_path: Path,
) -> None:
    settings = Settings(
        db_path=tmp_path / "nephos.db",
        catalog_roots=(tmp_path / "catalog",),
        kubeconfig=None,
        kube_context=None,
        managed_catalog_registries=(),
    )
    commands: list[list[str]] = []

    def fake_runner(command):
        commands.append(list(command))
        return subprocess.CompletedProcess(command, 0, "", "")

    ensure_managed_catalog_registries(settings, runner=fake_runner)

    assert commands == []


def test_ensure_managed_catalog_registries_rejects_existing_non_checkout(
    tmp_path: Path,
) -> None:
    registry = ManagedCatalogRegistry(
        name="core-registry",
        url="https://example.test/core-registry.git",
        path=tmp_path / ".nephos" / "registries" / "core-registry",
    )
    registry.path.mkdir(parents=True)

    def fake_runner(command):
        return subprocess.CompletedProcess(command, 0, "", "")

    with pytest.raises(RegistrySyncError, match="not a git checkout"):
        ensure_managed_catalog_registries(_settings(registry), runner=fake_runner)


def test_ensure_managed_catalog_registries_wraps_clone_failure(tmp_path: Path) -> None:
    registry = ManagedCatalogRegistry(
        name="core-registry",
        url="https://example.test/core-registry.git",
        path=tmp_path / ".nephos" / "registries" / "core-registry",
    )

    def fake_runner(command):
        raise subprocess.CalledProcessError(128, command, stderr="network down")

    with pytest.raises(RegistrySyncError, match="network down"):
        ensure_managed_catalog_registries(_settings(registry), runner=fake_runner)


def test_ensure_managed_catalog_registries_wraps_missing_git(tmp_path: Path) -> None:
    registry = ManagedCatalogRegistry(
        name="core-registry",
        url="https://example.test/core-registry.git",
        path=tmp_path / ".nephos" / "registries" / "core-registry",
    )

    def fake_runner(_command):
        raise FileNotFoundError("git")

    with pytest.raises(RegistrySyncError, match="git"):
        ensure_managed_catalog_registries(_settings(registry), runner=fake_runner)
