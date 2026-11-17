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
