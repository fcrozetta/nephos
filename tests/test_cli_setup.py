import contextlib

import pytest
from typer.testing import CliRunner

from nephos_api.bootstrap_drive import BootstrapDriveError
from nephos_api.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _home(monkeypatch, tmp_path):
    # Keep passphrase-cache writes off the real home directory.
    monkeypatch.setenv("HOME", str(tmp_path))


@pytest.fixture
def cluster_ok(monkeypatch):
    monkeypatch.setattr(
        "nephos_api.cli.hostctl.cluster_reachable", lambda context=None: True
    )


def _patch_control_plane(monkeypatch, applied: dict, *, cluster_secret="cluster-pass"):
    # Real resolve_passphrase runs (the seam that protects the passphrase
    # invariant); only the cluster read, render, and kubectl are stubbed.
    monkeypatch.setattr(
        "nephos_api.cli.hostctl.kubectl_get_secret_value",
        lambda *a, **k: cluster_secret,
    )
    monkeypatch.setattr(
        "nephos_api.cli.render_manifest",
        lambda profile, *, passphrase, manifest_path=None: f"RENDERED::{passphrase}",
    )
    monkeypatch.setattr(
        "nephos_api.cli.hostctl.kubectl_apply",
        lambda manifest, context=None: (
            applied.update(manifest=manifest, context=context) or ""
        ),
    )
    monkeypatch.setattr(
        "nephos_api.cli.hostctl.kubectl_rollout_status", lambda *a, **k: ""
    )


def test_up_uses_cluster_passphrase_and_does_not_regenerate(
    monkeypatch, cluster_ok
) -> None:
    applied: dict = {}
    _patch_control_plane(monkeypatch, applied, cluster_secret="cluster-pass")
    result = runner.invoke(app, ["up", "lcl"])
    assert result.exit_code == 0, result.output
    # The authoritative cluster value must flow through to the rendered manifest.
    assert applied["manifest"] == "RENDERED::cluster-pass"
    assert applied["context"] == "k3d-nephos"
    assert "generated a new Pulumi passphrase" not in result.output


def test_up_generates_passphrase_when_secret_absent(monkeypatch, cluster_ok) -> None:
    applied: dict = {}
    _patch_control_plane(monkeypatch, applied, cluster_secret=None)
    result = runner.invoke(app, ["up", "lcl"])
    assert result.exit_code == 0, result.output
    assert applied["manifest"].startswith("RENDERED::")
    assert applied["manifest"] != "RENDERED::cluster-pass"
    assert "generated a new Pulumi passphrase" in result.output


def test_up_aborts_when_secret_read_fails(monkeypatch, cluster_ok) -> None:
    from nephos_api.hostctl import HostCommandError

    def boom(*a, **k):
        raise HostCommandError(["kubectl", "get", "secret"], 1, "forbidden")

    monkeypatch.setattr("nephos_api.cli.hostctl.kubectl_get_secret_value", boom)
    applied: dict = {}
    monkeypatch.setattr(
        "nephos_api.cli.hostctl.kubectl_apply",
        lambda *a, **k: applied.update(called=True),
    )
    result = runner.invoke(app, ["up", "lcl"])
    assert result.exit_code == 1
    assert "failed to apply the control plane" in result.output
    # Critically: it must NOT have applied a (regenerated) passphrase.
    assert "called" not in applied


def test_up_unknown_instance_exits_1() -> None:
    result = runner.invoke(app, ["up", "prd"])
    assert result.exit_code == 1
    assert "unknown instance" in result.output


def test_up_unreachable_cluster_exits_1(monkeypatch) -> None:
    monkeypatch.setattr(
        "nephos_api.cli.hostctl.cluster_reachable", lambda context=None: False
    )
    result = runner.invoke(app, ["up", "lcl"])
    assert result.exit_code == 1
    assert "not reachable" in result.output


def _patch_setup_host(monkeypatch, events: list):
    monkeypatch.setattr("nephos_api.cli.hostctl.require_tools", lambda *a: None)
    monkeypatch.setattr(
        "nephos_api.cli.hostctl.run_local_routing_script",
        lambda script, *, domain, cluster: events.append(("routing", domain, cluster)),
    )
    monkeypatch.setattr(
        "nephos_api.cli.hostctl.docker_build",
        lambda tag, **k: events.append(("build", tag)),
    )
    monkeypatch.setattr(
        "nephos_api.cli.hostctl.k3d_image_import",
        lambda image, *, cluster: events.append(("import", image, cluster)),
    )

    @contextlib.contextmanager
    def fake_pf(*a, **k):
        events.append(("port-forward",))
        yield

    monkeypatch.setattr("nephos_api.cli.hostctl.port_forward", fake_pf)


