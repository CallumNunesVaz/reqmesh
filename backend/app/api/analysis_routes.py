"""Analysis, metrics, quality, evaluation, and reporting endpoints.

Extracted from ``extra_routes.py``: impact analysis, gap analysis, backlinks,
coverage analysis, conflict detection, compliance, metrics, backlog,
stakeholder value, quality analysis, and parametric evaluation.
"""
from __future__ import annotations

from typing import Optional, cast

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel

from app.core.dependencies import get_store
from app.core.rate_limit import rate_limit

router = APIRouter()


class ImpactRequest(BaseModel):
    # Deliberately untyped: a what-if payload with an unparseable value is
    # ignored and reported, not rejected. Tightening this to dict[str, float]
    # turns that into a 422 (test_impact_preview.py::test_malformed_value_ignored).
    overrides: dict = {}


# ── Impact Analysis ───────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/requirements/{req_id}/impact")
def get_impact(project_id: str, req_id: str):
    store = get_store(project_id)
    all_reqs = store.list_requirements()
    req = store.get_requirement(req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    dependents = []
    cascades = []
    for r in all_reqs:
        for rel in r.get("relations", []):
            if rel.get("target") == req_id:
                dependents.append({"id": r["id"], "name": r.get("name", ""), "relation": rel["type"]})
        if r.get("cascade_from") == req_id:
            cascades.append(r["id"])
        if r.get("parent") == req_id:
            dependents.append({"id": r["id"], "name": r.get("name", ""), "relation": "child"})
    return {"requirement": req_id, "dependents": dependents, "cascade_children": cascades, "count": len(dependents) + len(cascades)}


# ── Gap Analysis ──────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/gap-analysis")
def gap_analysis(project_id: str):
    store = get_store(project_id)
    reqs = store.list_requirements()
    gaps = []
    for r in reqs:
        issues = []
        if not r.get("description", "").strip(): issues.append("no_description")
        if not r.get("rationale", "").strip(): issues.append("no_rationale")
        if not r.get("source", "").strip(): issues.append("no_source")
        if not r.get("relations"): issues.append("unlinked")
        if issues:
            gaps.append({"id": r["id"], "name": r.get("name", ""), "issues": issues})
    return {"total": len(reqs), "gaps": len(gaps), "items": gaps}


# ── Coverage Analysis ─────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/entities/{entity_id}/backlinks")
def entity_backlinks(project_id: str, entity_id: str,
                     collection: Optional[str] = Query(None)):
    """Everything in the project that points at this entity, grouped by kind."""
    from app.services.link_registry import COLLECTION_LABELS, LINKS, find_referrers

    store = get_store(project_id)
    candidates = [collection] if collection else sorted({ln.target for ln in LINKS})

    found_in = None
    for coll in candidates:
        try:
            if any(i.get("id") == entity_id for i in store.list_items(coll)):
                found_in = coll
                break
        except Exception:
            continue
    if found_in is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    groups: dict[str, list] = {}
    for ref in find_referrers(store, found_in, entity_id):
        groups.setdefault(ref["holder"], []).append(ref)

    return {
        "id": entity_id,
        "collection": found_in,
        "total": sum(len(v) for v in groups.values()),
        "groups": [
            {"collection": k, "label": COLLECTION_LABELS.get(k, k), "items": v}
            for k, v in sorted(groups.items())
        ],
    }


@router.get("/coverage-needs")
def coverage_needs_vocabulary():
    """The obligation kinds a requirement may declare in ``needs``."""
    from app.services.tracing import NEEDS_VOCABULARY
    return {"items": [{"value": k, "label": v} for k, v in NEEDS_VOCABULARY.items()]}


@router.get("/projects/{project_id}/coverage")
def coverage_analysis(project_id: str, _rate: None = Depends(rate_limit(20, 60))):
    from app.services.tracing import trace_all
    items = trace_all(get_store(project_id))
    total = len(items)
    if total == 0:
        return {"total": 0, "shallow_covered": 0, "deep_covered": 0, "coverage_pct": 0, "deep_pct": 0, "items": []}
    shallow = sum(1 for i in items if i["shallow"])
    deep = sum(1 for i in items if i["deep"])
    return {
        "total": total, "shallow_covered": shallow, "deep_covered": deep,
        "coverage_pct": round(shallow / total * 100),
        "deep_pct": round(deep / total * 100),
        "items": items,
    }


# ── Conflict Detection ────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/conflicts")
def detect_conflicts(project_id: str):
    store = get_store(project_id)
    reqs = store.list_requirements()
    conflicts = []
    for r in reqs:
        for rel in r.get("relations", []):
            if rel["type"] == "conflicts":
                conflicts.append({"a": r["id"], "b": rel["target"], "type": "explicit_conflict"})

    duplicate_names: dict[str, list[str]] = {}
    for r in reqs:
        name_key = r.get("name", "").strip().lower()
        if name_key:
            duplicate_names.setdefault(name_key, []).append(r["id"])
    for name, ids in duplicate_names.items():
        if len(ids) > 1:
            conflicts.append({"ids": ids, "type": "duplicate_name", "name": name})
    return {"count": len(conflicts), "conflicts": conflicts}


# ── Compliance ────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/compliance")
def compliance_status(project_id: str):
    store = get_store(project_id)
    reqs = store.list_requirements()
    standards: dict[str, int] = {}
    for r in reqs:
        for attr in r.get("attributes", []):
            if attr.get("key") == "standard" and attr.get("value"):
                std = attr["value"]
                standards[std] = (standards.get(std) or 0) + 1
    return {"standards": [{"name": k, "count": v} for k, v in sorted(standards.items())], "tracked_count": sum(standards.values()), "total_requirements": len(reqs)}


# ── Metrics ───────────────────────────────────────────────────────────────────

# A risk is only "live" in these statuses. Closed and accepted risks stay in the
# register as a record of the decision, so counting them would make a project
# look riskier the longer it has been managed well.
OPEN_RISK_STATUSES = {"open", "mitigating", "monitoring"}


def _risk_metrics(store) -> dict:
    """Risk-register health, rated through the project's own matrix.

    Ratings are derived here rather than read off the risk, for the same reason
    the register derives them on read (see ``services/risk_matrix``): a stored
    rating and a re-tuned matrix drift apart, and metrics that disagree with the
    page they summarise are worse than no metrics.
    """
    from app.services.risk_matrix import apply_rating, normalize_matrix

    matrix = normalize_matrix(store.read_meta().get("risk_matrix"))
    risks = apply_rating(store.list_items("risks"), matrix)
    total = len(risks)

    # Seed every band at zero so the chart keeps a stable set of columns —
    # otherwise a band nobody has hit vanishes and the axis silently rescales.
    by_band: dict[str, int] = {b["key"]: 0 for b in matrix["bands"]}
    open_by_band: dict[str, int] = dict.fromkeys(by_band, 0)
    by_status: dict[str, int] = {}
    unrated = with_mitigation = with_requirements = open_count = 0

    for r in risks:
        status = str(r.get("status") or "open").strip().lower()
        by_status[status] = by_status.get(status, 0) + 1
        is_open = status in OPEN_RISK_STATUSES
        open_count += is_open

        band = (r.get("rating") or {}).get("band")
        if band is None:
            unrated += 1
        elif band in by_band:
            by_band[band] += 1
            if is_open:
                open_by_band[band] += 1

        if str(r.get("mitigation") or "").strip():
            with_mitigation += 1
        if r.get("linked_requirements"):
            with_requirements += 1

    # Bands run least- to most-serious, so the tail is what needs attention.
    # "Severe" is the top two bands rather than a hardcoded name: the matrix is
    # project-configurable and a project may not have a band called "extreme".
    severe_keys = [b["key"] for b in matrix["bands"]][-2:]
    severe_open = sum(open_by_band.get(k, 0) for k in severe_keys)

    def pct(n: int) -> int:
        return round(n / total * 100) if total else 0

    return {
        "total": total,
        "open": open_count,
        "unrated": unrated,
        "severe_open": severe_open,
        "severe_bands": severe_keys,
        # Carried so the client colours bands from the project's matrix instead
        # of keeping its own copy of the palette, which would go stale the
        # moment someone edits the matrix.
        "bands": [dict(b) for b in matrix["bands"]],
        "by_band": by_band,
        "open_by_band": open_by_band,
        "by_status": by_status,
        "with_mitigation": with_mitigation,
        "with_requirements": with_requirements,
        "mitigation_pct": pct(with_mitigation),
        "linked_pct": pct(with_requirements),
        "top_open": [
            {
                "id": r.get("id"),
                "title": r.get("title") or r.get("name") or "",
                "band": r["rating"]["band"],
                "label": r["rating"]["label"],
                "color": r["rating"]["color"],
                "severity": r["rating"]["severity"],
                "likelihood": r["rating"]["likelihood"],
                "mitigated": bool(str(r.get("mitigation") or "").strip()),
            }
            for r in sorted(
                (r for r in risks
                 if (r.get("rating") or {}).get("band")
                 and str(r.get("status") or "open").strip().lower() in OPEN_RISK_STATUSES),
                key=lambda r: [b["key"] for b in matrix["bands"]].index(r["rating"]["band"]),
                reverse=True,
            )[:10]
        ],
    }


@router.get("/projects/{project_id}/metrics")
def project_metrics(project_id: str, _rate: None = Depends(rate_limit(20, 60))):
    store = get_store(project_id)
    reqs = store.list_requirements()
    vcs = store.list_verification_cases()
    total = len(reqs)
    risks = _risk_metrics(store)
    if total == 0:
        # A project can hold risks before it holds requirements, so the risk
        # block ships even on the empty-project path.
        return {"total": 0, "risks": risks}
    statuses: dict[str, int] = {}
    baselines = set()
    with_desc = with_rationale = with_source = with_alloc = with_trace = with_cascade = 0
    for r in reqs:
        statuses[r.get("status", "proposed")] = statuses.get(r.get("status", "proposed"), 0) + 1
        for b in (r.get("baselines") or []):
            if b: baselines.add(b)
        if r.get("description", "").strip(): with_desc += 1
        if r.get("rationale", "").strip(): with_rationale += 1
        if r.get("source", "").strip(): with_source += 1
        if r.get("allocated_to", "").strip(): with_alloc += 1
        if r.get("relations"): with_trace += 1
        if r.get("cascade_from"): with_cascade += 1

    return {
        "total": total,
        "verification_cases": len(vcs),
        "baselines": len(baselines),
        "status_distribution": statuses,
        "risks": risks,
        "quality": {
            "with_description": with_desc,
            "with_rationale": with_rationale,
            "with_source": with_source,
            "with_allocation": with_alloc,
            "with_traceability": with_trace,
            "cascaded": with_cascade,
        },
        "quality_pct": {
            "description": round(with_desc / total * 100),
            "rationale": round(with_rationale / total * 100),
            "source": round(with_source / total * 100),
            "allocation": round(with_alloc / total * 100),
            "traceability": round(with_trace / total * 100),
        },
    }


@router.get("/projects/{project_id}/risk-bingo", summary="Risk bingo grid")
def risk_bingo_endpoint(project_id: str, _rate: None = Depends(rate_limit(20, 60))):
    """Severity × likelihood grid of risk counts per the project matrix."""
    from app.services.risk_matrix import risk_bingo, normalize_matrix

    store = get_store(project_id)
    matrix = normalize_matrix(store.read_meta().get("risk_matrix"))
    risks = store.list_items("risks")
    return risk_bingo(risks, matrix)


@router.get("/projects/{project_id}/backlog")
def prioritized_backlog(project_id: str, sort: str = "priority", _rate: None = Depends(rate_limit(20, 60))):
    """Requirements ranked by weighted stakeholder value, best first."""
    from app.services.meta_defs import normalize_stakeholders
    from app.services.stakeholder_value import rank_requirements

    store = get_store(project_id)
    stakeholders = normalize_stakeholders(store.read_meta().get("stakeholders", []))
    reqs = [r for r in store.list_requirements()
            if r.get("status") not in ("rejected", "deprecated")]
    by_id = {r["id"]: r for r in reqs}

    results = []
    for item in rank_requirements(reqs, stakeholders):
        results.append({
            **item,
            "priorities": by_id[item["id"]].get("priorities", {}),
            "combined_priority": item["value"] if item["value"] is not None else 0,
        })
    # Unscored last, otherwise by value.
    results.sort(key=lambda x: (x["value"] is None, -(x["value"] or 0)))
    return {"items": results, "stakeholders": stakeholders}


@router.get("/projects/{project_id}/requirements/{req_id}/value")
def requirement_value(project_id: str, req_id: str):
    """The weighted stakeholder value of one requirement, and its rank."""
    from app.services.meta_defs import normalize_stakeholders
    from app.services.stakeholder_value import rank_requirements

    store = get_store(project_id)
    if not store.get_requirement(req_id):
        raise HTTPException(status_code=404, detail="Requirement not found")
    stakeholders = normalize_stakeholders(store.read_meta().get("stakeholders", []))
    reqs = [r for r in store.list_requirements()
            if r.get("status") not in ("rejected", "deprecated")]
    ranked = rank_requirements(reqs, stakeholders)
    mine = next((r for r in ranked if r["id"] == req_id), None)
    if mine is None:
        from app.services.stakeholder_value import compute_value
        req = cast(dict, store.get_requirement(req_id))
        mine = {"id": req_id, "name": req.get("name", ""), "status": req.get("status", ""),
                **compute_value(req.get("priorities") or {}, stakeholders), "rank": None}
    return {**mine, "ranked_total": sum(1 for r in ranked if r["value"] is not None)}


# ── Pugh Matrix ───────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/pugh", summary="Pugh matrix")
def pugh_matrix_endpoint(
    project_id: str,
    datum: Optional[str] = Query(None),
    limit: int = Query(8, ge=1, le=20),
    _rate: None = Depends(rate_limit(20, 60)),
):
    """A Pugh matrix comparing the best-valued requirements against each other,
    relative to a chosen datum. Stakeholders are the criteria; their weights
    scale the comparison so a heavier stakeholder moves the `weighted` total
    further than a light one."""
    from app.services.meta_defs import normalize_stakeholders
    from app.services.stakeholder_value import pugh_matrix

    store = get_store(project_id)
    stakeholders = normalize_stakeholders(store.read_meta().get("stakeholders", []))
    reqs = [r for r in store.list_requirements()
            if r.get("status") not in ("rejected", "deprecated")]
    return pugh_matrix(reqs, stakeholders, datum_id=datum or None, limit=limit)


# ── Quality Analysis ──────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/quality")
def quality_analysis(project_id: str, _rate: None = Depends(rate_limit(20, 60))):
    from app.services.quality import project_quality
    return project_quality(get_store(project_id))


# ── Parametric Evaluation ─────────────────────────────────────────────────────

@router.get("/projects/{project_id}/evaluation")
def parametric_evaluation(project_id: str, _rate: None = Depends(rate_limit(20, 60))):
    """Evaluate every parameter, constraint and measurement in the project."""
    from app.services.evaluation import evaluate_project
    return evaluate_project(get_store(project_id))


@router.post("/projects/{project_id}/evaluation/impact")
def evaluation_impact(project_id: str, data: ImpactRequest, _rate: None = Depends(rate_limit(20, 60))):
    """Returns the evaluation with hypothetical overrides plus a
    dependency-ordered trace of every parameter and constraint that
    changes — so the frontend can animate the what-if cascade."""
    from app.services.evaluation import evaluate_project, build_impact, coerce_number

    store = get_store(project_id)
    overrides: dict[str, float] = {}
    override_issues: list[dict] = []
    for ref, val in (data.overrides or {}).items():
        coerced = coerce_number(val,
                                 kind="non_numeric_override",
                                 ref=ref,
                                 source="",
                                 issues=override_issues)
        if coerced is not None:
            overrides[ref] = coerced

    evaluation = evaluate_project(store, extra_overrides=overrides)
    evaluation["data_issues"] = sorted(evaluation["data_issues"] + override_issues,
                                       key=lambda i: (i["kind"], i["ref"], i["source"]))
    impact = build_impact(store, overrides)
    return {
        "evaluation": evaluation,
        "steps": impact["steps"],
        "affected": impact["affected"],
        "roots": impact["roots"],
    }
