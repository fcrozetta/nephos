from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from nephos_api import hostctl
from nephos_api.bootstrap_drive import BootstrapDriveError, drive_bootstrap
from nephos_api.config import load_settings
from nephos_api.db import migrate_database, reset_database
from nephos_api.deploy_manifest import render_manifest
from nephos_api.domain import InvalidDomainSuffixError
from nephos_api.instance import (
    InstanceProfile,
    UnknownInstanceError,
    resolve_instance,
    resolve_passphrase,
)
from nephos_api.registries import RegistrySyncError, ensure_managed_catalog_registries
from nephos_api.repository import DesiredStateRepository

# Local port the host binds when port-forwarding the in-cluster API (setup/status).
_BOOTSTRAP_LOCAL_PORT = 18099
_SECRET_NAME = "nephos-api-secrets"
_PASSPHRASE_KEY = "PULUMI_CONFIG_PASSPHRASE"

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
            "Internal root domain for generated App routes. Required: set this "
            "or NEPHOS_API_INTERNAL_DOMAIN (no default)."
        ),
    ),
) -> None:
    settings = load_settings()
    resolved_internal_domain = internal_domain or settings.internal_domain
    if not resolved_internal_domain:
        typer.echo(
            "internal domain is required: set NEPHOS_API_INTERNAL_DOMAIN "
            "or pass --internal-domain",
            err=True,
        )
        raise typer.Exit(1)
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
            f"Alpha backbone smoke skipped: {result.blocker_code}: {result.message}"
        )
        return
    typer.echo(
        f"Alpha backbone smoke blocked: {result.blocker_code}: {result.message}",
        err=True,
    )
    raise typer.Exit(2)


@app.command("setup")
def setup(
    name: str = typer.Argument(..., help="Instance name (lcl)."),
    skip_image_build: bool = typer.Option(
        False, "--skip-image-build", help="Reuse the imported image; skip docker build."
    ),
    timeout_seconds: int = typer.Option(300, "--timeout-seconds", min=1),
) -> None:
    """One-time greenfield bootstrap: cluster + routing (LCL) -> control plane ->
    OpenBao -> console, from nothing to a running in-cluster Nephos."""
    profile = _resolve_instance_or_exit(name)
    hostctl.require_tools("kubectl")

    if profile.is_local:
        hostctl.require_tools("docker", "k3d")
        script = Path.cwd() / "scripts" / "setup-local-routing.sh"
        if not script.exists():
            typer.echo(f"routing script not found: {script}", err=True)
            raise typer.Exit(1)
        typer.echo(f"- local routing (domain {profile.internal_domain})")
        hostctl.run_local_routing_script(
            script,
            domain=profile.internal_domain,
            cluster=profile.k3d_cluster or "nephos",
        )
        if not skip_image_build:
            typer.echo(f"- building {profile.image}")
            hostctl.docker_build(profile.image)
        typer.echo(f"- importing {profile.image} into k3d {profile.k3d_cluster}")
        hostctl.k3d_image_import(profile.image, cluster=profile.k3d_cluster or "nephos")
    elif not hostctl.cluster_reachable(profile.kube_context):
        typer.echo(f"cluster context {profile.kube_context} not reachable", err=True)
        raise typer.Exit(1)

    _apply_control_plane_or_exit(profile)

    typer.echo("- driving backbone (OpenBao + console)")
    try:
        with hostctl.port_forward(
            "nephos-api",
            namespace=profile.namespace,
            local_port=_BOOTSTRAP_LOCAL_PORT,
            remote_port=8099,
            context=profile.kube_context,
        ):
            drive_bootstrap(
                f"http://127.0.0.1:{_BOOTSTRAP_LOCAL_PORT}",
                domain_name=profile.name,
                domain=profile.internal_domain,
                api_service_url=profile.api_service_url,
                timeout_seconds=float(timeout_seconds),
                progress=lambda message: typer.echo(f"  - {message}"),
            )
    except (BootstrapDriveError, hostctl.HostCommandError) as exc:
        typer.echo(f"bootstrap drive failed: {exc}", err=True)
        typer.echo("re-run `nephos setup` once the cluster settles (it is convergent).")
        raise typer.Exit(2) from exc

    typer.echo(
        f"\nnephos '{name}' is up. Finish first-run admin at "
        f"http://console.{profile.internal_domain}/setup"
    )


