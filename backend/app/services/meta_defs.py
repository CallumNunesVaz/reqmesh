"""Normalization and serialization of the project's ``_meta.yaml`` definition lists.

``_meta.yaml`` holds three hand-editable, git-versioned lists — ``baselines``,
``system_states`` and ``stakeholders`` — alongside the workflow and other
project settings. These lists are the one place a stored YAML document is not
validated by ``load_guard.validate_on_load`` (that runs only on the
per-collection read path), so the read side here degrades malformed entries and
sanitises rich text, and the write side drops the derived ``order`` field so a
hand-edited file cannot express a sequence that disagrees with itself.
"""

from __future__ import annotations

from app.models.baseline import DUE_DATE_RE
from app.services.sanitize import sanitize_html


def normalize_baseline_defs(baselines: list) -> list[dict]:
    """Normalize baseline definitions to {name, symbol, description, due_date,
    order}.

    Accepts the legacy bare-string form as well as the object form, mirroring
    normalize_stakeholders.

    **List position is the sequence.** ``order`` is derived here as a 1-based
    index rather than read from the item, so a hand-edited `_meta.yaml` cannot
    express a sequence that disagrees with itself. Callers that reorder rewrite
    the list; they never write an ``order`` key back.

    A ``due_date`` that is not ``YYYY-MM-DD`` degrades to "". `_meta.yaml` is
    hand-editable and arrives by git pull, so one bad date must not take down
    every listing that reads baselines — the same reasoning as the is_safe_id
    guard in list_baselines.

    ``description`` is sanitised here for the same reason, and it matters more:
    it is rich text that ends up in the baselines page, exports and published
    documents, and `_meta.yaml` never passes through
    ``load_guard.validate_on_load`` — that runs only on the per-collection read
    path, so meta-held HTML had no sanitiser on either the read or the write
    side. Doing it in this function covers both, because every route that reads
    or writes baseline definitions goes through it. (The baselines page used to
    inject it with ``dangerouslySetInnerHTML``, which made this the only guard;
    it now renders through ``AutoLinkHtml``, so this is the outer of two.)
    """
    result: list[dict] = []
    for item in (baselines or []):
        if isinstance(item, str):
            item = {"name": item}
        if not isinstance(item, dict):
            continue
        due = str(item.get("due_date", "") or "").strip()
        if due and not DUE_DATE_RE.match(due):
            due = ""
        result.append({
            "name": item.get("name", ""),
            "symbol": item.get("symbol", ""),
            "description": sanitize_html(item.get("description", "")),
            "due_date": due,
            "order": len(result) + 1,
        })
    return result


def normalize_system_states(states: list) -> list[dict]:
    """Normalize project system-state definitions to {name, description, order}.

    Mirrors normalize_baseline_defs, including its reasoning: a bare string is
    accepted so a project that listed state names before they had descriptions
    keeps working, and ``order`` is the list position rather than a stored field,
    so `_meta.yaml` cannot express a sequence that disagrees with itself.

    States are what a requirement's ``system_states`` refers to by name. Defining
    them on the project is what lets the requirement editor offer a list instead
    of a comma-separated free-text box, where a typo silently creates a state
    nobody can find again.
    """
    result: list[dict] = []
    for item in (states or []):
        if isinstance(item, str):
            item = {"name": item}
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        result.append({
            "name": name,
            "description": item.get("description", ""),
            "order": len(result) + 1,
        })
    return result


def serialize_meta_defs(defs: list[dict]) -> list[dict]:
    """The `_meta.yaml` form of normalized definitions (baselines and system states).

    Drops ``order`` — it is the list position, derived on read, and writing it
    back would create a second copy of the sequence free to disagree with the
    first. Empty optional fields are omitted so a project that never set a
    symbol or a due date keeps a clean `_meta.yaml`.
    """
    return [
        {k: v for k, v in d.items() if k != "order" and (k == "name" or v)}
        for d in defs
    ]


def normalize_stakeholders(stakeholders: list) -> list[dict]:
    """Normalize project stakeholder definitions to {name, weight}.

    Accepts a bare string (weight defaults to 1.0) so a project that listed
    stakeholder names before weights existed keeps working, mirroring how
    normalize_baseline_defs tolerates legacy string baselines.

    Weights are relative, not required to sum to anything: the value shown per
    requirement is a weighted mean, so adding a stakeholder does not silently
    rescale every existing score.
    """
    result: list[dict] = []
    for item in (stakeholders or []):
        if isinstance(item, str):
            result.append({"name": item, "weight": 1.0})
        elif isinstance(item, dict) and item.get("name"):
            try:
                weight = float(item.get("weight", 1.0))
            except (TypeError, ValueError):
                weight = 1.0
            result.append({"name": item["name"], "weight": max(0.0, weight)})
    return result
