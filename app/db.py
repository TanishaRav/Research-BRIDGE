"""SPARK database layer: single source of SQL.

Provides connect() -> sqlite3.Connection (Row factory + foreign keys ON),
init_db() to create the full schema from design.md s3, and typed query
helpers. All SQL is parameterized; callers never build SQL with string
interpolation of untrusted values.
"""

import os
import sqlite3
from datetime import datetime, timezone

# Repo-root spark.db by default; overridable for tests via SPARK_DB env var.
DB_PATH = os.environ.get(
    "SPARK_DB",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "spark.db"),
)


def utcnow():
    """Return a UTC ISO-8601 timestamp string (explicit timezone, per design)."""
    return datetime.now(timezone.utc).isoformat()


def connect(db_path=None):
    """Return a sqlite3.Connection with Row rows and foreign keys enforced."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ---------------------------------------------------------------------------
# Schema (design.md s3). Migrations-by-recreate for the demo.
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS org_units (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL,            -- 'university' | 'college' | 'department'
    parent_id   INTEGER REFERENCES org_units(id) ON DELETE SET NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    email          TEXT NOT NULL UNIQUE,
    display_name   TEXT NOT NULL,
    given_name     TEXT NOT NULL DEFAULT '',
    family_name    TEXT NOT NULL DEFAULT '',
    role           TEXT NOT NULL,         -- 'admin' | 'manager' | 'faculty' | 'student'
    password_hash  TEXT NOT NULL,         -- PBKDF2-HMAC-SHA256 hex digest
    password_salt  TEXT NOT NULL,         -- per-user random salt (hex)
    password_iter  INTEGER NOT NULL,      -- PBKDF2 iteration count
    is_blocked     INTEGER NOT NULL DEFAULT 0,
    org_unit_id    INTEGER REFERENCES org_units(id) ON DELETE SET NULL,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS departments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    org_unit_id INTEGER REFERENCES org_units(id) ON DELETE SET NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS majors (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    kind         TEXT NOT NULL DEFAULT 'major',  -- 'major' | 'minor'
    department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

-- symmetric relatedness between majors (biology ~ bioinformatics, etc.)
CREATE TABLE IF NOT EXISTS related_majors (
    major_id         INTEGER NOT NULL REFERENCES majors(id) ON DELETE CASCADE,
    related_major_id INTEGER NOT NULL REFERENCES majors(id) ON DELETE CASCADE,
    weight           REAL NOT NULL DEFAULT 1.0,
    PRIMARY KEY (major_id, related_major_id)
);

CREATE TABLE IF NOT EXISTS match_sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    org_unit_id   INTEGER REFERENCES org_units(id) ON DELETE SET NULL,
    mode          TEXT NOT NULL,          -- 'mutual' | 'student' preference modes
    status        TEXT NOT NULL,          -- 'draft'|'open'|'preferencing'|'matching'|'review'|'contracting'|'closed'
    prefs_open_at TEXT,
    prefs_close_at TEXT,
    timezone      TEXT NOT NULL DEFAULT 'UTC',
    description   TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_managers (
    session_id  INTEGER NOT NULL REFERENCES match_sessions(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (session_id, user_id)
);

CREATE TABLE IF NOT EXISTS custom_questions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES match_sessions(id) ON DELETE CASCADE,
    prompt      TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'text',  -- 'text' | 'longtext' | 'choice'
    required    INTEGER NOT NULL DEFAULT 0,
    max_words   INTEGER,
    position    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    INTEGER NOT NULL REFERENCES match_sessions(id) ON DELETE CASCADE,
    title         TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',   -- sanitized HTML (allowlist) at write time
    capacity      INTEGER NOT NULL DEFAULT 1,
    status        TEXT NOT NULL DEFAULT 'draft', -- 'draft'|'published'|'withdrawn'
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_mentors (
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role        TEXT NOT NULL DEFAULT 'faculty',  -- 'faculty' | 'co-mentor'
    created_at  TEXT NOT NULL,
    PRIMARY KEY (project_id, user_id)
);

CREATE TABLE IF NOT EXISTS project_eligible_majors (
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    major_id    INTEGER NOT NULL REFERENCES majors(id) ON DELETE CASCADE,
    PRIMARY KEY (project_id, major_id)
);

CREATE TABLE IF NOT EXISTS student_profiles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id    INTEGER NOT NULL REFERENCES match_sessions(id) ON DELETE CASCADE,
    year          TEXT NOT NULL DEFAULT '',
    gpa           REAL,
    bio           TEXT NOT NULL DEFAULT '',
    submitted     INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    UNIQUE (user_id, session_id)
);

CREATE TABLE IF NOT EXISTS profile_majors (
    profile_id  INTEGER NOT NULL REFERENCES student_profiles(id) ON DELETE CASCADE,
    major_id    INTEGER NOT NULL REFERENCES majors(id) ON DELETE CASCADE,
    PRIMARY KEY (profile_id, major_id)
);

CREATE TABLE IF NOT EXISTS answers (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id   INTEGER NOT NULL REFERENCES student_profiles(id) ON DELETE CASCADE,
    question_id  INTEGER NOT NULL REFERENCES custom_questions(id) ON DELETE CASCADE,
    body         TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    UNIQUE (profile_id, question_id)
);

CREATE TABLE IF NOT EXISTS favorites (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL,
    UNIQUE (user_id, project_id)
);

-- Ranked preferences. actor_role distinguishes student->project and
-- faculty/project->student preferencing used in mutual-preference sessions.
CREATE TABLE IF NOT EXISTS preferences (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES match_sessions(id) ON DELETE CASCADE,
    actor_role  TEXT NOT NULL,            -- 'student' | 'project'
    student_id  INTEGER REFERENCES users(id) ON DELETE CASCADE,
    project_id  INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    rank        INTEGER NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS match_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   INTEGER NOT NULL REFERENCES match_sessions(id) ON DELETE CASCADE,
    status       TEXT NOT NULL DEFAULT 'pending',  -- 'pending'|'complete'|'failed'
    config_json  TEXT NOT NULL DEFAULT '{}',
    stats_json   TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS matches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES match_sessions(id) ON DELETE CASCADE,
    run_id      INTEGER REFERENCES match_runs(id) ON DELETE SET NULL,
    student_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    status      TEXT NOT NULL DEFAULT 'proposed', -- 'proposed'|'accepted'|'declined'|'rematch'
    score       REAL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contracts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id    INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    status      TEXT NOT NULL DEFAULT 'draft',  -- 'draft'|'sent'|'signed'|'placed'
    terms       TEXT NOT NULL DEFAULT '',
    signed_at   TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,
    subject     TEXT NOT NULL DEFAULT '',
    body        TEXT NOT NULL DEFAULT '',
    is_read     INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ratings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES match_sessions(id) ON DELETE CASCADE,
    rater_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    stars       INTEGER NOT NULL,
    comment     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- Server-side session store for signed, HttpOnly cookies.
CREATE TABLE IF NOT EXISTS auth_sessions (
    token       TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf_token  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    last_seen   TEXT NOT NULL
);
"""