@app.command("up")
def up(name: str = typer.Argument(..., help="Instance name (lcl).")) -> None:
    """Converge an existing instance's control plane to match its profile and be
    running. Does not create the cluster, build images, or seed the backbone."""
    profile = _resolve_instance_or_exit(name)
    if not hostctl.cluster_reachable(profile.kube_context):
        typer.echo(f"cluster context {profile.kube_context} not reachable", err=True)
        raise typer.Exit(1)
    _apply_control_plane_or_exit(profile)
    typer.echo(f"nephos '{name}' control plane is up ({profile.kube_context})")


@app.command("status")
def status(name: str = typer.Argument(..., help="Instance name (lcl).")) -> None:
    """Read-only health of a named instance."""
    profile = _resolve_instance_or_exit(name)
    if not hostctl.cluster_reachable(profile.kube_context):
        typer.echo(f"cluster context {profile.kube_context} not reachable", err=True)
        raise typer.Exit(1)
    raw = hostctl.kubectl(
        [
            "get",
            "deploy",
            "nephos-api",
            "-n",
            profile.namespace,
            "-o",
            "jsonpath={.status.readyReplicas}/{.status.replicas}",
        ],
        context=profile.kube_context,
        check=False,
    ).strip()
    # Kubernetes omits readyReplicas/replicas when 0, so jsonpath yields "/1" or
    # "/"; coerce each side to 0 rather than printing a malformed string.
    ready_s, _, total_s = raw.partition("/")
    ready = ready_s.strip() or "0"
    total = total_s.strip() or "0"
    typer.echo(f"nephos-api deployment: {ready}/{total} ready")


@app.command("down")
def down(
    name: str = typer.Argument(..., help="Instance name (lcl)."),
    destroy: bool = typer.Option(
        False,
        "--destroy",
        help="Delete the namespace and Pulumi state (not just stop).",
    ),
    yes: bool = typer.Option(False, "--yes", help="Confirm a destructive/prd action."),
) -> None:
    """Stop (default) or tear down a named instance."""
    profile = _resolve_instance_or_exit(name)
    if profile.env == "prd" and not yes:
        typer.echo("refusing to act on a prd instance without --yes", err=True)
        raise typer.Exit(1)
    if not hostctl.cluster_reachable(profile.kube_context):
        typer.echo(f"cluster context {profile.kube_context} not reachable", err=True)
        raise typer.Exit(1)

    if not destroy:
        hostctl.kubectl_scale(
            "nephos-api",
            replicas=0,
            namespace=profile.namespace,
            context=profile.kube_context,
        )
        typer.echo(
            f"nephos '{name}' stopped (state retained; `nephos up {name}` to resume)"
        )
        return

    if not yes:
        typer.echo("--destroy deletes Pulumi state; pass --yes to confirm", err=True)
        raise typer.Exit(1)
    hostctl.kubectl_delete_namespace(profile.namespace, context=profile.kube_context)
    typer.echo(
        f"nephos '{name}' destroyed: namespace {profile.namespace} deleted "
        "(Pulumi state + passphrase lost). Workloads Pulumi created in other "
        "namespaces (e.g. svc-openbao, app-console) keep running and are now "
        "orphaned; for a full local teardown run "
        f"`k3d cluster delete {profile.k3d_cluster or 'nephos'}`."
    )


def main() -> None:
    app()


def _ensure_catalog_registries(settings) -> None:
    try:
        ensure_managed_catalog_registries(settings)
    except RegistrySyncError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


def _resolve_instance_or_exit(name: str) -> InstanceProfile:
    try:
        return resolve_instance(name)
    except UnknownInstanceError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


def _apply_control_plane_or_exit(profile: InstanceProfile) -> None:
    try:
        _apply_control_plane(profile)
    except hostctl.HostCommandError as exc:
        typer.echo(f"failed to apply the control plane: {exc}", err=True)
        raise typer.Exit(1) from exc


def _apply_control_plane(profile: InstanceProfile) -> None:
    passphrase, generated = _ensure_passphrase(profile)
    if generated:
        typer.echo("- generated a new Pulumi passphrase (cached under ~/.nephos)")
    manifest = render_manifest(profile, passphrase=passphrase)
    hostctl.kubectl_apply(manifest, context=profile.kube_context)
    hostctl.kubectl_rollout_status(
        "nephos-api", namespace=profile.namespace, context=profile.kube_context
    )


def _ensure_passphrase(profile: InstanceProfile) -> tuple[str, bool]:
    in_cluster = hostctl.kubectl_get_secret_value(
        _SECRET_NAME,
        namespace=profile.namespace,
        key=_PASSPHRASE_KEY,
        context=profile.kube_context,
    )
    return resolve_passphrase(profile, in_cluster_value=in_cluster)


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
