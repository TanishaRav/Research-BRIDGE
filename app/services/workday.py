"""Workday people/org directory service stub (R3.2, R3.8).

The production system will call an external Workday API to search people and
pull org/department/major reference data. For the demo this stub searches the
seeded users/departments/majors already in SQLite, behind the same small
interface so FEAT-004 can swap in the real placement integration without
touching callers.

Stdlib only; takes an open sqlite3 connection so it shares the request
transaction and never opens the network (INTEGRATIONS_ONLY).
"""


def search_people(conn, query, limit=10):
    """Return faculty/staff users matching `query` by name or email.

    Case-insensitive substring match over display_name, given_name,
    family_name, and email. Restricted to faculty-capable roles so the mentor
    picker never surfaces students.
    """
    q = (query or "").strip().lower()
    rows = conn.execute(
        "SELECT id, display_name, given_name, family_name, email, role "
        "FROM users WHERE role IN ('faculty', 'manager', 'admin') "
        "ORDER BY family_name, given_name"
    ).fetchall()
    if not q:
        return [dict(r) for r in rows[:limit]]
    out = []
    for r in rows:
        hay = " ".join([
            r["display_name"] or "", r["given_name"] or "",
            r["family_name"] or "", r["email"] or "",
        ]).lower()
        if q in hay:
            out.append(dict(r))
        if len(out) >= limit:
            break
    return out


def list_departments(conn):
    """Return seeded departments (id, name)."""
    rows = conn.execute(
        "SELECT id, name FROM departments ORDER BY name"
    ).fetchall()
    return [dict(r) for r in rows]


def list_majors(conn):
    """Return seeded majors/minors (id, name, kind)."""
    rows = conn.execute(
        "SELECT id, name, kind FROM majors ORDER BY name"
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Placement synthesis (R8.4). In production these call Workday to register a
# student in a course section (for-credit) or open an hourly job requisition
# (for-pay). The stub derives a deterministic, human-readable placement_ref
# from the project's department and the match id so the demo can show a result.
# ---------------------------------------------------------------------------

# Department name -> course subject prefix for a synthesized section code.
_SUBJECT_PREFIXES = {
    "Biology": "BIOL",
    "Materials Engineering": "MSE",
    "Chemistry": "CHEM",
}


def _subject_for_project(conn, project):
    """Return a short subject prefix (e.g. 'BIOL') for a project row."""
    dept_id = project["primary_department_id"] if "primary_department_id" in project.keys() else None
    name = None
    if dept_id:
        row = conn.execute(
            "SELECT name FROM departments WHERE id = ?", (dept_id,)
        ).fetchone()
        if row is not None:
            name = row["name"]
    if name and name in _SUBJECT_PREFIXES:
        return _SUBJECT_PREFIXES[name]
    if name:
        # Fall back to the first four uppercase letters of the department name.
        letters = "".join(ch for ch in name.upper() if ch.isalpha())
        return (letters[:4] or "RSCH")
    return "RSCH"


def assign_course_section(conn, match, project):
    """Synthesize a for-credit course section reference, e.g. 'BIOL 2900-34'.

    The catalog number is a fixed research-course number (2900); the section
    suffix is derived from the match id so each placement gets a distinct,
    stable code.
    """
    subject = _subject_for_project(conn, project)
    section = 10 + (match["id"] % 90)  # two-digit section 10..99
    return "%s 2900-%02d" % (subject, section)


def add_hourly_job(conn, match, project):
    """Synthesize a for-pay hourly job requisition reference, e.g. 'JOB-000042'."""
    return "JOB-%06d" % match["id"]
