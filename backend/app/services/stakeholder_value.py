"""Weighted stakeholder value for a requirement.

A project defines its stakeholders and how much each one's opinion counts
(``_meta.yaml: stakeholders: [{name, weight}]``). A requirement scores itself
against them (``priorities: {stakeholder: score}``). This turns the two into a
single comparable number.

The value is a **weighted mean over the stakeholders that actually have a
score**, not a sum:

  * A sum — which is what ``/backlog`` returned as ``combined_priority`` — ranks
    a requirement higher merely for having been scored by more people, so
    scoring an extra stakeholder raises a requirement's rank without anyone
    changing their opinion of it.
  * A mean over *all* defined stakeholders would treat "not yet scored" as
    "scored zero", so adding a stakeholder to the project would silently
    depress every existing requirement.

Averaging only over scored stakeholders avoids both, at the cost of a
requirement scored by one stakeholder being comparable to one scored by all.
That is a real limitation rather than a hidden one: ``scored_count`` and
``stakeholder_count`` are returned so the UI can show "2 of 3 scored" and the
reader can judge how much to trust the number.
"""

from __future__ import annotations


def compute_value(priorities: dict, stakeholders: list[dict]) -> dict:
    """Return the weighted value of one requirement.

    ``priorities`` maps stakeholder name -> score. ``stakeholders`` is the
    project's normalized [{name, weight}] list.

    Returns ``value: None`` when nothing usable is scored, which the caller
    should render as "not scored" rather than as zero — a requirement nobody
    has assessed is not the same as one everybody rated zero.
    """
    weights = {s["name"]: s.get("weight", 1.0) for s in (stakeholders or [])}

    contributions: list[dict] = []
    weighted_sum = 0.0
    weight_total = 0.0

    for name, weight in weights.items():
        raw = priorities.get(name)
        score: float | None
        try:
            score = float(raw) if raw is not None else None
        except (TypeError, ValueError):
            score = None
        contribution = None
        if score is not None:
            contribution = weight * score
            weighted_sum += contribution
            weight_total += weight
        contributions.append({
            "name": name, "weight": weight, "score": score, "contribution": contribution,
        })

    # Scores against stakeholders the project no longer defines are surfaced
    # rather than dropped: they are the residue of a renamed or removed
    # stakeholder, and silently ignoring them makes a requirement look unscored
    # while its data still says otherwise.
    unknown = sorted(k for k in (priorities or {}) if k not in weights)

    scored = sum(1 for c in contributions if c["score"] is not None)
    value = round(weighted_sum / weight_total, 2) if weight_total > 0 else None

    return {
        "value": value,
        "scored_count": scored,
        "stakeholder_count": len(weights),
        "contributions": contributions,
        "unknown_stakeholders": unknown,
    }


def rank_requirements(reqs: list[dict], stakeholders: list[dict]) -> list[dict]:
    """Value every requirement and assign a dense rank, best first.

    Unscored requirements keep ``value: None`` and ``rank: None`` — they sort
    last, but are not given rank 0, which would read as "worst" rather than
    "unknown".
    """
    scored: list[dict] = []
    for r in reqs:
        result = compute_value(r.get("priorities") or {}, stakeholders)
        scored.append({"id": r["id"], "name": r.get("name", ""),
                       "status": r.get("status", "proposed"), **result})

    ordered = sorted(
        [s for s in scored if s["value"] is not None],
        key=lambda s: -s["value"],
    )
    rank_by_id: dict[str, int] = {}
    prev_value = None
    rank = 0
    for i, s in enumerate(ordered, start=1):
        if s["value"] != prev_value:
            rank = i
            prev_value = s["value"]
        rank_by_id[s["id"]] = rank

    for s in scored:
        s["rank"] = rank_by_id.get(s["id"])
    return scored


def pugh_matrix(reqs: list[dict], stakeholders: list[dict],
                datum_id: str | None = None, limit: int = 8) -> dict:
    """Compare the best-valued requirements against each other, Pugh-style.

    A Pugh matrix scores a handful of *alternatives* against weighted
    *criteria*, relative to a chosen *datum*. Here the criteria are the
    stakeholders and the alternatives are requirements, so each cell asks "does
    this requirement matter more to this stakeholder than the datum does?".

    Candidates are the scored requirements from :func:`rank_requirements`, best
    first, capped at ``limit`` — the cap is not a detail. A Pugh matrix over
    every requirement is not a Pugh matrix, it is a spreadsheet; the technique
    only says anything when a person can hold the columns in their head.

    The datum is ``datum_id`` when it names a candidate, else the top-ranked
    one. Its own column is all zeroes **by definition**, not by accident.

    ``sign`` is 1 above the datum, -1 below, 0 equal, and ``None`` when either
    side is unscored — an unscored stakeholder cannot be compared, and calling
    that 0 would assert a parity nobody stated. ``None`` signs are excluded
    from ``plus``, ``minus`` and ``weighted``.

    Returns ``{datum, limit, total_candidates, stakeholders, columns}``; see
    ``PughMatrix`` in ``frontend/src/api/client.ts`` for the wire shape. With
    nothing scored, ``datum`` is None and ``columns`` is empty — an empty
    matrix, not an error.
    """
    raise NotImplementedError
