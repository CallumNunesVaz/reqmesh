"""Server-side sanitisation of rich-text (TipTap) HTML.

Descriptions are stored as HTML. The editor cleans content client-side, but the
API accepts a plain ``str``, so anything can be written by calling
``PUT /requirements/{id}`` directly — and the published HTML report interpolated
that value raw. This module is the server-side counterpart to the frontend's
read-only renderer (``frontend/src/components/autoLink.tsx``) and deliberately
mirrors its allowlist so both surfaces agree on what rich text may contain.

Approach is allowlist-only, built on the standard library so no new dependency
is pinned:

* tags not on the allowlist are **unwrapped** — their text survives, the tag
  does not (matching the frontend);
* ``script``/``style``/``iframe``/``object``/``embed``/``svg``/``math`` are
  dropped *with their contents*, since their bodies aren't prose;
* every attribute is dropped, except ``src`` on ``<img>`` and only when it is a
  ``data:image/...`` URI. That keeps embedded images working while removing the
  ``file://`` / ``http://`` fetches that WeasyPrint would otherwise perform
  server-side during PDF export;
* text is re-escaped on the way out, so no markup can survive by accident.
"""

from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser

# Mirrors ALLOWED_TAGS in frontend/src/components/autoLink.tsx, plus <br> and
# the restricted <img> handled below.
ALLOWED_TAGS = frozenset({
    "p", "strong", "em", "b", "i", "u", "s", "ul", "ol", "li",
    "h1", "h2", "h3", "code", "pre", "blockquote", "br", "img",
})

# Elements whose *content* must go too — it isn't prose.
DROP_WITH_CONTENT = frozenset({
    "script", "style", "iframe", "object", "embed", "svg", "math", "template",
})

VOID_TAGS = frozenset({"br", "img"})

_DATA_IMAGE = re.compile(r"^data:image/(png|jpeg|jpg|gif|webp);base64,[A-Za-z0-9+/=\s]+$", re.I)


class _Sanitiser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._out: list[str] = []
        self._open: list[str] = []      # allowlisted tags awaiting a close
        self._suppress = 0              # depth inside a drop-with-content element

    # -- helpers ----------------------------------------------------------
    def _img_src(self, attrs) -> str | None:
        for name, value in attrs:
            if name.lower() == "src" and value and _DATA_IMAGE.match(value.strip()):
                return value.strip()
        return None

    # -- parser callbacks -------------------------------------------------
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in DROP_WITH_CONTENT:
            self._suppress += 1
            return
        if self._suppress:
            return
        if tag not in ALLOWED_TAGS:
            return  # unwrap: emit nothing, children still render
        if tag == "img":
            src = self._img_src(attrs)
            if src:
                self._out.append(f'<img src="{escape(src, quote=True)}" />')
            return  # a remote/file-backed image is dropped entirely
        if tag == "br":
            self._out.append("<br />")
            return
        self._out.append(f"<{tag}>")
        self._open.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in DROP_WITH_CONTENT:
            self._suppress = max(0, self._suppress - 1)
            return
        if self._suppress or tag in VOID_TAGS or tag not in ALLOWED_TAGS:
            return
        # Close back to the matching open tag so malformed nesting can't leak
        # an unbalanced document into the report.
        if tag in self._open:
            while self._open:
                open_tag = self._open.pop()
                self._out.append(f"</{open_tag}>")
                if open_tag == tag:
                    break

    def handle_data(self, data):
        if self._suppress:
            return
        self._out.append(escape(data, quote=False))

    def result(self) -> str:
        while self._open:
            self._out.append(f"</{self._open.pop()}>")
        return "".join(self._out)


def safe_url_fetcher(extra_allowed: "set[str] | None" = None):
    """A WeasyPrint ``url_fetcher`` that refuses to reach off-box.

    WeasyPrint's default fetcher registers ``file://``, ``http://``, ``https://``
    and ``ftp://`` handlers, so any ``<img src=...>`` reaching the renderer is
    fetched *server-side* while producing the PDF — a local-file read and an
    SSRF primitive against internal addresses, returned to the caller inside the
    document.

    ``data:`` URIs are always allowed (they're inline bytes, no network).
    ``extra_allowed`` holds exact URLs that are operator-configured rather than
    user-supplied — in practice the report logo — so that feature keeps working
    without reopening arbitrary fetches.
    """
    from weasyprint.urls import URLFetcher

    allowed = {u for u in (extra_allowed or set()) if u}
    # Only the schemes actually needed: data, plus whatever the operator's
    # allowlisted URLs use. Redirects are refused so an allowlisted host can't
    # bounce the fetch to an internal address.
    protocols = {"data"} | {u.split(":", 1)[0].lower() for u in allowed if ":" in u}
    delegate = URLFetcher(allowed_protocols=tuple(sorted(protocols)), allow_redirects=False)

    def fetcher(url: str, *args, **kwargs):
        if url.startswith("data:") or url in allowed:
            return delegate(url)
        raise ValueError(f"Blocked non-local resource in document: {url[:80]}")

    return fetcher


def sanitize_html(value: str | None) -> str:
    """Return ``value`` reduced to the allowlisted rich-text subset.

    Safe to call repeatedly — sanitising already-clean content is a no-op.
    """
    if not value:
        return ""
    if not isinstance(value, str):
        return ""
    parser = _Sanitiser()
    try:
        parser.feed(value)
        parser.close()
    except Exception:
        # Never let malformed markup take down a write or an export; fall back
        # to the text-only reading of the input.
        return escape(re.sub(r"<[^>]*>", "", value), quote=False)
    return parser.result()
