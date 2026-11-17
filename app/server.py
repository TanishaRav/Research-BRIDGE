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

from app import db
from app import templates

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
