"""SPARK HTTP server: ThreadingHTTPServer + custom Router + auth middleware.

Stdlib only. Provides:
  - a Router with path params (/sessions/{id}) and static file serving,
  - PBKDF2-HMAC-SHA256 password hashing with per-user salt,
  - server-side sessions behind a signed, HttpOnly, SameSite=Lax cookie,
  - per-session CSRF tokens required on all mutating (POST) requests,
  - a role gate + session-visibility helpers reusable by later handlers,
  - blocked-user rejection in middleware (R1.6).

Run with `python -m app.server` (default port 8000).
"""

import hashlib
import hmac
import os
import re
import secrets
import sys
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from datetime import datetime

import json

from app import db
from app import sanitize
from app import templates
from app.services import cyhire as cyhire_service
from app.services import export as export_service
from app.services import ics as ics_service
from app.services import notify as notify_service
from app.services import workday
from matching import engine as match_engine

# ---------------------------------------------------------------------------
# Configuration / secrets
# ---------------------------------------------------------------------------

# Cookie-signing key. In production this must come from the environment; for
# the demo we fall back to a stable dev key so restarts keep sessions valid.
SECRET_KEY = os.environ.get("SPARK_SECRET_KEY", "spark-dev-secret-change-me").encode()
COOKIE_NAME = "spark_session"
PBKDF2_ITERATIONS = 240_000
VALID_ROLES = ("admin", "manager", "faculty", "student")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# Allowlisted content types for static assets.
STATIC_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


# ---------------------------------------------------------------------------
# Password hashing (PBKDF2-HMAC-SHA256, per-user salt)
# ---------------------------------------------------------------------------

def hash_password(password, salt=None, iterations=PBKDF2_ITERATIONS):
    """Return (hash_hex, salt_hex, iterations) for a plaintext password."""
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations
    )
    return dk.hex(), salt, iterations


def verify_password(password, stored_hash, salt, iterations):
    """Constant-time check of a plaintext password against a stored hash."""
    candidate, _, _ = hash_password(password, salt=salt, iterations=iterations)
    return hmac.compare_digest(candidate, stored_hash)


# ---------------------------------------------------------------------------
# Signed cookie value helpers
# ---------------------------------------------------------------------------

def _sign(token):
    return hmac.new(SECRET_KEY, token.encode(), hashlib.sha256).hexdigest()


def make_cookie_value(token):
    """token.signature -- signature binds the token to our secret key."""
    return "%s.%s" % (token, _sign(token))


def read_cookie_value(value):
    """Return the token if the signature validates, else None."""
    if not value or "." not in value:
        return None
    token, sig = value.rsplit(".", 1)
    if hmac.compare_digest(sig, _sign(token)):
        return token
    return None


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class Route:
    def __init__(self, method, pattern, handler):
        self.method = method
        self.handler = handler
        # Convert /sessions/{id} -> regex with named groups.
        regex = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", pattern)
        self.regex = re.compile("^%s$" % regex)


class Router:
    def __init__(self):
        self.routes = []

    def add(self, method, pattern, handler):
        self.routes.append(Route(method, pattern, handler))

    def match(self, method, path):
        """Return (handler, params) or (None, None). Distinguish 404 vs 405."""
        path_matched = False
        for route in self.routes:
            m = route.regex.match(path)
            if m:
                path_matched = True
                if route.method == method:
                    return route.handler, m.groupdict()
        if path_matched:
            return "405", None
        return None, None


ROUTER = Router()


def route(method, pattern):
    def deco(fn):
        ROUTER.add(method, pattern, fn)
        return fn
    return deco


# ---------------------------------------------------------------------------
# Request/response context
# ---------------------------------------------------------------------------

class Response:
    def __init__(self, status=200, body="", content_type="text/html; charset=utf-8"):
        self.status = status
        self.body = body
        self.content_type = content_type
        self.headers = []
        self.cookies = []

    def add_header(self, key, value):
        self.headers.append((key, value))

    def set_cookie(self, name, value, http_only=True, same_site="Lax", max_age=None):
        parts = ["%s=%s" % (name, value), "Path=/", "SameSite=%s" % same_site]
        if http_only:
            parts.append("HttpOnly")
        if max_age is not None:
            parts.append("Max-Age=%d" % max_age)
        self.cookies.append("; ".join(parts))


class Context:
    """Per-request state passed to handlers."""

    def __init__(self, handler, params, query, form, conn, user, auth_session):
        self.handler = handler
        self.params = params
        self.query = query
        self.form = form
        self.conn = conn
        self.user = user          # sqlite3.Row augmented with csrf_token, or None
        self.auth_session = auth_session


# ---------------------------------------------------------------------------
# Auth helpers reusable by later handlers
# ---------------------------------------------------------------------------

def require_login(ctx):
    """Return a redirect Response if not logged in, else None."""
    if ctx.user is None:
        return redirect("/login")
    return None


def require_role(ctx, *roles):
    """Return a 403 Response if the user lacks one of the given roles (R1.4)."""
    if ctx.user is None:
        return redirect("/login")
    if ctx.user["role"] not in roles:
        return forbidden("You do not have access to this page.")
    return None


def check_csrf(ctx):
    """Return an error Response if the POST CSRF token is missing/invalid."""
    if ctx.user is None:
        return forbidden("You must be logged in.")
    submitted = (ctx.form.get("csrf_token") or [""])[0]
    expected = ctx.user["csrf_token"]
    if not expected or not hmac.compare_digest(submitted, expected):
        return forbidden("Invalid or missing CSRF token.")
    return None


# ---------------------------------------------------------------------------
# Response constructors
# ---------------------------------------------------------------------------

def html_response(body, status=200):
    return Response(status=status, body=body)


def redirect(location, status=303):
    r = Response(status=status, body="")
    r.add_header("Location", location)
    return r


def forbidden(message="Forbidden"):
    body = templates.layout("Forbidden", templates.error_page(403, "Forbidden", message))
    return Response(status=403, body=body)


def not_found(message="Page not found"):
    body = templates.layout("Not found", templates.error_page(404, "Not Found", message))
    return Response(status=404, body=body)


# ---------------------------------------------------------------------------
# Handlers (R1 / R3)
# ---------------------------------------------------------------------------

@route("GET", "/")
def dashboard(ctx):
    if ctx.user is None:
        inner = (
            "<p>Welcome to SPARK, which matches undergraduates to faculty "
            "research projects.</p>"
            '<p><a href="/login">Log in</a> or <a href="/register">create an account</a> '
            "to get started.</p>"
        )
        return html_response(templates.layout("Welcome", templates.page("Welcome to SPARK", inner), ctx.user))

    role = ctx.user["role"]
    sessions = db.list_sessions(ctx.conn)
    rows = "".join(
        '<li><a href="/sessions/%d">%s</a> <span class="pill">%s</span></li>'
        % (s["id"], templates.esc(s["name"]), templates.esc(s["status"]))
        for s in sessions
    )
    session_list = "<ul class=\"session-list\">%s</ul>" % rows if rows else "<p>No match sessions yet.</p>"
    role_blurbs = {
        "admin": "You can manage org units, sessions, and user accounts.",
        "manager": "You manage match sessions and run the matching engine.",
        "faculty": "You create research projects and review matched students.",
        "student": "You browse sessions, build a profile, and rank projects.",
    }
    inner = (
        "<p>%s</p>"
        "<section aria-labelledby=\"sessions-h\">"
        "<h2 id=\"sessions-h\">Match sessions</h2>%s</section>"
        % (templates.esc(role_blurbs.get(role, "")), session_list)
    )
    return html_response(
        templates.layout("Dashboard", templates.page("Your dashboard", inner), ctx.user)
    )


def _register_form(values=None, error=None):
    values = values or {}
    role_options = "".join(
        '<option value="%s"%s>%s</option>'
        % (r, " selected" if values.get("role") == r else "", r.capitalize())
        # Self-registration is limited to student/faculty; staff roles are
        # provisioned by an admin.
        for r in ("student", "faculty")
    )
    err = '<p class="error" role="alert">%s</p>' % templates.esc(error) if error else ""
    body = (
        "%s"
        '<form method="post" action="/register" class="auth-form">'
        "%s%s%s%s%s"
        '<p class="field"><label for="f-role">Role</label>'
        '<select id="f-role" name="role" required>%s</select></p>'
        "%s"
        '<p><button type="submit">Create account</button></p>'
        "</form>"
        '<p>Already have an account? <a href="/login">Log in</a>.</p>'
    ) % (
        err,
        templates.field("Email", "email", "email", values.get("email", ""), required=True, autocomplete="email"),
        templates.field("Display name", "display_name", "text", values.get("display_name", ""), required=True),
        templates.field("Given name", "given_name", "text", values.get("given_name", "")),
        templates.field("Family name", "family_name", "text", values.get("family_name", "")),
        templates.field("Password", "password", "password", "", required=True, autocomplete="new-password"),
        role_options,
        "",  # CSRF not required for registration (no authenticated session yet)
    )
    return templates.layout("Register", templates.page("Create your account", body))


@route("GET", "/register")
def register_get(ctx):
    if ctx.user is not None:
        return redirect("/")
    return html_response(_register_form())


@route("POST", "/register")
def register_post(ctx):
    if ctx.user is not None:
        return redirect("/")
    f = ctx.form
    email = (f.get("email") or [""])[0].strip().lower()
    display_name = (f.get("display_name") or [""])[0].strip()
    given_name = (f.get("given_name") or [""])[0].strip()
    family_name = (f.get("family_name") or [""])[0].strip()
    password = (f.get("password") or [""])[0]
    role = (f.get("role") or [""])[0].strip()

    values = {
        "email": email, "display_name": display_name,
        "given_name": given_name, "family_name": family_name, "role": role,
    }
    if not email or "@" not in email:
        return html_response(_register_form(values, "Enter a valid email address."), 400)
    if not display_name:
        return html_response(_register_form(values, "Display name is required."), 400)
    if len(password) < 8:
        return html_response(_register_form(values, "Password must be at least 8 characters."), 400)
    # Self-registration restricted to student/faculty.
    if role not in ("student", "faculty"):
        return html_response(_register_form(values, "Select a valid role."), 400)
    if db.get_user_by_email(ctx.conn, email) is not None:
        return html_response(_register_form(values, "An account with that email already exists."), 400)

    pw_hash, salt, iters = hash_password(password)
    db.insert(
        ctx.conn, "users",
        email=email, display_name=display_name, given_name=given_name,
        family_name=family_name, role=role,
        password_hash=pw_hash, password_salt=salt, password_iter=iters,
        is_blocked=0, updated_at=db.utcnow(),
    )
    ctx.conn.commit()

    user = db.get_user_by_email(ctx.conn, email)
    resp = redirect("/")
    _start_session(ctx.conn, resp, user["id"])
    return resp


def _login_form(email="", error=None):
    err = '<p class="error" role="alert">%s</p>' % templates.esc(error) if error else ""
    body = (
        "%s"
        '<form method="post" action="/login" class="auth-form">'
        "%s%s"
        '<p><button type="submit">Log in</button></p>'
        "</form>"
        '<p>No account yet? <a href="/register">Register</a>.</p>'
    ) % (
        err,
        templates.field("Email", "email", "email", email, required=True, autocomplete="email"),
        templates.field("Password", "password", "password", "", required=True, autocomplete="current-password"),
    )
    return templates.layout("Log in", templates.page("Log in", body))


@route("GET", "/login")
def login_get(ctx):
    if ctx.user is not None:
        return redirect("/")
    return html_response(_login_form())


@route("POST", "/login")
def login_post(ctx):
    if ctx.user is not None:
        return redirect("/")
    email = (ctx.form.get("email") or [""])[0].strip().lower()
    password = (ctx.form.get("password") or [""])[0]
    user = db.get_user_by_email(ctx.conn, email)

    # Non-specific error for all failure modes (R1.2): unknown email, wrong
    # password, and blocked account all look identical to avoid enumeration.
    generic = "Invalid email or password."
    if user is None:
        # Still run a hash to reduce timing signal.
        hash_password(password)
        return html_response(_login_form(email, generic), 401)
    if user["is_blocked"]:
        return html_response(_login_form(email, generic), 401)
    if not verify_password(password, user["password_hash"], user["password_salt"], user["password_iter"]):
        return html_response(_login_form(email, generic), 401)

    resp = redirect("/")
    _start_session(ctx.conn, resp, user["id"])
    return resp


@route("POST", "/logout")
def logout_post(ctx):
    if ctx.user is None:
        return redirect("/")
    csrf_err = check_csrf(ctx)
    if csrf_err:
        return csrf_err
    if ctx.auth_session is not None:
        db.delete_auth_session(ctx.conn, ctx.auth_session["token"])
    resp = redirect("/")
    resp.set_cookie(COOKIE_NAME, "", max_age=0)
    return resp


def _start_session(conn, resp, user_id):
    """Create a server-side session and set the signed cookie on resp."""
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    db.create_auth_session(conn, token, user_id, csrf)
    resp.set_cookie(COOKIE_NAME, make_cookie_value(token), http_only=True, same_site="Lax")


# ---------------------------------------------------------------------------
# FEAT-003 shared helpers: form parsing, deadlines, timezones
# ---------------------------------------------------------------------------

# Lifecycle phases (design.md conceptual list) mapped onto the db.py status
# vocabulary. Advancing walks this ordered list.
PHASE_ORDER = [
    "draft", "open", "preferencing", "matching",
    "review", "contracting", "closed",
]

PHASE_LABELS = {
    "draft": "Configuration",
    "open": "Registration",
    "preferencing": "Preferencing",
    "matching": "Initial matching",
    "review": "Review / interviews",
    "contracting": "Contracting",
    "closed": "Placement finalized / archived",
}

# Per-phase deadline column for the lifecycle locking rule (R2.5).
DEADLINE_COLUMNS = {
    "student_profile": "deadline_student_profile",
    "faculty_project": "deadline_faculty_project",
    "student_preference": "deadline_student_preference",
    "faculty_preference": "deadline_faculty_preference",
    "contract": "deadline_contract",
}

MATCHING_METHODS = ("none", "ai", "student", "mutual")
WEIGHTINGS = ("equal", "faculty_heavy")
COMMON_TIMEZONES = (
    "UTC", "America/New_York", "America/Chicago", "America/Denver",
    "America/Los_Angeles", "Europe/London", "Europe/Berlin", "Asia/Tokyo",
)
CREDIT_OPTIONS = ("1", "2", "3", "1-2", "1-3", "2-3")


def fv(form, key, default=""):
    """First value for `key` in a parse_qs dict, stripped."""
    return (form.get(key) or [default])[0].strip()


def fvlist(form, key):
    """All values for `key` (e.g. multi-select), trimmed and non-empty."""
    return [v.strip() for v in form.get(key, []) if v.strip()]


def fbool(form, key):
    """Checkbox -> 0/1."""
    return 1 if (form.get(key) or [""])[0] else 0


def fint(form, key, default=None):
    raw = fv(form, key)
    if raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return None


def combine_deadline(date_str, time_str, tz_name):
    """Build a tz-aware ISO-8601 string from date+time+zone, or '' (R2.3)."""
    date_str = (date_str or "").strip()
    if not date_str:
        return ""
    time_str = (time_str or "").strip() or "23:59"
    try:
        from zoneinfo import ZoneInfo
        naive = datetime.fromisoformat("%sT%s" % (date_str, time_str))
        aware = naive.replace(tzinfo=ZoneInfo(tz_name or "UTC"))
        return aware.isoformat()
    except Exception:
        return ""


def deadline_passed(iso_value):
    """True if `iso_value` is a valid timestamp in the past."""
    if not iso_value:
        return False
    try:
        from datetime import timezone as _tz
        dt = datetime.fromisoformat(iso_value)
        now = datetime.now(_tz.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_tz.utc)
        return dt < now
    except Exception:
        return False


def _reopened_set(session):
    raw = session["reopened_phases"] if "reopened_phases" in session.keys() else ""
    return set(p for p in (raw or "").split(",") if p)


def phase_locked(session, phase_key):
    """True if `phase_key`'s deadline has passed and it is not reopened (R2.5)."""
    col = DEADLINE_COLUMNS.get(phase_key)
    if col is None:
        return False
    if phase_key in _reopened_set(session):
        return False
    return deadline_passed(session[col])


