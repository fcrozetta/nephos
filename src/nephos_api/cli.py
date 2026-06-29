from __future__ import annotations

from typing import Any

import typer

from nephos_api.config import load_settings
from nephos_api.db import migrate_database, reset_database
from nephos_api.domain import InvalidDomainSuffixError
from nephos_api.registries import RegistrySyncError, ensure_managed_catalog_registries
from nephos_api.repository import DesiredStateRepository

app = typer.Typer(no_args_is_help=True)
db_app = typer.Typer(no_args_is_help=True)
dev_app = typer.Typer(no_args_is_help=True)
app.add_typer(db_app, name="db")
app.add_typer(dev_app, name="dev")


def run_reference_smoke(*args: Any, **kwargs: Any) -> Any:
    from nephos_api.dev_reference import run_reference_smoke as _run_reference_smoke

    return _run_reference_smoke(*args, **kwargs)


def run_backbone_smoke(*args: Any, **kwargs: Any) -> Any:
    from nephos_api.dev_backbone import run_backbone_smoke as _run_backbone_smoke

    return _run_backbone_smoke(*args, **kwargs)


@app.command("init")
def init(
    internal_domain: str | None = typer.Option(
        None,
        "--internal-domain",
        help=(
            "Default internal root domain for generated App routes. "
            "Defaults to NEPHOS_API_INTERNAL_DOMAIN or nephos.local."
        ),
    ),
) -> None:
    settings = load_settings()
    resolved_internal_domain = internal_domain or settings.internal_domain
    migrate_database(db_path=settings.db_path)
    try:
        configured_domain = _ensure_internal_platform_domain(
            settings.db_path,
            internal_domain=resolved_internal_domain,
        )
    except InvalidDomainSuffixError as exc:
        typer.echo(f"invalid internal domain: {resolved_internal_domain}", err=True)
        raise typer.Exit(1) from exc
    _ensure_catalog_registries(settings)
    typer.echo(
        f"Initialized Nephos API state at {settings.db_path} "
        f"with internal domain {configured_domain}"
    )


@db_app.command("migrate")
def migrate() -> None:
    settings = load_settings()
    migrate_database(db_path=settings.db_path)
    typer.echo(f"Migrated database at {settings.db_path}")


@db_app.command("reset")
def reset(force: bool = typer.Option(False, "--force")) -> None:
    if not force:
        typer.echo("db reset requires --force", err=True)
        raise typer.Exit(1)

    settings = load_settings()
    reset_database(db_path=settings.db_path, force=True)
    typer.echo(f"Reset database at {settings.db_path}")


@app.command("serve")
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
) -> None:
    import uvicorn

    from nephos_api.main import (
        create_app,
        default_postgres_provisioner_factory,
        default_provider_deployer_factory,
    )

    settings = load_settings()
    migrate_database(db_path=settings.db_path)
    _ensure_catalog_registries(settings)
    uvicorn.run(
        create_app(
            settings=settings,
            start_reconciler=True,
            deployer_factory=default_provider_deployer_factory,
            provisioner_factory=default_postgres_provisioner_factory,
            ensure_registries=False,
        ),
        host=host,
        port=port,
    )


@dev_app.command("smoke")
def dev_smoke(
    timeout_seconds: int = typer.Option(240, "--timeout-seconds", min=1),
) -> None:
    settings = load_settings()
    _ensure_catalog_registries(settings)
    context = settings.kube_context or "current context"
    typer.echo(f"Running reference smoke test against {context}")
    result = run_reference_smoke(
        settings=settings,
        timeout_seconds=timeout_seconds,
        progress=lambda message: typer.echo(f"- {message}"),
    )
    typer.echo(
        "Reference smoke test passed: "
        f"app={result.app_slug} service={result.service_slug} "
        f"url={result.canonical_url}"
    )


@dev_app.command("backbone-smoke")
def dev_backbone_smoke(
    timeout_seconds: int = typer.Option(600, "--timeout-seconds", min=1),
) -> None:
    settings = load_settings()
    context = settings.kube_context or "current context"
    typer.echo(f"Running alpha backbone smoke against {context}")
    result = run_backbone_smoke(
        settings=settings,
        timeout_seconds=timeout_seconds,
        progress=lambda message: typer.echo(f"- {message}"),
    )
    if result.status == "passed":
        typer.echo(
            "Alpha backbone smoke passed: "
            f"app={result.app_slug} services={','.join(result.service_slugs)}"
        )
        return
    if result.status == "skipped":
        typer.echo(
            "Alpha backbone smoke skipped: "
            f"{result.blocker_code}: {result.message}"
        )
        return
    typer.echo(
        "Alpha backbone smoke blocked: "
        f"{result.blocker_code}: {result.message}",
        err=True,
    )
    raise typer.Exit(2)


def main() -> None:
    app()


def _ensure_catalog_registries(settings) -> None:
    try:
        ensure_managed_catalog_registries(settings)
    except RegistrySyncError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


def _ensure_internal_platform_domain(
    db_path,
    *,
    internal_domain: str,
) -> str:
    repo = DesiredStateRepository(db_path)
    existing = repo.list_platform_domains()
    if existing:
        default = next(
            (domain for domain in existing if domain.is_default),
            existing[0],
        )
        return default.domain
    with repo.transaction() as tx:
        domain = tx.create_platform_domain(
            name="internal",
            domain=internal_domain,
            is_default=True,
        )
        return domain.domain
