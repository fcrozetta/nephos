import subprocess

from nephos_api.runtime_errors import RuntimeBlockedError
from nephos_api.secret_refs import (
    OnePasswordCliSecretResolver,
    StaticSecretResolver,
    is_secret_reference,
    resolve_runtime_secret_value,
)


def test_resolve_runtime_secret_value_ignores_plain_values() -> None:
    resolver = StaticSecretResolver({})

    assert resolve_runtime_secret_value("plain", resolver) == "plain"
    assert resolve_runtime_secret_value(42, resolver) == 42
    assert not is_secret_reference("https://example.test")


def test_resolve_runtime_secret_value_resolves_onepassword_refs() -> None:
    ref = "op://nephos-lcl/postgres-admin/password"
    resolver = StaticSecretResolver({ref: "resolved-secret"})

    assert is_secret_reference(ref)
    assert resolve_runtime_secret_value(ref, resolver) == "resolved-secret"


def test_resolve_runtime_secret_value_blocks_without_provider() -> None:
    try:
        resolve_runtime_secret_value("op://nephos-lcl/postgres-admin/password", None)
    except RuntimeBlockedError as exc:
        assert exc.reason == "secret_ref_provider_unavailable"
    else:
        raise AssertionError("expected missing provider to block")


def test_onepassword_cli_secret_resolver_uses_op_read(monkeypatch) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, "resolved-secret\n", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    ref = "op://nephos-lcl/postgres-admin/password"

    resolved = OnePasswordCliSecretResolver(
        env={"OP_SERVICE_ACCOUNT_TOKEN": "token"}
    ).resolve(ref)

    assert resolved == "resolved-secret"
    assert calls[0][0] == ["op", "read", ref]
    assert calls[0][1]["capture_output"] is True
    assert calls[0][1]["env"]["OP_SERVICE_ACCOUNT_TOKEN"] == "token"


def test_onepassword_cli_secret_resolver_sanitizes_failed_reads(monkeypatch) -> None:
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, "", "sensitive stderr")

    monkeypatch.setattr(subprocess, "run", fake_run)

    try:
        OnePasswordCliSecretResolver().resolve(
            "op://nephos-lcl/postgres-admin/password"
        )
    except RuntimeBlockedError as exc:
        assert exc.reason == "secret_ref_unavailable"
        assert "sensitive stderr" not in str(exc)
    else:
        raise AssertionError("expected failed op read to block")
