import pytest

from nephos_api.passwords import (
    InvalidPasswordError,
    hash_password,
    validate_password,
    verify_password,
)


def test_hash_verify_roundtrip() -> None:
    encoded = hash_password("P@ssw0rd")
    assert encoded.startswith("scrypt$")
    assert verify_password("P@ssw0rd", encoded) is True


def test_verify_rejects_wrong_password() -> None:
    encoded = hash_password("P@ssw0rd")
    assert verify_password("wrong-password", encoded) is False


def test_hash_is_salted() -> None:
    assert hash_password("P@ssw0rd") != hash_password("P@ssw0rd")


def test_verify_rejects_malformed_encoding() -> None:
    assert verify_password("P@ssw0rd", "not-a-hash") is False
    assert verify_password("P@ssw0rd", "bcrypt$1$2$3$4$5") is False


def test_validate_password_length_policy() -> None:
    with pytest.raises(InvalidPasswordError):
        validate_password("short")
    with pytest.raises(InvalidPasswordError):
        validate_password("x" * 129)
    assert validate_password("P@ssw0rd") == "P@ssw0rd"
