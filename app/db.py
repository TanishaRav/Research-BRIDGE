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
    matching_method TEXT NOT NULL DEFAULT 'mutual', -- 'none'|'ai'|'student'|'mutual'
    weighting     TEXT NOT NULL DEFAULT 'equal',    -- 'equal'|'faculty_heavy'
    prefs_open_at TEXT,
    prefs_close_at TEXT,
    timezone      TEXT NOT NULL DEFAULT 'UTC',
    -- Per-phase deadlines (ISO-8601 with explicit offset; see deadlines helper).
    deadline_student_profile    TEXT,
    deadline_faculty_project    TEXT,
    deadline_student_preference TEXT,
    deadline_faculty_preference TEXT,
    deadline_contract           TEXT,
    -- Per-phase manual reopen flags: when 1 the phase accepts edits even past
    -- its deadline (R2.5). Stored as a comma-separated set of phase keys.
    reopened_phases TEXT NOT NULL DEFAULT '',
    -- Feature toggles (R2.7).
    allow_super_interest INTEGER NOT NULL DEFAULT 0,
    favorite_invites     INTEGER NOT NULL DEFAULT 0,
    show_ratings         INTEGER NOT NULL DEFAULT 0,
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
    target      TEXT NOT NULL DEFAULT 'profile', -- 'profile' | 'project' (R2.9)
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
    background    TEXT NOT NULL DEFAULT '',   -- plain text, <=100 words (R3.4)
    responsibilities TEXT NOT NULL DEFAULT '',-- plain text, <=100 words (R3.4)
    primary_department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
    is_group      INTEGER NOT NULL DEFAULT 0,
    positions     INTEGER NOT NULL DEFAULT 1,
    capacity      INTEGER NOT NULL DEFAULT 1, -- kept in sync with positions
    noncitizen_eligible INTEGER NOT NULL DEFAULT 1, -- default yes (R3.6)
    comp_type     TEXT NOT NULL DEFAULT 'credit', -- 'credit' | 'pay'
    credit_option TEXT NOT NULL DEFAULT '',   -- '1'|'2'|'3'|'1-2'|'1-3'|'2-3'
    course_name   TEXT NOT NULL DEFAULT '',
    hourly_rate   REAL,
    cap_kind      TEXT NOT NULL DEFAULT '',   -- 'hours' | 'dollars' | ''
    cap_value     REAL,
    major_policy  TEXT NOT NULL DEFAULT 'none', -- 'must' | 'prefer' | 'none' (R3.8)
    alert_on_preference INTEGER NOT NULL DEFAULT 0, -- (R3.9)
    alert_scope   TEXT NOT NULL DEFAULT 'each', -- 'each' | 'digest'
    copied_from_project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL, -- (R3.13)
    status        TEXT NOT NULL DEFAULT 'draft', -- 'draft'|'published'|'withdrawn'
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_mentors (
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role        TEXT NOT NULL DEFAULT 'faculty',  -- 'faculty' | 'co-mentor'
    is_pi       INTEGER NOT NULL DEFAULT 0,        -- exactly one PI per project (R3.1)
    permission  TEXT NOT NULL DEFAULT 'editor',   -- 'editor' | 'preferencing' | 'viewer'
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
    email         TEXT NOT NULL DEFAULT '',
    given_name    TEXT NOT NULL DEFAULT '',
    family_name   TEXT NOT NULL DEFAULT '',
    year          TEXT NOT NULL DEFAULT '',
    gpa           REAL,
    bio           TEXT NOT NULL DEFAULT '',
    interests     TEXT NOT NULL DEFAULT '',   -- <=250 words (R4.3)
    background    TEXT NOT NULL DEFAULT '',   -- <=100 words
    programming   TEXT NOT NULL DEFAULT '',   -- <=100 words
    time_kind     TEXT NOT NULL DEFAULT 'credit', -- 'credit' | 'pay' (R4.4)
    credit_option TEXT NOT NULL DEFAULT '',   -- '1'|'2'|'3'|'1-2'|'1-3'|'2-3'
    pay_hours     INTEGER,
    noncitizen    INTEGER NOT NULL DEFAULT 0,
    copied_from_profile_id INTEGER REFERENCES student_profiles(id) ON DELETE SET NULL, -- (R4.5)
    submitted     INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    UNIQUE (user_id, session_id)
);

