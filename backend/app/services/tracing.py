from __future__ import annotations

from collections import defaultdict
from typing import cast

from app.services.link_registry import LINKS, targets_of
from app.services.verification_links import attach as attach_verification_cases


# The coverage obligations a requirement can declare in ``needs``.
#
# These are *artifact kinds*, satisfied by the existence of a linked artifact —
# mirroring the SysML v2 relationships reqmesh already exports (``satisfy``,
# ``verify``). They previously had to match the ``type`` of a child
# requirement, which meant the two values the demo project ships with,
# ``design`` and ``verification_case``, could never be satisfied by anything:
# neither is a member of RequirementType, so the API will not create a
# requirement of that type, and every project using them reported permanent
# coverage gaps that no amount of modelling could close.
NEEDS_VOCABULARY = {
    # SysML v2 `satisfy` — a component claims to realise the requirement.
    "design": "A component satisfies this requirement",
    # SysML v2 `verify` — a verification case exercises it.
    "verification_case": "A verification case verifies this requirement",
    # An analysis case whose scope includes it.
    "analysis_case": "An analysis case covers this requirement",
    # Decomposition: any child requirement.
    "child_requirement": "A child requirement decomposes this requirement",
    # A source-code / document reference of any kind.
    "reference": "An external reference (code, test, doc) is attached",
}


def _build_coverage_graph(store) -> dict:
    reqs = store.list_requirements()
    vcs = store.list_verification_cases()
    attach_verification_cases(store, reqs, vcs)
    components = store.list_components()
    try:
        analyses = store.list_items("analysis_cases")
    except Exception:
        analyses = []
    req_map = {r["id"]: r for r in reqs}

    # requirement id -> {(need_kind, covering_entity_id)}
    covered_by: dict[str, set] = defaultdict(set)

    # `design`: components that satisfy the requirement. This is the same
    # relationship the allocation matrix and the SysML exporter both use.
    for c in components:
        for target in c.get("satisfies") or []:
            covered_by[target].add(("design", c["id"]))

    # `verification_case`: VCs that verify it, from either direction — the VC's
    # own list, and the requirement's, since the UI writes both.
    for vc in vcs:
        for target in vc.get("verified_requirements") or []:
            covered_by[target].add(("verification_case", vc["id"]))
    for req in reqs:
        for vc_id in req.get("verification_cases") or []:
            covered_by[req["id"]].add(("verification_case", vc_id))

    # `analysis_case`: an analysis whose scope names the requirement. An empty
    # scope means "the whole project", so it covers every requirement.
    for a in analyses:
        scope = a.get("scope") or []
        targets = scope if scope else [r["id"] for r in reqs]
        for target in targets:
            covered_by[target].add(("analysis_case", a["id"]))

    for req in reqs:
        rid = req["id"]

        # `child_requirement`: decomposition, via parent links and the
        # explicit refine/derive relations that mean the same thing.
        parent = req.get("parent")
        if parent and parent in req_map:
            covered_by[parent].add(("child_requirement", rid))
        for rel in req.get("relations", []):
            if rel.get("type") in ("refines", "derives"):
                covered_by[rel["target"]].add(("child_requirement", rid))

        # `reference`: any attached external reference. Keyed by requirement id
        # — the previous code keyed these by ``ref["path"]``, so they landed
        # under a filesystem path that is never a requirement id and could not
        # count towards anything.
        if req.get("references"):
            covered_by[rid].add(("reference", rid))

    return {
        "req_map": req_map,
        "covered_by": dict(covered_by),
    }


def shallow_status(req: dict, graph: dict) -> dict:
    rid = req["id"]
    needs = set(req.get("needs", []))
    covered = graph.get("covered_by", {}).get(rid, set())
    covered_types = set()
    for ctype, _ in covered:
        covered_types.add(ctype)

    uncovered = needs - covered_types
    unwanted = covered_types - needs

    return {
        "id": rid,
        "name": req.get("name", ""),
        "needs": sorted(needs),
        "covered_types": sorted(covered_types),
        "uncovered_types": sorted(uncovered),
        "unwanted_coverage": sorted(unwanted),
        "shallow": len(uncovered) == 0,
    }


MAX_DEPTH = 1000


def deep_status(req: dict, graph: dict, memo: dict | None = None, visiting: set | None = None, depth: int = 0) -> bool:
    if depth > MAX_DEPTH:
        cast(dict, memo)[req["id"]] = False if memo is not None else False
        return False
    if memo is None:
        memo = {}
    if visiting is None:
        visiting = set()
    rid = req["id"]

    if rid in memo:
        return memo[rid]
    if rid in visiting:
        memo[rid] = False
        return False

    shallow = shallow_status(req, graph)
    if not shallow["shallow"]:
        memo[rid] = False
        return False

    needs = set(req.get("needs", []))
    if not needs:
        memo[rid] = True
        return True

    visiting.add(rid)
    req_map = graph.get("req_map", {})
    covered = graph.get("covered_by", {}).get(rid, set())

    # Only decomposition recurses. The other obligations are satisfied by
    # artifacts that are not requirements — a component, a verification case,
    # an analysis — and have no coverage of their own to be deep about. The
    # previous code looked every covering id up in req_map and skipped the
    # misses, which happened to work only because every covering id *was* a
    # requirement then.
    all_covered_deep = True
    for ctype, source_id in covered:
        if ctype != "child_requirement":
            continue
        source_req = req_map.get(source_id)
        if source_req is None:
            continue
        if not deep_status(source_req, graph, memo, visiting, depth + 1):
            all_covered_deep = False
            break

    visiting.discard(rid)
    memo[rid] = all_covered_deep
    return all_covered_deep


def all_links(store) -> list[dict]:
    """Every declared relationship in the project, one dict per edge.

    -> [{"source": str, "target": str, "type": str, "holder": str,
         "target_collection": str, "stored": bool}]
    """
    edges: dict[tuple[str, str, str], dict] = {}

    # Registry-derived edges.
    for link in LINKS:
        if link.tree:
            continue
        try:
            items = store.list_items(link.holder)
        except Exception:
            continue
        for item in items:
            source_id = item.get("id", "")
            if not source_id:
                continue
            for target_id in targets_of(item, link):
                key = (source_id, target_id, link.label)
                if key not in edges:
                    edges[key] = {
                        "source": source_id,
                        "target": target_id,
                        "type": link.label,
                        "holder": link.holder,
                        "target_collection": link.target,
                        "stored": False,
                    }

    # Hand-authored traces (stored: True).  The overwrite means a stored edge
    # is never masked by a derived twin.
    traces = store.read_traces()
    for link in traces.get("links", []):
        key = (link["source"], link["target"], link["type"])
        edges[key] = {
            "source": link["source"],
            "target": link["target"],
            "type": link["type"],
            "holder": "traces",
            "target_collection": "traces",
            "stored": True,
        }

    result = sorted(edges.values(), key=lambda e: (e["source"], e["target"], e["type"]))
    return result


def trace_all(store) -> list[dict]:
    graph = _build_coverage_graph(store)
    memo: dict = {}
    results = []
    reqs = store.list_requirements()
    vcs = store.list_verification_cases()
    attach_verification_cases(store, reqs, vcs)
    for r in reqs:
        if r.get("normative", True) is False:
            continue
        shallow = shallow_status(r, graph)
        deep = deep_status(r, graph, memo)
        results.append({
            **shallow,
            "deep": deep,
            "broken_chain": shallow["shallow"] and not deep,
        })
    return results
