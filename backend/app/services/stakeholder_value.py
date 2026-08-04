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
    # Rank all requirements first — build the matrix on top of the ranking
    # rather than recomputing values.
    ranked = rank_requirements(reqs, stakeholders)

    # Candidates are every requirement with a non-None value, best first.
    candidates = [r for r in ranked if r["value"] is not None]
    total_candidates = len(candidates)

    if total_candidates == 0:
        return {
            "datum": None,
            "limit": limit,
            "total_candidates": 0,
            "stakeholders": stakeholders,
            "columns": [],
        }

    # Determine the datum.  An explicit id that names a candidate is honoured;
    # anything else (None, not scored, not in the capped set) falls back to the
    # top-ranked candidate so a stale link still renders.
    limited = candidates[:limit]
    limited_ids = {c["id"] for c in limited}

    if datum_id and datum_id in {c["id"] for c in candidates}:
        if datum_id in limited_ids:
            datum_id_actual = datum_id
        else:
            # The caller asked for a datum that exists but is not among the
            # capped columns — fall back to top-ranked so the matrix is still
            # useful.
            datum_id_actual = limited[0]["id"]
    else:
        datum_id_actual = limited[0]["id"]

    # Build an id->priorities lookup over the raw requirements so we can
    # compare the datum's scores against every candidate's without a linear
    # scan per stakeholder.
    req_by_id: dict[str, dict] = {r["id"]: r for r in reqs}
    datum_req = req_by_id.get(datum_id_actual, {})
    datum_priorities = datum_req.get("priorities", {})

    columns: list[dict] = []
    for cand in limited:
        cand_req = req_by_id.get(cand["id"], {})
        cand_priorities = cand_req.get("priorities", {})
        is_datum = cand["id"] == datum_id_actual

        cells: dict[str, dict] = {}
        plus = 0
        minus = 0
        weighted_sum = 0.0

        for s in stakeholders:
            name = s["name"]
            weight = float(s.get("weight", 1.0))

            d_score = datum_priorities.get(name)
            c_score = cand_priorities.get(name)

            # Score shown in the cell is this requirement's own score.
            score = c_score if c_score is not None else None

            if is_datum:
                # The datum's own column is all zeroes — that is what a datum
                # means, not a bug.
                sign = 0
            elif d_score is None or c_score is None:
                # An unscored stakeholder on either side cannot be compared.
                sign = None
            elif c_score > d_score:
                sign = 1
                plus += 1
                weighted_sum += weight * sign
            elif c_score < d_score:
                sign = -1
                minus += 1
                weighted_sum += weight * sign
            else:
                sign = 0

            cells[name] = {"score": score, "sign": sign}

        columns.append({
            "id": cand["id"],
            "name": cand.get("name", ""),
            "value": cand["value"],
            "rank": cand["rank"],
            "cells": cells,
            "plus": plus,
            "minus": minus,
            "weighted": round(weighted_sum, 2),
        })

    return {
        "datum": datum_id_actual,
        "limit": limit,
        "total_candidates": total_candidates,
        "stakeholders": stakeholders,
        "columns": columns,
    }
