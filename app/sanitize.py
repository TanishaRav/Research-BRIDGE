"""HTML sanitization and small text helpers (R3.5, R3.4, R13.3).

`sanitize_html` reduces rich project descriptions to a strict allowlist so that
stored markup can be rendered without escaping while still being XSS-safe:
bold/italic, bullet and numbered lists, links, and up to two embedded images
or videos. Everything else (notably <script>, <style>, event handlers, and
javascript: URLs) is stripped. Bare URLs in text are auto-linked (R3.5).

Stdlib only: uses html.parser.HTMLParser.
"""

import html
import re
from html.parser import HTMLParser

# Tags kept in output. Attributes are filtered per-tag below.
_ALLOWED_TAGS = {
    "b", "strong", "i", "em", "u",
    "p", "br",
    "ul", "ol", "li",
    "a", "img",
    "video", "source",
}

# Per-tag allowed attributes.
_ALLOWED_ATTRS = {
    "a": {"href", "title"},
    "img": {"src", "alt"},
    "video": {"src", "controls", "width", "height"},
    "source": {"src", "type"},
}

_VOID_TAGS = {"br", "img", "source"}

# Tags whose entire content is dropped (not just the tag).
_DROP_CONTENT_TAGS = {"script", "style"}

# Cap on embedded media (R3.5): up to 2 images/videos combined.
_MAX_MEDIA = 2

_URL_RE = re.compile(r"(https?://[^\s<>\"']+)")


def _safe_url(value):
    """Return the URL if its scheme is safe, else empty string."""
    if value is None:
        return ""
    v = value.strip()
    low = v.lower()
    # Block javascript:, data:, vbscript: and protocol-relative tricks.
    if low.startswith(("javascript:", "data:", "vbscript:")):
        return ""
    # Allow http(s), mailto, and site-relative/anchor links.
    if low.startswith(("http://", "https://", "mailto:", "/", "#")):
        return v
    # Reject anything else with a scheme-like prefix.
    if ":" in low.split("/", 1)[0]:
        return ""
    return v


class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self._skip_depth = 0
        self._media = 0
        self._in_anchor = 0

    def handle_starttag(self, tag, attrs):
        if tag in _DROP_CONTENT_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag not in _ALLOWED_TAGS:
            return
        if tag in ("img", "video"):
            if self._media >= _MAX_MEDIA:
                return
            self._media += 1
        if tag == "a":
            self._in_anchor += 1
        kept = []
        allowed = _ALLOWED_ATTRS.get(tag, set())
        for name, value in attrs:
            if name not in allowed:
                continue
            if name in ("href", "src"):
                value = _safe_url(value)
                if not value:
                    continue
            kept.append((name, value))
        attr_str = "".join(
            ' %s="%s"' % (n, html.escape(v or "", quote=True)) for n, v in kept
        )
        if tag in _VOID_TAGS:
            self.out.append("<%s%s>" % (tag, attr_str))
        else:
            self.out.append("<%s%s>" % (tag, attr_str))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in _DROP_CONTENT_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag not in _ALLOWED_TAGS or tag in _VOID_TAGS:
            return
        if tag == "a" and self._in_anchor:
            self._in_anchor -= 1
        self.out.append("</%s>" % tag)

    def handle_data(self, data):
        if self._skip_depth:
            return
        # Do not auto-link inside an existing <a>, to avoid nested links.
        if self._in_anchor:
            self.out.append(html.escape(data, quote=False))
        else:
            self.out.append(_autolink_text(data))

    def result(self):
        return "".join(self.out)


def sanitize_html(raw):
    """Return XSS-safe HTML limited to the allowlist. None -> ''."""
    if not raw:
        return ""
    parser = _Sanitizer()
    parser.feed(raw)
    parser.close()
    return parser.result()


def _autolink_text(text):
    """Escape a text node and turn bare http(s) URLs into links (R3.5)."""
    parts = []
    last = 0
    for m in _URL_RE.finditer(text):
        parts.append(html.escape(text[last:m.start()], quote=False))
        url = m.group(1)
        safe = _safe_url(url)
        esc = html.escape(url, quote=True)
        if safe:
            parts.append('<a href="%s" rel="nofollow noopener">%s</a>' % (esc, esc))
        else:
            parts.append(esc)
        last = m.end()
    parts.append(html.escape(text[last:], quote=False))
    return "".join(parts)


def autolink(text):
    """Escape plain text and turn bare http(s) URLs into links (R3.5)."""
    if not text:
        return ""
    return _autolink_text(text)


def word_count(text):
    """Count whitespace-delimited words in `text`."""
    if not text:
        return 0
    return len([w for w in text.strip().split() if w])
