"""iCalendar (.ics) builder for phase-deadline reminders (R9.2).

Stdlib only. Produces a valid VCALENDAR with one VEVENT per reminder, using
CRLF line endings as required by RFC 5545. Each event carries a stable UID,
a DTSTAMP, a DTSTART (UTC), and a SUMMARY. Long lines are folded at 75 octets.
"""

from datetime import datetime, timezone

PRODID = "-//SPARK//Research Match Reminders//EN"


def _to_utc(dt):
    """Return a timezone-aware datetime in UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _fmt_utc(dt):
    """RFC 5545 UTC timestamp: YYYYMMDDTHHMMSSZ."""
    return _to_utc(dt).strftime("%Y%m%dT%H%M%SZ")


def _escape_text(value):
    """Escape a TEXT value per RFC 5545 (backslash, comma, semicolon, newline)."""
    s = "" if value is None else str(value)
    s = s.replace("\\", "\\\\").replace("\n", "\\n")
    s = s.replace(",", "\\,").replace(";", "\\;")
    return s


def _fold(line):
    """Fold a content line to <=75 octets, continuation lines start with a space."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    chunks = []
    start = 0
    limit = 75
    while start < len(raw):
        chunk = raw[start:start + limit]
        chunks.append(chunk)
        start += limit
        limit = 74  # continuation lines lose one octet to the leading space
    out = chunks[0].decode("utf-8", "ignore")
    for c in chunks[1:]:
        out += "\r\n " + c.decode("utf-8", "ignore")
    return out


def build_ics(events):
    """Build an .ics byte string from a list of event dicts.

    Each event dict supports:
      - uid:     stable unique id (required-ish; a fallback is generated)
      - start:   datetime (naive treated as UTC) -> DTSTART
      - summary: text -> SUMMARY
      - description: optional text -> DESCRIPTION
      - dtstamp: optional datetime; defaults to now (UTC)

    Returns UTF-8 bytes with CRLF line endings, ready to serve as
    ``text/calendar``.
    """
    now = datetime.now(timezone.utc)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:" + PRODID,
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for idx, ev in enumerate(events):
        start = ev.get("start")
        if start is None:
            continue
        uid = ev.get("uid") or ("spark-%d-%s@spark" % (idx, _fmt_utc(start)))
        dtstamp = ev.get("dtstamp") or now
        lines.append("BEGIN:VEVENT")
        lines.append("UID:" + _escape_text(uid))
        lines.append("DTSTAMP:" + _fmt_utc(dtstamp))
        lines.append("DTSTART:" + _fmt_utc(start))
        lines.append("SUMMARY:" + _escape_text(ev.get("summary", "Reminder")))
        if ev.get("description"):
            lines.append("DESCRIPTION:" + _escape_text(ev["description"]))
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    folded = [_fold(line) for line in lines]
    return ("\r\n".join(folded) + "\r\n").encode("utf-8")
