from __future__ import annotations

import re
import sqlite3
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Request, status
from pydantic import BaseModel

from nephos_api.domain import AdminAccount
from nephos_api.errors import NephosError
from nephos_api.passwords import (
    InvalidPasswordError,
    hash_password,
    validate_password,
    verify_password,
)
from nephos_api.repository import DesiredStateRepository

router = APIRouter(tags=["auth"])

_USERNAME_RE = re.compile(r"^[A-Za-z0-9._@-]{1,64}$")

# Matches the console's session cookie lifetime. A shorter token would expire
# mid-session with no recovery: the console mints its session from the subject
# alone and keeps no password to re-authenticate with (ADR 20260726).
AUTH_TOKEN_TTL_SECONDS = 12 * 60 * 60


class AdminCredentials(BaseModel):
    username: str
    password: str


@router.get("/auth/state")
def read_auth_state(request: Request) -> dict[str, bool]:
    repo = _repo(request)
    return {"adminExists": repo.count_admin_accounts() > 0}


@router.post("/admin/accounts", status_code=status.HTTP_201_CREATED)
def create_admin_account(
    payload: AdminCredentials,
    request: Request,
) -> dict[str, Any]:
    username = _validate_username(payload.username)
    try:
        validate_password(payload.password)
    except InvalidPasswordError as exc:
        raise NephosError(
            status_code=400,
            code="admin_password_invalid",
            message="Admin password does not meet the length policy.",
        ) from exc

    repo = _repo(request)
    password_hash = hash_password(payload.password)
    # IMMEDIATE serializes the zero-admin check with the insert: the API is
    # unauthenticated, so account creation must be a one-shot bootstrap.
    try:
        with repo.transaction(immediate=True) as tx:
            if tx.count_admin_accounts() > 0:
                raise _admin_exists()
            account = tx.create_admin_account(
                username=username,
                password_hash=password_hash,
            )
    except sqlite3.IntegrityError as exc:
        raise _admin_exists() from exc

    return {"resource": _account_payload(account)}


@router.post("/auth/login")
def login(payload: AdminCredentials, request: Request) -> dict[str, Any]:
    repo = _repo(request)
    credentials = repo.get_admin_credentials(payload.username)
    if credentials is None:
        # Burn comparable time so a missing username is not distinguishable
        # from a wrong password by response latency.
        verify_password(payload.password, _dummy_hash())
        raise _invalid_credentials()
    if not verify_password(payload.password, str(credentials["password_hash"])):
        raise _invalid_credentials()
    subject = str(credentials["username"])
    # ADR 20260726: `token`/`expiresAt` are additive. Callers that only read
    # `authenticated`/`subject` keep working, so this does not break the console's
    # existing login path.
    with repo.transaction() as tx:
        token, expires_at = tx.create_admin_token(
            subject=subject,
            ttl_seconds=AUTH_TOKEN_TTL_SECONDS,
        )
    return {
        "authenticated": True,
        "subject": subject,
        "token": token,
        "expiresAt": expires_at,
    }


@router.post("/auth/logout")
def logout(request: Request) -> dict[str, bool]:
    """Revoke the presented bearer token.

    Idempotent: an absent or already-revoked token still reports success, so a
    client cleaning up cannot get stuck on a token the server no longer knows.
    """
    token = _bearer_token(request)
    if token is None:
        return {"revoked": False}
    with _repo(request).transaction() as tx:
        revoked = tx.delete_admin_token(token)
    return {"revoked": revoked}


def require_admin_token(request: Request) -> str:
    """FastAPI dependency: the subject behind a valid bearer token.

    Gates only the endpoints that ask for it. The rest of the API stays
    unauthenticated (ADR 20260726), which is a recorded open question and not
    something this dependency closes.
    """
    token = _bearer_token(request)
    if token is None:
        raise _missing_token()
    subject = _repo(request).resolve_admin_token_subject(token)
    if subject is None:
        raise _invalid_token()
    return subject


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if not header:
        return None
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def _repo(request: Request) -> DesiredStateRepository:
    return DesiredStateRepository(request.app.state.settings.db_path)


def _validate_username(value: str) -> str:
    username = value.strip()
    if not _USERNAME_RE.fullmatch(username):
        raise NephosError(
            status_code=400,
            code="admin_username_invalid",
            message="Admin username must be 1-64 chars of letters, digits, . _ @ -.",
            details={"username": value},
        )
    return username


def _admin_exists() -> NephosError:
    return NephosError(
        status_code=409,
        code="admin_already_exists",
        message="An admin account already exists.",
    )


def _invalid_credentials() -> NephosError:
    return NephosError(
        status_code=401,
        code="invalid_credentials",
        message="Invalid username or password.",
    )


def _missing_token() -> NephosError:
    return NephosError(
        status_code=401,
        code="auth_token_required",
        message="A bearer token is required for this operation.",
    )


def _invalid_token() -> NephosError:
    return NephosError(
        status_code=401,
        code="auth_token_invalid",
        message="Bearer token is unknown or expired.",
    )


def _account_payload(account: AdminAccount) -> dict[str, Any]:
    return {
        "id": account.id,
        "username": account.username,
        "createdAt": account.created_at,
        "updatedAt": account.updated_at,
    }


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return hash_password("nephos-timing-equalizer")
