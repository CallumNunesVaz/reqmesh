"""Risk rating derived from a project-configurable risk matrix.

A risk carries two *inputs* — how bad it would be (``severity``) and how likely
it is (``likelihood``) — and the project's matrix turns that pair into one
*output*, the rating band. The rating is never stored on the risk: it is
computed on read, so re-tuning the matrix re-rates every existing risk at once.
Storing it would let the two drift, and a risk register whose ratings disagree
with its own matrix is worse than one with no ratings.

The default is a 4x5 matrix whose severity axis is the vocabulary risks already
used (low/medium/high/critical), so existing projects need no migration. The
likelihood axis is the conventional five-band scale; the free-text
``probability`` field that preceded it is mapped on read (see LEGACY_LIKELIHOOD).

Axes are ordered least-severe first and least-likely first, so cell (0, 0) is
the bottom-left of a conventionally drawn matrix.
"""

from __future__ import annotations

DEFAULT_SEVERITIES = ["low", "medium", "high", "critical"]
DEFAULT_LIKELIHOODS = ["rare", "unlikely", "possible", "likely", "almost_certain"]

#: How likely a risk is to be spotted before it bites, best detection first.
#: Configurable per project like the other axes, and — unlike them — it does not
#: address a cell: the matrix stays two-dimensional, so adding detection cannot
#: re-rate a single existing risk.
DEFAULT_DETECTIONS = ["obvious", "likely", "possible", "unlikely", "undetectable"]

#: The risk lifecycle. A plain list rather than an enum, matching how severity
#: and likelihood are handled here: a project that renames a state must not find
#: every stored risk invalid. The UI offers these; it does not enforce them.
DEFAULT_RISK_STATUSES = ["open", "mitigating", "monitoring", "accepted", "closed"]

# Rating bands, least to most serious. The colours are the matrix's whole
# point — a band without one cannot be drawn — so they live with the band
# rather than in the frontend, and travel with the project when it is exported.
DEFAULT_BANDS = [
    {"key": "low", "label": "Low", "color": "#22c55e"},
    {"key": "medium", "label": "Medium", "color": "#eab308"},
    {"key": "high", "label": "High", "color": "#f97316"},
    {"key": "extreme", "label": "Extreme", "color": "#ef4444"},
]

# cells[severity_index][likelihood_index] -> band key.
# Rows are severities (low..critical), columns likelihoods (rare..almost_certain).
DEFAULT_CELLS = [
    ["low", "low", "low", "medium", "medium"],
    ["low", "low", "medium", "medium", "high"],
    ["low", "medium", "high", "high", "extreme"],
    ["medium", "high", "high", "extreme", "extreme"],
]

# Risks predating the likelihood axis stored a free-text ``probability``.
LEGACY_LIKELIHOOD = {
    "low": "unlikely",
    "medium": "possible",
    "high": "likely",
    "critical": "almost_certain",
    "very low": "rare",
    "very high": "almost_certain",
}


def default_matrix() -> dict:
    return {
        "severities": list(DEFAULT_SEVERITIES),
        "likelihoods": list(DEFAULT_LIKELIHOODS),
        # Not an axis of `cells` — see DEFAULT_DETECTIONS. It travels with the
        # matrix because it is the same kind of thing (a per-project vocabulary
        # the UI offers), not because it addresses a cell.
        "detections": list(DEFAULT_DETECTIONS),
        "bands": [dict(b) for b in DEFAULT_BANDS],
        "cells": [list(row) for row in DEFAULT_CELLS],
    }


def normalize_matrix(matrix) -> dict:
    """Coerce a stored matrix into a usable one, falling back per-field.

    A matrix half-edited by hand must not take the risk register down with it,
    so every field degrades to its default independently and ``cells`` is
    resized to match the axes rather than trusted to be the right shape.
    """
    base = default_matrix()
    if not isinstance(matrix, dict):
        return base

    def _names(key):
        raw = matrix.get(key)
        if not isinstance(raw, list):
            return base[key]
        out = [str(x).strip() for x in raw if str(x).strip()]
        # Duplicate level names would make a cell unaddressable.
        seen, unique = set(), []
        for n in out:
            if n not in seen:
                seen.add(n)
                unique.append(n)
        return unique or base[key]

    severities = _names("severities")
    likelihoods = _names("likelihoods")

    bands = []
    for b in (matrix.get("bands") if isinstance(matrix.get("bands"), list) else []):
        if isinstance(b, dict) and str(b.get("key", "")).strip():
            key = str(b["key"]).strip()
            bands.append({
                "key": key,
                "label": str(b.get("label") or key.replace("_", " ").title()),
                "color": str(b.get("color") or "#6b7280"),
            })
    if not bands:
        bands = [dict(b) for b in DEFAULT_BANDS]
    band_keys = {b["key"] for b in bands}
    fallback = bands[0]["key"]

    raw_cells = matrix.get("cells") if isinstance(matrix.get("cells"), list) else []
    cells = []
    for si in range(len(severities)):
        row_in = raw_cells[si] if si < len(raw_cells) and isinstance(raw_cells[si], list) else []
        row = []
        for li in range(len(likelihoods)):
            value = row_in[li] if li < len(row_in) else None
            row.append(value if value in band_keys else fallback)
        cells.append(row)

    return {"severities": severities, "likelihoods": likelihoods,
            "detections": _names("detections"),
            "bands": bands, "cells": cells}


