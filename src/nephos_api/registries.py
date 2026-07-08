import subprocess
from collections.abc import Callable, Sequence

from nephos_api.config import ManagedCatalogRegistry, Settings


class RegistrySyncError(RuntimeError):
    pass


CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def ensure_managed_catalog_registries(
    settings: Settings,
    *,
    runner: CommandRunner | None = None,
) -> None:
    run = runner or _run_git
    for registry in settings.managed_catalog_registries:
        _ensure_git_registry(registry, runner=run)


def _ensure_git_registry(
    registry: ManagedCatalogRegistry,
    *,
    runner: CommandRunner,
) -> None:
    path = registry.path
    if path.exists():
        if (path / ".git").exists():
            _refresh_git_registry(registry, runner=runner)
            return
        raise RegistrySyncError(
            f"managed catalog registry path exists but is not a git checkout: {path}"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        runner(["git", "clone", "--depth", "1", registry.url, str(path)])
    except subprocess.CalledProcessError as exc:
        raise RegistrySyncError(
            _git_failure_message(
                action="clone",
                registry=registry,
                detail=(exc.stderr or "").strip(),
            )
        ) from exc
    except OSError as exc:
        raise RegistrySyncError(
            f"failed to clone managed catalog registry {registry.name}: {exc}"
        ) from exc


def _refresh_git_registry(
    registry: ManagedCatalogRegistry,
    *,
    runner: CommandRunner,
) -> None:
    try:
        status = runner(["git", "-C", str(registry.path), "status", "--porcelain"])
        if status.stdout.strip():
            raise RegistrySyncError(
                "managed catalog registry "
                f"{registry.name} has local changes; refusing to refresh "
                f"{registry.path}"
            )
        ahead = runner(
            [
                "git",
                "-C",
                str(registry.path),
                "rev-list",
                "--count",
                "@{upstream}..HEAD",
            ]
        )
        if ahead.stdout.strip() not in ("", "0"):
            raise RegistrySyncError(
                "managed catalog registry "
                f"{registry.name} has local commits ahead of upstream; "
                f"refusing to refresh {registry.path}"
            )
        runner(["git", "-C", str(registry.path), "pull", "--ff-only"])
    except RegistrySyncError:
        raise
    except subprocess.CalledProcessError as exc:
        raise RegistrySyncError(
            _git_failure_message(
                action="refresh",
                registry=registry,
                detail=(exc.stderr or "").strip(),
            )
        ) from exc
    except OSError as exc:
        raise RegistrySyncError(
            f"failed to refresh managed catalog registry {registry.name}: {exc}"
        ) from exc


def _git_failure_message(
    *,
    action: str,
    registry: ManagedCatalogRegistry,
    detail: str,
) -> str:
    suffix = f": {detail}" if detail else ""
    if action == "clone":
        return (
            f"failed to clone managed catalog registry {registry.name} from "
            f"{registry.url}{suffix}"
        )
    return (
        f"failed to refresh managed catalog registry {registry.name} at "
        f"{registry.path}; checkout must be clean and fast-forwardable{suffix}"
    )


def _run_git(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=True,
        capture_output=True,
        text=True,
    )
