"""Project-level customisable status workflow.

The workflow is stored in the project's _meta.yaml under the ``workflow`` key.
When absent the built-in defaults are used (free-form transitions).
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

# All transitions are allowed by default (permissive mode).
# When a custom workflow is defined, only explicit transitions are valid.
DEFAULT_TRANSITIONS: dict[str, list[str]] = {s: list(DEFAULT_STATES) for s in DEFAULT_STATES}

VC_STATES = ["pending", "in_progress", "passed", "failed"]


def get_workflow(meta: dict) -> dict:
    """Return the merged workflow config for a project.

    Returns ``{"states": [...], "transitions": {...}, "default": "proposed"}``.
    """
    wf = meta.get("workflow")
    if not wf or not isinstance(wf, dict):
        return {
            "states": list(DEFAULT_STATES),
            "transitions": {k: list(v) for k, v in DEFAULT_TRANSITIONS.items()},
            "default": "proposed",
        }
    states = wf.get("states") or list(DEFAULT_STATES)
    transitions = wf.get("transitions") or {k: list(v) for k, v in DEFAULT_TRANSITIONS.items()}
    return {
        "states": states,
        "transitions": {k: list(v) for k, v in transitions.items()},
        "default": wf.get("default", states[0] if states else "proposed"),
    }


def validate_transition(meta: dict, current_status: str, new_status: str) -> Optional[str]:
    """Check if a status change is allowed. Returns an error message or None if valid."""
    if current_status == new_status:
        return None
    wf = get_workflow(meta)
    # If no custom workflow is defined (or transitions are permissive), allow everything.
    if "workflow" not in meta or not isinstance(meta.get("workflow"), dict):
        return None
    allowed = wf["transitions"].get(current_status, [])
    if new_status not in allowed:
        allowed_str = ", ".join(allowed) if allowed else "terminal"
        return f"Transition from '{current_status}' to '{new_status}' is not allowed. Valid next states: {allowed_str}"
    return None
