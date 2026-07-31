"""The verify relationship, with one owner.

``verification_case.verified_requirements`` and
``requirement.verification_cases`` recorded the same relationship in two
places, written independently and reconciled by nothing. One ordinary PUT
desynced them, and nothing reported it: ``tracing.py`` unioned both sides so
coverage still looked right, while ``sysml_export.py`` read both and would emit
a verify relationship the requirement no longer claimed.

The verification case now owns the link. ``requirement.verification_cases`` is
derived from it on read — the same shape as ``requirement.allocated_to``, which
has been derived from ``component.satisfies`` since the allocation matrix was
built. Writes that arrive on the requirement side are translated into the
owning field so existing clients keep working.

The stored ``verification_cases`` key is left on disk rather than stripped: it
costs nothing, keeps older exports and hand-written YAML loadable, and
``repair_asymmetry`` can then bring a project into line in one pass instead of
the data being silently discarded on first read.
"""

from __future__ import annotations


def cases_for(requirement_id: str, vcs: list[dict]) -> list[str]:
    """The verification cases that claim to verify this requirement."""
    return sorted(
        vc["id"] for vc in vcs
        if requirement_id in (vc.get("verified_requirements") or [])
    )


def attach(store, requirements: list[dict], vcs: list[dict] | None = None) -> list[dict]:
    """Set ``verification_cases`` on each requirement from the owning side.

    Mutates in place and returns the list, matching ``apply_rating``.
    """
    if vcs is None:
        vcs = store.list_verification_cases()
    owned: dict[str, list[str]] = {}
    for vc in vcs:
        for req_id in (vc.get("verified_requirements") or []):
            owned.setdefault(req_id, []).append(vc["id"])
    for r in requirements:
        r["verification_cases"] = sorted(owned.get(r["id"], []))
    return requirements


def sync_from_requirement(store, requirement_id: str, case_ids: list[str]) -> None:
    """Apply a write that arrived on the requirement side to the owning cases.

    Adds the requirement to every case in ``case_ids`` and removes it from any
    other case that currently claims it, so setting the list to ``[]`` actually
    clears the relationship instead of leaving the owner untouched — which is
    exactly the divergence this module exists to remove.
    """
    wanted = set(case_ids or [])
    for vc in store.list_verification_cases():
        current = list(vc.get("verified_requirements") or [])
        has = requirement_id in current
        if vc["id"] in wanted and not has:
            current.append(requirement_id)
            store.update_verification_case(vc["id"], {"verified_requirements": current})
        elif vc["id"] not in wanted and has:
            store.update_verification_case(
                vc["id"],
                {"verified_requirements": [r for r in current if r != requirement_id]},
            )


def repair_asymmetry(store) -> dict:
    """Bring stored requirement-side lists into line with the owning cases.

    Union rather than truncate: where the two sides disagree the requirement's
    entry is a link somebody made through the requirement UI before the case
    owned it, so dropping it would delete real traceability. The union is
    written back to the cases, which then own it.
    """
    reqs = store.list_requirements()
    vcs = store.list_verification_cases()
    vc_ids = {v["id"] for v in vcs}

    additions: dict[str, set] = {}
    for r in reqs:
        for vc_id in (r.get("verification_cases") or []):
            if vc_id in vc_ids and r["id"] not in (
                next(v for v in vcs if v["id"] == vc_id).get("verified_requirements") or []
            ):
                additions.setdefault(vc_id, set()).add(r["id"])

    for vc_id, req_ids in additions.items():
        vc = next(v for v in vcs if v["id"] == vc_id)
        merged = sorted(set(vc.get("verified_requirements") or []) | req_ids)
        store.update_verification_case(vc_id, {"verified_requirements": merged})

    return {
        "cases_updated": len(additions),
        "links_recovered": sum(len(v) for v in additions.values()),
    }