def _session_or_404(ctx):
    sid = fint_param(ctx, "id")
    if sid is None:
        return None, not_found("Session not found.")
    session = db.get_session(ctx.conn, sid)
    if session is None:
        return None, not_found("Session not found.")
    return session, None


def fint_param(ctx, name):
    try:
        return int(ctx.params.get(name))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Session create / configure / lifecycle (R2)
# ---------------------------------------------------------------------------

def _tz_options(selected):
    return "".join(
        '<option value="%s"%s>%s</option>'
        % (templates.esc(z), " selected" if z == selected else "", templates.esc(z))
        for z in COMMON_TIMEZONES
    )


def _select(name, options, selected, label):
    opts = "".join(
        '<option value="%s"%s>%s</option>'
        % (templates.esc(v), " selected" if v == selected else "", templates.esc(text))
        for v, text in options
    )
    return (
        '<p class="field"><label for="f-%s">%s</label>'
        '<select id="f-%s" name="%s">%s</select></p>'
        % (templates.esc(name), templates.esc(label), templates.esc(name),
           templates.esc(name), opts)
    )


def _session_form(ctx, values, errors=None, heading="Create a match session", action="/sessions"):
    errors = errors or {}
    csrf = templates.csrf_input(ctx.user["csrf_token"])
    org_rows = ctx.conn.execute("SELECT id, name FROM org_units ORDER BY name").fetchall()
    org_opts = [("", "-- none --")] + [(str(r["id"]), r["name"]) for r in org_rows]

    deadline_fields = []
    for key, col in DEADLINE_COLUMNS.items():
        label = key.replace("_", " ").title()
        date_val = values.get("%s_date" % key, "")
        time_val = values.get("%s_time" % key, "")
        deadline_fields.append(
            '<fieldset class="deadline"><legend>%s deadline</legend>'
            '<p class="field"><label for="f-%s_date">Date</label>'
            '<input id="f-%s_date" type="date" name="%s_date" value="%s"></p>'
            '<p class="field"><label for="f-%s_time">Time</label>'
            '<input id="f-%s_time" type="time" name="%s_time" value="%s"></p>'
            "</fieldset>"
            % (templates.esc(label), key, key, key, templates.esc(date_val),
               key, key, key, templates.esc(time_val))
        )

    def err(name):
        return templates.field_error(errors.get(name))

    body = (
        "%s"
        '<form method="post" action="%s" class="stacked">'
        "%s"
        '<p class="field"><label for="f-name">Session name</label>'
        '<input id="f-name" name="name" value="%s" required>%s</p>'
        "%s"  # org
        "%s"  # method
        "%s"  # weighting
        "%s"  # timezone
        "<fieldset><legend>Per-phase deadlines (shown with timezone)</legend>%s</fieldset>"
        '<fieldset><legend>Feature toggles</legend>'
        '<p class="field check"><label><input type="checkbox" name="allow_super_interest"%s> Allow super-interest</label></p>'
        '<p class="field check"><label><input type="checkbox" name="favorite_invites"%s> Favorite invites</label></p>'
        '<p class="field check"><label><input type="checkbox" name="show_ratings"%s> Show ratings</label></p>'
        "</fieldset>"
        '<p class="field"><label for="f-questions_profile">Student custom questions (one per line)</label>'
        '<textarea id="f-questions_profile" name="questions_profile" rows="3">%s</textarea></p>'
        '<p class="field"><label for="f-questions_project">Project custom questions (one per line)</label>'
        '<textarea id="f-questions_project" name="questions_project" rows="3">%s</textarea></p>'
        '<p><button type="submit">Save session</button></p>'
        "</form>"
    ) % (
        '<p class="error" role="alert">%s</p>' % templates.esc(errors["_form"]) if errors.get("_form") else "",
        action, csrf,
        templates.esc(values.get("name", "")), err("name"),
        _select("org_unit_id", org_opts, values.get("org_unit_id", ""), "Owning org unit"),
        _select("matching_method", [(m, m) for m in MATCHING_METHODS], values.get("matching_method", "mutual"), "Matching method"),
        _select("weighting", [(w, w) for w in WEIGHTINGS], values.get("weighting", "equal"), "Weighting"),
        '<p class="field"><label for="f-timezone">Timezone</label>'
        '<select id="f-timezone" name="timezone">%s</select></p>' % _tz_options(values.get("timezone", "UTC")),
        "".join(deadline_fields),
        " checked" if values.get("allow_super_interest") else "",
        " checked" if values.get("favorite_invites") else "",
        " checked" if values.get("show_ratings") else "",
        templates.esc(values.get("questions_profile", "")),
        templates.esc(values.get("questions_project", "")),
    )
    return templates.layout(heading, templates.page(heading, body), ctx.user)


@route("GET", "/sessions")
def sessions_index(ctx):
    guard = require_login(ctx)
    if guard:
        return guard
    sessions = db.list_sessions_for_user(ctx.conn, ctx.user)
    rows = "".join(
        '<li><a href="/sessions/%d">%s</a> '
        '<span class="pill">%s</span> <span class="pill">%s</span></li>'
        % (s["id"], templates.esc(s["name"]),
           templates.esc(PHASE_LABELS.get(s["status"], s["status"])),
           templates.esc(s["mode"]))
        for s in sessions
    )
    listing = '<ul class="session-list">%s</ul>' % rows if rows else "<p>No sessions visible to you yet.</p>"
    create = ""
    if ctx.user["role"] in ("admin", "manager"):
        create = '<p><a class="button-link" href="/sessions/new">Create a session</a></p>'
    body = create + listing
    return html_response(templates.layout("Sessions", templates.page("Match sessions", body), ctx.user))


@route("GET", "/sessions/new")
def sessions_new(ctx):
    guard = require_role(ctx, "admin", "manager")
    if guard:
        return guard
    return html_response(_session_form(ctx, {"timezone": "UTC", "matching_method": "mutual", "weighting": "equal"}))


@route("POST", "/sessions")
def sessions_create(ctx):
    guard = require_role(ctx, "admin", "manager")
    if guard:
        return guard
    csrf_err = check_csrf(ctx)
    if csrf_err:
        return csrf_err
    f = ctx.form
    values = {
        "name": fv(f, "name"),
        "org_unit_id": fv(f, "org_unit_id"),
        "matching_method": fv(f, "matching_method", "mutual"),
        "weighting": fv(f, "weighting", "equal"),
        "timezone": fv(f, "timezone", "UTC"),
        "allow_super_interest": fbool(f, "allow_super_interest"),
        "favorite_invites": fbool(f, "favorite_invites"),
        "show_ratings": fbool(f, "show_ratings"),
        "questions_profile": fv(f, "questions_profile"),
        "questions_project": fv(f, "questions_project"),
    }
    for key in DEADLINE_COLUMNS:
        values["%s_date" % key] = fv(f, "%s_date" % key)
        values["%s_time" % key] = fv(f, "%s_time" % key)

    errors = {}
    if not values["name"]:
        errors["name"] = "Session name is required."
    if values["matching_method"] not in MATCHING_METHODS:
        errors["_form"] = "Invalid matching method."
    if values["weighting"] not in WEIGHTINGS:
        errors["_form"] = "Invalid weighting."
    tz = values["timezone"] or "UTC"
    if errors:
        return html_response(_session_form(ctx, values, errors), 400)

    # Map matching method to the stored session mode (student vs mutual).
    mode = "mutual" if values["matching_method"] == "mutual" else "student"
    cols = {
        "name": values["name"],
        "org_unit_id": int(values["org_unit_id"]) if values["org_unit_id"] else None,
        "mode": mode,
        "matching_method": values["matching_method"],
        "weighting": values["weighting"],
        "status": "draft",
        "timezone": tz,
        "allow_super_interest": values["allow_super_interest"],
        "favorite_invites": values["favorite_invites"],
        "show_ratings": values["show_ratings"],
        "updated_at": db.utcnow(),
    }
    for key, col in DEADLINE_COLUMNS.items():
        cols[col] = combine_deadline(values["%s_date" % key], values["%s_time" % key], tz)
    session_id = db.insert(ctx.conn, "match_sessions", **cols)
    db.add_session_manager(ctx.conn, session_id, ctx.user["id"])

    _seed_questions(ctx.conn, session_id, values["questions_profile"], "profile")
    _seed_questions(ctx.conn, session_id, values["questions_project"], "project")
    ctx.conn.commit()
    return redirect("/sessions/%d" % session_id)


def _seed_questions(conn, session_id, text, target):
    pos = 0
    for line in (text or "").splitlines():
        prompt = line.strip()
        if not prompt:
            continue
        db.insert(conn, "custom_questions", session_id=session_id, target=target,
                  prompt=prompt, kind="longtext", required=0, position=pos,
                  updated_at=db.utcnow())
        pos += 1


@route("GET", "/sessions/{id}")
def session_detail(ctx):
    guard = require_login(ctx)
    if guard:
        return guard
    session, err = _session_or_404(ctx)
    if err:
        return err
    if not db.can_view_session(ctx.conn, session, ctx.user):
        return forbidden("You do not have access to this session.")

    manages = db.can_manage_session(ctx.conn, session, ctx.user)
    tz = session["timezone"]
    deadline_rows = "".join(
        "<tr><td data-label=\"Phase\">%s</td><td data-label=\"Deadline\">%s</td>"
        "<td data-label=\"Status\">%s</td></tr>"
        % (templates.esc(key.replace("_", " ").title()),
           templates.tz_label(session[col], tz),
           "locked" if phase_locked(session, key) else "open")
        for key, col in DEADLINE_COLUMNS.items()
    )

    actions = []
    if manages:
        cur = session["status"]
        idx = PHASE_ORDER.index(cur) if cur in PHASE_ORDER else 0
        if idx < len(PHASE_ORDER) - 1:
            nxt = PHASE_ORDER[idx + 1]
            actions.append(
                '<form method="post" action="/sessions/%d/phase" class="inline">%s'
                '<input type="hidden" name="to" value="%s">'
                '<button type="submit">Advance to %s</button></form>'
                % (session["id"], templates.csrf_input(ctx.user["csrf_token"]),
                   templates.esc(nxt), templates.esc(PHASE_LABELS[nxt])))
        # Reopen any locked phase.
        for key, col in DEADLINE_COLUMNS.items():
            if phase_locked(session, key):
                actions.append(
                    '<form method="post" action="/sessions/%d/phase" class="inline">%s'
                    '<input type="hidden" name="reopen" value="%s">'
                    '<button type="submit">Reopen %s</button></form>'
                    % (session["id"], templates.csrf_input(ctx.user["csrf_token"]),
                       templates.esc(key), templates.esc(key.replace("_", " "))))

    if manages:
        actions.append('<a class="button-link" href="/sessions/%d/match">Run / review matching</a>' % session["id"])

    role = ctx.user["role"]
    participant_links = []
    if role == "faculty":
        participant_links.append('<a href="/sessions/%d/projects">Post / manage projects</a>' % session["id"])
    if role == "student":
        participant_links.append('<a href="/sessions/%d/profile">My profile</a>' % session["id"])
        participant_links.append('<a href="/sessions/%d/open-positions">Open positions</a>' % session["id"])
    participant_links.append('<a href="/sessions/%d/browse">Browse</a>' % session["id"])
    participant_links.append('<a href="/matches/mine">My matches</a>')
    participant_links.append('<a href="/reminders.ics?session_id=%d">Calendar reminders (.ics)</a>' % session["id"])
    if manages:
        participant_links.append('<a href="/sessions/%d/reports">Reports</a>' % session["id"])

    body = (
        '<p class="pill">%s</p> <p class="pill">mode: %s</p> '
        '<p class="pill">method: %s</p> <p class="pill">weighting: %s</p>'
        "<p>%s</p>"
        '<section aria-labelledby="dl-h"><h2 id="dl-h">Phase deadlines (%s)</h2>'
        "<table><thead><tr><th>Phase</th><th>Deadline</th><th>Status</th></tr></thead>"
        "<tbody>%s</tbody></table></section>"
        '<section aria-labelledby="act-h"><h2 id="act-h">Actions</h2><p>%s</p></section>'
    ) % (
        templates.esc(PHASE_LABELS.get(session["status"], session["status"])),
        templates.esc(session["mode"]),
        templates.esc(session["matching_method"]),
        templates.esc(session["weighting"]),
        templates.esc(session["description"]),
        templates.esc(tz),
        deadline_rows,
        " ".join(participant_links + actions) or "No actions available.",
    )
    return html_response(templates.layout(session["name"], templates.page(templates.esc(session["name"]), body), ctx.user))


@route("POST", "/sessions/{id}/phase")
def session_phase(ctx):
    guard = require_role(ctx, "admin", "manager")
    if guard:
        return guard
    csrf_err = check_csrf(ctx)
    if csrf_err:
        return csrf_err
    session, err = _session_or_404(ctx)
    if err:
        return err
    if not db.can_manage_session(ctx.conn, session, ctx.user):
        return forbidden("You do not manage this session.")

    reopen = fv(ctx.form, "reopen")
    if reopen and reopen in DEADLINE_COLUMNS:
        current = _reopened_set(session)
        current.add(reopen)
        db.update_session(ctx.conn, session["id"], reopened_phases=",".join(sorted(current)))
        ctx.conn.commit()
        return redirect("/sessions/%d" % session["id"])

    to = fv(ctx.form, "to")
    if to not in PHASE_ORDER:
        return redirect("/sessions/%d" % session["id"])
    cur_idx = PHASE_ORDER.index(session["status"]) if session["status"] in PHASE_ORDER else 0
    if PHASE_ORDER.index(to) != cur_idx + 1:
        # Only allow single-step advancement.
        return redirect("/sessions/%d" % session["id"])
    db.update_session(ctx.conn, session["id"], status=to)
    ctx.conn.commit()
    return redirect("/sessions/%d" % session["id"])


# ---------------------------------------------------------------------------
# Faculty project posting (R3)
# ---------------------------------------------------------------------------

def _major_checkboxes(conn, name, selected_ids):
    selected = set(selected_ids or [])
    rows = db.list_majors(conn)
    items = "".join(
        '<label class="check"><input type="checkbox" name="%s" value="%d"%s> %s</label>'
        % (name, r["id"], " checked" if r["id"] in selected else "", templates.esc(r["name"]))
        for r in rows
    )
    return '<div class="checkgroup">%s</div>' % items


def _dept_options(conn, selected):
    rows = db.list_departments(conn)
    opts = [("", "-- none --")] + [(str(r["id"]), r["name"]) for r in rows]
    return _select("primary_department_id", opts, str(selected) if selected else "", "Primary mentor department")


def _mentor_options(conn, selected_pi):
    people = workday.search_people(conn, "", limit=50)
    return "".join(
        '<option value="%d"%s>%s (%s)</option>'
        % (p["id"], " selected" if p["id"] == selected_pi else "",
           templates.esc(p["display_name"]), templates.esc(p["email"]))
        for p in people
    )


