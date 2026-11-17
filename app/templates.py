"""Tiny string-template HTML helper (no Jinja).

Renders a page shell with semantic landmarks (<header><nav><main>), exactly
one <h1> per page, and escapes all user-supplied text via html.escape. Keep
markup minimal and accessible; later features extend components here.
"""

import html


def esc(value):
    """Escape user text for safe HTML output. None renders as empty string."""
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _nav(user):
    """Role-aware primary navigation. `user` is a sqlite3.Row or None."""
    links = ['<a href="/">Home</a>']
    if user is None:
        links.append('<a href="/login">Log in</a>')
        links.append('<a href="/register">Register</a>')
    else:
        role = user["role"]
        if role in ("admin", "manager"):
            links.append('<a href="/sessions">Sessions</a>')
        if role == "faculty":
            links.append('<a href="/sessions">My projects</a>')
        if role == "student":
            links.append('<a href="/sessions">Browse sessions</a>')
        name = esc(user["display_name"])
        links.append(
            '<form method="post" action="/logout" class="nav-logout">'
            '<input type="hidden" name="csrf_token" value="%s">'
            '<button type="submit">Log out</button></form>'
            % esc(user["csrf_token"] if "csrf_token" in user.keys() else "")
        )
        items = "".join('<li>%s</li>' % l for l in links)
        return (
            '<nav aria-label="Primary">'
            '<span class="nav-user">Signed in as %s (%s)</span>'
            '<ul>%s</ul></nav>' % (name, esc(role), items)
        )
    items = "".join('<li>%s</li>' % l for l in links)
    return '<nav aria-label="Primary"><ul>%s</ul></nav>' % items


def layout(title, body, user=None, flash=None):
    """Render a complete HTML document.

    title: page title (also drives the single <h1> unless body supplies one).
    body:  pre-escaped HTML string for <main>.
    user:  current user Row or None (drives nav).
    flash: optional notice message (plain text, escaped here).
    """
    flash_html = ""
    if flash:
        flash_html = '<p class="flash" role="status">%s</p>' % esc(flash)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>%s &middot; SPARK</title>\n"
        '<link rel="stylesheet" href="/static/spark.css">\n'
        "</head>\n<body>\n"
        '<a class="skip-link" href="#main">Skip to main content</a>\n'
        '<header><p class="brand"><a href="/">SPARK</a></p>'
        "<p class=\"tagline\">Student-Project Alignment for Research Knowledge</p></header>\n"
        "%s\n"
        '<main id="main">\n%s%s\n</main>\n'
        '<script src="/static/spark.js"></script>\n'
        "</body>\n</html>\n"
    ) % (esc(title), _nav(user), flash_html, body)


def page(title, inner_html):
    """Wrap inner HTML with a single <h1> heading for the page body."""
    return "<h1>%s</h1>\n%s" % (esc(title), inner_html)


def field(label, name, type_="text", value="", required=False, autocomplete=None):
    """Render a labelled form input (label associated via id)."""
    req = " required" if required else ""
    ac = ' autocomplete="%s"' % esc(autocomplete) if autocomplete else ""
    return (
        '<p class="field"><label for="f-%s">%s</label>'
        '<input id="f-%s" name="%s" type="%s" value="%s"%s%s></p>'
        % (esc(name), esc(label), esc(name), esc(name), esc(type_),
           esc(value), req, ac)
    )


def csrf_input(csrf_token):
    """Hidden CSRF field for mutating forms."""
    return '<input type="hidden" name="csrf_token" value="%s">' % esc(csrf_token)


def error_page(status, title, message):
    """Standalone error page body (used for 404/500)."""
    return page("%s %s" % (status, title), '<p class="error">%s</p>' % esc(message))


def textarea(label, name, value="", max_words=None, rows=4, required=False, hint=None):
    """Labelled textarea with optional word-count cap and spellcheck (R3.5)."""
    wc = ' data-wordcount="%s"' % int(max_words) if max_words else ""
    req = " required" if required else ""
    hint_html = '<span class="hint">%s</span>' % esc(hint) if hint else ""
    return (
        '<p class="field"><label for="f-%s">%s</label>%s'
        '<textarea id="f-%s" name="%s" rows="%d" spellcheck="true"%s%s>%s</textarea></p>'
        % (esc(name), esc(label), hint_html, esc(name), esc(name), int(rows),
           wc, req, esc(value))
    )


def field_error(message):
    """Inline field-level error message (R3.10, R4.6)."""
    if not message:
        return ""
    return '<span class="field-error" role="alert">%s</span>' % esc(message)


def tz_label(iso_value, tz_name):
    """Render an ISO-8601 timestamp with an explicit timezone label (R13.3).

    `iso_value` is a stored ISO string (may carry an offset) or empty; `tz_name`
    is the session's IANA zone. Falls back gracefully if parsing fails.
    """
    from datetime import datetime
    try:
        from zoneinfo import ZoneInfo
    except Exception:  # pragma: no cover - zoneinfo always present on 3.11
        ZoneInfo = None
    if not iso_value:
        return '<span class="muted">not set</span>'
    try:
        dt = datetime.fromisoformat(iso_value)
        if ZoneInfo is not None and tz_name:
            try:
                dt = dt.astimezone(ZoneInfo(tz_name))
            except Exception:
                pass
        label = dt.strftime("%Y-%m-%d %H:%M")
        zone = tz_name or (dt.tzname() or "UTC")
        return "%s <span class=\"tz\">(%s)</span>" % (esc(label), esc(zone))
    except Exception:
        return "%s <span class=\"tz\">(%s)</span>" % (esc(iso_value), esc(tz_name or "UTC"))
