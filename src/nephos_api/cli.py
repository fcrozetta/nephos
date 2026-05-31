from __future__ import annotations

from typing import Annotated

import typer
import uvicorn

from nephos_api.config import get_settings
from nephos_api.migrations import apply_migrations, reset_database
from nephos_api.reconciler import Reconciler

app = typer.Typer(help="Backend-local Nephos API development commands.")
db_app = typer.Typer(help="SQLite database commands.")
reconcile_app = typer.Typer(help="Persisted reconciliation queue commands.")
app.add_typer(db_app, name="db")
app.add_typer(reconcile_app, name="reconcile")


@db_app.command("migrate")
def db_migrate() -> None:
    """Apply pending SQLite migrations."""
    result = apply_migrations(get_settings())
    if result.applied:
        typer.echo(f"Applied migrations: {', '.join(result.applied)}")
    else:
        typer.echo("No pending migrations.")
    typer.echo(f"Database: {result.db_path}")


@db_app.command("reset")
def db_reset(
    force: Annotated[
        bool,
        typer.Option("--force", help="Required destructive reset flag."),
    ] = False,
) -> None:
    """Delete and recreate the local SQLite database."""
    if not force:
        raise typer.BadParameter("refusing to reset database without --force")
    result = reset_database(get_settings(), force=force)
    typer.echo(f"Reset database: {result.db_path}")
    if result.applied:
        typer.echo(f"Applied migrations: {', '.join(result.applied)}")


@reconcile_app.command("run-once")
def reconcile_run_once() -> None:
    """Claim and process one pending reconciliation request."""
    result = Reconciler(get_settings()).run_once()
    if not result.processed or result.request is None:
        typer.echo("No pending reconciliation requests.")
        return
    typer.echo(
        f"Processed {result.request['id']}: "
        f"{result.request['action']} -> {result.request['state']}"
    )


@reconcile_app.command("drain")
def reconcile_drain(
    limit: Annotated[
        int | None,
        typer.Option("--limit", help="Maximum number of requests to process."),
    ] = None,
) -> None:
    """Process pending reconciliation requests until the queue is empty or limit is reached."""
    result = Reconciler(get_settings()).drain(limit=limit)
    if not result.processed:
        typer.echo("No pending reconciliation requests.")
        return
    state_counts = ", ".join(
        f"{state}={count}" for state, count in sorted(result.states.items())
    )
    typer.echo(f"Processed {result.processed} reconciliation request(s): {state_counts}")


@app.command("serve")
def serve(
    host: Annotated[str, typer.Option(help="Bind host.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Bind port.")] = 8000,
    reload: Annotated[bool, typer.Option(help="Reload on code changes.")] = False,
) -> None:
    """Run the FastAPI backend as a local development process."""
    uvicorn.run("nephos_api.main:app", host=host, port=port, reload=reload)


def main() -> None:
    app()