def _project_form(ctx, session, values, errors=None, project=None):
    errors = errors or {}
    csrf = templates.csrf_input(ctx.user["csrf_token"])
    action = "/projects/%d" % project["id"] if project else "/sessions/%d/projects" % session["id"]
    project_id = project["id"] if project else 0
    questions = db.list_questions(ctx.conn, session["id"], "project")

    def err(name):
        return templates.field_error(errors.get(name))

    q_html = "".join(
        templates.textarea("Q: %s" % q["prompt"], "q_%d" % q["id"],
                           values.get("q_%d" % q["id"], ""), max_words=q["max_words"], rows=3)
        for q in questions
    )
    autosave_attr = ' data-autosave="/projects/%d/autosave"' % project_id if project_id else ""

    pi_selected = values.get("pi_id", "")
    pi_int = int(pi_selected) if str(pi_selected).isdigit() else None
    comp_type = values.get("comp_type", "credit")

    body = (
        "%s"
        '<form method="post" action="%s" class="stacked" id="project-form"%s>'
        "%s"
        '<div aria-live="polite" class="autosave-status" id="autosave-status"></div>'
        '<p class="field"><label for="f-title">Project title</label>'
        '<input id="f-title" name="title" value="%s" required>%s</p>'
        '<p class="field"><label for="f-pi_id">Principal investigator (PI)</label>'
        '<select id="f-pi_id" name="pi_id">%s</select>%s</p>'
        '<p class="field"><label for="f-mentor_ids">Additional mentors</label>'
        '<select id="f-mentor_ids" name="mentor_ids" multiple size="4">%s</select>'
        '<span class="hint">Exactly one PI; add co-mentors here.</span></p>'
        "%s"  # primary department
        "%s"  # description textarea (<=250 words)
        "%s"  # background (<=100)
        "%s"  # responsibilities (<=100)
        '<p class="field check"><label><input type="checkbox" name="is_group"%s> Group project</label></p>'
        '<p class="field"><label for="f-positions">Positions</label>'
        '<input id="f-positions" name="positions" type="number" min="1" value="%s" data-positions>%s'
        '<span class="hint">Warns if more than 20.</span></p>'
        '<p class="field check"><label><input type="checkbox" name="noncitizen_eligible"%s> Non-citizens eligible</label></p>'
        '<fieldset><legend>Compensation</legend>%s'
        '<div class="comp-credit"><p class="field"><label for="f-credit_option">Credit option</label>'
        '<select id="f-credit_option" name="credit_option">%s</select></p>'
        '<p class="field"><label for="f-course_name">Course name</label>'
        '<input id="f-course_name" name="course_name" value="%s"></p></div>'
        '<div class="comp-pay"><p class="field"><label for="f-hourly_rate">Hourly rate</label>'
        '<input id="f-hourly_rate" name="hourly_rate" type="number" step="0.01" min="0" value="%s"></p>'
        '<p class="field"><label for="f-cap_kind">Cap kind</label>'
        '<select id="f-cap_kind" name="cap_kind"><option value="">none</option>'
        '<option value="hours"%s>hours</option><option value="dollars"%s>dollars</option></select></p>'
        '<p class="field"><label for="f-cap_value">Cap value</label>'
        '<input id="f-cap_value" name="cap_value" type="number" step="0.01" min="0" value="%s"></p></div>'
        "</fieldset>"
        '<fieldset><legend>Major policy</legend>%s'
        '<p>Eligible / preferred majors:</p>%s</fieldset>'
        '<fieldset><legend>Alerts</legend>'
        '<p class="field check"><label><input type="checkbox" name="alert_on_preference"%s> Alert me when a student prefers this</label></p>'
        '<p class="field"><label for="f-alert_scope">Alert scope</label>'
        '<select id="f-alert_scope" name="alert_scope"><option value="each"%s>each</option>'
        '<option value="digest"%s>daily digest</option></select></p></fieldset>'
        "%s"  # custom questions
        '<p><button type="submit" name="action" value="publish">Publish project</button> '
        '<button type="submit" name="action" value="draft" class="secondary">Save draft</button></p>'
        "</form>"
    ) % (
        '<p class="error" role="alert">%s</p>' % templates.esc(errors["_form"]) if errors.get("_form") else "",
        action, autosave_attr, csrf,
        templates.esc(values.get("title", "")), err("title"),
        _mentor_options(ctx.conn, pi_int), err("pi_id"),
        _mentor_options(ctx.conn, None),
        _dept_options(ctx.conn, values.get("primary_department_id", "")),
        templates.textarea("Description (rich, <=250 words)", "description_html",
                           values.get("description_html", ""), max_words=250, rows=6,
                           hint="Allowed: bold, lists, links, up to 2 images/videos.") + err("description_html"),
        templates.textarea("Background (<=100 words)", "background",
                           values.get("background", ""), max_words=100, rows=3),
        templates.textarea("Responsibilities (<=100 words)", "responsibilities",
                           values.get("responsibilities", ""), max_words=100, rows=3),
        " checked" if values.get("is_group") else "",
        templates.esc(values.get("positions", "1")), err("positions"),
        " checked" if values.get("noncitizen_eligible", True) else "",
        '<p class="field"><label for="f-comp_type">Type</label>'
        '<select id="f-comp_type" name="comp_type" data-comp-toggle>'
        '<option value="credit"%s>credit</option><option value="pay"%s>pay</option></select></p>'
        % (" selected" if comp_type == "credit" else "", " selected" if comp_type == "pay" else ""),
        "".join('<option value="%s"%s>%s</option>'
                % (c, " selected" if values.get("credit_option") == c else "", c) for c in CREDIT_OPTIONS),
        templates.esc(values.get("course_name", "")),
        templates.esc(values.get("hourly_rate", "")),
        " selected" if values.get("cap_kind") == "hours" else "",
        " selected" if values.get("cap_kind") == "dollars" else "",
        templates.esc(values.get("cap_value", "")),
        _select("major_policy", [("none", "none"), ("prefer", "prefer"), ("must", "must")],
                values.get("major_policy", "none"), "Policy"),
        _major_checkboxes(ctx.conn, "eligible_majors", values.get("eligible_majors", [])),
        " checked" if values.get("alert_on_preference") else "",
        " selected" if values.get("alert_scope", "each") == "each" else "",
        " selected" if values.get("alert_scope") == "digest" else "",
        q_html,
    )
    heading = "Edit project" if project else "Post a research project"
    return templates.layout(heading, templates.page(heading, body), ctx.user)


def _read_project_form(f):
    return {
        "title": fv(f, "title"),
        "pi_id": fv(f, "pi_id"),
        "mentor_ids": fvlist(f, "mentor_ids"),
        "primary_department_id": fv(f, "primary_department_id"),
        "description_html": fv(f, "description_html"),
        "background": fv(f, "background"),
        "responsibilities": fv(f, "responsibilities"),
        "is_group": fbool(f, "is_group"),
        "positions": fv(f, "positions", "1"),
        "noncitizen_eligible": fbool(f, "noncitizen_eligible"),
        "comp_type": fv(f, "comp_type", "credit"),
        "credit_option": fv(f, "credit_option"),
        "course_name": fv(f, "course_name"),
        "hourly_rate": fv(f, "hourly_rate"),
        "cap_kind": fv(f, "cap_kind"),
        "cap_value": fv(f, "cap_value"),
        "major_policy": fv(f, "major_policy", "none"),
        "eligible_majors": [int(x) for x in fvlist(f, "eligible_majors") if x.isdigit()],
        "alert_on_preference": fbool(f, "alert_on_preference"),
        "alert_scope": fv(f, "alert_scope", "each"),
    }


def _validate_project(values, finalize):
    """Return (errors, warnings). Required-field checks only on finalize (R3.10)."""
    errors = {}
    warnings = []
    positions = None
    try:
        positions = int(values["positions"])
    except (ValueError, TypeError):
        errors["positions"] = "Positions must be a whole number."
    else:
        if positions < 1:
            errors["positions"] = "Positions must be at least 1."
        elif positions > 20:
            warnings.append("Positions is greater than 20 (%d); please confirm." % positions)
    if sanitize.word_count(values["description_html"]) > 250:
        errors["description_html"] = "Description exceeds 250 words."
    if finalize:
        if not values["title"]:
            errors["title"] = "Title is required."
        if not values["pi_id"] or not str(values["pi_id"]).isdigit():
            errors["pi_id"] = "Select a principal investigator."
        if not values["description_html"]:
            errors["description_html"] = errors.get("description_html") or "Description is required."
        if values["comp_type"] == "credit" and not values["credit_option"]:
            errors["_form"] = "Choose a credit option."
        if values["comp_type"] == "pay" and not values["hourly_rate"]:
            errors["_form"] = "Enter an hourly rate for paid positions."
        if values["major_policy"] in ("must", "prefer") and not values["eligible_majors"]:
            errors["_form"] = "Select at least one major for this policy."
    return errors, warnings, positions


def _save_project(conn, session, values, positions, status, project_id=None):
    sanitized = sanitize.sanitize_html(values["description_html"])
    rate = None
    if values["hourly_rate"]:
        try:
            rate = float(values["hourly_rate"])
        except ValueError:
            rate = None
    cap_value = None
    if values["cap_value"]:
        try:
            cap_value = float(values["cap_value"])
        except ValueError:
            cap_value = None
    cols = {
        "session_id": session["id"],
        "title": values["title"] or "Untitled draft",
        "description": sanitized,
        "background": values["background"],
        "responsibilities": values["responsibilities"],
        "primary_department_id": int(values["primary_department_id"]) if values["primary_department_id"] else None,
        "is_group": values["is_group"],
        "positions": positions if positions else 1,
        "capacity": positions if positions else 1,
        "noncitizen_eligible": values["noncitizen_eligible"],
        "comp_type": values["comp_type"],
        "credit_option": values["credit_option"],
        "course_name": values["course_name"],
        "hourly_rate": rate,
        "cap_kind": values["cap_kind"],
        "cap_value": cap_value,
        "major_policy": values["major_policy"],
        "alert_on_preference": values["alert_on_preference"],
        "alert_scope": values["alert_scope"],
        "status": status,
    }
    if project_id is None:
        project_id = db.insert(conn, "projects", updated_at=db.utcnow(), **cols)
    else:
        db.update_project(conn, project_id, **cols)

    # Mentors: PI + co-mentors.
    mentors = []
    if str(values["pi_id"]).isdigit():
        mentors.append({"user_id": int(values["pi_id"]), "is_pi": True, "permission": "editor"})
    for mid in values["mentor_ids"]:
        if mid.isdigit() and int(mid) != int(values["pi_id"] or 0):
            mentors.append({"user_id": int(mid), "is_pi": False, "permission": "preferencing"})
    if mentors:
        db.set_project_mentors(conn, project_id, mentors)
    db.set_project_eligible_majors(conn, project_id, values["eligible_majors"])

    # Custom-question answers.
    for q in db.list_questions(conn, session["id"], "project"):
        db.upsert_answer(conn, q["id"], "", project_id=project_id)  # ensure row
    return project_id


@route("GET", "/sessions/{id}/projects")
def project_list_or_new(ctx):
    guard = require_role(ctx, "faculty", "admin", "manager")
    if guard:
        return guard
    session, err = _session_or_404(ctx)
    if err:
        return err
    if not db.can_view_session(ctx.conn, session, ctx.user):
        return forbidden("You do not have access to this session.")
    # Faculty see a new-project form plus their existing projects.
    projects = db.list_projects(ctx.conn, session["id"])
    mine = [p for p in projects if db.is_project_mentor(ctx.conn, p["id"], ctx.user["id"])]
    listing = "".join(
        '<li><a href="/projects/%d">%s</a> <span class="pill">%s</span></li>'
        % (p["id"], templates.esc(p["title"]), templates.esc(p["status"]))
        for p in mine
    )
    existing = '<section aria-labelledby="mine-h"><h2 id="mine-h">My projects</h2><ul class="session-list">%s</ul></section>' % listing if listing else ""
    values = {"positions": "1", "noncitizen_eligible": True, "comp_type": "credit", "alert_scope": "each"}
    form_html = _project_form(ctx, session, values)
    # The form helper already returns a full layout; render list above it by
    # re-wrapping: simplest is to show the list page first with a link.
    return html_response(form_html if not existing else _wrap_with_section(form_html, existing))


def _wrap_with_section(full_layout_html, section_html):
    """Inject a section right after the opening <main>'s <h1> line."""
    marker = '<main id="main">\n'
    idx = full_layout_html.find(marker)
    if idx == -1:
        return full_layout_html
    insert_at = idx + len(marker)
    # Insert the section after the <h1> that follows.
    h1_end = full_layout_html.find("</h1>", insert_at)
    if h1_end != -1:
        insert_at = h1_end + len("</h1>\n")
    return full_layout_html[:insert_at] + section_html + full_layout_html[insert_at:]


@route("POST", "/sessions/{id}/projects")
def project_create(ctx):
    guard = require_role(ctx, "faculty", "admin", "manager")
    if guard:
        return guard
    csrf_err = check_csrf(ctx)
    if csrf_err:
        return csrf_err
    session, err = _session_or_404(ctx)
    if err:
        return err
    if not db.can_view_session(ctx.conn, session, ctx.user):
        return forbidden("You do not have access to this session.")
    if phase_locked(session, "faculty_project"):
        return forbidden("The project submission deadline has passed.")

    values = _read_project_form(ctx.form)
    finalize = fv(ctx.form, "action", "publish") == "publish"
    errors, warnings, positions = _validate_project(values, finalize)
    if errors:
        return html_response(_project_form(ctx, session, values, errors), 400)
    status = "published" if finalize else "draft"
    project_id = _save_project(ctx.conn, session, values, positions, status)
    for q in db.list_questions(ctx.conn, session["id"], "project"):
        db.upsert_answer(ctx.conn, q["id"], fv(ctx.form, "q_%d" % q["id"]), project_id=project_id)
    ctx.conn.commit()
    return redirect("/projects/%d" % project_id)


def _can_edit_project(ctx, project):
    if ctx.user["role"] in ("admin", "manager"):
        return True
    return db.is_project_mentor(ctx.conn, project["id"], ctx.user["id"])


@route("GET", "/projects/{id}")
def project_detail(ctx):
    guard = require_login(ctx)
    if guard:
        return guard
    # The literal /projects/export path also matches this pattern (id="export");
    # delegate to the batch export handler so both routes coexist.
    if ctx.params.get("id") == "export":
        return project_export_batch(ctx)
    pid = fint_param(ctx, "id")
    project = db.get_project(ctx.conn, pid) if pid else None
    if project is None:
        return not_found("Project not found.")
    session = db.get_session(ctx.conn, project["session_id"])
    if not db.can_view_session(ctx.conn, session, ctx.user):
        return forbidden("You do not have access to this project.")

    # CyHire forward action, shown to editors/managers once the session has
    # ended (closed) and the project still has unfilled openings (R11.1).
    cyhire_html = ""
    if (session["status"] == "closed"
            and _remaining_capacity(ctx.conn, session["id"], project) > 0
            and (db.is_project_mentor(ctx.conn, project["id"], ctx.user["id"])
                 or db.can_manage_session(ctx.conn, session, ctx.user))):
        cyhire_html = (
            '<section aria-labelledby="cy-h"><h2 id="cy-h">CyHire</h2>'
            '<p>This session has ended and this project still has unfilled openings.</p>'
            '<form method="post" action="/projects/%d/cyhire" class="inline">%s'
            '<button type="submit">Forward unfilled opening(s) to CyHire</button></form>'
            "</section>"
            % (project["id"], templates.csrf_input(ctx.user["csrf_token"])))

    export_links = (
        '<section aria-labelledby="ex-h"><h2 id="ex-h">Export</h2>'
        '<p><a href="/projects/%d/export.html">HTML (email) view</a> &middot; '
        '<a href="/projects/%d/export.pdf">Print / PDF view</a></p></section>'
        % (project["id"], project["id"]))

    # Editors get the edit form prefilled; others get a read-only view.
    if _can_edit_project(ctx, project):
        values = _project_to_values(ctx.conn, project)
        full = _project_form(ctx, session, values, project=project)
        return html_response(_wrap_with_section(full, export_links + cyhire_html))

    mentors = db.project_mentors(ctx.conn, project["id"])
    mentor_html = ", ".join(
        "%s%s" % (templates.esc(m["display_name"]), " (PI)" if m["is_pi"] else "")
        for m in mentors
    )
    favs = db.favorite_count(ctx.conn, project["id"])
    badge = _project_rating_badge(ctx.conn, session, project["id"])
    body = (
        "<p>%s</p>"
        "<p><strong>Mentors:</strong> %s</p>"
        "<p><strong>Positions:</strong> %d &middot; <strong>Compensation:</strong> %s %s</p>"
        '<p class="popularity">%d student(s) favored this.</p>'
        '<div class="rich">%s</div>'
        "%s%s"
    ) % (
        templates.esc(session["name"]), mentor_html, project["positions"],
        templates.esc(project["comp_type"]), badge, favs,
        project["description"],  # already sanitized at write time
        export_links, cyhire_html,
    )
    return html_response(templates.layout(project["title"], templates.page(templates.esc(project["title"]), body), ctx.user))