def test_setup_orchestrates_full_bootstrap(monkeypatch, cluster_ok) -> None:
    events: list = []
    _patch_setup_host(monkeypatch, events)
    _patch_control_plane(monkeypatch, {})

    drive_args: dict = {}

    def fake_drive(base_url, **kwargs):
        drive_args.update(base_url=base_url, **kwargs)
        events.append(("drive",))

    monkeypatch.setattr("nephos_api.cli.drive_bootstrap", fake_drive)

    result = runner.invoke(app, ["setup", "lcl"])
    assert result.exit_code == 0, result.output
    assert ("routing", "nephos.lcl", "nephos") in events
    assert ("build", "nephos-api:dev") in events
    assert ("import", "nephos-api:dev", "nephos") in events
    assert ("drive",) in events
    assert drive_args["domain"] == "nephos.lcl"
    assert drive_args["api_service_url"].endswith("svc.cluster.local:8099")
    assert events.index(("routing", "nephos.lcl", "nephos")) < events.index(("drive",))


def test_setup_skip_image_build_still_imports(monkeypatch, cluster_ok) -> None:
    events: list = []
    _patch_setup_host(monkeypatch, events)
    _patch_control_plane(monkeypatch, {})
    monkeypatch.setattr("nephos_api.cli.drive_bootstrap", lambda *a, **k: None)

    result = runner.invoke(app, ["setup", "lcl", "--skip-image-build"])
    assert result.exit_code == 0, result.output
    assert ("build", "nephos-api:dev") not in events
    assert ("import", "nephos-api:dev", "nephos") in events


def test_setup_exit_2_on_drive_failure(monkeypatch, cluster_ok) -> None:
    events: list = []
    _patch_setup_host(monkeypatch, events)
    _patch_control_plane(monkeypatch, {})

    def fail_drive(*a, **k):
        raise BootstrapDriveError("openbao not ready within 300s")

    monkeypatch.setattr("nephos_api.cli.drive_bootstrap", fail_drive)

    result = runner.invoke(app, ["setup", "lcl"])
    assert result.exit_code == 2
    assert "bootstrap drive failed" in result.output
    assert "re-run" in result.output


def test_status_reports_deployment_readiness(monkeypatch, cluster_ok) -> None:
    monkeypatch.setattr("nephos_api.cli.hostctl.kubectl", lambda args, **k: "1/1")
    result = runner.invoke(app, ["status", "lcl"])
    assert result.exit_code == 0
    assert "1/1 ready" in result.output


def test_status_missing_deployment_shows_zero(monkeypatch, cluster_ok) -> None:
    # kubectl (check=False) yields "" when the deployment is absent.
    monkeypatch.setattr("nephos_api.cli.hostctl.kubectl", lambda args, **k: "")
    result = runner.invoke(app, ["status", "lcl"])
    assert result.exit_code == 0
    assert "0/0 ready" in result.output


def test_status_zero_ready_is_not_malformed(monkeypatch, cluster_ok) -> None:
    # Kubernetes omits readyReplicas at 0, so jsonpath yields "/1".
    monkeypatch.setattr("nephos_api.cli.hostctl.kubectl", lambda args, **k: "/1")
    result = runner.invoke(app, ["status", "lcl"])
    assert result.exit_code == 0
    assert "0/1 ready" in result.output


def test_down_stop_scales_to_zero(monkeypatch, cluster_ok) -> None:
    scaled: dict = {}
    monkeypatch.setattr(
        "nephos_api.cli.hostctl.kubectl_scale",
        lambda dep, *, replicas, namespace, context=None: scaled.update(
            replicas=replicas
        ),
    )
    result = runner.invoke(app, ["down", "lcl"])
    assert result.exit_code == 0
    assert scaled["replicas"] == 0
    assert "stopped" in result.output


def test_down_destroy_requires_yes(monkeypatch, cluster_ok) -> None:
    result = runner.invoke(app, ["down", "lcl", "--destroy"])
    assert result.exit_code == 1
    assert "--yes" in result.output


def test_down_destroy_with_yes_deletes_namespace(monkeypatch, cluster_ok) -> None:
    deleted: dict = {}
    monkeypatch.setattr(
        "nephos_api.cli.hostctl.kubectl_delete_namespace",
        lambda ns, context=None: deleted.update(ns=ns),
    )
    result = runner.invoke(app, ["down", "lcl", "--destroy", "--yes"])
    assert result.exit_code == 0
    assert deleted["ns"] == "nephos-system"
    assert "destroyed" in result.output
