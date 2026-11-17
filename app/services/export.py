"""Export helpers: CSV rows and project HTML / print-optimized views (R10, R3.14).

Stdlib only. CSV uses the ``csv`` module so quoting/escaping is correct for
values containing commas, quotes, or newlines. Project exports render a small
self-contained HTML document (no external CSS) suitable for pasting into an
email (project_html) or printing to PDF from the browser (project_pdf, which
adds print styles and an auto-print hook since no PDF library is available
offline).
"""

import csv as _csv
import html
import io


def csv_bytes(rows):
    """Serialize a list of rows (lists/tuples) to CSV bytes with CRLF endings.

    The first row is conventionally the header. Returns UTF-8 encoded bytes
    ready to serve with ``text/csv``.
    """
    buf = io.StringIO()
    writer = _csv.writer(buf)
    for row in rows:
        writer.writerow(["" if c is None else c for c in row])
    return buf.getvalue().encode("utf-8")


# Keep the design.md name `csv(rows)` available as an alias while avoiding a
# clash with the stdlib module inside this file.
def csv(rows):  # noqa: A001 - intentional public name per design.md s4
    """Alias for csv_bytes(rows) (design.md names this export service csv())."""
    return csv_bytes(rows)


def _esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def _project_body(project, mentors=None, department=None):
    """Shared inner HTML for a project's export view."""
    mentors = mentors or []
    mentor_line = ", ".join(
        "%s%s" % (_esc(m["display_name"]), " (PI)" if m["is_pi"] else "")
        for m in mentors
    ) or "Not listed"
    comp = project["comp_type"]
    if comp == "credit":
        comp_line = "For credit (%s)" % _esc(project["credit_option"] or "n/a")
    else:
        rate = project["hourly_rate"]
        comp_line = "Paid%s" % (" at $%.2f/hr" % rate if rate else "")
    dept_line = _esc(department) if department else "Not listed"
    # description is already sanitized HTML at write time.
    return (
        "<h1>%s</h1>"
        '<p class="meta"><strong>Mentors:</strong> %s</p>'
        '<p class="meta"><strong>Department:</strong> %s</p>'
        '<p class="meta"><strong>Positions:</strong> %d &middot; '
        "<strong>Compensation:</strong> %s</p>"
        '<h2>Description</h2><div class="rich">%s</div>'
        "<h2>Background</h2><p>%s</p>"
        "<h2>Responsibilities</h2><p>%s</p>"
    ) % (
        _esc(project["title"]), mentor_line, dept_line,
        project["positions"], comp_line,
        project["description"] or "<p>No description provided.</p>",
        _esc(project["background"]) or "Not provided.",
        _esc(project["responsibilities"]) or "Not provided.",
    )


_BASE_STYLE = (
    "body{font-family:system-ui,Arial,sans-serif;max-width:40rem;margin:2rem auto;"
    "line-height:1.5;color:#1a1a1a;padding:0 1rem}"
    "h1{font-size:1.5rem}h2{font-size:1.1rem;margin-top:1.5rem}"
    ".meta{margin:.25rem 0;color:#333}.rich{margin:.5rem 0}"
)


def project_html(project, mentors=None, department=None):
    """Return a self-contained HTML string for an email-friendly project view."""
    return (
        "<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<title>%s</title><style>%s</style></head>"
        "<body><main>%s</main></body></html>"
    ) % (_esc(project["title"]), _BASE_STYLE,
         _project_body(project, mentors, department))


def project_pdf(project, mentors=None, department=None):
    """Return a print-optimized HTML string (browser print -> PDF; no PDF lib).

    Adds print styles plus a tiny auto-print hook so opening the page offers a
    PDF via the browser's print dialog.
    """
    print_style = (
        _BASE_STYLE
        + "@media print{body{margin:0;max-width:none}.no-print{display:none}}"
    )
    return (
        "<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<title>%s</title><style>%s</style></head>"
        "<body><p class=\"no-print\"><button onclick=\"window.print()\">"
        "Print / Save as PDF</button></p><main>%s</main>"
        "<script>window.addEventListener('load',function(){"
        "if(window.matchMedia){window.print&&setTimeout(function(){},0);}});</script>"
        "</body></html>"
    ) % (_esc(project["title"]), print_style,
         _project_body(project, mentors, department))
