"""Password hashing for the Nephos admin account.

Uses the standard library's memory-hard ``hashlib.scrypt`` so no third-party
dependency is pulled in. Encoded form is a single self-describing string
(``scrypt$n$r$p$salt$hash``) so parameters travel with the hash and can be
tuned later without a migration.
"""

from __future__ import annotations

import hashlib
import hmac
from base64 import b64decode, b64encode
from secrets import token_bytes, token_urlsafe

_SCHEME = "scrypt"
_N = 2**14
_R = 8
_P = 1
_DKLEN = 32
_SALT_BYTES = 16
# scrypt needs ~128 * N * r * p bytes; give OpenSSL headroom above that.
_MAXMEM = 128 * _N * _R * _P * 2

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

# 256 bits of entropy, urlsafe so it survives an Authorization header untouched.
_TOKEN_BYTES = 32


class InvalidPasswordError(ValueError):
    """Raised when a password fails length policy."""


def validate_password(password: str) -> str:
    if not (MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH):
        raise InvalidPasswordError(
            f"password must be {MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_LENGTH} characters"
        )
    return password


def hash_password(password: str) -> str:
    salt = token_bytes(_SALT_BYTES)
    derived = _derive(password, salt)
    return "$".join(
        (
            _SCHEME,
            str(_N),
            str(_R),
            str(_P),
            b64encode(salt).decode("ascii"),
            b64encode(derived).decode("ascii"),
        )
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, hash_b64 = encoded.split("$")
        if scheme != _SCHEME:
            return False
        salt = b64decode(salt_b64)
        expected = b64decode(hash_b64)
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
            maxmem=128 * int(n) * int(r) * int(p) * 2,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derived, expected)


def generate_auth_token() -> str:
    """A bearer token for the reveal endpoint (ADR 20260726)."""
    return token_urlsafe(_TOKEN_BYTES)


def hash_auth_token(token: str) -> str:
    """Deterministic hash of a bearer token, for storage and lookup.

    Plain SHA-256 rather than the scrypt used for passwords, and deliberately so:
    a token carries 256 bits of entropy from a CSPRNG, so there is no dictionary
    or brute-force surface for a memory-hard KDF to defend against. The salt that
    makes `hash_password` safe is also what makes it unusable here, since a salted
    hash cannot be looked up by value.

    Storing only this hash means a read of `admin_tokens` yields nothing usable,
    which is the same property `admin_accounts` gets from `password_hash`.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _derive(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_N,
        r=_R,
        p=_P,
        dklen=_DKLEN,
        maxmem=_MAXMEM,
    )
