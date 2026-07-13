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
    return {"authenticated": True, "subject": str(credentials["username"])}


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
