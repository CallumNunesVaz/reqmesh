"""In-memory search over the YAML store.

Projects are directories of small YAML files that are fully loaded for most
operations anyway, so search filters the loaded documents directly. This
keeps the project directory free of derived artifacts (no _search.db to
commit or drift out of sync) and removes the need for index maintenance.

Project-wide search covers every entity type — requirements, components,
verification cases, specifications, change requests, risks, comments,
decisions, definitions, analysis cases, and baselines — with simple
substring matching and relevance scoring.
"""

from __future__ import annotations

from app.services.verification_links import attach as attach_verification_cases
from app.services.html_text import strip_html

FILTERABLE_FIELDS = ("type", "priority", "status", "verification_status")

_KIND_LABELS: dict[str, str] = {
    "requirement": "Requirement",
    "component": "Component",
    "verification": "Verification Case",
    "specification": "Specification",
    "change_request": "Change Request",
    "risk": "Risk",
    "comment": "Comment",
    "decision": "Decision",
    "definition": "Definition",
    "analysis": "Analysis Case",
    "baseline": "Baseline",
}

_KIND_ICON: dict[str, str] = {
    "requirement": "clipboard-list",
    "component": "boxes",
    "verification": "check-circle",
    "specification": "file-text",
    "change_request": "git-pull-request",
    "risk": "alert-triangle",
    "comment": "message-square",
    "decision": "scale",
    "definition": "sigma",
    "analysis": "flask-conical",
    "baseline": "history",
}


def _searchable_text(req: dict) -> str:
    parts = [v for v in req.values() if isinstance(v, str)]
    for attr in req.get("attributes") or []:
        if isinstance(attr, dict):
            parts.append(str(attr.get("value", "")))
    return " ".join(parts).lower()


def search_requirements(reqs: list[dict], query: str = "", filters: dict | None = None) -> list[dict]:
    query = (query or "").strip().lower()
    results = []
    for req in reqs:
        if filters and any(
            req.get(field) != value
            for field, value in filters.items()
            if value and field in FILTERABLE_FIELDS
        ):
            continue
        if query and query not in _searchable_text(req):
            continue
        results.append(req)
    results.sort(key=lambda r: r.get("modified", ""), reverse=True)
    return results


