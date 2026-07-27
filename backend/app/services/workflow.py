"""Project-level customisable status workflow.

The workflow is stored in the project's _meta.yaml under the ``workflow`` key.
When absent the built-in defaults are used. Transition validation has been
removed — any status may jump to any other status.
"""

from __future__ import annotations

from typing import Optional

DEFAULT_STATES = [
    "proposed",
    "in_review",
    "approved",
    "implemented",
    "verified",
    "rejected",
    "deprecated",
]

# All transitions are always allowed — status changes are never blocked.
DEFAULT_TRANSITIONS: dict[str, list[str]] = {s: list(DEFAULT_STATES) for s in DEFAULT_STATES}

VC_STATES = ["pending", "in_progress", "passed", "failed"]


def get_workflow(meta: dict) -> dict:
    """Return the merged workflow config for a project.

    Returns ``{"states": [...], "transitions": {...}, "default": "proposed"}``.
    Transitions are always fully permissive (every state → every state).
    """
    wf = meta.get("workflow")
    if not wf or not isinstance(wf, dict):
        return _permissive_default()
    states = wf.get("states") or list(DEFAULT_STATES)
    transitions = wf.get("transitions") or {s: list(states) for s in states}
    return {
        "states": states,
        "transitions": {k: list(v) for k, v in transitions.items()},
        "default": wf.get("default", states[0] if states else "proposed"),
    }


def _permissive_default() -> dict:
    states = list(DEFAULT_STATES)
    return {
        "states": states,
        "transitions": {s: list(states) for s in states},
        "default": "proposed",
    }


def validate_transition(meta: dict, current_status: str, new_status: str) -> Optional[str]:
    """Always returns None — all status transitions are permitted."""
    return None
