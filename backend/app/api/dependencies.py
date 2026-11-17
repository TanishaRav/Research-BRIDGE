from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request

from backend.app.domain.models import DemoRole
from backend.app.repositories.sqlite import SQLiteRepository
from backend.app.api.errors import ApiError


@dataclass(frozen=True)
class DemoPrincipal:
    role: DemoRole
    persona_id: str


def get_repository(request: Request) -> SQLiteRepository:
    return request.app.state.repository


def get_principal(
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
    role_header: Annotated[str | None, Header(alias="X-Demo-Role")] = None,
    persona_id: Annotated[str | None, Header(alias="X-Demo-Persona-Id")] = None,
) -> DemoPrincipal:
    if role_header is None or persona_id is None:
        raise ApiError(
            401,
            "demo_role_required",
            "X-Demo-Role and X-Demo-Persona-Id are required. The demo role is not authentication.",
        )
    try:
        role = DemoRole(role_header)
    except ValueError as exc:
        raise ApiError(403, "invalid_demo_role", "The declared demo role is not recognized.") from exc
    valid = False
    if role == DemoRole.ADMIN:
        valid = persona_id == "admin-demo-001"
    elif role == DemoRole.STUDENT:
        valid = repository.get_student(persona_id) is not None
    elif role == DemoRole.FACULTY:
        valid = repository.get_faculty(persona_id) is not None
    if not valid:
        raise ApiError(
            403,
            "invalid_demo_persona",
            "The persona does not belong to the declared seeded demo role.",
        )
    return DemoPrincipal(role=role, persona_id=persona_id)


def require_roles(*allowed: DemoRole):
    def dependency(
        principal: Annotated[DemoPrincipal, Depends(get_principal)],
    ) -> DemoPrincipal:
        if principal.role not in allowed:
            raise ApiError(403, "role_forbidden", "This demo role cannot access the route.")
        return principal

    return dependency


def require_idempotency_key(
    value: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    if value is None or not value.strip():
        raise ApiError(
            400,
            "idempotency_key_required",
            "Idempotency-Key is required for this consequential demo operation.",
            field_errors={"Idempotency-Key": ["Provide a nonempty idempotency key."]},
        )
    if len(value) > 200:
        raise ApiError(
            422,
            "invalid_idempotency_key",
            "Idempotency-Key must be at most 200 characters.",
            field_errors={"Idempotency-Key": ["Must be at most 200 characters."]},
        )
    return value