def search_project(store, query: str, kind: str | None = None, limit: int = 50) -> list[dict]:
    query = (query or "").strip().lower()
    if not query or len(query) < 2:
        return []

    results: list[dict] = []
    q_lower = query

    def _score_text(identifier: str, name: str, detail: str, extra: str = "") -> tuple[int, str, str]:
        # Keep the original-cased text alongside the folded copy: matching is
        # case-insensitive, but the snippet is shown to the user, and slicing
        # it out of the lowercased string rendered every result all-lowercase.
        detail_s = strip_html(detail)
        extra_s = strip_html(extra)
        id_l, name_l = identifier.lower(), name.lower()
        detail_l, extra_l = detail_s.lower(), extra_s.lower()

        if q_lower == id_l:
            score = 100
        elif q_lower == name_l:
            score = 80
        elif q_lower in name_l:
            score = 60
        elif q_lower in detail_l:
            score = 40
        elif q_lower in extra_l or q_lower in id_l:
            score = 20
        else:
            return 0, "", ""

        snippet = ""
        for src, folded in ((detail_s, detail_l), (extra_s, extra_l), (name, name_l)):
            idx = folded.find(q_lower)
            if idx >= 0:
                start = max(0, idx - 30)
                end = min(len(src), idx + len(q_lower) + 60)
                snippet = src[start:end]
                if start > 0:
                    snippet = "..." + snippet
                if end < len(src):
                    snippet = snippet + "..."
                break
        return score, strip_html(name) or identifier, snippet

    # Requirements
    if not kind or kind == "requirement":
        reqs = store.list_requirements()
        attach_verification_cases(store, reqs)
        for r in reqs:
            score, name, snippet = _score_text(
                r.get("id", ""), r.get("name", ""),
                r.get("description", ""),
                f"{r.get('rationale', '')} {r.get('source', '')}",
            )
            if score > 0:
                results.append(dict(kind="requirement", id=r["id"], name=name,
                                    snippet=snippet, score=score,
                                    status=r.get("status", "")))

    # Components
    if not kind or kind == "component":
        for c in store.list_components():
            score, name, snippet = _score_text(
                c.get("id", ""), c.get("name", ""),
                c.get("description", ""),
                f"{c.get('part_number', '')} {c.get('supplier', '')}",
            )
            if score > 0:
                results.append(dict(kind="component", id=c["id"], name=name,
                                    snippet=snippet, score=score,
                                    status=c.get("type", "")))

    # Specifications
    if not kind or kind == "specification":
        for s in store.list_specifications():
            score, name, snippet = _score_text(
                s.get("id", ""), s.get("name", ""), s.get("description", ""),
            )
            if score > 0:
                results.append(dict(kind="specification", id=s["id"], name=name,
                                    snippet=snippet, score=score, status=""))

    # Verification cases
    if not kind or kind == "verification":
        for v in store.list_verification_cases():
            score, name, snippet = _score_text(
                v.get("id", ""), v.get("name", ""),
                v.get("description", ""),
                f"{v.get('test_procedure', '')} {v.get('environment', '')}",
            )
            if score > 0:
                results.append(dict(kind="verification", id=v["id"], name=name,
                                    snippet=snippet, score=score,
                                    status=v.get("status", "")))

    # Change requests
    if not kind or kind == "change_request":
        for cr in store.list_items("change_requests"):
            score, name, snippet = _score_text(
                cr.get("id", ""), cr.get("title", ""), cr.get("description", ""),
            )
            if score > 0:
                results.append(dict(kind="change_request", id=cr["id"], name=name,
                                    snippet=snippet, score=score,
                                    status=cr.get("status", "")))

    # Risks
    if not kind or kind == "risk":
        for rk in store.list_items("risks"):
            score, name, snippet = _score_text(
                rk.get("id", ""), rk.get("title", ""),
                rk.get("description", ""),
                f"{rk.get('impact', '')} {rk.get('mitigation', '')}",
            )
            if score > 0:
                results.append(dict(kind="risk", id=rk["id"], name=name,
                                    snippet=snippet, score=score,
                                    status=rk.get("severity", "")))

    # Comments
    if not kind or kind == "comment":
        for cm in store.list_items("comments"):
            score, name, snippet = _score_text(
                cm.get("id", ""), cm.get("author", cm.get("id", "")),
                cm.get("text", ""),
            )
            if score > 0:
                results.append(dict(kind="comment", id=cm["id"], name=name,
                                    snippet=snippet, score=score, status=""))

    # Decisions
    if not kind or kind == "decision":
        for d in store.list_items("decisions"):
            score, name, snippet = _score_text(
                d.get("id", ""), d.get("title", ""),
                d.get("decision", ""),
                f"{d.get('context', '')} {d.get('rationale', '')}",
            )
            if score > 0:
                results.append(dict(kind="decision", id=d["id"], name=name,
                                    snippet=snippet, score=score, status=""))

    # Definitions
    if not kind or kind == "definition":
        for d in store.list_items("definitions"):
            score, name, snippet = _score_text(
                d.get("id", ""), d.get("name", ""), d.get("doc", ""),
                d.get("expr", ""),
            )
            if score > 0:
                results.append(dict(kind="definition", id=d["id"], name=name,
                                    snippet=snippet, score=score, status=""))

    # Analysis cases
    if not kind or kind == "analysis":
        for a in store.list_items("analysis_cases"):
            score, name, snippet = _score_text(
                a.get("id", ""), a.get("name", ""), a.get("doc", ""),
            )
            if score > 0:
                results.append(dict(kind="analysis", id=a["id"], name=name,
                                    snippet=snippet, score=score, status=""))

    # Baselines
    if not kind or kind == "baseline":
        for b in store.list_items("baselines"):
            name = b.get("name", "")
            desc = b.get("description", "")
            score, _, snippet = _score_text(name, name, desc)
            if score > 0:
                results.append(dict(kind="baseline", id=name, name=name,
                                    snippet=snippet, score=score, status=""))

    results.sort(key=lambda r: (-r["score"], r["name"]))
    if limit and len(results) > limit:
        results = results[:limit]

    for r in results:
        r["kind_label"] = _KIND_LABELS.get(r["kind"], r["kind"])
        r["kind_icon"] = _KIND_ICON.get(r["kind"], "search")

    return results