def _project_to_values(conn, project):
    elig = db.project_eligible_major_ids(conn, project["id"])
    mentors = db.project_mentors(conn, project["id"])
    pi = next((m for m in mentors if m["is_pi"]), None)
    co = [str(m["user_id"]) for m in mentors if not m["is_pi"]]
    answers = db.get_project_answers(conn, project["id"])
    values = {
        "title": project["title"],
        "pi_id": str(pi["user_id"]) if pi else "",
        "mentor_ids": co,
        "primary_department_id": project["primary_department_id"] or "",
        "description_html": project["description"],
        "background": project["background"],
        "responsibilities": project["responsibilities"],
        "is_group": project["is_group"],
        "positions": str(project["positions"]),
        "noncitizen_eligible": bool(project["noncitizen_eligible"]),
        "comp_type": project["comp_type"],
        "credit_option": project["credit_option"],
        "course_name": project["course_name"],
        "hourly_rate": project["hourly_rate"] if project["hourly_rate"] is not None else "",
        "cap_kind": project["cap_kind"],
        "cap_value": project["cap_value"] if project["cap_value"] is not None else "",
        "major_policy": project["major_policy"],
        "eligible_majors": elig,
        "alert_on_preference": project["alert_on_preference"],
        "alert_scope": project["alert_scope"],
    }
    for qid, body in answers.items():
        values["q_%d" % qid] = body
    return values


@route("POST", "/projects/{id}")
def project_update(ctx):
    guard = require_login(ctx)
    if guard:
        return guard
    csrf_err = check_csrf(ctx)
    if csrf_err:
        return csrf_err
    pid = fint_param(ctx, "id")
    project = db.get_project(ctx.conn, pid) if pid else None
    if project is None:
        return not_found("Project not found.")
    session = db.get_session(ctx.conn, project["session_id"])
    if not _can_edit_project(ctx, project):
        return forbidden("You cannot edit this project.")
    if phase_locked(session, "faculty_project"):
        return forbidden("The project submission deadline has passed.")

    values = _read_project_form(ctx.form)
    finalize = fv(ctx.form, "action", "publish") == "publish"
    errors, warnings, positions = _validate_project(values, finalize)
    if errors:
        return html_response(_project_form(ctx, session, values, errors, project=project), 400)
    status = "published" if finalize else project["status"]
    _save_project(ctx.conn, session, values, positions, status, project_id=project["id"])
    for q in db.list_questions(ctx.conn, session["id"], "project"):
        db.upsert_answer(ctx.conn, q["id"], fv(ctx.form, "q_%d" % q["id"]), project_id=project["id"])
    ctx.conn.commit()
    return redirect("/projects/%d" % project["id"])


@route("POST", "/projects/{id}/autosave")
def project_autosave(ctx):
    guard = require_login(ctx)
    if guard:
        return guard
    csrf_err = check_csrf(ctx)
    if csrf_err:
        return csrf_err
    pid = fint_param(ctx, "id")
    project = db.get_project(ctx.conn, pid) if pid else None
    if project is None:
        return _json(404, {"ok": False, "error": "not found"})
    if not _can_edit_project(ctx, project):
        return _json(403, {"ok": False, "error": "forbidden"})
    session = db.get_session(ctx.conn, project["session_id"])
    values = _read_project_form(ctx.form)
    _errors, _warn, positions = _validate_project(values, finalize=False)
    _save_project(ctx.conn, session, values, positions, project["status"], project_id=project["id"])
    for q in db.list_questions(ctx.conn, session["id"], "project"):
        db.upsert_answer(ctx.conn, q["id"], fv(ctx.form, "q_%d" % q["id"]), project_id=project["id"])
    ctx.conn.commit()
    return _json(200, {"ok": True, "saved_at": db.utcnow()})


def _json(status, obj):
    import json
    return Response(status=status, body=json.dumps(obj),
                    content_type="application/json; charset=utf-8")


# ---------------------------------------------------------------------------
# Student profile (R4)
# ---------------------------------------------------------------------------

def _profile_form(ctx, session, values, errors=None, profile=None):
    errors = errors or {}
    csrf = templates.csrf_input(ctx.user["csrf_token"])
    action = "/sessions/%d/profile" % session["id"]
    profile_id = profile["id"] if profile else 0
    autosave_attr = ' data-autosave="/profile/%d/autosave"' % profile_id if profile_id else ""
    questions = db.list_questions(ctx.conn, session["id"], "profile")

    def err(name):
        return templates.field_error(errors.get(name))

    q_html = "".join(
        templates.textarea("Q: %s" % q["prompt"], "q_%d" % q["id"],
                           values.get("q_%d" % q["id"], ""), max_words=q["max_words"], rows=3)
        for q in questions
    )
    time_kind = values.get("time_kind", "credit")
    body = (
        "%s"
        '<form method="post" action="%s" class="stacked" id="profile-form"%s>'
        "%s"
        '<div aria-live="polite" class="autosave-status" id="autosave-status"></div>'
        "%s"  # email
        "%s"  # given name
        "%s"  # family name
        '<fieldset><legend>Majors</legend>'
        "<p>Primary / secondary majors and minors (check all that apply):</p>%s</fieldset>"
        '<fieldset><legend>Available time</legend>'
        '<p class="field"><label for="f-time_kind">Type</label>'
        '<select id="f-time_kind" name="time_kind" data-time-toggle>'
        '<option value="credit"%s>credit</option><option value="pay"%s>pay</option></select></p>'
        '<div class="time-credit"><p class="field"><label for="f-credit_option">Credit option</label>'
        '<select id="f-credit_option" name="credit_option">%s</select>'
        '<span class="hint">1 credit ~= 3 hours.</span></p></div>'
        '<div class="time-pay"><p class="field"><label for="f-pay_hours">Pay hours / week (max 20)</label>'
        '<input id="f-pay_hours" name="pay_hours" type="number" min="0" max="20" value="%s" data-payhours>'
        '<span class="hint" data-payhours-warn></span></p></div>'
        "</fieldset>"
        "%s"  # interests
        "%s"  # background
        "%s"  # programming
        "%s"  # custom questions
        '<p><button type="submit" name="action" value="submit">Submit profile</button> '
        '<button type="submit" name="action" value="draft" class="secondary">Save draft</button></p>'
        "</form>"
    ) % (
        '<p class="error" role="alert">%s</p>' % templates.esc(errors["_form"]) if errors.get("_form") else "",
        action, autosave_attr, csrf,
        templates.field("Email", "email", "email", values.get("email", ""), required=True) + err("email"),
        templates.field("Given (first) name", "given_name", "text", values.get("given_name", ""), required=True) + err("given_name"),
        templates.field("Family (last) name", "family_name", "text", values.get("family_name", ""), required=True) + err("family_name"),
        _profile_major_checkboxes(ctx.conn, values),
        " selected" if time_kind == "credit" else "", " selected" if time_kind == "pay" else "",
        "".join('<option value="%s"%s>%s</option>'
                % (c, " selected" if values.get("credit_option") == c else "", c) for c in CREDIT_OPTIONS),
        templates.esc(values.get("pay_hours", "")),
        templates.textarea("Interests (<=250 words)", "interests", values.get("interests", ""), max_words=250, rows=5) + err("interests"),
        templates.textarea("Background (<=100 words)", "background", values.get("background", ""), max_words=100, rows=3),
        templates.textarea("Programming experience (<=100 words)", "programming", values.get("programming", ""), max_words=100, rows=3),
        q_html,
    )
    heading = "Your profile for %s" % session["name"]
    return templates.layout("My profile", templates.page(templates.esc(heading), body), ctx.user)


def _profile_major_checkboxes(conn, values):
    rows = db.list_majors(conn)
    selected = values.get("majors_map", {})  # major_id -> kind
    parts = []
    for r in rows:
        current = selected.get(r["id"], "")
        opts = "".join(
            '<option value="%s"%s>%s</option>'
            % (k, " selected" if current == k else "", k or "-- not selected --")
            for k in ("", "major", "secondary", "minor")
        )
        parts.append(
            '<label class="major-row">%s '
            '<select name="major_kind_%d">%s</select></label>'
            % (templates.esc(r["name"]), r["id"], opts)
        )
    return '<div class="checkgroup">%s</div>' % "".join(parts)


def _read_profile_form(conn, f):
    majors_map = {}
    for r in db.list_majors(conn):
        kind = fv(f, "major_kind_%d" % r["id"])
        if kind in ("major", "secondary", "minor"):
            majors_map[r["id"]] = kind
    return {
        "email": fv(f, "email"),
        "given_name": fv(f, "given_name"),
        "family_name": fv(f, "family_name"),
        "majors_map": majors_map,
        "time_kind": fv(f, "time_kind", "credit"),
        "credit_option": fv(f, "credit_option"),
        "pay_hours": fv(f, "pay_hours"),
        "interests": fv(f, "interests"),
        "background": fv(f, "background"),
        "programming": fv(f, "programming"),
    }


def _validate_profile(values, finalize):
    errors = {}
    warnings = []
    if values["pay_hours"]:
        try:
            ph = int(values["pay_hours"])
            if ph > 20:
                errors["_form"] = "Pay hours cannot exceed 20 per week."
            elif ph > 10:
                warnings.append("More than 10 hours per week (%d) may be a heavy load." % ph)
        except ValueError:
            errors["_form"] = "Pay hours must be a whole number."
    if sanitize.word_count(values["interests"]) > 250:
        errors["interests"] = "Interests exceeds 250 words."
    if finalize:
        if not values["email"] or "@" not in values["email"]:
            errors["email"] = "A valid email is required."
        if not values["given_name"]:
            errors["given_name"] = "Given name is required."
        if not values["family_name"]:
            errors["family_name"] = "Family name is required."
        if not values["interests"]:
            errors["interests"] = "Please describe your interests."
    return errors, warnings


def _save_profile(conn, session, user_id, values, submitted, profile_id=None):
    pay_hours = None
    if values["pay_hours"]:
        try:
            pay_hours = int(values["pay_hours"])
        except ValueError:
            pay_hours = None
    cols = {
        "email": values["email"],
        "given_name": values["given_name"],
        "family_name": values["family_name"],
        "time_kind": values["time_kind"],
        "credit_option": values["credit_option"],
        "pay_hours": pay_hours,
        "interests": values["interests"],
        "background": values["background"],
        "programming": values["programming"],
        "bio": values["interests"][:500],
        "submitted": submitted,
    }
    if profile_id is None:
        profile_id = db.insert(conn, "student_profiles", user_id=user_id,
                               session_id=session["id"], updated_at=db.utcnow(), **cols)
    else:
        db.update_profile(conn, profile_id, **cols)
    items = [(mid, kind) for mid, kind in values["majors_map"].items()]
    db.set_profile_majors(conn, profile_id, items)
    return profile_id


@route("GET", "/sessions/{id}/profile")
def profile_get(ctx):
    guard = require_role(ctx, "student")
    if guard:
        return guard
    session, err = _session_or_404(ctx)
    if err:
        return err
    if not db.can_view_session(ctx.conn, session, ctx.user):
        return forbidden("You do not have access to this session.")
    profile = db.get_profile_for_user(ctx.conn, session["id"], ctx.user["id"])
    if profile is None:
        # Autopopulate from the account (R4.2).
        majors_map = {}
        values = {
            "email": ctx.user["email"],
            "given_name": ctx.user["given_name"],
            "family_name": ctx.user["family_name"],
            "majors_map": majors_map,
            "time_kind": "credit",
        }
        return html_response(_profile_form(ctx, session, values))
    values = _profile_to_values(ctx.conn, profile)
    return html_response(_profile_form(ctx, session, values, profile=profile))


def _profile_to_values(conn, profile):
    majors_map = {}
    for r in conn.execute(
            "SELECT major_id, kind FROM profile_majors WHERE profile_id = ?",
            (profile["id"],)).fetchall():
        majors_map[r["major_id"]] = r["kind"]
    values = {
        "email": profile["email"],
        "given_name": profile["given_name"],
        "family_name": profile["family_name"],
        "majors_map": majors_map,
        "time_kind": profile["time_kind"],
        "credit_option": profile["credit_option"],
        "pay_hours": profile["pay_hours"] if profile["pay_hours"] is not None else "",
        "interests": profile["interests"],
        "background": profile["background"],
        "programming": profile["programming"],
    }
    for qid, body in db.get_profile_answers(conn, profile["id"]).items():
        values["q_%d" % qid] = body
    return values


@route("POST", "/sessions/{id}/profile")
def profile_post(ctx):
    guard = require_role(ctx, "student")
    if guard:
        return guard
    csrf_err = check_csrf(ctx)
    if csrf_err:
        return csrf_err
    session, err = _session_or_404(ctx)
    if err:
        return err
    if not db.can_view_session(ctx.conn, session, ctx.user):
        return forbidden("You do not have access to this session.")
    if phase_locked(session, "student_profile"):
        return forbidden("The profile deadline has passed.")

    profile = db.get_profile_for_user(ctx.conn, session["id"], ctx.user["id"])
    values = _read_profile_form(ctx.conn, ctx.form)
    finalize = fv(ctx.form, "action", "submit") == "submit"
    errors, warnings = _validate_profile(values, finalize)
    if errors:
        return html_response(_profile_form(ctx, session, values, errors, profile=profile), 400)
    submitted = 1 if finalize else (profile["submitted"] if profile else 0)
    profile_id = _save_profile(ctx.conn, session, ctx.user["id"], values, submitted,
                               profile_id=profile["id"] if profile else None)
    for q in db.list_questions(ctx.conn, session["id"], "profile"):
        db.upsert_answer(ctx.conn, q["id"], fv(ctx.form, "q_%d" % q["id"]), profile_id=profile_id)
    ctx.conn.commit()
    flash = "Profile submitted." if finalize else "Draft saved."
    return redirect("/sessions/%d/browse?msg=%s" % (session["id"], "submitted" if finalize else "draft"))


@route("POST", "/profile/{id}/autosave")
def profile_autosave(ctx):
    guard = require_role(ctx, "student")
    if guard:
        return guard
    csrf_err = check_csrf(ctx)
    if csrf_err:
        return csrf_err
    pid = fint_param(ctx, "id")
    profile = db.get_profile(ctx.conn, pid) if pid else None
    if profile is None or profile["user_id"] != ctx.user["id"]:
        return _json(403, {"ok": False, "error": "forbidden"})
    session = db.get_session(ctx.conn, profile["session_id"])
    values = _read_profile_form(ctx.conn, ctx.form)
    _save_profile(ctx.conn, session, ctx.user["id"], values, profile["submitted"], profile_id=profile["id"])
    for q in db.list_questions(ctx.conn, session["id"], "profile"):
        db.upsert_answer(ctx.conn, q["id"], fv(ctx.form, "q_%d" % q["id"]), profile_id=profile["id"])
    ctx.conn.commit()
    return _json(200, {"ok": True, "saved_at": db.utcnow()})


# ---------------------------------------------------------------------------
# Browsing / favorites / preferencing (R5)
# ---------------------------------------------------------------------------

