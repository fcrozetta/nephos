from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class NephosError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def nephos_error_response(_request: Request, exc: NephosError) -> JSONResponse:
    error: dict[str, Any] = {
        "code": exc.code,
        "message": exc.message,
    }
    if exc.details is not None:
        error["details"] = exc.details
    return JSONResponse(status_code=exc.status_code, content={"error": error})
