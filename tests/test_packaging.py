import tomllib
from pathlib import Path


def test_dev_smoke_testclient_dependency_is_packaged_for_wheel_installs() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    runtime_dependencies = pyproject["project"]["dependencies"]
    runtime_dependency_names = {
        _dependency_name(dependency) for dependency in runtime_dependencies
    }

    assert {"httpx", "httpx2"}.issubset(runtime_dependency_names)


def _dependency_name(dependency: str) -> str:
    name = dependency
    for separator in ("[", "<", ">", "=", ";"):
        name = name.split(separator, 1)[0]
    return name.strip().lower()