def _student_browse(ctx, session):
    q = fv(ctx.query, "q")
    major_id = fint(ctx.query, "major")
    broader = fv(ctx.query, "mode") == "broader"
    fit_only = fv(ctx.query, "fit") != "all"  # default "fits my major(s)"

    my_profile = db.get_profile_for_user(ctx.conn, session["id"], ctx.user["id"])
    my_major_ids = set(db.profile_major_ids(ctx.conn, my_profile["id"])) if my_profile else set()
    if broader:
        my_major_ids = my_major_ids | db.related_major_ids(ctx.conn, my_major_ids)

    projects = db.list_published_projects(ctx.conn, session["id"])
    favs = db.favorite_project_ids(ctx.conn, ctx.user["id"])
    rows = []
    for p in projects:
        elig = set(db.project_eligible_major_ids(ctx.conn, p["id"]))
        if q and q.lower() not in (p["title"] or "").lower() and q.lower() not in (p["description"] or "").lower():
            continue
        if major_id is not None:
            match_set = {major_id}
            if broader:
                match_set |= db.related_major_ids(ctx.conn, {major_id})
            if not (elig & match_set):
                continue
        if fit_only and my_major_ids and elig and not (elig & my_major_ids):
            continue
        favored = p["id"] in favs
        count = db.favorite_count(ctx.conn, p["id"])
        fav_btn = (
            '<form method="post" action="/favorites" class="inline">%s'
            '<input type="hidden" name="session_id" value="%d">'
            '<input type="hidden" name="project_id" value="%d">'
            '<input type="hidden" name="op" value="%s">'
            '<button type="submit">%s</button></form>'
            % (templates.csrf_input(ctx.user["csrf_token"]), session["id"], p["id"],
               "remove" if favored else "add", "Unfavorite" if favored else "Favorite")
        )
        badge = _project_rating_badge(ctx.conn, session, p["id"])
        rows.append(
            "<tr><td data-label=\"Project\"><a href=\"/projects/%d\">%s</a> %s</td>"
            "<td data-label=\"Favorited by\">%d</td><td data-label=\"\">%s</td></tr>"
            % (p["id"], templates.esc(p["title"]), badge, count, fav_btn)
        )
    table = ("<table><thead><tr><th>Project</th><th>Favorited by</th><th></th></tr></thead>"
             "<tbody>%s</tbody></table>" % "".join(rows)) if rows else "<p>No matching projects.</p>"

    major_opts = "".join(
        '<option value="%d"%s>%s</option>'
        % (m["id"], " selected" if major_id == m["id"] else "", templates.esc(m["name"]))
        for m in db.list_majors(ctx.conn)
    )
    controls = (
        '<form method="get" class="filters">'
        '<p class="field"><label for="f-q">Keyword</label><input id="f-q" name="q" value="%s"></p>'
        '<p class="field"><label for="f-major">Major / department</label>'
        '<select id="f-major" name="major"><option value="">any</option>%s</select></p>'
        '<p class="field check"><label><input type="checkbox" name="mode" value="broader"%s> Broader (related majors)</label></p>'
        '<p class="field check"><label><input type="checkbox" name="fit" value="all"%s> Show all (ignore my majors)</label></p>'
        '<p><button type="submit">Search</button></p></form>'
    ) % (templates.esc(q), major_opts, " checked" if broader else "",
         " checked" if not fit_only else "")

    pref_link = ('<p><a class="button-link" href="/sessions/%d/preferences">Rank my favorites &amp; submit</a></p>'
                 % session["id"])
    note = ('<p class="hint">Preferencing is optional in %s-preference sessions, '
            "but ranking your favorites improves your match (R5.9).</p>"
            % templates.esc(session["mode"]))
    body = controls + note + pref_link + table
    return html_response(templates.layout("Browse projects", templates.page("Browse projects", body), ctx.user))


def _faculty_browse(ctx, session):
    q = fv(ctx.query, "q")
    scope = fv(ctx.query, "scope", "all")  # 'all' | 'favorited'
    project_id = fint(ctx.query, "project")

    my_projects = [p for p in db.list_projects(ctx.conn, session["id"])
                   if db.is_project_mentor(ctx.conn, p["id"], ctx.user["id"])]
    favorited_students = set()
    if scope == "favorited" and project_id:
        favorited_students = {r["user_id"] for r in db.students_who_favorited(ctx.conn, project_id)}

    profiles = db.list_submitted_profiles(ctx.conn, session["id"])
    rows = []
    for p in profiles:
        name = "%s %s" % (p["given_name"], p["family_name"])
        if q and q.lower() not in name.lower() and q.lower() not in (p["interests"] or "").lower():
            continue
        if scope == "favorited" and p["user_id"] not in favorited_students:
            continue
        rows.append(
            "<tr><td data-label=\"Student\">%s</td><td data-label=\"Interests\">%s</td></tr>"
            % (templates.esc(name or p["display_name"]), templates.esc((p["interests"] or "")[:120]))
        )
    table = ("<table><thead><tr><th>Student</th><th>Interests</th></tr></thead><tbody>%s</tbody></table>"
             % "".join(rows)) if rows else "<p>No matching students.</p>"

    proj_opts = "".join(
        '<option value="%d"%s>%s</option>'
        % (p["id"], " selected" if project_id == p["id"] else "", templates.esc(p["title"]))
        for p in my_projects
    )
    controls = (
        '<form method="get" class="filters">'
        '<p class="field"><label for="f-q">Keyword</label><input id="f-q" name="q" value="%s"></p>'
        '<p class="field"><label for="f-scope">Scope</label>'
        '<select id="f-scope" name="scope"><option value="all"%s>Entire undergraduate pool</option>'
        '<option value="favorited"%s>Only students who favorited my project</option></select></p>'
        '<p class="field"><label for="f-project">My project (for favorited scope)</label>'
        '<select id="f-project" name="project"><option value="">--</option>%s</select></p>'
        '<p><button type="submit">Search</button></p></form>'
    ) % (templates.esc(q), " selected" if scope == "all" else "",
         " selected" if scope == "favorited" else "", proj_opts)
    return html_response(templates.layout("Browse students", templates.page("Browse students", controls + table), ctx.user))


@route("GET", "/sessions/{id}/browse")
def browse(ctx):
    guard = require_login(ctx)
    if guard:
        return guard
    session, err = _session_or_404(ctx)
    if err:
        return err
    if not db.can_view_session(ctx.conn, session, ctx.user):
        return forbidden("You do not have access to this session.")
    if ctx.user["role"] == "student":
        return _student_browse(ctx, session)
    if ctx.user["role"] in ("faculty", "admin", "manager"):
        return _faculty_browse(ctx, session)
    return forbidden("Browsing is not available for your role.")


@route("POST", "/favorites")
def favorites_post(ctx):
    guard = require_login(ctx)
    if guard:
        return guard
    csrf_err = check_csrf(ctx)
    if csrf_err:
        return csrf_err
    session_id = fint(ctx.form, "session_id")
    project_id = fint(ctx.form, "project_id")
    op = fv(ctx.form, "op", "add")
    if session_id is None or project_id is None:
        return redirect("/")
    session = db.get_session(ctx.conn, session_id)
    project = db.get_project(ctx.conn, project_id)
    if session is None or project is None or project["session_id"] != session_id:
        return not_found("Not found.")
    if not db.can_view_session(ctx.conn, session, ctx.user):
        return forbidden("You do not have access to this session.")

    if op == "remove":
        db.remove_favorite(ctx.conn, ctx.user["id"], project_id)
    else:
        db.add_favorite(ctx.conn, ctx.user["id"], project_id)
        # R5.5: optionally notify the project's mentors when invites are on.
        if session["favorite_invites"]:
            for m in db.project_mentors(ctx.conn, project_id):
                notify_service.notify(
                    ctx.conn, m["user_id"], kind="favorite_invite",
                    subject="A student favorited your project",
                    body="%s favorited '%s'." % (ctx.user["display_name"], project["title"]))
    ctx.conn.commit()
    return redirect("/sessions/%d/browse" % session_id)


def _preferences_page(ctx, session, msg=None):
    favs = db.list_favorites(ctx.conn, ctx.user["id"], session["id"])
    current = db.get_preferences(ctx.conn, session["id"], "student", student_id=ctx.user["id"])
    order = [r["project_id"] for r in current]
    # Favorites not yet ranked are appended.
    ranked_ids = set(order)
    fav_by_id = {p["id"]: p for p in favs}
    for p in favs:
        if p["id"] not in ranked_ids:
            order.append(p["id"])

    items = []
    for idx, pid in enumerate(order):
        p = fav_by_id.get(pid)
        if p is None:
            continue
        items.append(
            '<li class="rank-item" draggable="true" data-pid="%d">'
            '<span class="rank-handle" aria-hidden="true">::</span> %s '
            '<input type="hidden" name="order" value="%d">'
            '<button type="button" class="rank-up" aria-label="Move up">Up</button>'
            '<button type="button" class="rank-down" aria-label="Move down">Down</button>'
            "</li>" % (pid, templates.esc(p["title"]), pid)
        )
    ranked_list = ('<ol class="rank-list" id="rank-list">%s</ol>' % "".join(items)
                   if items else "<p>Favorite some projects first, then rank them here.</p>")

    submitted = bool(current)
    locked = phase_locked(session, "student_preference")
    state = ""
    if msg == "saved":
        state = '<p class="flash" role="status">Preferences saved.</p>'
    deadline = session["deadline_student_preference"]
    deadline_msg = ("<p>Preference deadline: %s</p>" % templates.tz_label(deadline, session["timezone"])) if deadline else ""
    status_line = ""
    if submitted:
        status_line = '<p class="pill">Submitted (%d ranked). You can edit while the deadline is open.</p>' % len(current)
    if locked:
        status_line += '<p class="error">The preference deadline has passed; your list is read-only.</p>'

    buttons = ""
    if not locked:
        buttons = (
            '<p><button type="submit" name="action" value="save">Save order</button> '
            '<button type="submit" name="action" value="submit">Submit preferences</button></p>'
        )
    body = (
        "%s%s%s"
        '<form method="post" action="/preferences" id="pref-form">'
        "%s<input type=\"hidden\" name=\"session_id\" value=\"%d\">"
        "%s%s</form>"
    ) % (state, deadline_msg, status_line,
         templates.csrf_input(ctx.user["csrf_token"]), session["id"],
         ranked_list, buttons)
    return html_response(templates.layout("My preferences", templates.page("Rank your favorites", body), ctx.user))


@route("GET", "/sessions/{id}/preferences")
def preferences_get(ctx):
    guard = require_role(ctx, "student")
    if guard:
        return guard
    session, err = _session_or_404(ctx)
    if err:
        return err
    if not db.can_view_session(ctx.conn, session, ctx.user):
        return forbidden("You do not have access to this session.")
    return _preferences_page(ctx, session, msg=fv(ctx.query, "msg"))


@route("POST", "/preferences")
def preferences_post(ctx):
    guard = require_role(ctx, "student")
    if guard:
        return guard
    csrf_err = check_csrf(ctx)
    if csrf_err:
        return csrf_err
    session_id = fint(ctx.form, "session_id")
    session = db.get_session(ctx.conn, session_id) if session_id else None
    if session is None:
        return not_found("Session not found.")
    if not db.can_view_session(ctx.conn, session, ctx.user):
        return forbidden("You do not have access to this session.")
    if phase_locked(session, "student_preference"):
        return forbidden("The preference deadline has passed.")

    order = [int(x) for x in fvlist(ctx.form, "order") if x.isdigit()]
    # Only keep projects the student actually favorited in this session.
    fav_ids = {p["id"] for p in db.list_favorites(ctx.conn, ctx.user["id"], session_id)}
    order = [pid for pid in order if pid in fav_ids]
    db.replace_student_preferences(ctx.conn, session_id, ctx.user["id"], order)
    ctx.conn.commit()
    action = fv(ctx.form, "action", "save")
    if action == "submit":
        return redirect("/preferences/submit?session_id=%d" % session_id)
    return redirect("/sessions/%d/preferences?msg=saved" % session_id)


@route("GET", "/preferences/submit")
def preferences_submit_get(ctx):
    # Submitting is also reachable via POST redirect; show confirmation.
    guard = require_role(ctx, "student")
    if guard:
        return guard
    session_id = fint(ctx.query, "session_id")
    session = db.get_session(ctx.conn, session_id) if session_id else None
    if session is None:
        return not_found("Session not found.")
    current = db.get_preferences(ctx.conn, session_id, "student", student_id=ctx.user["id"])
    deadline = session["deadline_student_preference"]
    body = (
        '<p class="flash" role="status">Your %d ranked preference(s) are submitted to the matching algorithm.</p>'
        "<p>Deadline: %s. You may edit your list until then.</p>"
        '<p><a href="/sessions/%d/preferences">Edit preferences</a> &middot; '
        '<a href="/sessions/%d/browse">Back to browse</a></p>'
    ) % (len(current), templates.tz_label(deadline, session["timezone"]),
         session_id, session_id)
    return html_response(templates.layout("Preferences submitted", templates.page("Preferences submitted", body), ctx.user))


@route("POST", "/preferences/submit")
def preferences_submit_post(ctx):
    guard = require_role(ctx, "student")
    if guard:
        return guard
    csrf_err = check_csrf(ctx)
    if csrf_err:
        return csrf_err
    session_id = fint(ctx.form, "session_id")
    return redirect("/preferences/submit?session_id=%d" % session_id if session_id else "/")


# ---------------------------------------------------------------------------
# Matching run + publish (R6.8), review (R7), contracting + placement (R8)
# ---------------------------------------------------------------------------

# Phases in which a matching run only reassigns unmatched students into
# remaining capacity (R7.6). The initial run happens in 'matching'.
REMATCH_PHASES = ("review",)

CREDIT_RANGE_CHOICES = {
    "1-2": ["1", "2"],
    "1-3": ["1", "2", "3"],
    "2-3": ["2", "3"],
}


def _fmt_pct(value):
    """Render a 0-100 fit score as a percentage string."""
    try:
        return "%.0f%%" % float(value)
    except (TypeError, ValueError):
        return "0%"


# Minimum distinct raters before an average rating may be shown (R12.1).
RATING_MIN_RATERS = 5


def _project_rating_badge(conn, session, project_id):
    """Return an HTML rating badge for a project, or '' when it must stay hidden.

    Shown only where the session's show_ratings toggle is enabled AND the
    project has at least RATING_MIN_RATERS distinct raters (R12.1).
    """
    if not session or not session["show_ratings"]:
        return ""
    avg, raters = db.project_rating_summary(conn, project_id)
    if avg is None or raters < RATING_MIN_RATERS:
        return ""
    return ('<span class="rating" title="%d raters">&#9733; %.1f (%d)</span>'
            % (raters, avg, raters))


def _build_match_inputs(conn, session, restrict_unmatched=False):
    """Build (students, projects, config) for the engine from session data.

    When `restrict_unmatched` is True (rematch run, R7.6) only students without
    an active match are included, and each project's capacity is reduced by the
    number of slots already consumed by active matches so the run can never
    exceed capacity.
    """
    sid = session["id"]
    method = session["matching_method"]
    weighting = session["weighting"]

    # Students: submitted profiles only.
    profiles = db.list_submitted_profiles(conn, sid)
    students = []
    for p in profiles:
        uid = p["user_id"]
        if restrict_unmatched and db.match_for_student(conn, sid, uid) is not None:
            continue
        major_ids = set(db.profile_major_ids(conn, p["id"]))
        prefs = [r["project_id"] for r in db.get_preferences(
            conn, sid, "student", student_id=uid)]
        students.append(match_engine.StudentIn(
            id=uid, major_ids=major_ids,
            noncitizen=bool(p["noncitizen"]), prefs=prefs))

    # Projects: published projects with positive remaining capacity.
    projects = []
    for proj in db.list_published_projects(conn, sid):
        capacity = proj["capacity"] or proj["positions"] or 0
        if restrict_unmatched:
            capacity = capacity - db.project_filled_count(conn, sid, proj["id"])
        if capacity <= 0:
            continue
        elig = set(db.project_eligible_major_ids(conn, proj["id"]))
        must = elig if proj["major_policy"] == "must" else set()
        prefer = elig if proj["major_policy"] == "prefer" else set()
        # Faculty/project preference list (mutual mode).
        fac_prefs = []
        if method == "mutual":
            fac_prefs = [r["student_id"] for r in db.get_preferences(
                conn, sid, "project", project_id=proj["id"])]
        projects.append(match_engine.ProjectIn(
            id=proj["id"], capacity=capacity,
            noncitizen_ok=bool(proj["noncitizen_eligible"]),
            must_majors=must, prefer_majors=prefer, prefs=fac_prefs))

    config = match_engine.Config(weighting=weighting)
    return students, projects, config


