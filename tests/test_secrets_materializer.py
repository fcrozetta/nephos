import pytest

from nephos_api.runtime_errors import RuntimeBlockedError
from nephos_api.secret_refs import (
    SecretCASConflictError,
    SecretGenSpec,
    SecretRead,
    SecretsMaterializer,
)

PW = SecretGenSpec(kind="password", length=24)


class FakeProvider:
    """In-memory SecretsProvider with KV-v2-style CAS semantics."""

    def __init__(self) -> None:
        self.store: dict[str, tuple[dict[str, str], int]] = {}
        self.writes = 0
        self._concurrent_field: tuple[str, str] | None = None

    def inject_concurrent_write(self, path: str, field: str, value: str) -> None:
        """Make the next write to `path` lose a CAS race to a concurrent writer
        that stored `field=value` and bumped the version."""
        self._concurrent_field = (path, field, value)  # type: ignore[assignment]

    def read_secret(self, path: str) -> SecretRead | None:
        if path not in self.store:
            return None
        fields, version = self.store[path]
        return SecretRead(fields=dict(fields), version=version)

    def write_secret(
        self, path: str, fields: dict[str, str], *, expected_version: int
    ) -> None:
        self.writes += 1
        if self._concurrent_field is not None and self._concurrent_field[0] == path:
            _, cfield, cvalue = self._concurrent_field
            self._concurrent_field = None
            existing, version = self.store.get(path, ({}, 0))
            merged = {**existing, cfield: cvalue}
            self.store[path] = (merged, version + 1)
            raise SecretCASConflictError(path)
        current_version = self.store.get(path, ({}, 0))[1]
        if expected_version != current_version:
            raise SecretCASConflictError(path)
        self.store[path] = (dict(fields), current_version + 1)

    def capability_ready(self) -> bool:
        return True


def _materializer() -> tuple[SecretsMaterializer, FakeProvider]:
    provider = FakeProvider()
    return SecretsMaterializer(provider), provider


def test_returns_existing_value_without_writing() -> None:
    mat, provider = _materializer()
    provider.store["nephos/svc/postgres/admin"] = ({"password": "already"}, 3)

    value = mat.materialize("secrets://svc/postgres/admin/password", generate=PW)

    assert value == "already"
    assert provider.writes == 0  # no-lockout: never regenerate


def test_generates_when_absent() -> None:
    mat, provider = _materializer()

    value = mat.materialize("secrets://svc/postgres/admin/password", generate=PW)

    assert len(value) == 24
    assert provider.writes == 1
    assert provider.store["nephos/svc/postgres/admin"][0]["password"] == value


def test_maps_platform_scope_path() -> None:
    mat, provider = _materializer()

    mat.materialize("secrets://platform/master/key", generate=PW)

    assert "nephos/platform/master" in provider.store


def test_gen_none_fails_closed_when_absent() -> None:
    mat, _ = _materializer()

    with pytest.raises(RuntimeBlockedError) as exc:
        mat.materialize("secrets://svc/postgres/admin/password", generate=None)

    assert exc.value.reason == "secret_ref_unavailable"


def test_resolve_is_read_only() -> None:
    mat, provider = _materializer()

    with pytest.raises(RuntimeBlockedError):
        mat.resolve("secrets://svc/postgres/admin/password")
    assert provider.writes == 0


def test_cas_conflict_retries_and_merges() -> None:
    mat, provider = _materializer()
    path = "nephos/svc/postgres/admin"
    provider.inject_concurrent_write(path, "other", "x")

    value = mat.materialize("secrets://svc/postgres/admin/password", generate=PW)

    # first write lost the race, second merged and won
    assert provider.writes == 2
    stored = provider.store[path][0]
    assert stored["other"] == "x"
    assert stored["password"] == value


def test_preserves_sibling_fields_on_generate() -> None:
    mat, provider = _materializer()
    provider.store["nephos/svc/postgres/admin"] = ({"username": "postgres"}, 1)

    mat.materialize("secrets://svc/postgres/admin/password", generate=PW)

    fields = provider.store["nephos/svc/postgres/admin"][0]
    assert fields["username"] == "postgres"
    assert "password" in fields


@pytest.mark.parametrize(
    "reference",
    [
        "secrets://svc/postgres",  # too few segments
        "secrets://svc/postgres/admin/password/extra",  # svc scope must be 2
        "secrets://platform/master/key/extra",  # platform scope must be 1
        "secrets://bogus/name/field",  # unknown scope head
        "secrets://svc//admin/password",  # empty segment
    ],
)
def test_invalid_references_fail_closed(reference: str) -> None:
    mat, _ = _materializer()

    with pytest.raises(RuntimeBlockedError):
        mat.materialize(reference, generate=PW)
