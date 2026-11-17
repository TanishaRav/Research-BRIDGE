from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.db import create_database
from backend.app.main import create_app
from backend.app.repositories.sqlite import SQLiteRepository
from backend.app.seed.seed_data import seed_database


@pytest.fixture
def settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'researchbridge-test.db'}",
        solver_timeout_seconds=3,
        cors_origins=["http://localhost:3000"],
    )


@pytest.fixture
def database(settings):
    database = create_database(settings.database_url)
    seed_database(database)
    return database


@pytest.fixture
def repository(database):
    return SQLiteRepository(database)


@pytest.fixture
def app(settings, database):
    return create_app(settings, seed_if_empty=False)


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=False) as value:
        yield value


@pytest.fixture
def admin_headers():
    return {"X-Demo-Role": "admin", "X-Demo-Persona-Id": "admin-demo-001"}


@pytest.fixture
def student_headers():
    return {"X-Demo-Role": "student", "X-Demo-Persona-Id": "student-syn-001"}


@pytest.fixture
def faculty_headers():
    return {
        "X-Demo-Role": "faculty",
        "X-Demo-Persona-Id": "faculty-fictional-001",
    }