def _run_matching(conn, session, restrict_unmatched):
    """Execute a matching run, persist a match_runs row + proposed matches.

    Returns (run_id, result). Matches from this run are stored unpublished.
    """
    students, projects, config = _build_match_inputs(
        conn, session, restrict_unmatched=restrict_unmatched)
    result = match_engine.match(students, projects, config)

    round_ = db.next_run_round(conn, session["id"])
    config_snapshot = {
        "matching_method": session["matching_method"],
        "weighting": session["weighting"],
        "restrict_unmatched": restrict_unmatched,
        "student_count": len(students),
        "project_count": len(projects),
    }
    stats_snapshot = {
        "overall_fit": result.overall_fit,
        "per_project_fit": {str(k): v for k, v in result.per_project_fit.items()},
        "unmatched_students": result.unmatched_students,
    }
    run_id = db.create_match_run(
        conn, session["id"], round_, result.overall_fit,
        json.dumps(config_snapshot), json.dumps(stats_snapshot),
        published=0, status="complete")
    for a in result.assignments:
        db.create_match(
            conn, session["id"], run_id, a.student_id, a.project_id, round_,
            student_fit=a.student_fit, project_fit=a.project_fit,
            status="proposed", score=a.student_fit)
    conn.commit()
    return run_id, result


def _user_label(conn, user_id):
    u = db.get_user_by_id(conn, user_id)
    if u is None:
        return "Unknown"
    return u["display_name"]


def _match_preview_page(ctx, session, run, result=None):
    """Render the preview of a run's proposed assignments + fit stats."""
    matches = db.matches_for_run(ctx.conn, run["id"])
    rows = []
    for m in matches:
        proj = db.get_project(ctx.conn, m["project_id"])
        rows.append(
            "<tr><td data-label=\"Student\">%s</td>"
            "<td data-label=\"Project\">%s</td>"
            "<td data-label=\"Student fit\">%s</td>"
            "<td data-label=\"Project fit\">%s</td></tr>"
            % (templates.esc(_user_label(ctx.conn, m["student_id"])),
               templates.esc(proj["title"] if proj else "?"),
               _fmt_pct(m["student_fit"]), _fmt_pct(m["project_fit"])))
    table = ("<table><thead><tr><th>Student</th><th>Project</th>"
             "<th>Student fit</th><th>Project fit</th></tr></thead>"
             "<tbody>%s</tbody></table>" % "".join(rows)) if rows else \
            "<p>No assignments were produced for this run.</p>"

    # Per-project fit summary.
    stats = json.loads(run["stats_json"] or "{}")
    per_project = stats.get("per_project_fit", {})
    pp_rows = []
    for pid_str, fit in per_project.items():
        proj = db.get_project(ctx.conn, int(pid_str))
        pp_rows.append("<tr><td data-label=\"Project\">%s</td>"
                       "<td data-label=\"Fit\">%s</td></tr>"
                       % (templates.esc(proj["title"] if proj else pid_str),
                          _fmt_pct(fit)))
    pp_table = ("<table><thead><tr><th>Project</th><th>Fit</th></tr></thead>"
                "<tbody>%s</tbody></table>" % "".join(pp_rows)) if pp_rows else ""

    unmatched = stats.get("unmatched_students", [])
    unmatched_html = ""
    if unmatched:
        names = ", ".join(templates.esc(_user_label(ctx.conn, uid)) for uid in unmatched)
        unmatched_html = "<p><strong>Unmatched students:</strong> %s</p>" % names

    published = run["published"]
    publish_form = ""
    if not published and db.can_manage_session(ctx.conn, session, ctx.user):
        publish_form = (
            '<form method="post" action="/sessions/%d/publish" class="inline">%s'
            '<input type="hidden" name="run_id" value="%d">'
            '<button type="submit">Publish this run to participants</button></form>'
            % (session["id"], templates.csrf_input(ctx.user["csrf_token"]), run["id"]))
    rerun_form = (
        '<form method="post" action="/sessions/%d/match" class="inline">%s'
        '<button type="submit">Run matching again</button></form>'
        % (session["id"], templates.csrf_input(ctx.user["csrf_token"])))

    state = '<p class="pill">%s</p>' % ("published" if published else "preview (not yet published)")
    body = (
        "%s"
        '<p>Run #%d &middot; round %d &middot; overall fit: <strong>%s</strong></p>'
        "%s"
        '<section aria-labelledby="pa-h"><h2 id="pa-h">Proposed assignments</h2>%s</section>'
        '<section aria-labelledby="pp-h"><h2 id="pp-h">Per-project fit</h2>%s</section>'
        '<p>%s %s</p>'
    ) % (state, run["id"], run["round"], _fmt_pct(run["overall_fit"]),
         unmatched_html, table, pp_table, publish_form, rerun_form)
    return html_response(templates.layout(
        "Matching preview", templates.page("Matching results for %s" % templates.esc(session["name"]), body),
        ctx.user))


@route("POST", "/sessions/{id}/match")
def session_match(ctx):
    guard = require_role(ctx, "admin", "manager")
    if guard:
        return guard
    csrf_err = check_csrf(ctx)
    if csrf_err:
        return csrf_err
    session, err = _session_or_404(ctx)
    if err:
        return err
    if not db.can_manage_session(ctx.conn, session, ctx.user):
        return forbidden("You do not manage this session.")
    restrict = session["status"] in REMATCH_PHASES
    run_id, _result = _run_matching(ctx.conn, session, restrict_unmatched=restrict)
    return redirect("/sessions/%d/match/%d" % (session["id"], run_id))


@route("GET", "/sessions/{id}/match")
def session_match_latest(ctx):
    guard = require_login(ctx)
    if guard:
        return guard
    session, err = _session_or_404(ctx)
    if err:
        return err
    if not db.can_manage_session(ctx.conn, session, ctx.user):
        return forbidden("You do not manage this session.")
    run = db.latest_run(ctx.conn, session["id"])
    if run is None:
        body = ('<p>No matching run yet.</p>'
                '<form method="post" action="/sessions/%d/match">%s'
                '<button type="submit">Run matching</button></form>'
                % (session["id"], templates.csrf_input(ctx.user["csrf_token"])))
        return html_response(templates.layout(
            "Matching", templates.page("Matching for %s" % templates.esc(session["name"]), body), ctx.user))
    return _match_preview_page(ctx, session, run)


@route("GET", "/sessions/{id}/match/{run_id}")
def session_match_run(ctx):
    guard = require_login(ctx)
    if guard:
        return guard
    session, err = _session_or_404(ctx)
    if err:
        return err
    if not db.can_manage_session(ctx.conn, session, ctx.user):
        return forbidden("You do not manage this session.")
    try:
        run_id = int(ctx.params.get("run_id"))
    except (TypeError, ValueError):
        return not_found("Run not found.")
    run = db.get_match_run(ctx.conn, run_id)
    if run is None or run["session_id"] != session["id"]:
        return not_found("Run not found.")
    return _match_preview_page(ctx, session, run)


@route("POST", "/sessions/{id}/publish")
def session_publish(ctx):
    guard = require_role(ctx, "admin", "manager")
    if guard:
        return guard
    csrf_err = check_csrf(ctx)
    if csrf_err:
        return csrf_err
    session, err = _session_or_404(ctx)
    if err:
        return err
    if not db.can_manage_session(ctx.conn, session, ctx.user):
        return forbidden("You do not manage this session.")
    run_id = fint(ctx.form, "run_id")
    run = db.get_match_run(ctx.conn, run_id) if run_id else db.latest_run(ctx.conn, session["id"])
    if run is None or run["session_id"] != session["id"]:
        return not_found("Run not found.")
    db.publish_run(ctx.conn, run["id"])
    # Notify each matched participant that results are available (R7.1).
    for m in db.matches_for_run(ctx.conn, run["id"]):
        if m["status"] in ("rejected", "rematch"):
            continue
        proj = db.get_project(ctx.conn, m["project_id"])
        notify_service.send(
            ctx.conn, m["student_id"], channel="email", kind="match_published",
            subject="Your research match is ready",
            body="You have a proposed match for '%s'." % (proj["title"] if proj else "a project"))
        for mentor in db.project_mentors(ctx.conn, m["project_id"]):
            notify_service.send(
                ctx.conn, mentor["user_id"], channel="email", kind="match_published",
                subject="A proposed match is ready to review",
                body="A student was matched to '%s'." % (proj["title"] if proj else "your project"))
    ctx.conn.commit()
    return redirect("/sessions/%d/match/%d" % (session["id"], run["id"]))


# ---------------------------------------------------------------------------
# Participant review (R7.1-R7.3)
# ---------------------------------------------------------------------------

def _match_card(ctx, m, for_student):
    proj = db.get_project(ctx.conn, m["project_id"])
    student_name = _user_label(ctx.conn, m["student_id"])
    title = proj["title"] if proj else "(project)"
    csrf = templates.csrf_input(ctx.user["csrf_token"])
    fit = _fmt_pct(m["student_fit"]) if for_student else _fmt_pct(m["project_fit"])
    actions = []
    status = m["status"]
    if status in ("proposed", "accepted"):
        if for_student:
            actions.append(
                '<form method="post" action="/matches/%d/accept" class="inline">%s'
                '<button type="submit">Accept</button></form>' % (m["id"], csrf))
            actions.append(
                '<form method="post" action="/matches/%d/rematch" class="inline">%s'
                '<button type="submit" class="secondary">Request rematch</button></form>'
                % (m["id"], csrf))
            if session_allows_super_interest(ctx.conn, m):
                actions.append(
                    '<form method="post" action="/matches/%d/super-interest" class="inline">%s'
                    '<button type="submit" class="secondary">Super-interest</button></form>'
                    % (m["id"], csrf))
        else:
            actions.append(
                '<form method="post" action="/matches/%d/accept" class="inline">%s'
                '<button type="submit">Accept</button></form>' % (m["id"], csrf))
            actions.append(
                '<form method="post" action="/matches/%d/reject" class="inline">%s'
                '<button type="submit" class="secondary">Not a good match</button></form>'
                % (m["id"], csrf))
        actions.append('<a class="button-link" href="/matches/%d/contract">Contract</a>' % m["id"])
    elif status == "finalized":
        actions.append('<a class="button-link" href="/matches/%d/contract">View placement</a>' % m["id"])

    who = ("Project: <strong>%s</strong>" % templates.esc(title)) if for_student else \
          ("Student: <strong>%s</strong> for <strong>%s</strong>"
           % (templates.esc(student_name), templates.esc(title)))
    return (
        '<li class="match-card"><p>%s</p>'
        '<p class="pill">%s</p> <p class="pill">fit: %s</p>'
        "<p>%s</p></li>" % (who, templates.esc(status), fit, " ".join(actions)))


def session_allows_super_interest(conn, m):
    session = db.get_session(conn, m["session_id"])
    return bool(session and session["allow_super_interest"])


@route("GET", "/matches/mine")
def matches_mine(ctx):
    guard = require_login(ctx)
    if guard:
        return guard
    for_student = ctx.user["role"] == "student"
    # Gather across all sessions the user participates in.
    cards = []
    for session in db.list_sessions(ctx.conn):
        if not db.can_view_session(ctx.conn, session, ctx.user):
            continue
        for m in db.matches_visible_to_user(ctx.conn, session["id"], ctx.user):
            cards.append(_match_card(ctx, m, for_student))
    listing = '<ul class="match-list">%s</ul>' % "".join(cards) if cards else \
              "<p>You have no published matches yet.</p>"
    heading = "My match" if for_student else "Matches to review"
    return html_response(templates.layout(heading, templates.page(heading, listing), ctx.user))


def _load_match_for_party(ctx, require_student=False, require_faculty=False):
    """Return (match, None) if the user is a party to the match, else (None, resp)."""
    mid = fint_param(ctx, "id")
    m = db.get_match(ctx.conn, mid) if mid else None
    if m is None:
        return None, not_found("Match not found.")
    if not db.user_is_match_party(ctx.conn, m, ctx.user):
        return None, forbidden("You are not a party to this match.")
    if require_student and ctx.user["role"] != "student":
        return None, forbidden("Only the student can do that.")
    if require_faculty and ctx.user["role"] not in ("faculty", "admin", "manager"):
        return None, forbidden("Only faculty can do that.")
    return m, None


@route("POST", "/matches/{id}/accept")
def match_accept(ctx):
    guard = require_login(ctx)
    if guard:
        return guard
    csrf_err = check_csrf(ctx)
    if csrf_err:
        return csrf_err
    m, resp = _load_match_for_party(ctx)
    if resp:
        return resp
    if m["status"] in ("proposed", "accepted"):
        db.update_match(ctx.conn, m["id"], status="accepted")
        ctx.conn.commit()
    return redirect("/matches/mine")


@route("POST", "/matches/{id}/reject")
def match_reject(ctx):
    """Faculty 'not a good match': unmatch the student + notify them (R7.2)."""
    guard = require_role(ctx, "faculty", "admin", "manager")
    if guard:
        return guard
    csrf_err = check_csrf(ctx)
    if csrf_err:
        return csrf_err
    m, resp = _load_match_for_party(ctx, require_faculty=True)
    if resp:
        return resp
    db.update_match(ctx.conn, m["id"], status="rejected")
    proj = db.get_project(ctx.conn, m["project_id"])
    notify_service.notify(
        ctx.conn, m["student_id"], kind="rematch_needed",
        subject="You need a new research match",
        body="The faculty for '%s' determined it was not a good match. "
             "Please browse open positions and request a rematch."
             % (proj["title"] if proj else "your project"))
    ctx.conn.commit()
    return redirect("/matches/mine")


@route("POST", "/matches/{id}/rematch")
def match_rematch(ctx):
    """Student requests a rematch (R7.3). Optionally target an open project."""
    guard = require_role(ctx, "student")
    if guard:
        return guard
    csrf_err = check_csrf(ctx)
    if csrf_err:
        return csrf_err
    m, resp = _load_match_for_party(ctx, require_student=True)
    if resp:
        return resp
    db.update_match(ctx.conn, m["id"], status="rematch")
    session = db.get_session(ctx.conn, m["session_id"])

    # Optional: the student targets a specific open project to approach another
    # faculty member (R7.4). Create a fresh proposed match if there is capacity.
    target_pid = fint(ctx.form, "project_id")
    if target_pid:
        proj = db.get_project(ctx.conn, target_pid)
        if (proj and proj["session_id"] == session["id"] and proj["status"] == "published"
                and _remaining_capacity(ctx.conn, session["id"], proj) > 0):
            run = db.latest_run(ctx.conn, session["id"], published_only=True)
            db.create_match(
                ctx.conn, session["id"], run["id"] if run else None,
                ctx.user["id"], target_pid, run["round"] if run else 1,
                student_fit=0.0, project_fit=0.0, status="proposed")
            for mentor in db.project_mentors(ctx.conn, target_pid):
                notify_service.notify(
                    ctx.conn, mentor["user_id"], kind="rematch_request",
                    subject="A student requested to join your project",
                    body="%s requested a rematch with '%s'."
                         % (ctx.user["display_name"], proj["title"]))
    # Notify managers that a rematch was requested.
    for mgr in ctx.conn.execute(
            "SELECT user_id FROM session_managers WHERE session_id = ?",
            (session["id"],)).fetchall():
        notify_service.notify(
            ctx.conn, mgr["user_id"], kind="rematch_request",
            subject="A student requested a rematch",
            body="%s requested a rematch." % ctx.user["display_name"])
    ctx.conn.commit()
    return redirect("/sessions/%d/open-positions" % session["id"])


@route("POST", "/matches/{id}/super-interest")
def match_super_interest(ctx):
    """Student signals super-interest (R7.5), only where the toggle is on."""
    guard = require_role(ctx, "student")
    if guard:
        return guard
    csrf_err = check_csrf(ctx)
    if csrf_err:
        return csrf_err
    m, resp = _load_match_for_party(ctx, require_student=True)
    if resp:
        return resp
    session = db.get_session(ctx.conn, m["session_id"])
    if not session["allow_super_interest"]:
        return forbidden("Super-interest is not enabled for this session.")
    proj = db.get_project(ctx.conn, m["project_id"])
    for mentor in db.project_mentors(ctx.conn, m["project_id"]):
        notify_service.notify(
            ctx.conn, mentor["user_id"], kind="super_interest",
            subject="A student is super interested in your project",
            body="%s is super interested in '%s'. Consider opening an extra slot."
                 % (ctx.user["display_name"], proj["title"] if proj else "your project"))
    ctx.conn.commit()
    return redirect("/matches/mine")


# ---------------------------------------------------------------------------
# Rematch flow: open positions (R7.4)
# ---------------------------------------------------------------------------

