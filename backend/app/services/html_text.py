"""Shared HTML-to-plain-text conversion.

One implementation for every place that renders requirement text without its
TipTap markup — search snippets and spreadsheet exports. Kept here so the text a
search returns and the text an export writes can never diverge again.
"""

from __future__ import annotations

import re
from html import unescape as html_unescape

_HTML_TAG = re.compile(r"<[^>]*>")


def strip_html(text: str) -> str:
    """Strip tags — each becomes a space — and HTML-unescape the result.

    Replacing a tag with a space rather than nothing keeps ``<p>a</p><p>b</p>``
    as ``a b`` instead of welding it into ``ab``.
    """
    return _HTML_TAG.sub(" ", html_unescape(text or ""))
