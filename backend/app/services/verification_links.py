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


# Verification status, worst first. A requirement is only as verified as its
# weakest case: one failing case means the requirement is not met, however many
# others passed, and one case still pending means the answer is not yet in.
# Reporting the most advanced status instead would let a requirement read as
# verified while a case proving otherwise sat next to it.
_STATUS_PRECEDENCE = ("failed", "pending", "in_progress", "passed")

#: What a requirement's status is when nothing verifies it at all.
UNVERIFIED_STATUS = "pending"

#: What a requirement's method is when nothing verifies it at all. Matches the
#: previous stored default, so a requirement with no cases looks unchanged.
UNVERIFIED_METHOD = "test"


def group_cases_by_requirement(vcs: list[dict]) -> dict[str, list[dict]]:
    """Verification cases keyed by the requirement id each one verifies."""
    grouped: dict[str, list[dict]] = {}
    for vc in vcs:
        for req_id in (vc.get("verified_requirements") or []):
            grouped.setdefault(req_id, []).append(vc)
    return grouped


def derive_verification_from(mine: list[dict]) -> dict:
    """The derived fields, given only the cases that verify one requirement."""
    if not mine:
        return {
            "verification_status": UNVERIFIED_STATUS,
            "verification_method": UNVERIFIED_METHOD,
            "verification_methods": [],
        }

    statuses = {(vc.get("status") or "").strip().lower() for vc in mine}
    status = next(
        (s for s in _STATUS_PRECEDENCE if s in statuses),
        UNVERIFIED_STATUS,
    )
    methods = sorted({(vc.get("method") or "").strip().lower() for vc in mine if vc.get("method")})
    return {
        "verification_status": status,
        "verification_method": methods[0] if methods else UNVERIFIED_METHOD,
        "verification_methods": methods,
    }


def derive_verification(requirement_id: str, vcs: list[dict]) -> dict:
    """The verification status and method implied by the cases that verify this.

    Returns ``{"verification_status": str, "verification_method": str,
    "verification_methods": list[str]}``.

    ``verification_status`` is the worst status among the verifying cases, by
    :data:`_STATUS_PRECEDENCE`. An unrecognised status counts as ``pending``:
    the vocabulary is open on disk and an unknown value is not evidence of
    success.

    ``verification_methods`` is every distinct method, sorted — a requirement
    verified by both a test and an analysis genuinely has two.
    ``verification_method`` is the singular form kept for the many existing
    readers, and is the first of those; it is the *only* lossy part of this and
    is why the list is exposed alongside it.
    """
    return derive_verification_from(
        group_cases_by_requirement(vcs).get(requirement_id, [])
    )


def attach(store, requirements: list[dict], vcs: list[dict] | None = None) -> list[dict]:
    """Set the case-derived fields on each requirement from the owning side.

    Sets ``verification_cases``, ``verification_status``, ``verification_method``
    and ``verification_methods``. Mutates in place and returns the list,
    matching ``apply_rating``.

    The stored values for these keys are overwritten rather than merged. They
    were previously hand-set on the requirement and drifted from the cases that
    actually determine them — a requirement could read ``verified`` with every
    case pending.
    """
    if vcs is None:
        vcs = store.list_verification_cases()
    grouped = group_cases_by_requirement(vcs)
    for r in requirements:
        mine = grouped.get(r["id"], [])
        r["verification_cases"] = sorted(vc["id"] for vc in mine)
        r.update(derive_verification_from(mine))
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
