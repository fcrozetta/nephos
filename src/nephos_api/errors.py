from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class NephosError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


def nephos_error_response(error: NephosError) -> JSONResponse:
    payload: dict[str, Any] = {
        "error": {
            "code": error.code,
            "message": error.message,
        }
    }
    if error.details is not None:
        payload["error"]["details"] = error.details
    return JSONResponse(status_code=error.status_code, content=payload)


async def nephos_error_handler(_request: Request, exc: NephosError) -> JSONResponse:
    return nephos_error_response(exc)
