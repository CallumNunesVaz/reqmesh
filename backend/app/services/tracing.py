from __future__ import annotations

from collections import defaultdict


def _build_coverage_graph(store) -> dict:
    reqs = store.list_requirements()
    vcs = store.list_verification_cases()
    req_map = {r["id"]: r for r in reqs}

    covering: dict[str, set] = defaultdict(set)
    covered_by: dict[str, set] = defaultdict(set)

    for req in reqs:
        rid = req["id"]
        req_type = req.get("type", "functional")
        for rel in req.get("relations", []):
            target = rel["target"]
            covered_by[target].add((req_type, rid))

        for vc in vcs:
            vcid = vc["id"]
            for target in vc.get("verified_requirements", []):
                covered_by[target].add(("verification_case", vcid))

        for ref in req.get("references", []):
            ref_kind = ref.get("kind", "impl")
            covered_by[ref.get("path", "")].add((ref_kind, rid))

        parent = req.get("parent")
        if parent and parent in req_map:
            parent_type = req_map[parent].get("type", "functional")
            covered_by[parent].add((parent_type, rid))

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
        memo[req["id"]] = False if memo is not None else False
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

    all_covered_deep = True
    for ctype, source_id in covered:
        if ctype not in needs:
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


def trace_all(store) -> list[dict]:
    graph = _build_coverage_graph(store)
    memo: dict = {}
    results = []
    for r in store.list_requirements():
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
