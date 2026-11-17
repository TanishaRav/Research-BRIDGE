from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.config import get_settings

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


class Database:
    """SQLite database boundary with explicit SQL migrations and short transactions."""

    def __init__(self, url: str) -> None:
        self.url = url
        self._ensure_sqlite_parent()
        self.engine = self._build_engine()
        self.session_factory = sessionmaker(
            bind=self.engine, class_=Session, expire_on_commit=False, autoflush=False
        )

    def _ensure_sqlite_parent(self) -> None:
        parsed = make_url(self.url)
        if parsed.drivername.startswith("sqlite") and parsed.database not in (None, ":memory:"):
            Path(parsed.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

    def _build_engine(self) -> Engine:
        connect_args = {"check_same_thread": False} if self.url.startswith("sqlite") else {}
        engine_options: dict[str, object] = {"future": True, "connect_args": connect_args}
        if make_url(self.url).database == ":memory:":
            engine_options["poolclass"] = StaticPool
        engine = create_engine(self.url, **engine_options)

        if self.url.startswith("sqlite"):

            @event.listens_for(engine, "connect")
            def configure_sqlite(dbapi_connection: object, _connection_record: object) -> None:
                cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=5000")
                try:
                    cursor.execute("PRAGMA journal_mode=WAL")
                except Exception:
                    # Some in-memory/read-only SQLite connections cannot switch journal mode.
                    pass
                cursor.close()

        return engine

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def migrate(self) -> list[str]:
        migration_files = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"))
        applied: list[str] = []
        raw = self.engine.raw_connection()
        try:
            cursor = raw.cursor()
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, filename TEXT NOT NULL UNIQUE, "
                "applied_at TEXT NOT NULL DEFAULT "
                "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now')))"
            )
            existing = {row[0] for row in cursor.execute("SELECT version FROM schema_migrations")}
            for migration_file in migration_files:
                version = int(migration_file.name.split("_", 1)[0])
                if version in existing:
                    continue
                cursor.executescript(migration_file.read_text(encoding="utf-8"))
                cursor.execute(
                    "INSERT INTO schema_migrations(version, filename) VALUES (?, ?)",
                    (version, migration_file.name),
                )
                raw.commit()
                applied.append(migration_file.name)
            raw.commit()
        except Exception:
            raw.rollback()
            raise
        finally:
            raw.close()
        return applied

    def is_ready(self) -> tuple[bool, str]:
        try:
            with self.engine.connect() as connection:
                count = connection.execute(
                    text("SELECT COUNT(*) FROM schema_migrations")
                ).scalar_one()
            return (count > 0, "ready" if count > 0 else "migrations-missing")
        except Exception:
            return (False, "unavailable")

    def recreate(self) -> None:
        """Replace only the configured local SQLite demo database."""
        parsed = make_url(self.url)
        if not parsed.drivername.startswith("sqlite"):
            raise RuntimeError("demo reset is limited to SQLite")
        self.engine.dispose()
        if parsed.database not in (None, ":memory:"):
            database_path = Path(parsed.database).expanduser().resolve()
            for candidate in (
                database_path,
                Path(f"{database_path}-wal"),
                Path(f"{database_path}-shm"),
            ):
                candidate.unlink(missing_ok=True)
        self.migrate()


def create_database(url: str | None = None, *, migrate: bool = True) -> Database:
    database = Database(url or get_settings().database_url)
    if migrate:
        database.migrate()
    return database


def main() -> None:
    parser = argparse.ArgumentParser(description="ResearchBridge database migration runner")
    parser.add_argument("command", choices=["migrate", "status"])
    args = parser.parse_args()
    database = create_database(migrate=False)
    if args.command == "migrate":
        applied = database.migrate()
        print(json.dumps({"database": "synthetic-demo", "applied": applied, "ready": True}))
    else:
        ready, detail = database.is_ready()
        print(json.dumps({"ready": ready, "detail": detail}))
        raise SystemExit(0 if ready else 1)


if __name__ == "__main__":
    main()
