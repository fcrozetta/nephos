import base64

import pytest

from nephos_api import hostctl
from nephos_api.hostctl import HostCommandError


def test_get_secret_value_returns_none_when_absent(monkeypatch) -> None:
    # --ignore-not-found -> exit 0 with empty stdout when the Secret is absent.
    monkeypatch.setattr(hostctl, "_run", lambda cmd, **k: "")
    assert hostctl.kubectl_get_secret_value("s", namespace="ns", key="k") is None


def test_get_secret_value_decodes_present(monkeypatch) -> None:
    encoded = base64.b64encode(b"secret").decode()
    monkeypatch.setattr(hostctl, "_run", lambda cmd, **k: encoded)
    assert hostctl.kubectl_get_secret_value("s", namespace="ns", key="k") == "secret"


def test_get_secret_value_raises_on_read_error(monkeypatch) -> None:
    def boom(cmd, **k):
        raise HostCommandError(cmd, 1, "forbidden")

    monkeypatch.setattr(hostctl, "_run", boom)
    # A real read failure must propagate (not masquerade as absence), so the
    # caller aborts instead of regenerating the authoritative passphrase.
    with pytest.raises(HostCommandError):
        hostctl.kubectl_get_secret_value("s", namespace="ns", key="k")


def test_get_secret_value_uses_ignore_not_found_and_checks(monkeypatch) -> None:
    captured: dict = {}

    def fake_run(cmd, **k):
        captured["cmd"] = list(cmd)
        captured["kwargs"] = k
        return ""

    monkeypatch.setattr(hostctl, "_run", fake_run)
    hostctl.kubectl_get_secret_value("s", namespace="ns", key="k")
    assert "--ignore-not-found" in captured["cmd"]
    # check must stay True (default) so non-zero exits raise.
    assert captured["kwargs"].get("check", True) is True


def test_port_forward_refuses_when_port_in_use(monkeypatch) -> None:
    monkeypatch.setattr(hostctl, "_port_in_use", lambda port, host="127.0.0.1": True)
    with (
        pytest.raises(HostCommandError, match="already in use"),
        hostctl.port_forward("svc", namespace="ns", local_port=18099, remote_port=8099),
    ):
        pass