def _index(levels: list[str], value) -> int | None:
    if value is None:
        return None
    v = str(value).strip().lower()
    for i, level in enumerate(levels):
        if level.strip().lower() == v:
            return i
    return None


def resolve_likelihood(risk: dict, likelihoods: list[str]) -> str | None:
    """The risk's likelihood, falling back to its pre-matrix ``probability``."""
    for candidate in (risk.get("likelihood"), risk.get("probability")):
        if candidate is None or str(candidate).strip() == "":
            continue
        if _index(likelihoods, candidate) is not None:
            return str(candidate).strip()
        mapped = LEGACY_LIKELIHOOD.get(str(candidate).strip().lower())
        if mapped is not None and _index(likelihoods, mapped) is not None:
            return mapped
    return None


def rate(risk: dict, matrix: dict) -> dict:
    """Return the rating for one risk.

    ``band`` is None when either input is missing or names a level the matrix
    does not define — an unrateable risk is reported as such rather than
    defaulted into a band, because a wrong rating is read as a real assessment.
    """
    m = normalize_matrix(matrix)
    likelihood = resolve_likelihood(risk, m["likelihoods"])
    si = _index(m["severities"], risk.get("severity"))
    li = _index(m["likelihoods"], likelihood)

    if si is None or li is None:
        reason = []
        if si is None:
            reason.append(f"severity {risk.get('severity')!r} is not a matrix level")
        if li is None:
            reason.append("likelihood is not set" if likelihood is None
                          else f"likelihood {likelihood!r} is not a matrix level")
        return {"band": None, "label": None, "color": None,
                "severity": risk.get("severity"), "likelihood": likelihood,
                "unrated_reason": "; ".join(reason)}

    key = m["cells"][si][li]
    band = next((b for b in m["bands"] if b["key"] == key), m["bands"][0])
    return {"band": band["key"], "label": band["label"], "color": band["color"],
            "severity": m["severities"][si], "likelihood": m["likelihoods"][li],
            "unrated_reason": None}


def apply_rating(risks: list[dict], matrix: dict) -> list[dict]:
    """Attach ``rating`` to each risk. Normalizes the matrix once, not per risk."""
    m = normalize_matrix(matrix)
    for r in risks:
        r["rating"] = rate(r, m)
    return risks


def risk_bingo(risks: list[dict], matrix: dict) -> dict:
    """Return a severity × likelihood count grid and its per-cell band keys.

    Returns the ``RiskBingo`` shape: ``severities``, ``likelihoods``,
    ``counts[severityIndex][likelihoodIndex]``, ``bands[severityIndex][likelihoodIndex]``,
    ``unrated``, and ``total``.

    A risk whose severity or (resolved) likelihood is not a matrix level counts
    once in ``unrated`` and in no cell.  ``total`` is every risk, so
    ``sum(counts) + unrated == total`` holds.
    """
    m = normalize_matrix(matrix)
    ns = len(m["severities"])
    nl = len(m["likelihoods"])

    counts: list[list[int]] = [[0] * nl for _ in range(ns)]
    bands: list[list[str]] = [
        [m["cells"][si][li] for li in range(nl)] for si in range(ns)
    ]

    total = len(risks)
    unrated = 0
    for r in risks:
        si = _index(m["severities"], r.get("severity"))
        likelihood = resolve_likelihood(r, m["likelihoods"])
        li = _index(m["likelihoods"], likelihood)
        if si is None or li is None:
            unrated += 1
        else:
            counts[si][li] += 1

    return {
        "severities": list(m["severities"]),
        "likelihoods": list(m["likelihoods"]),
        "counts": counts,
        "bands": bands,
        "unrated": unrated,
        "total": total,
    }