def init_db(db_path=None):
    """Create the full schema if it does not yet exist."""
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def reset_db(db_path=None):
    """Drop and recreate the database file (migrations-by-recreate for the demo)."""
    path = db_path or DB_PATH
    if os.path.exists(path):
        os.remove(path)
    init_db(path)


# ---------------------------------------------------------------------------
# Typed query helpers (all parameterized).
# ---------------------------------------------------------------------------

def _table_columns(conn, table):
    """Return the set of column names for a table (trusted literal name)."""
    rows = conn.execute("PRAGMA table_info(%s)" % table).fetchall()
    return {r["name"] for r in rows}


def insert(conn, table, **cols):
    """Insert a row with a created_at default where the table has one.

    `table` is a trusted literal supplied by application code, never user
    input. Column names come from keyword args (also trusted literals);
    values are always bound as parameters.
    """
    columns_present = _table_columns(conn, table)
    if "created_at" in columns_present and "created_at" not in cols:
        cols["created_at"] = utcnow()
    keys = list(cols.keys())
    placeholders = ", ".join("?" for _ in keys)
    columns = ", ".join(keys)
    sql = "INSERT INTO %s (%s) VALUES (%s)" % (table, columns, placeholders)
    cur = conn.execute(sql, [cols[k] for k in keys])
    return cur.lastrowid


def get_user_by_email(conn, email):
    return conn.execute(
        "SELECT * FROM users WHERE email = ?", (email,)
    ).fetchone()


def get_user_by_id(conn, user_id):
    return conn.execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ).fetchone()


def create_auth_session(conn, token, user_id, csrf_token):
    now = utcnow()
    conn.execute(
        "INSERT INTO auth_sessions (token, user_id, csrf_token, created_at, last_seen) "
        "VALUES (?, ?, ?, ?, ?)",
        (token, user_id, csrf_token, now, now),
    )
    conn.commit()


def get_auth_session(conn, token):
    return conn.execute(
        "SELECT * FROM auth_sessions WHERE token = ?", (token,)
    ).fetchone()


def touch_auth_session(conn, token):
    conn.execute(
        "UPDATE auth_sessions SET last_seen = ? WHERE token = ?",
        (utcnow(), token),
    )
    conn.commit()


def delete_auth_session(conn, token):
    conn.execute("DELETE FROM auth_sessions WHERE token = ?", (token,))
    conn.commit()


def list_sessions(conn):
    return conn.execute(
        "SELECT * FROM match_sessions ORDER BY created_at DESC"
    ).fetchall()


def get_session(conn, session_id):
    return conn.execute(
        "SELECT * FROM match_sessions WHERE id = ?", (session_id,)
    ).fetchone()


def is_session_manager(conn, session_id, user_id):
    row = conn.execute(
        "SELECT 1 FROM session_managers WHERE session_id = ? AND user_id = ?",
        (session_id, user_id),
    ).fetchone()
    return row is not None
