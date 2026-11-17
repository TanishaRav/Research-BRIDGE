from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api.errors import ApiError, validation_field_errors
from backend.app.api.routes import router
from backend.app.config import Settings, get_settings
from backend.app.db import create_database
from backend.app.repositories.sqlite import RepositoryConflict, SQLiteRepository
from backend.app.seed.seed_data import seed_database

logger = logging.getLogger("researchbridge.api")


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", f"request-{uuid4().hex}")


def create_app(settings: Settings | None = None, *, seed_if_empty: bool = True) -> FastAPI:
    selected_settings = settings or get_settings()
    database = create_database(selected_settings.database_url)
    repository = SQLiteRepository(database)
    if seed_if_empty and repository.count_students() == 0:
        seed_database(database)

    application = FastAPI(
        title="ResearchBridge API",
        summary="Synthetic-data, explainable research placement prototype",
        description=(
            "Independent prototype with demo persona guards, not production authentication or "
            "an official Iowa State service."
        ),
        version="0.2.0",
    )
    application.state.settings = selected_settings
    application.state.database = database
    application.state.repository = repository

    application.add_middleware(
        CORSMiddleware,
        allow_origins=selected_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "X-Demo-Role",
            "X-Demo-Persona-Id",
            "Idempotency-Key",
        ],
    )

    @application.middleware("http")
    async def attach_request_id(request: Request, call_next):
        request.state.request_id = f"request-{uuid4().hex}"
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        return response

    @application.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        content = {
            "code": exc.code,
            "message": exc.message,
            "request_id": _request_id(request),
        }
        if exc.field_errors:
            content["field_errors"] = exc.field_errors
        return JSONResponse(status_code=exc.status_code, content=content)

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": "request_validation_failed",
                "message": "The request contains invalid or missing fields.",
                "field_errors": validation_field_errors(exc.errors()),
                "request_id": _request_id(request),
            },
        )

    @application.exception_handler(RepositoryConflict)
    async def repository_conflict_handler(
        request: Request, exc: RepositoryConflict
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "code": "state_conflict",
                "message": str(exc),
                "request_id": _request_id(request),
            },
        )

    @application.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled API error request_id=%s error_type=%s",
            _request_id(request),
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content={
                "code": "internal_error",
                "message": "The synthetic demo request could not be completed.",
                "request_id": _request_id(request),
            },
        )

    @application.get("/health/live", tags=["health"])
    def live() -> dict[str, str]:
        return {"status": "ok", "service": "researchbridge-api"}

    @application.get("/health/ready", tags=["health"])
    def ready() -> JSONResponse:
        is_ready, detail = database.is_ready()
        status_code = 200 if is_ready else 503
        return JSONResponse(
            status_code=status_code,
            content={
                "status": "ready" if is_ready else "not-ready",
                "database": detail,
                "synthetic_demo": "independent-prototype",
            },
        )

    application.include_router(router)
    return application


app = create_app()