def _remaining_capacity(conn, session_id, project):
    cap = project["capacity"] or project["positions"] or 0
    return cap - db.project_filled_count(conn, session_id, project["id"])


@route("GET", "/sessions/{id}/open-positions")
def open_positions(ctx):
    """Students browse projects with remaining capacity and request a rematch."""
    guard = require_role(ctx, "student")
    if guard:
        return guard
    session, err = _session_or_404(ctx)
    if err:
        return err
    if not db.can_view_session(ctx.conn, session, ctx.user):
        return forbidden("You do not have access to this session.")

    current = db.match_for_student(ctx.conn, session["id"], ctx.user["id"])
    rematch_match = ctx.conn.execute(
        "SELECT * FROM matches WHERE session_id = ? AND student_id = ? AND status = 'rematch' "
        "ORDER BY id DESC LIMIT 1", (session["id"], ctx.user["id"])).fetchone()
    rows = []
    for proj in db.list_published_projects(ctx.conn, session["id"]):
        remaining = _remaining_capacity(ctx.conn, session["id"], proj)
        if remaining <= 0:
            continue
        # Build a rematch request against a prior rejected/rematch match row so
        # the student always has a match id to act through.
        anchor = rematch_match or current
        action = ""
        if anchor is not None:
            action = (
                '<form method="post" action="/matches/%d/rematch" class="inline">%s'
                '<input type="hidden" name="project_id" value="%d">'
                '<button type="submit">Request this project</button></form>'
                % (anchor["id"], templates.csrf_input(ctx.user["csrf_token"]), proj["id"]))
        rows.append(
            "<tr><td data-label=\"Project\"><a href=\"/projects/%d\">%s</a></td>"
            "<td data-label=\"Open slots\">%d</td><td data-label=\"\">%s</td></tr>"
            % (proj["id"], templates.esc(proj["title"]), remaining, action))
    table = ("<table><thead><tr><th>Project</th><th>Open slots</th><th></th></tr></thead>"
             "<tbody>%s</tbody></table>" % "".join(rows)) if rows else \
            "<p>No open positions remain in this session.</p>"
    note = ("<p class=\"hint\">These are projects with capacity beyond their accepted "
            "matches. Requesting one approaches that faculty member for a rematch.</p>")
    body = note + table
    return html_response(templates.layout(
        "Open positions", templates.page("Open positions in %s" % templates.esc(session["name"]), body),
        ctx.user))


# ---------------------------------------------------------------------------
# Contracting + placement (R8.1-R8.4)
# ---------------------------------------------------------------------------

def _credit_choices_for_project(project):
    """Return the list of selectable credit counts for a project, or [] if the
    credit option is a single fixed value or the project is paid."""
    if project["comp_type"] != "credit":
        return []
    opt = project["credit_option"] or ""
    return CREDIT_RANGE_CHOICES.get(opt, [])


def _contract_page(ctx, m, contract, errors=None):
    errors = errors or {}
    proj = db.get_project(ctx.conn, m["project_id"])
    session = db.get_session(ctx.conn, m["session_id"])
    student_name = _user_label(ctx.conn, m["student_id"])
    csrf = templates.csrf_input(ctx.user["csrf_token"])
    terms = json.loads(contract["terms_json"] or "{}")
    is_student = ctx.user["role"] == "student"
    signed_student = bool(contract["student_signed_at"])
    signed_faculty = bool(contract["faculty_signed_at"])

    credit_choices = _credit_choices_for_project(proj)
    comp_line = ""
    credit_field = ""
    if proj["comp_type"] == "credit":
        if credit_choices:
            current = contract["final_credit"] or terms.get("final_credit", "")
            opts = "".join(
                '<option value="%s"%s>%s credit(s)</option>'
                % (c, " selected" if current == c else "", c) for c in credit_choices)
            credit_field = (
                '<p class="field"><label for="f-final_credit">Final credit count '
                '(range %s)</label><select id="f-final_credit" name="final_credit">'
                '<option value="">-- choose --</option>%s</select>%s</p>'
                % (templates.esc(proj["credit_option"]), opts,
                   templates.field_error(errors.get("final_credit"))))
            comp_line = "For credit (flexible range %s)" % templates.esc(proj["credit_option"])
        else:
            comp_line = "For credit (%s)" % templates.esc(proj["credit_option"] or "n/a")
    else:
        rate = proj["hourly_rate"]
        comp_line = "Paid position%s" % (" at $%.2f/hr" % rate if rate else "")

    responsibilities = terms.get("responsibilities", proj["responsibilities"] or "")

    placement_html = ""
    if contract["placement_ref"]:
        placement_html = ('<p class="flash" role="status">Placement recorded: '
                          '<strong>%s</strong>. This match is finalized.</p>'
                          % templates.esc(contract["placement_ref"]))

    sign_state = (
        "<ul><li>Student signed: %s</li><li>Faculty signed: %s</li></ul>"
        % (templates.tz_label(contract["student_signed_at"], session["timezone"]) if signed_student else "not yet",
           templates.tz_label(contract["faculty_signed_at"], session["timezone"]) if signed_faculty else "not yet"))

    already_signed = (is_student and signed_student) or (not is_student and signed_faculty)
    form = ""
    if not contract["placement_ref"]:
        button = "Sign contract"
        if already_signed:
            button = "Update terms"
        form = (
            '<form method="post" action="/matches/%d/contract" class="stacked">%s'
            "%s"  # credit field
            '<p class="field"><label for="f-responsibilities">Responsibilities</label>'
            '<textarea id="f-responsibilities" name="responsibilities" rows="4">%s</textarea></p>'
            '<p class="field check"><label><input type="checkbox" name="sign" value="1"%s> '
            'I agree to these terms and sign as %s</label></p>'
            '<p><button type="submit">%s</button></p></form>'
            % (m["id"], csrf, credit_field, templates.esc(responsibilities),
               " checked" if already_signed else "",
               "the student" if is_student else "faculty", button))

    body = (
        "%s"
        '<p><strong>Student:</strong> %s</p>'
        '<p><strong>Project:</strong> %s</p>'
        '<p><strong>Compensation:</strong> %s</p>'
        "%s"  # signing state
        "%s"  # form
    ) % (placement_html, templates.esc(student_name),
         templates.esc(proj["title"] if proj else "?"), comp_line, sign_state, form)
    return html_response(templates.layout(
        "Contract", templates.page("Research placement contract", body), ctx.user))


@route("GET", "/matches/{id}/contract")
def contract_get(ctx):
    guard = require_login(ctx)
    if guard:
        return guard
    m, resp = _load_match_for_party(ctx)
    if resp:
        return resp
    cid = db.ensure_contract(ctx.conn, m["id"])
    ctx.conn.commit()
    contract = db.get_contract(ctx.conn, m["id"])
    return _contract_page(ctx, m, contract)


@route("POST", "/matches/{id}/contract")
def contract_post(ctx):
    guard = require_login(ctx)
    if guard:
        return guard
    csrf_err = check_csrf(ctx)
    if csrf_err:
        return csrf_err
    m, resp = _load_match_for_party(ctx)
    if resp:
        return resp
    db.ensure_contract(ctx.conn, m["id"])
    contract = db.get_contract(ctx.conn, m["id"])
    if contract["placement_ref"]:
        return redirect("/matches/%d/contract" % m["id"])  # already placed

    proj = db.get_project(ctx.conn, m["project_id"])
    is_student = ctx.user["role"] == "student"
    credit_choices = _credit_choices_for_project(proj)

    terms = json.loads(contract["terms_json"] or "{}")
    terms["responsibilities"] = fv(ctx.form, "responsibilities")

    final_credit = contract["final_credit"]
    errors = {}
    if credit_choices:
        chosen = fv(ctx.form, "final_credit")
        if chosen:
            if chosen not in credit_choices:
                errors["final_credit"] = "Choose a valid credit count."
            else:
                final_credit = chosen
                terms["final_credit"] = chosen

    signing = fv(ctx.form, "sign") == "1"
    # A flexible-credit project must have its final credit chosen before the
    # placement can complete (R8.2).
    if signing and credit_choices and not final_credit:
        errors["final_credit"] = "Select the final credit count before signing."

    if errors:
        # Persist responsibilities even on error, then re-render.
        db.update_contract(ctx.conn, contract["id"], terms_json=json.dumps(terms))
        ctx.conn.commit()
        contract = db.get_contract(ctx.conn, m["id"])
        return _contract_page(ctx, m, contract, errors)

    cols = {"terms_json": json.dumps(terms)}
    if final_credit:
        cols["final_credit"] = final_credit
    if signing:
        if is_student:
            cols["student_signed_at"] = db.utcnow()
        else:
            cols["faculty_signed_at"] = db.utcnow()
    db.update_contract(ctx.conn, contract["id"], **cols)
    ctx.conn.commit()

    # Record compensation detail in terms for the placement.
    contract = db.get_contract(ctx.conn, m["id"])
    both_signed = contract["student_signed_at"] and contract["faculty_signed_at"]
    if both_signed and not contract["placement_ref"]:
        if proj["comp_type"] == "credit":
            placement_ref = workday.assign_course_section(ctx.conn, m, proj)
        else:
            placement_ref = workday.add_hourly_job(ctx.conn, m, proj)
        terms = json.loads(contract["terms_json"] or "{}")
        terms["comp_type"] = proj["comp_type"]
        if proj["comp_type"] == "credit":
            terms["credit"] = contract["final_credit"] or proj["credit_option"]
        else:
            terms["hourly_rate"] = proj["hourly_rate"]
        db.update_contract(ctx.conn, contract["id"], status="placed",
                           placement_ref=placement_ref, terms_json=json.dumps(terms))
        db.update_match(ctx.conn, m["id"], status="finalized")
        notify_service.notify(
            ctx.conn, m["student_id"], kind="placement",
            subject="Your research placement is confirmed",
            body="Placement reference: %s" % placement_ref)
        ctx.conn.commit()
    return redirect("/matches/%d/contract" % m["id"])


# ---------------------------------------------------------------------------
# Notifications & inbox (R9.1, R9.3)
# ---------------------------------------------------------------------------

@route("GET", "/inbox")
def inbox(ctx):
    guard = require_login(ctx)
    if guard:
        return guard
    notes = db.list_notifications(ctx.conn, ctx.user["id"])
    rows = []
    for n in notes:
        unread = not n["is_read"]
        mark = ""
        if unread:
            mark = (
                '<form method="post" action="/inbox/%d/read" class="inline">%s'
                '<button type="submit">Mark read</button></form>'
                % (n["id"], templates.csrf_input(ctx.user["csrf_token"])))
        rows.append(
            '<li class="note %s"><p><strong>%s</strong> '
            '<span class="pill">%s</span> %s</p><p>%s</p>%s</li>'
            % ("unread" if unread else "read",
               templates.esc(n["subject"] or n["kind"]),
               templates.esc(n["channel"]),
               '<span class="pill">new</span>' if unread else "",
               templates.esc(n["body"]), mark))
    listing = '<ul class="inbox">%s</ul>' % "".join(rows) if rows else "<p>No notifications yet.</p>"
    mark_all = ""
    if any(not n["is_read"] for n in notes):
        mark_all = (
            '<form method="post" action="/inbox/read-all" class="inline">%s'
            '<button type="submit">Mark all read</button></form>'
            % templates.csrf_input(ctx.user["csrf_token"]))
    body = mark_all + listing
    return html_response(templates.layout("Inbox", templates.page("Your inbox", body), ctx.user))


@route("POST", "/inbox/{id}/read")
def inbox_read(ctx):
    guard = require_login(ctx)
    if guard:
        return guard
    csrf_err = check_csrf(ctx)
    if csrf_err:
        return csrf_err
    nid = fint_param(ctx, "id")
    if nid is not None:
        db.mark_notification_read(ctx.conn, nid, ctx.user["id"])
        ctx.conn.commit()
    return redirect("/inbox")


@route("POST", "/inbox/read-all")
def inbox_read_all(ctx):
    guard = require_login(ctx)
    if guard:
        return guard
    csrf_err = check_csrf(ctx)
    if csrf_err:
        return csrf_err
    db.mark_all_notifications_read(ctx.conn, ctx.user["id"])
    ctx.conn.commit()
    return redirect("/inbox")


# ---------------------------------------------------------------------------
# Reporting & export (R10.1-R10.5)
# ---------------------------------------------------------------------------

def _report_rows(conn, session):
    """Build the structured report data for a session (used by HTML + CSV)."""
    sid = session["id"]
    students = db.session_student_participants(conn, sid)
    faculty = db.session_faculty_participants(conn, sid)
    projects = db.list_projects(conn, sid)
    total_slots = sum((p["positions"] or 0) for p in projects)
    pref_projects = db.most_preferred_projects(conn, sid)
    pref_students = db.most_preferred_students(conn, sid)
    run = db.latest_run(conn, sid, published_only=True) or db.latest_run(conn, sid)
    return {
        "students": students,
        "faculty": faculty,
        "projects": projects,
        "total_slots": total_slots,
        "pref_projects": pref_projects,
        "pref_students": pref_students,
        "run": run,
    }


@route("GET", "/sessions/{id}/reports")
def session_reports(ctx):
    guard = require_role(ctx, "admin", "manager")
    if guard:
        return guard
    session, err = _session_or_404(ctx)
    if err:
        return err
    if not db.can_manage_session(ctx.conn, session, ctx.user):
        return forbidden("You do not manage this session.")
    data = _report_rows(ctx.conn, session)

    student_names = ", ".join(
        templates.esc("%s %s" % (s["given_name"], s["family_name"]) or s["display_name"])
        for s in data["students"]) or "none"
    faculty_names = ", ".join(templates.esc(f["display_name"]) for f in data["faculty"]) or "none"

    proj_rows = "".join(
        "<tr><td data-label=\"Project\">%s</td><td data-label=\"Slots\">%d</td></tr>"
        % (templates.esc(p["title"]), p["positions"] or 0)
        for p in data["projects"]) or "<tr><td colspan=\"2\">No projects.</td></tr>"

    pref_proj_rows = "".join(
        "<tr><td data-label=\"Project\">%s</td><td data-label=\"Favorites\">%d</td>"
        "<td data-label=\"Ranked by students\">%d</td></tr>"
        % (templates.esc(p["title"]), p["favorites"], p["prefs"])
        for p in data["pref_projects"]) or "<tr><td colspan=\"3\">No data.</td></tr>"

    pref_stud_rows = "".join(
        "<tr><td data-label=\"Student\">%s</td><td data-label=\"Times ranked by faculty\">%d</td></tr>"
        % (templates.esc(s["display_name"]), s["times_ranked"])
        for s in data["pref_students"]) or "<tr><td colspan=\"2\">No data.</td></tr>"

    fit_section = "<p>No matching run has been recorded yet.</p>"
    run = data["run"]
    if run is not None:
        stats = json.loads(run["stats_json"] or "{}")
        per_project = stats.get("per_project_fit", {})
        pp_rows = "".join(
            "<tr><td data-label=\"Project\">%s</td><td data-label=\"Fit\">%s</td></tr>"
            % (templates.esc((db.get_project(ctx.conn, int(pid)) or {"title": pid})["title"]
                             if db.get_project(ctx.conn, int(pid)) else pid),
               _fmt_pct(fit))
            for pid, fit in per_project.items()) or "<tr><td colspan=\"2\">No per-project fit.</td></tr>"
        matches = db.matches_for_run(ctx.conn, run["id"])
        ps_rows = "".join(
            "<tr><td data-label=\"Student\">%s</td><td data-label=\"Fit\">%s</td></tr>"
            % (templates.esc(_user_label(ctx.conn, m["student_id"])), _fmt_pct(m["student_fit"]))
            for m in matches if m["status"] not in ("rejected", "rematch")
        ) or "<tr><td colspan=\"2\">No matched students.</td></tr>"
        fit_section = (
            "<p>Overall fit (run #%d): <strong>%s</strong></p>"
            "<h3>Per-project fit</h3><table><thead><tr><th>Project</th><th>Fit</th></tr>"
            "</thead><tbody>%s</tbody></table>"
            "<h3>Per-student fit</h3><table><thead><tr><th>Student</th><th>Fit</th></tr>"
            "</thead><tbody>%s</tbody></table>"
        ) % (run["id"], _fmt_pct(run["overall_fit"]), pp_rows, ps_rows)

    body = (
        '<p><a class="button-link" href="/sessions/%d/reports.csv">Download CSV</a></p>'
        '<section aria-labelledby="part-h"><h2 id="part-h">Participants</h2>'
        "<p><strong>Students (%d):</strong> %s</p>"
        "<p><strong>Faculty (%d):</strong> %s</p></section>"
        '<section aria-labelledby="proj-h"><h2 id="proj-h">Projects (%d) &middot; total slots: %d</h2>'
        "<table><thead><tr><th>Project</th><th>Slots</th></tr></thead><tbody>%s</tbody></table></section>"
        '<section aria-labelledby="pp-h"><h2 id="pp-h">Most-preferred projects</h2>'
        "<table><thead><tr><th>Project</th><th>Favorites</th><th>Ranked by students</th></tr></thead>"
        "<tbody>%s</tbody></table></section>"
        '<section aria-labelledby="ps-h"><h2 id="ps-h">Most-preferred students</h2>'
        "<table><thead><tr><th>Student</th><th>Times ranked by faculty</th></tr></thead>"
        "<tbody>%s</tbody></table></section>"
        '<section aria-labelledby="fit-h"><h2 id="fit-h">Fit after matching</h2>%s</section>'
    ) % (
        session["id"], len(data["students"]), student_names,
        len(data["faculty"]), faculty_names,
        len(data["projects"]), data["total_slots"], proj_rows,
        pref_proj_rows, pref_stud_rows, fit_section,
    )
    return html_response(templates.layout(
        "Reports", templates.page("Reports for %s" % templates.esc(session["name"]), body), ctx.user))


