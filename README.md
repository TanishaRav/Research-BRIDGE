# SPARK — Student-Project Alignment for Research Knowledge

SPARK matches undergraduates to faculty research projects. It is a
server-rendered HTML web application built entirely on the Python 3.11
standard library: no web framework, no template engine, no JavaScript
toolchain, and no third-party packages. The whole app is `http.server` +
`sqlite3` + a small amount of progressive-enhancement JavaScript.

## Requirements

- Python 3.11 (standard library only — nothing to `pip install`)

That is the entire dependency list. See [Technology stack](#technology-stack-stdlib-only) for why.

## Run it

From the repository root:

```bash
python seed.py          # create and populate spark.db with demo data
python -m app.server    # start the server
```

The server listens on **port 8000** by default and prints the URL on start.
Open:

```
http://localhost:8000
```

To use a different port, set `SPARK_PORT` (for example `SPARK_PORT=9000 python -m app.server`).

### Cookie-signing secret

Signed session cookies are keyed by `SPARK_SECRET_KEY`. Set it in any real
deployment so sessions survive restarts. When it is unset, the app generates a
random per-process secret at startup rather than using a fixed fallback, so a
forgotten env var cannot leave cookies signed with a publicly known key. The
only cost is that existing cookies are invalidated on restart, which is fine
for the zero-config demo run above.

`seed.py` recreates `spark.db` from scratch on every run, so it is safe to
re-run whenever you want a clean demo state. `spark.db` is generated and is
not checked in.

## Demo login credentials

Every demo account uses the password **`sparkdemo123`**. These are the exact
accounts `python seed.py` prints:

| Email                | Role     | Notes                                      |
|----------------------|----------|--------------------------------------------|
| `admin@spark.edu`    | admin    | Site administrator                         |
| `manager@spark.edu`  | manager  | Manages both sessions                      |
| `rivera@spark.edu`   | faculty  | Biology projects                           |
| `nakamura@spark.edu` | faculty  | Materials Engineering projects             |
| `ava@spark.edu`      | student  | Biology, has ranked preferences            |
| `eli@spark.edu`      | student  | Materials Engineering                      |
| `blocked@spark.edu`  | student  | BLOCKED — cannot log in (R1.6 demo)        |

The blocked account exists to demonstrate that a disabled user is rejected at
login with the same non-specific error as any other failed login (no account
enumeration).

### Seeded sessions

Two match sessions are seeded, both in the `America/Chicago` timezone:

1. **Biology Research Match (Spring)** — `mode=mutual`, status
   `preferencing` (mid-lifecycle). Students and faculty both rank each other.
   Three projects, four students with submitted profiles and ranked
   preferences, and faculty-to-student preferences already in place. Ratings
   are enabled on this session.
2. **Materials Engineering Match (Spring)** — `mode=student`, status `open`.
   Student-preference matching. Two projects seeded.

## Demo walkthrough

The Biology session is seeded mid-lifecycle specifically so you can drive the
matching lifecycle end to end in one sitting. Log in as
`manager@spark.edu` (password `sparkdemo123`) and open
**Biology Research Match (Spring)**, then:

1. **Run matching.** From the session, open **Run matching**. Because the
   session's method is mutual preference, the engine uses both the students'
   and the faculty's rankings to produce a capacitated bipartite matching.
   Run it to create a match run.
2. **Review.** Open the match run to review the proposed assignments with
   per-student and per-project fit statistics.
3. **Rematch.** Adjust inputs (for example, lock or exclude an assignment) and
   run matching again to produce a new run. Compare the runs.
4. **Contract.** From a reviewed assignment, generate the contract for a
   student/project pairing and record agreement.
5. **Placement.** Finalize the placement. This is where the production system
   would push a placement reference back to Workday; in the demo the
   `services/workday.py` stub synthesizes the reference locally (see below).

Along the way you can log in as `ava@spark.edu` to see a student's profile,
favorites, and ranked preferences, or as `rivera@spark.edu` to see a faculty
member's projects and student rankings. Phase deadlines, when set, render with
an explicit timezone label on every page, and you can download per-phase
deadline reminders as an `.ics` file.

## Where stubs stand in for real integrations

SPARK is designed so that four external integrations sit behind small,
swappable interfaces. In this build each is a local stub that does real work
against the seeded SQLite data but never touches the network, so the full
lifecycle is demonstrable offline. Swapping in a production provider is a
localized change behind each interface; callers do not change.

- **ISU SSO → account-based auth.** Instead of institutional single sign-on,
  authentication is plain account-based login (`app/server.py`):
  PBKDF2-HMAC-SHA256 password hashing with a per-user salt, signed HttpOnly
  `SameSite=Lax` session cookies, and a per-session CSRF token on every
  mutating POST. In production this would be replaced by the SSO handshake;
  the session and role model stays the same.
- **Workday → `app/services/workday.py`.** The production system calls Workday
  to search people and pull org/department/major reference data, and to record
  placement references. The stub searches the seeded users, departments, and
  majors already in SQLite and synthesizes placement references locally,
  behind the same interface. It shares the request's `sqlite3` connection and
  opens no sockets.
- **CyHire (12twenty) → `app/services/cyhire.py`.** When a closed session still
  has unfilled project openings, a manager can forward an opening to CyHire.
  The stub builds the 12twenty-shaped JSON payload and records it as an
  `integration_events` row. No live HTTP call is made.
- **Email / SMS → `app/services/notify.py`.** Notifications route through a
  pluggable provider interface. Every send persists a `notifications` row (the
  in-app **Inbox** is the system of record and default channel); the default
  provider for email/SMS/ICS is the in-app recorder, so delivery is simulated
  via the inbox rather than sent over a wire. Registering a real provider is a
  single `register_provider()` call at startup.
- **Calendar reminders → `app/services/ics.py`.** Phase-deadline reminders are
  emitted as a standards-compliant `.ics` (RFC 5545) file the user downloads;
  there is no calendar-server integration.

## Technology stack (stdlib only)

The app targets an `INTEGRATIONS_ONLY` environment with no package installs,
so it uses **only** the Python 3.11 standard library:

- `http.server` (`ThreadingHTTPServer` + `BaseHTTPRequestHandler`) with a
  small custom router for path parameters and static file serving.
- `sqlite3` for storage (`spark.db`, a single file). All SQL lives in
  `app/db.py`.
- `hashlib` / `hmac` / `secrets` for password hashing, cookie signing, and
  CSRF tokens.
- `html` for output escaping; a tiny string-template helper in
  `app/templates.py` renders pages (no Jinja).
- `zoneinfo` / `datetime` so every rendered time carries an explicit timezone
  label.
- `urllib.parse`, `json`, `csv`, and `email`/calendar helpers for form
  parsing, payloads, CSV export, and `.ics` generation.

The matching engine (`matching/engine.py`, `matching/stats.py`) imports
nothing from `app` — it is pure stdlib so it can be unit-tested in isolation.
The front end is server-rendered HTML with a single progressive-enhancement
script (`app/static/spark.js`); the app works with JavaScript disabled.

### Accessibility and responsive design

- Semantic landmarks (`<header>`, `<nav aria-label="Primary">`, `<main>`) and
  exactly one `<h1>` on every page, plus a skip-to-content link.
- Every form control has an associated `<label>`.
- `aria-live` regions announce word-count and auto-save status.
- Visible focus outlines on all interactive elements; color choices in
  `app/static/spark.css` meet at least 4.5:1 contrast.
- Mobile-first CSS with a single breakpoint; data tables collapse to cards on
  narrow screens via per-cell `data-label`.
- Drag-to-rank preferencing has a keyboard Up/Down fallback.

## Project layout

```
app/
  server.py            # router, request handling, auth/CSRF middleware, handlers
  db.py                # SQLite schema and query helpers (single source of SQL)
  templates.py         # string-template HTML helper (landmarks, labeled fields)
  sanitize.py          # project-description HTML allowlist sanitizer
  static/
    spark.css          # mobile-first stylesheet
    spark.js           # progressive enhancement (word-count, autosave, drag-rank)
  services/
    workday.py         # people/org/placement stub
    notify.py          # notification provider interface (in-app inbox default)
    ics.py             # .ics reminder builder
    export.py          # CSV rows + project HTML/PDF export
    cyhire.py          # 12twenty payload builder
matching/
  engine.py            # isolated capacitated bipartite matching
  stats.py             # fit statistics
seed.py                # demo data + printed credentials
tests/                 # engine and service unit tests
```

## Tests

```bash
pytest tests/
# or, with no third-party test runner:
python -m unittest discover -s tests
```