CREATE TABLE IF NOT EXISTS profile_majors (
    profile_id  INTEGER NOT NULL REFERENCES student_profiles(id) ON DELETE CASCADE,
    major_id    INTEGER NOT NULL REFERENCES majors(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL DEFAULT 'major', -- 'major' | 'secondary' | 'minor' (R4.3)
    PRIMARY KEY (profile_id, major_id, kind)
);

-- Custom-question answers. A row belongs to either a student profile or a
-- project (R2.9); exactly one of profile_id/project_id is set.
CREATE TABLE IF NOT EXISTS answers (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id   INTEGER REFERENCES student_profiles(id) ON DELETE CASCADE,
    project_id   INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    question_id  INTEGER NOT NULL REFERENCES custom_questions(id) ON DELETE CASCADE,
    body         TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    UNIQUE (profile_id, question_id),
    UNIQUE (project_id, question_id)
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


# ---------------------------------------------------------------------------
# Session visibility and lifecycle (R2)
# ---------------------------------------------------------------------------

def list_sessions_for_user(conn, user):
    """Sessions visible to `user` (R2.8): admin sees all; a manager sees the
    sessions they own or were added to via session_managers; others see only
    non-draft sessions they can participate in."""
    role = user["role"]
    if role == "admin":
        return conn.execute(
            "SELECT * FROM match_sessions ORDER BY created_at DESC"
        ).fetchall()
    if role == "manager":
        return conn.execute(
            "SELECT * FROM match_sessions WHERE id IN "
            "(SELECT session_id FROM session_managers WHERE user_id = ?) "
            "ORDER BY created_at DESC",
            (user["id"],),
        ).fetchall()
    # Faculty/students see any session that is past 'draft'.
    return conn.execute(
        "SELECT * FROM match_sessions WHERE status != 'draft' ORDER BY created_at DESC"
    ).fetchall()


def can_manage_session(conn, session, user):
    """True if `user` may configure/advance `session` (R2.8)."""
    if user is None:
        return False
    if user["role"] == "admin":
        return True
    if user["role"] == "manager":
        return is_session_manager(conn, session["id"], user["id"])
    return False


def can_view_session(conn, session, user):
    """True if `user` may see `session` at all."""
    if user is None:
        return False
    if can_manage_session(conn, session, user):
        return True
    return session["status"] != "draft"


def add_session_manager(conn, session_id, user_id):
    row = conn.execute(
        "SELECT 1 FROM session_managers WHERE session_id = ? AND user_id = ?",
        (session_id, user_id),
    ).fetchone()
    if row is None:
        insert(conn, "session_managers", session_id=session_id, user_id=user_id)


# ---------------------------------------------------------------------------
# Majors / departments (R3.8, R4.3, R5.2)
# ---------------------------------------------------------------------------

def list_majors(conn, kind=None):
    if kind is None:
        return conn.execute("SELECT * FROM majors ORDER BY name").fetchall()
    return conn.execute(
        "SELECT * FROM majors WHERE kind = ? ORDER BY name", (kind,)
    ).fetchall()


def list_departments(conn):
    return conn.execute("SELECT * FROM departments ORDER BY name").fetchall()


def related_major_ids(conn, major_ids):
    """Return the set of major ids related to any id in `major_ids` (R5.2)."""
    if not major_ids:
        return set()
    out = set()
    for mid in major_ids:
        rows = conn.execute(
            "SELECT related_major_id FROM related_majors WHERE major_id = ?", (mid,)
        ).fetchall()
        for r in rows:
            out.add(r["related_major_id"])
    return out


# ---------------------------------------------------------------------------
# Custom questions / answers (R2.9)
# ---------------------------------------------------------------------------

def list_questions(conn, session_id, target):
    return conn.execute(
        "SELECT * FROM custom_questions WHERE session_id = ? AND target = ? "
        "ORDER BY position, id",
        (session_id, target),
    ).fetchall()


def get_profile_answers(conn, profile_id):
    rows = conn.execute(
        "SELECT * FROM answers WHERE profile_id = ?", (profile_id,)
    ).fetchall()
    return {r["question_id"]: r["body"] for r in rows}


def get_project_answers(conn, project_id):
    rows = conn.execute(
        "SELECT * FROM answers WHERE project_id = ?", (project_id,)
    ).fetchall()
    return {r["question_id"]: r["body"] for r in rows}


def upsert_answer(conn, question_id, body, profile_id=None, project_id=None):
    if profile_id is not None:
        existing = conn.execute(
            "SELECT id FROM answers WHERE profile_id = ? AND question_id = ?",
            (profile_id, question_id),
        ).fetchone()
    else:
        existing = conn.execute(
            "SELECT id FROM answers WHERE project_id = ? AND question_id = ?",
            (project_id, question_id),
        ).fetchone()
    if existing is None:
        insert(conn, "answers", profile_id=profile_id, project_id=project_id,
               question_id=question_id, body=body, updated_at=utcnow())
    else:
        conn.execute(
            "UPDATE answers SET body = ?, updated_at = ? WHERE id = ?",
            (body, utcnow(), existing["id"]),
        )


# ---------------------------------------------------------------------------
# Projects (R3)
# ---------------------------------------------------------------------------

def list_projects(conn, session_id):
    return conn.execute(
        "SELECT * FROM projects WHERE session_id = ? ORDER BY created_at DESC, id DESC",
        (session_id,),
    ).fetchall()


def list_published_projects(conn, session_id):
    return conn.execute(
        "SELECT * FROM projects WHERE session_id = ? AND status = 'published' "
        "ORDER BY title",
        (session_id,),
    ).fetchall()


def get_project(conn, project_id):
    return conn.execute(
        "SELECT * FROM projects WHERE id = ?", (project_id,)
    ).fetchone()


def project_mentors(conn, project_id):
    return conn.execute(
        "SELECT pm.*, u.display_name, u.email, u.given_name, u.family_name "
        "FROM project_mentors pm JOIN users u ON u.id = pm.user_id "
        "WHERE pm.project_id = ? ORDER BY pm.is_pi DESC, u.display_name",
        (project_id,),
    ).fetchall()


def is_project_mentor(conn, project_id, user_id):
    row = conn.execute(
        "SELECT 1 FROM project_mentors WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()
    return row is not None


def project_eligible_major_ids(conn, project_id):
    rows = conn.execute(
        "SELECT major_id FROM project_eligible_majors WHERE project_id = ?",
        (project_id,),
    ).fetchall()
    return [r["major_id"] for r in rows]


def set_project_eligible_majors(conn, project_id, major_ids):
    conn.execute("DELETE FROM project_eligible_majors WHERE project_id = ?", (project_id,))
    for mid in major_ids:
        insert(conn, "project_eligible_majors", project_id=project_id, major_id=mid)


def set_project_mentors(conn, project_id, mentors):
    """mentors: list of dicts {user_id, is_pi, permission}."""
    conn.execute("DELETE FROM project_mentors WHERE project_id = ?", (project_id,))
    for m in mentors:
        insert(conn, "project_mentors", project_id=project_id, user_id=m["user_id"],
               role="faculty", is_pi=1 if m.get("is_pi") else 0,
               permission=m.get("permission", "editor"))


# ---------------------------------------------------------------------------
# Student profiles (R4)
# ---------------------------------------------------------------------------

def get_profile(conn, profile_id):
    return conn.execute(
        "SELECT * FROM student_profiles WHERE id = ?", (profile_id,)
    ).fetchone()


def get_profile_for_user(conn, session_id, user_id):
    return conn.execute(
        "SELECT * FROM student_profiles WHERE session_id = ? AND user_id = ?",
        (session_id, user_id),
    ).fetchone()


def list_submitted_profiles(conn, session_id):
    return conn.execute(
        "SELECT sp.*, u.display_name FROM student_profiles sp "
        "JOIN users u ON u.id = sp.user_id "
        "WHERE sp.session_id = ? AND sp.submitted = 1 ORDER BY sp.family_name, sp.given_name",
        (session_id,),
    ).fetchall()


def profile_majors(conn, profile_id):
    return conn.execute(
        "SELECT pm.major_id, pm.kind, m.name FROM profile_majors pm "
        "JOIN majors m ON m.id = pm.major_id WHERE pm.profile_id = ?",
        (profile_id,),
    ).fetchall()


def profile_major_ids(conn, profile_id):
    rows = conn.execute(
        "SELECT major_id FROM profile_majors WHERE profile_id = ?", (profile_id,)
    ).fetchall()
    return [r["major_id"] for r in rows]


def set_profile_majors(conn, profile_id, items):
    """items: list of (major_id, kind)."""
    conn.execute("DELETE FROM profile_majors WHERE profile_id = ?", (profile_id,))
    seen = set()
    for mid, kind in items:
        key = (mid, kind)
        if key in seen:
            continue
        seen.add(key)
        insert(conn, "profile_majors", profile_id=profile_id, major_id=mid, kind=kind)


# ---------------------------------------------------------------------------
# Favorites and preferences (R5)
# ---------------------------------------------------------------------------

def add_favorite(conn, user_id, project_id):
    row = conn.execute(
        "SELECT 1 FROM favorites WHERE user_id = ? AND project_id = ?",
        (user_id, project_id),
    ).fetchone()
    if row is None:
        insert(conn, "favorites", user_id=user_id, project_id=project_id)


def remove_favorite(conn, user_id, project_id):
    conn.execute(
        "DELETE FROM favorites WHERE user_id = ? AND project_id = ?",
        (user_id, project_id),
    )


def list_favorites(conn, user_id, session_id):
    return conn.execute(
        "SELECT p.* FROM favorites f JOIN projects p ON p.id = f.project_id "
        "WHERE f.user_id = ? AND p.session_id = ? ORDER BY f.created_at",
        (user_id, session_id),
    ).fetchall()


def favorite_project_ids(conn, user_id):
    rows = conn.execute(
        "SELECT project_id FROM favorites WHERE user_id = ?", (user_id,)
    ).fetchall()
    return {r["project_id"] for r in rows}


def favorite_count(conn, project_id):
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM favorites WHERE project_id = ?", (project_id,)
    ).fetchone()
    return row["n"]


def students_who_favorited(conn, project_id):
    return conn.execute(
        "SELECT DISTINCT user_id FROM favorites WHERE project_id = ?", (project_id,)
    ).fetchall()


def get_preferences(conn, session_id, actor_role, student_id=None, project_id=None):
    if actor_role == "student":
        return conn.execute(
            "SELECT * FROM preferences WHERE session_id = ? AND actor_role = 'student' "
            "AND student_id = ? ORDER BY rank",
            (session_id, student_id),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM preferences WHERE session_id = ? AND actor_role = 'project' "
        "AND project_id = ? ORDER BY rank",
        (session_id, project_id),
    ).fetchall()


def replace_student_preferences(conn, session_id, student_id, project_ids):
    conn.execute(
        "DELETE FROM preferences WHERE session_id = ? AND actor_role = 'student' "
        "AND student_id = ?",
        (session_id, student_id),
    )
    for rank, pid in enumerate(project_ids, start=1):
        insert(conn, "preferences", session_id=session_id, actor_role="student",
               student_id=student_id, project_id=pid, rank=rank, updated_at=utcnow())


def replace_project_preferences(conn, session_id, project_id, student_ids):
    conn.execute(
        "DELETE FROM preferences WHERE session_id = ? AND actor_role = 'project' "
        "AND project_id = ?",
        (session_id, project_id),
    )
    for rank, sid in enumerate(student_ids, start=1):
        insert(conn, "preferences", session_id=session_id, actor_role="project",
               student_id=sid, project_id=project_id, rank=rank, updated_at=utcnow())


def update_session(conn, session_id, **cols):
    if not cols:
        return
    cols["updated_at"] = utcnow()
    keys = list(cols.keys())
    assignments = ", ".join("%s = ?" % k for k in keys)
    conn.execute(
        "UPDATE match_sessions SET %s WHERE id = ?" % assignments,
        [cols[k] for k in keys] + [session_id],
    )


def update_project(conn, project_id, **cols):
    if not cols:
        return
    cols["updated_at"] = utcnow()
    keys = list(cols.keys())
    assignments = ", ".join("%s = ?" % k for k in keys)
    conn.execute(
        "UPDATE projects SET %s WHERE id = ?" % assignments,
        [cols[k] for k in keys] + [project_id],
    )


def update_profile(conn, profile_id, **cols):
    if not cols:
        return
    cols["updated_at"] = utcnow()
    keys = list(cols.keys())
    assignments = ", ".join("%s = ?" % k for k in keys)
    conn.execute(
        "UPDATE student_profiles SET %s WHERE id = ?" % assignments,
        [cols[k] for k in keys] + [profile_id],
    )