@route("GET", "/sessions/{id}/reports.csv")
def session_reports_csv(ctx):
    guard = require_role(ctx, "admin", "manager")
    if guard:
        return guard
    session, err = _session_or_404(ctx)
    if err:
        return err
    if not db.can_manage_session(ctx.conn, session, ctx.user):
        return forbidden("You do not manage this session.")
    data = _report_rows(ctx.conn, session)

    rows = [["Section", "Item", "Value"]]
    rows.append(["summary", "session", session["name"]])
    rows.append(["summary", "student_participants", len(data["students"])])
    rows.append(["summary", "faculty_participants", len(data["faculty"])])
    rows.append(["summary", "projects", len(data["projects"])])
    rows.append(["summary", "total_slots", data["total_slots"]])
    for s in data["students"]:
        rows.append(["student", "%s %s" % (s["given_name"], s["family_name"]), s["email"]])
    for f in data["faculty"]:
        rows.append(["faculty", f["display_name"], f["email"]])
    for p in data["projects"]:
        rows.append(["project", p["title"], p["positions"] or 0])
    for p in data["pref_projects"]:
        rows.append(["most_preferred_project", p["title"], p["favorites"]])
    for s in data["pref_students"]:
        rows.append(["most_preferred_student", s["display_name"], s["times_ranked"]])
    run = data["run"]
    if run is not None:
        rows.append(["fit", "overall_fit", run["overall_fit"]])
        for m in db.matches_for_run(ctx.conn, run["id"]):
            if m["status"] in ("rejected", "rematch"):
                continue
            rows.append(["student_fit", _user_label(ctx.conn, m["student_id"]), m["student_fit"]])

    payload = export_service.csv(rows)
    filename = "session-%d-report.csv" % session["id"]
    resp = Response(status=200, body=payload, content_type="text/csv; charset=utf-8")
    resp.add_header("Content-Disposition", 'attachment; filename="%s"' % filename)
    return resp


@route("GET", "/admin/sessions")
def admin_sessions(ctx):
    """Cross-session status & trends (R10.4). Admin sees all; manager sees own."""
    guard = require_role(ctx, "admin", "manager")
    if guard:
        return guard
    sessions = db.list_sessions_for_user(ctx.conn, ctx.user)
    rows = []
    for s in sessions:
        students = len(db.session_student_participants(ctx.conn, s["id"]))
        projects = len(db.list_projects(ctx.conn, s["id"]))
        run = db.latest_run(ctx.conn, s["id"])
        fit = _fmt_pct(run["overall_fit"]) if run else "n/a"
        rows.append(
            "<tr><td data-label=\"Session\"><a href=\"/sessions/%d\">%s</a></td>"
            "<td data-label=\"Phase\">%s</td><td data-label=\"Mode\">%s</td>"
            "<td data-label=\"Students\">%d</td><td data-label=\"Projects\">%d</td>"
            "<td data-label=\"Overall fit\">%s</td>"
            "<td data-label=\"Reports\"><a href=\"/sessions/%d/reports\">Reports</a></td></tr>"
            % (s["id"], templates.esc(s["name"]),
               templates.esc(PHASE_LABELS.get(s["status"], s["status"])),
               templates.esc(s["mode"]), students, projects, fit, s["id"]))
    table = ("<table><thead><tr><th>Session</th><th>Phase</th><th>Mode</th>"
             "<th>Students</th><th>Projects</th><th>Overall fit</th><th></th></tr></thead>"
             "<tbody>%s</tbody></table>" % "".join(rows)) if rows else "<p>No sessions visible.</p>"
    return html_response(templates.layout(
        "Cross-session status", templates.page("Cross-session status & trends", table), ctx.user))


# ---------------------------------------------------------------------------
# Project export: HTML / print-to-PDF / batch (R3.14)
# ---------------------------------------------------------------------------

def _load_viewable_project(ctx, pid):
    """Return (project, session, None) if viewable, else (None, None, resp)."""
    project = db.get_project(ctx.conn, pid) if pid else None
    if project is None:
        return None, None, not_found("Project not found.")
    session = db.get_session(ctx.conn, project["session_id"])
    if not db.can_view_session(ctx.conn, session, ctx.user):
        return None, None, forbidden("You do not have access to this project.")
    # Draft projects are only viewable by their editors / managers.
    if project["status"] != "published" and not _can_edit_project(ctx, project):
        return None, None, forbidden("This project is not available.")
    return project, session, None


def _department_name(conn, project):
    dept_id = project["primary_department_id"]
    if not dept_id:
        return None
    row = conn.execute("SELECT name FROM departments WHERE id = ?", (dept_id,)).fetchone()
    return row["name"] if row else None


@route("GET", "/projects/{id}/export.html")
def project_export_html(ctx):
    guard = require_login(ctx)
    if guard:
        return guard
    pid = fint_param(ctx, "id")
    project, _session, resp = _load_viewable_project(ctx, pid)
    if resp:
        return resp
    mentors = db.project_mentors(ctx.conn, project["id"])
    dept = _department_name(ctx.conn, project)
    html = export_service.project_html(project, mentors=mentors, department=dept)
    return Response(status=200, body=html)


@route("GET", "/projects/{id}/export.pdf")
def project_export_pdf(ctx):
    guard = require_login(ctx)
    if guard:
        return guard
    pid = fint_param(ctx, "id")
    project, _session, resp = _load_viewable_project(ctx, pid)
    if resp:
        return resp
    mentors = db.project_mentors(ctx.conn, project["id"])
    dept = _department_name(ctx.conn, project)
    # Served as HTML for the browser to print to PDF (no PDF lib offline).
    html = export_service.project_pdf(project, mentors=mentors, department=dept)
    return Response(status=200, body=html)


@route("GET", "/projects/export")
def project_export_batch(ctx):
    """Batch export for a faculty with multiple projects: ?ids=1,2 or all mine."""
    guard = require_login(ctx)
    if guard:
        return guard
    ids_raw = fv(ctx.query, "ids")
    wanted = [int(x) for x in ids_raw.split(",") if x.strip().isdigit()] if ids_raw else None
    sections = []
    exported = 0
    for pid in (wanted or _my_project_ids(ctx)):
        project, _session, resp = _load_viewable_project(ctx, pid)
        if resp:
            continue
        if not _can_edit_project(ctx, project):
            continue
        mentors = db.project_mentors(ctx.conn, project["id"])
        dept = _department_name(ctx.conn, project)
        inner = export_service._project_body(project, mentors=mentors, department=dept)
        sections.append('<article class="export-card">%s</article>' % inner)
        exported += 1
    if exported == 0:
        return not_found("No projects available to export.")
    body = (
        '<p class="no-print"><button onclick="window.print()">Print / Save as PDF</button></p>'
        "%s" % "".join(sections))
    return html_response(templates.layout(
        "Batch project export", templates.page("Batch project export (%d)" % exported, body), ctx.user))


def _my_project_ids(ctx):
    """Project ids the current user mentors, across all sessions they can see."""
    ids = []
    for session in db.list_sessions(ctx.conn):
        if not db.can_view_session(ctx.conn, session, ctx.user):
            continue
        for p in db.list_projects(ctx.conn, session["id"]):
            if db.is_project_mentor(ctx.conn, p["id"], ctx.user["id"]):
                ids.append(p["id"])
    return ids


# ---------------------------------------------------------------------------
# Calendar reminders ICS (R9.2)
# ---------------------------------------------------------------------------

def _session_reminder_events(session):
    """Build ICS event dicts from a session's per-phase deadlines."""
    events = []
    for key, col in DEADLINE_COLUMNS.items():
        iso = session[col]
        if not iso:
            continue
        try:
            start = datetime.fromisoformat(iso)
        except ValueError:
            continue
        label = key.replace("_", " ").title()
        events.append({
            "uid": "spark-session-%d-%s@spark" % (session["id"], key),
            "start": start,
            "summary": "%s deadline: %s" % (label, session["name"]),
            "description": "SPARK %s deadline for session '%s'." % (label, session["name"]),
        })
    return events


@route("GET", "/reminders.ics")
def reminders_ics(ctx):
    """Opt-in download of per-phase deadline reminders for a session."""
    guard = require_login(ctx)
    if guard:
        return guard
    sid = fint(ctx.query, "session_id")
    session = db.get_session(ctx.conn, sid) if sid else None
    if session is None:
        return not_found("Session not found.")
    if not db.can_view_session(ctx.conn, session, ctx.user):
        return forbidden("You do not have access to this session.")
    events = _session_reminder_events(session)
    payload = ics_service.build_ics(events)
    resp = Response(status=200, body=payload, content_type="text/calendar; charset=utf-8")
    resp.add_header("Content-Disposition",
                    'attachment; filename="spark-session-%d-reminders.ics"' % session["id"])
    return resp


# ---------------------------------------------------------------------------
# CyHire forward (R11.1)
# ---------------------------------------------------------------------------

@route("POST", "/projects/{id}/cyhire")
def project_cyhire_forward(ctx):
    """Forward an unfilled opening to CyHire. Allowed only when the session has
    ended (closed) and the project still has unfilled openings."""
    guard = require_role(ctx, "faculty", "admin", "manager")
    if guard:
        return guard
    csrf_err = check_csrf(ctx)
    if csrf_err:
        return csrf_err
    pid = fint_param(ctx, "id")
    project = db.get_project(ctx.conn, pid) if pid else None
    if project is None:
        return not_found("Project not found.")
    session = db.get_session(ctx.conn, project["session_id"])
    if not (_can_edit_project(ctx, project) or db.can_manage_session(ctx.conn, session, ctx.user)):
        return forbidden("You cannot forward this project.")
    if session["status"] != "closed":
        return forbidden("CyHire forwarding is available only after the session has ended.")
    openings = _remaining_capacity(ctx.conn, session["id"], project)
    if openings <= 0:
        return forbidden("This project has no unfilled openings to forward.")
    cyhire_service.forward(ctx.conn, project, openings=openings)
    ctx.conn.commit()
    return redirect("/projects/%d" % project["id"])


# ---------------------------------------------------------------------------
# HTTP handler (middleware lives here)
# ---------------------------------------------------------------------------

class SparkHandler(BaseHTTPRequestHandler):
    server_version = "SPARK/0.1"

    def log_message(self, fmt, *args):
        # Quieter logging to stderr.
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # -- static files --------------------------------------------------------
    def _serve_static(self, path):
        rel = path[len("/static/"):]
        # Prevent path traversal: resolve and confirm containment.
        full = os.path.normpath(os.path.join(STATIC_DIR, rel))
        if not full.startswith(STATIC_DIR + os.sep):
            return self._send(not_found("Asset not found."))
        if not os.path.isfile(full):
            return self._send(not_found("Asset not found."))
        ext = os.path.splitext(full)[1].lower()
        ctype = STATIC_TYPES.get(ext)
        if ctype is None:
            return self._send(forbidden("Unsupported asset type."))
        with open(full, "rb") as fh:
            data = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    # -- request plumbing ----------------------------------------------------
    def _load_user(self, conn):
        """Resolve the current user from the signed cookie. Returns (user, auth_session).

        Blocked users are rejected here in middleware (R1.6): their session is
        destroyed and they are treated as logged out.
        """
        cookie_header = self.headers.get("Cookie")
        if not cookie_header:
            return None, None
        jar = SimpleCookie()
        try:
            jar.load(cookie_header)
        except Exception:
            return None, None
        morsel = jar.get(COOKIE_NAME)
        if morsel is None:
            return None, None
        token = read_cookie_value(morsel.value)
        if token is None:
            return None, None
        auth_session = db.get_auth_session(conn, token)
        if auth_session is None:
            return None, None
        user_row = db.get_user_by_id(conn, auth_session["user_id"])
        if user_row is None:
            db.delete_auth_session(conn, token)
            return None, None
        if user_row["is_blocked"]:
            db.delete_auth_session(conn, token)
            return None, auth_session
        db.touch_auth_session(conn, token)
        # Augment user with the session CSRF token for templates/handlers.
        user = dict(user_row)
        user["csrf_token"] = auth_session["csrf_token"]
        return _RowLike(user), auth_session

    def _read_form(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8", "replace")
        return parse_qs(raw, keep_blank_values=True)

    def _dispatch(self, method):
        parsed = urlparse(self.path)
        path = parsed.path
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")

        if method == "GET" and path.startswith("/static/"):
            return self._serve_static(path)

        conn = db.connect()
        try:
            user, auth_session = self._load_user(conn)
            blocked_notice = (user is None and auth_session is not None)

            handler, params = ROUTER.match(method, path)
            if handler is None:
                return self._send(not_found("We could not find that page."))
            if handler == "405":
                resp = Response(405, templates.layout(
                    "Not allowed", templates.error_page(405, "Method Not Allowed", "That method is not allowed here.")))
                resp.add_header("Allow", "GET, POST")
                return self._send(resp)

            query = parse_qs(parsed.query, keep_blank_values=True)
            form = self._read_form() if method == "POST" else {}
            ctx = Context(self, params, query, form, conn, user, auth_session)

            try:
                resp = handler(ctx)
            except Exception:  # noqa: BLE001 - convert to 500 page
                import traceback
                traceback.print_exc()
                resp = Response(500, templates.layout(
                    "Server error",
                    templates.error_page(500, "Server Error", "Something went wrong on our end.")))

            if blocked_notice:
                resp.set_cookie(COOKIE_NAME, "", max_age=0)
                # Re-render a blocked notice on the landing page if we are there.
            return self._send(resp)
        finally:
            conn.close()

    def _send(self, resp):
        if resp is None:
            return
        body = resp.body.encode("utf-8") if isinstance(resp.body, str) else resp.body
        self.send_response(resp.status)
        self.send_header("Content-Type", resp.content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        for key, value in resp.headers:
            self.send_header(key, value)
        for cookie in resp.cookies:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")


class _RowLike(dict):
    """dict that also supports sqlite3.Row-style __getitem__ and .keys()."""
    # dict already supports both; this subclass is a clear marker + keys().


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def make_server(port=8000, host="0.0.0.0"):
    db.init_db()
    return ThreadingHTTPServer((host, port), SparkHandler)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    port = int(os.environ.get("SPARK_PORT", "8000"))
    if argv:
        try:
            port = int(argv[0])
        except ValueError:
            pass
    httpd = make_server(port=port)
    sys.stderr.write("SPARK serving on http://localhost:%d (Ctrl-C to stop)\n" % port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("\nShutting down.\n")
        httpd.shutdown()


if __name__ == "__main__":
    main()
