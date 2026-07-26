"""Authenticated reveal of Service config secrets (ADR 20260726)."""

from pathlib import Path

from fastapi.testclient import TestClient

from nephos_api.config import Settings
from nephos_api.db import migrate_database
from nephos_api.main import create_app
from nephos_api.runtime_errors import RuntimeBlockedError


class FakeSecretReader:
    """Stands in for the OpenBao-backed resolver chain."""

    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = values or {}
        self.resolved: list[str] = []

    def resolve(self, reference: str) -> str:
        self.resolved.append(reference)
        if reference not in self.values:
            raise RuntimeBlockedError(
                reason="secret_ref_unavailable",
                message=f"Secret reference {reference} has no value.",
            )
        return self.values[reference]


class UnavailableSecretReader:
    def resolve(self, reference: str) -> str:
        raise RuntimeBlockedError(
            reason="secret_ref_provider_unavailable",
            message=f"No secret provider is configured for {reference}.",
        )


def _write_service(root: Path, *, name: str = "postgres") -> Path:
    """A Service with one generated and two operator-supplied secrets."""
    path = root / "services" / name / "service.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""
apiVersion: nephos.pro/v1alpha1
kind: Service
metadata:
  name: {name}
spec:
  provides:
    - capability: sql
      protocol: postgres
      as: sql
  config:
    options:
    - name: admin-password
      type: string
      required: true
      generate:
        kind: password
        length: 32
    - name: root-password
      type: string
      required: true
    - name: license-key
      type: string
    - name: image
      type: string
      default: postgres:16-alpine
  provisioning:
    mode: app-scoped-resource
  operations: []
  runtime:
    type: provider
    provider:
      name: {name}
    values:
      mappings: []
