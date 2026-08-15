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
# point of use, so this is the whole of the stored-XSS surface. The risk FMECA
# fields join `description` here because the UI edits them with the same rich
# text editor that writes HTML.
_HTML_FIELDS = ("description", "rationale", "failure_mode", "effect", "cause")


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


def _validate_specification(item: dict) -> None:
    # `url` is rendered as an anchor, so a `javascript:` value stored by any
    # route other than the API is stored XSS. Blanked rather than withheld: the
    # specification is still perfectly usable without its link, whereas dropping
    # the item would break every requirement tracing to it.
    from app.services.sanitize import is_safe_external_url

    url = item.get("url")
    if url is not None and not (isinstance(url, str) and is_safe_external_url(url)):
        item["url"] = ""


def _validate_risk(item: dict) -> None:
    """Read-side FMECA fallback for risks predating the failure-mode split.

    Migration 3 rewrites these on disk, but — like ``_validate_comment`` — it
    cannot be relied on alone: a data root that predates the framework is
    stamped at the current schema without anything running, and a risk file
    that failed to migrate is left at the old shape on purpose. A risk written
    before the split therefore arrives here with ``description`` and no
    ``failure_mode``; reading the failure mode from the description keeps every
    consumer seeing the same content the register always showed.
    """
    if not item.get("failure_mode") and item.get("description"):
        item["failure_mode"] = item["description"]


def _validate_comment(item: dict) -> None:
    """Coerce a pre-schema-2 comment to ``entity_kind``/``entity_id``.

    Migration 2 rewrites these on disk, but it cannot be relied on alone: a data
    root that predates the migration framework is stamped at the current schema
    without anything running, and a comment file that failed to migrate is left
    at the old shape on purpose. Doing it here as well means the API never
    serves a comment with no target, whichever of those happened — the same
    "disk is not a trusted input" reasoning as the sanitiser above.
    """
    if item.get("entity_id"):
        return
    req_id = item.pop("requirement_id", "")
    if req_id:
        item["entity_kind"] = "requirements"
        item["entity_id"] = str(req_id)


_SPECIFIC = {
    "requirements": _validate_requirement,
    "specifications": _validate_specification,
    "comments": _validate_comment,
    "risks": _validate_risk,
}
