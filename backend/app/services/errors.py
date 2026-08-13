"""The one structured ``detail`` shape for error responses.

An ``HTTPException`` carries its message in ``detail``. There are two allowed
shapes, settled in ``AGENTS.md`` (the "one error shape" rule):

* a plain string — the message, nothing else; and
* an envelope ``{"error": <discriminator>, "message": <str>, ...}`` for errors
  that need to carry structured data (the delete guard's referrer list, a
  validation error's field list).

``error`` is the stable discriminator a client switches on; ``message`` is
always the human-readable text. FastAPI's own request-validation errors are the
one unavoidable exception — they are a list of error objects and we do not
control them.
"""

from __future__ import annotations


def error_envelope(error: str, message: str, **extra) -> dict:
    """Build the structured ``detail`` envelope.

    The single source of truth for the envelope shape, so the delete guard and
    the bulk routes cannot drift apart again.
    """
    return {"error": error, "message": message, **extra}