""".strip()
    )
    return path


def _client(
    tmp_path: Path,
    *,
    reader: object | None = None,
    config: dict[str, object] | None = None,
) -> tuple[TestClient, str]:
    db_path = tmp_path / "nephos.db"
    catalog_root = tmp_path / "catalog"
    _write_service(catalog_root)
    migrate_database(db_path=db_path)
    resolved = reader if reader is not None else FakeSecretReader()
    app = create_app(
        settings=Settings(
            db_path=db_path,
            catalog_roots=(catalog_root,),
            kubeconfig=None,
            kube_context=None,
        ),
        secret_reader_factory=lambda _settings: resolved,
    )
    client = TestClient(app)
    client.post("/admin/accounts", json={"username": "admin", "password": "P@ssw0rd"})
    token = client.post(
        "/auth/login", json={"username": "admin", "password": "P@ssw0rd"}
    ).json()["token"]
    installed = client.post(
        "/services",
        json={
            "catalogRef": {"kind": "Service", "name": "postgres"},
            "config": config if config is not None else {"root-password": "typed-pw"},
        },
    )
    assert installed.status_code == 202
    return client, token


def _reveal(client: TestClient, option: str, token: str | None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(
        f"/services/postgres/config/{option}/actions/reveal", headers=headers
    )


def test_reveal_requires_a_bearer_token(tmp_path: Path) -> None:
    # The rest of the API is unauthenticated, so this endpoint carrying its own
    # gate is the whole reason a credential can be served at all.
    client, _token = _client(tmp_path)

    response = _reveal(client, "root-password", None)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_token_required"


def test_reveal_rejects_an_unknown_token(tmp_path: Path) -> None:
    client, _token = _client(tmp_path)

    response = _reveal(client, "root-password", "not-a-real-token")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_token_invalid"


def test_reveal_returns_a_generated_secret_from_the_provider(tmp_path: Path) -> None:
    """The case this endpoint exists for.

    A generated option is absent from desired state entirely, so redaction was
    never what hid it. The value must come from the provider coordinate the
    deployer synthesizes.
    """
    reader = FakeSecretReader(
        {"secrets://svc/postgres/admin-password/value": "generated-32-chars"}
    )
    client, token = _client(tmp_path, reader=reader)

    response = _reveal(client, "admin-password", token)

    assert response.status_code == 200
    assert response.json() == {
        "value": "generated-32-chars",
        "source": "secrets-provider",
        "reference": "secrets://svc/postgres/admin-password/value",
    }
    assert reader.resolved == ["secrets://svc/postgres/admin-password/value"]


def test_reveal_returns_an_operator_supplied_secret_from_desired_state(
    tmp_path: Path,
) -> None:
    reader = FakeSecretReader()
    client, token = _client(tmp_path, reader=reader)

    response = _reveal(client, "root-password", token)

    assert response.status_code == 200
    assert response.json() == {"value": "typed-pw", "source": "desired-state"}
    # No provider round-trip for a literal.
    assert reader.resolved == []


def test_reveal_resolves_a_stored_reference(tmp_path: Path) -> None:
    reader = FakeSecretReader({"op://nephos-lcl/pg/password": "from-1password"})
    client, token = _client(
        tmp_path,
        reader=reader,
        config={"root-password": "op://nephos-lcl/pg/password"},
    )

    response = _reveal(client, "root-password", token)

    assert response.status_code == 200
    assert response.json()["value"] == "from-1password"
    assert response.json()["source"] == "secrets-provider"


def test_reveal_rejects_a_non_sensitive_option(tmp_path: Path) -> None:
    client, token = _client(tmp_path)

    response = _reveal(client, "image", token)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "config_option_not_sensitive"


def test_reveal_404s_for_an_unknown_option(tmp_path: Path) -> None:
    client, token = _client(tmp_path)

    response = _reveal(client, "nonexistent-password", token)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "config_option_not_found"


def test_reveal_409s_when_an_optional_secret_was_never_set(tmp_path: Path) -> None:
    client, token = _client(tmp_path)

    response = _reveal(client, "license-key", token)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "config_option_unset"


def test_reveal_503s_when_no_secrets_provider_is_configured(tmp_path: Path) -> None:
    # Distinguishable from "provider has no such value": one is a deployment
    # problem, the other means nothing was ever stored.
    client, token = _client(tmp_path, reader=UnavailableSecretReader())

    response = _reveal(client, "admin-password", token)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "secret_ref_provider_unavailable"


def test_reveal_409s_when_the_provider_has_no_value(tmp_path: Path) -> None:
    client, token = _client(tmp_path, reader=FakeSecretReader())

    response = _reveal(client, "admin-password", token)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "secret_ref_unavailable"


def test_logout_revokes_the_token(tmp_path: Path) -> None:
    reader = FakeSecretReader(
        {"secrets://svc/postgres/admin-password/value": "generated"}
    )
    client, token = _client(tmp_path, reader=reader)
    headers = {"Authorization": f"Bearer {token}"}
    assert _reveal(client, "admin-password", token).status_code == 200

    revoked = client.post("/auth/logout", headers=headers)

    assert revoked.status_code == 200
    assert revoked.json() == {"revoked": True}
    assert _reveal(client, "admin-password", token).status_code == 401


def test_logout_is_idempotent(tmp_path: Path) -> None:
    client, token = _client(tmp_path)
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/auth/logout", headers=headers)

    assert client.post("/auth/logout", headers=headers).json() == {"revoked": False}
    assert client.post("/auth/logout").json() == {"revoked": False}


def test_expired_token_is_rejected_and_deleted(tmp_path: Path) -> None:
    import sqlite3

    client, token = _client(tmp_path)
    db_path = tmp_path / "nephos.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE admin_tokens SET expires_at = '2020-01-01T00:00:00Z'"
        )

    assert _reveal(client, "root-password", token).status_code == 401

    with sqlite3.connect(db_path) as connection:
        remaining = connection.execute(
            "SELECT count(*) FROM admin_tokens"
        ).fetchone()[0]
    assert remaining == 0


def test_token_is_not_stored_in_plaintext(tmp_path: Path) -> None:
    import sqlite3

    client, token = _client(tmp_path)
    del client
    with sqlite3.connect(tmp_path / "nephos.db") as connection:
        stored = connection.execute(
            "SELECT token_hash FROM admin_tokens"
        ).fetchall()

    assert stored
    assert all(row[0] != token for row in stored)
