"""Validate entity dicts on the way *off disk*.

A project directory is git-tracked and hand-editable by design, so YAML reaches
the store by three routes and only one of them passes the API's validators:

1. the API (validated by the Pydantic models),
2. a developer editing files directly and committing,
3. ``git pull`` from a remote — possibly one somebody else controls.

An invariant enforced only on write is therefore not an invariant. This module
is the read-side counterpart: it runs at the point where the store parses a
collection off disk, so every consumer — the API, the evaluator, the publisher,
search, export — sees the same guaranteed-shaped data.

Two classes of problem are handled differently:

* **Structurally wrong** (a field holding the wrong type, an unknown enum
  value): coerced to a safe default. A merge conflict shouldn't 500 the app.
* **Semantically hostile** (an id that would escape the project directory):
  the item is *withheld entirely* and reported through
  ``YamlStore.corrupt_files`` rather than quietly patched, because an id is an
  identity — silently rewriting one would corrupt every link pointing at it.

Applied at the cache-fill path, so the cost is paid once per directory
generation rather than per request.
"""

from __future__ import annotations

import re

from app.services.sanitize import sanitize_html

# The same grammar as ``core.ids.safe_id``, expressed as a predicate rather
# than a raiser: on the read path a hostile id means "don't serve this file",
# not "return 400 to whoever happened to ask".
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]*$")

# Fields stored as HTML and rendered as HTML. Everything else is escaped at the
# point of use, so this is the whole of the stored-XSS surface.
_HTML_FIELDS = ("description",)


def is_safe_id(value: object) -> bool:
    """True if *value* is usable as an entity id (and so as a filename)."""
    if not isinstance(value, str):
        return False
    value = value.strip()
    return bool(value) and ".." not in value and bool(_ID_RE.match(value))


def id_rejection_reason(value: object) -> str | None:
    """A human-readable reason *value* is unusable as an id, or None."""
    if not isinstance(value, str):
        return f"'id' must be a string, got {type(value).__name__}"
    if not value.strip():
        return "'id' is empty"
    if ".." in value:
        return f"'id' contains '..' (path traversal): {value!r}"
    if not _ID_RE.match(value.strip()):
        return f"'id' has characters that are illegal in a filename: {value!r}"
    return None


def validate_on_load(collection: str, item: dict) -> dict | None:
    """Return *item* made safe to serve, or ``None`` if it must be withheld.

    Mutates and returns the same dict — callers own a fresh parse, and the
    store copies before caching.
    """
    if not is_safe_id(item.get("id")):
        return None

    for field in _HTML_FIELDS:
        value = item.get(field)
        if isinstance(value, str):
            # The parser is the expensive part, so skip it for the common case
            # of a description with no markup at all.
            if "<" in value or "&" in value:
                item[field] = sanitize_html(value)
        elif value is not None:
            item[field] = ""

    specific = _SPECIFIC.get(collection)
    if specific is not None:
        specific(item)
    return item


def _validate_requirement(item: dict) -> None:
    # Imported here rather than at module scope: models.requirement imports the
    # sanitiser, and the store imports this module, so a top-level import would
    # tie the model layer into the store's import graph.
    from app.models.requirement import normalise_requirement_on_load

    normalise_requirement_on_load(item)


_SPECIFIC = {
    "requirements": _validate_requirement,
}
