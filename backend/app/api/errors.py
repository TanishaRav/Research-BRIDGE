from __future__ import annotations

from typing import Any


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        field_errors: dict[str, list[str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.field_errors = field_errors


def validation_field_errors(errors: list[dict[str, Any]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for error in errors:
        location = [str(part) for part in error.get("loc", ()) if part not in {"body", "query", "header"}]
        path = ".".join(location) or "$"
        result.setdefault(path, []).append(str(error.get("msg", "Invalid value")))
    return result
