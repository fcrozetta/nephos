import io
import json
import subprocess
import urllib.request

from nephos_api.runtime_errors import RuntimeBlockedError
from nephos_api.secret_refs import (
    BaoSecretResolver,
    OnePasswordCliSecretResolver,
    SchemeRoutingSecretResolver,
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


def test_is_secret_reference_recognizes_bao_scheme() -> None:
    assert is_secret_reference("bao://secret/nephos-lcl/arcadedb-root/password")
    assert is_secret_reference("op://nephos-lcl/postgres-admin/password")
    assert not is_secret_reference("vault://x/y")


def test_bao_resolver_parses_mount_path_field() -> None:
    assert BaoSecretResolver._parse(
        "bao://secret/nephos-lcl/arcadedb-root/password"
    ) == ("secret", "nephos-lcl/arcadedb-root", "password")


def test_bao_resolver_rejects_short_reference() -> None:
    try:
        BaoSecretResolver(address="http://x", token="t").resolve("bao://secret/only")
    except RuntimeBlockedError as exc:
        assert exc.reason == "secret_ref_unavailable"
    else:
        raise AssertionError("expected malformed bao reference to block")


def test_bao_resolver_reads_kv_v2_field(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["token"] = request.get_header("X-vault-token")
        body = json.dumps({"data": {"data": {"password": "from-bao"}}}).encode()
        return io.BytesIO(body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    resolved = BaoSecretResolver(
        address="http://openbao:8200/", token="root-token"
    ).resolve("bao://secret/nephos-lcl/arcadedb-root/password")

    assert resolved == "from-bao"
    assert captured["url"] == (
        "http://openbao:8200/v1/secret/data/nephos-lcl/arcadedb-root"
    )
    assert captured["token"] == "root-token"


def test_scheme_routing_resolver_dispatches_by_scheme() -> None:
    resolver = SchemeRoutingSecretResolver(
        {
            "op://": StaticSecretResolver({"op://a/b/c": "op-value"}),
            "bao://": StaticSecretResolver({"bao://m/p/f": "bao-value"}),
        }
    )

    assert resolver.resolve("op://a/b/c") == "op-value"
    assert resolver.resolve("bao://m/p/f") == "bao-value"


def test_scheme_routing_resolver_blocks_unknown_scheme() -> None:
    resolver = SchemeRoutingSecretResolver({"op://": StaticSecretResolver({})})

    try:
        resolver.resolve("bao://m/p/f")
    except RuntimeBlockedError as exc:
        assert exc.reason == "secret_ref_provider_unavailable"
    else:
        raise AssertionError("expected unrouted scheme to block")
