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
            return
        raise RegistrySyncError(
            f"managed catalog registry path exists but is not a git checkout: {path}"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        runner(["git", "clone", "--depth", "1", registry.url, str(path)])
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        detail = f": {stderr}" if stderr else ""
        raise RegistrySyncError(
            f"failed to clone managed catalog registry {registry.name} from "
            f"{registry.url}{detail}"
        ) from exc
    except OSError as exc:
        raise RegistrySyncError(
            f"failed to clone managed catalog registry {registry.name}: {exc}"
        ) from exc


def _run_git(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=True,
        capture_output=True,
        text=True,
    )
