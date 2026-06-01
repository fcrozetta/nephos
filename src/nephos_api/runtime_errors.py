from __future__ import annotations


class RuntimeBlockedError(RuntimeError):
    def __init__(self, *, reason: str, message: str) -> None:
        self.reason = reason
        super().__init__(message)
