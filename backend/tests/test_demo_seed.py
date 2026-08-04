"""The bundled demo project must be valid against the models it ships with.

Every new install is seeded with this project, and it is the first thing anyone
sees. It had drifted badly from the app around it:

  * 26 requirements typed ``design`` and one ``constraint`` — a vocabulary
    removed from ``RequirementType``. The type dropdown had no such option, so
    those requirements displayed as "Functional" and the next save of any field
    silently rewrote them.
  * risks carried the pre-matrix free-text ``probability``, so the whole
    register rated only through a legacy compatibility mapping;
  * ``linked_requirements`` was hardcoded to ``[]`` by the writer, discarding
    what the register declared, so every risk looked untraced;
  * 55 requirements carried stakeholder priority scores while the project
    defined no stakeholders, so the weighted-value ranking returned nothing.

None of that failed a test, because nothing checked the demo against the models.
These do.
"""

import pytest

from app.models.requirement import (
    Priority, RequirementStatus, RequirementType, VerificationMethod,
)
from app.services.demo_seed import seed_demo_project
from app.services.risk_matrix import DEFAULT_LIKELIHOODS, apply_rating, normalize_matrix
from app.services.yaml_store import YamlStore


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    root = tmp_path_factory.mktemp("demo") / "projects"
    root.mkdir(parents=True)
    seed_demo_project(root)
    return YamlStore(next(p for p in root.iterdir() if p.is_dir()))


def test_every_requirement_uses_the_current_vocabulary(demo):
    valid = {e.value for e in RequirementType}
    offenders = sorted({r["type"] for r in demo.list_requirements() if r.get("type") not in valid})
    assert offenders == [], (
        f"demo requirements use types the enum does not have: {offenders} — the UI "
        "cannot offer them, and opening such a requirement rewrites it on save"
    )


def test_requirement_enums_are_all_current(demo):
    reqs = demo.list_requirements()
    assert reqs, "the demo seeded no requirements"
    for field, enum in (
        ("status", RequirementStatus),
        ("priority", Priority),
        ("verification_method", VerificationMethod),
    ):
        valid = {e.value for e in enum}
        bad = sorted({r.get(field) for r in reqs if r.get(field) not in valid})
        assert bad == [], f"invalid {field} values in the demo: {bad}"


def test_the_demo_shows_off_more_than_one_type(demo):
    """A floor, not a fact.

    The remap could have been done by pointing everything at one valid type,
    which would pass the check above while making the demo less useful than
    before. The demo should exercise the vocabulary it advertises.
    """
    kinds = {r["type"] for r in demo.list_requirements()}
    assert len(kinds) >= 6, f"demo only exercises {sorted(kinds)}"
    assert any(k.startswith("non_functional") for k in kinds)


def test_risks_rate_natively_through_the_matrix(demo):
    risks = demo.list_items("risks")
    assert risks
    for r in risks:
        assert r.get("likelihood") in DEFAULT_LIKELIHOODS, (
            f"{r['id']} does not carry a matrix likelihood: {r.get('likelihood')!r} "
            "(the legacy free-text `probability` only works via a compatibility map)"
        )
        assert "probability" not in r, f"{r['id']} still carries the legacy probability field"

    rated = apply_rating(risks, normalize_matrix(demo.read_meta().get("risk_matrix")))
    assert all(r["rating"]["band"] for r in rated), "a demo risk is unrateable"


def test_risks_are_traced_to_the_requirements_they_threaten(demo):
    """The writer used to hardcode this to [], so the register looked untraced."""
    req_ids = {r["id"] for r in demo.list_requirements()}
    risks = demo.list_items("risks")
    assert all(r.get("linked_requirements") for r in risks), "a demo risk links to nothing"
    for r in risks:
        dangling = [x for x in r["linked_requirements"] if x not in req_ids]
        assert dangling == [], f"{r['id']} links to missing requirements: {dangling}"


def test_the_risk_register_is_not_uniformly_open(demo):
    """Every risk sitting at `open` says nothing about how risk is managed."""
    statuses = {r.get("status") for r in demo.list_items("risks")}
    assert len(statuses) >= 3, f"demo risk statuses are all but identical: {statuses}"


def test_stakeholder_scores_have_stakeholders_to_weight_against(demo):
    from app.api.router import normalize_stakeholders
    from app.services.stakeholder_value import rank_requirements

    stakeholders = normalize_stakeholders(demo.read_meta().get("stakeholders", []))
    assert stakeholders, "the demo scores requirements against stakeholders it never defines"

    reqs = demo.list_requirements()
    scored = [r for r in rank_requirements(reqs, stakeholders) if r["value"] is not None]
    assert len(scored) > len(reqs) // 2, (
        f"only {len(scored)} of {len(reqs)} requirements rank — the backlog and "
        "value views would be nearly empty"
    )

    # Every name used on a requirement must be one the project declares, or the
    # score is silently ignored.
    declared = {s["name"] for s in stakeholders}
    used = {name for r in reqs for name in (r.get("priorities") or {})}
    assert used - declared == set(), f"scores against undeclared stakeholders: {used - declared}"


def test_the_seeded_project_is_structurally_sound(demo):
    from app.services.integrity import IntegrityChecker

    issues = IntegrityChecker(demo).check_all()["issues"]
    fatal = [i for i in issues if i["type"] in
             {"dangling_reference", "asymmetric_link", "corrupt_file", "orphan"}]
    assert fatal == [], f"demo project has structural problems: {fatal[:5]}"


# ── Baseline / status / verification spread tests (§2–§6) ──────────────────────


def test_requirement_status_is_not_uniform(demo):
    """Every workflow state appears, with the counts from the contract (§2)."""
    from app.models.requirement import RequirementStatus

    reqs = demo.list_requirements()
    counts = {s.value: 0 for s in RequirementStatus}
    for r in reqs:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    missing = [s for s, c in counts.items() if c == 0]
    assert missing == [], f"workflow states never used in the demo: {missing}"

    assert counts["proposed"] >= 2, "need >= 2 proposed"
    assert counts["in_review"] >= 2, "need >= 2 in_review"
    assert counts["approved"] >= 2, "need >= 2 approved"
    assert counts["implemented"] >= 2, "need >= 2 implemented"
    assert counts["verified"] >= 2, "need >= 2 verified"
    assert counts["rejected"] == 1, f"need exactly 1 rejected, got {counts['rejected']}"
    assert counts["deprecated"] == 1, f"need exactly 1 deprecated, got {counts['deprecated']}"


def test_every_status_is_in_the_workflow(demo):
    """A state the workflow does not allow would break the transition UI."""
    meta = demo.read_meta()
    valid = set(meta.get("workflow", {}).get("states", []))
    reqs = demo.list_requirements()
    used = {r["status"] for r in reqs}
    bad = used - valid
    assert bad == set(), f"requirements use states not in the workflow: {bad}"


def test_baselines_are_defined_in_meta(demo):
    """Four baseline definitions, in sequence order, ascending due dates, no order key."""
    meta = demo.read_meta()
    baselines = meta.get("baselines", [])
    assert len(baselines) == 4, f"expected 4 baselines, got {len(baselines)}"

    names = [b["name"] for b in baselines]
    assert names == ["SRR", "PDR", "CDR", "TRR"], f"wrong order or names: {names}"

    dates = []
    for b in baselines:
        assert "order" not in b, f"{b['name']} carries an 'order' key"
        assert b.get("due_date"), f"{b['name']} has no due_date"
        dates.append(b["due_date"])

    assert dates == sorted(dates), f"due dates not ascending: {dates}"


def test_every_baseline_name_is_defined(demo):
    """Every name in any requirement.baselines is a defined baseline."""
    meta = demo.read_meta()
    defined = {b["name"] for b in meta.get("baselines", [])}
    reqs = demo.list_requirements()
    for r in reqs:
        for bl in r.get("baselines", []):
            assert bl in defined, f"{r['id']} references undefined baseline {bl!r}"


def test_baseline_membership_spread(demo):
    """At least 40 baselined, at least 8 not, each baseline on ≥ 6 requirements."""
    meta = demo.read_meta()
    defined = {b["name"] for b in meta.get("baselines", [])}
    reqs = demo.list_requirements()

    baselined = [r for r in reqs if r.get("baselines")]
    unbaselined = [r for r in reqs if not r.get("baselines")]
    assert len(baselined) >= 40, f"only {len(baselined)} baselined (need ≥ 40)"
    assert len(unbaselined) >= 8, f"only {len(unbaselined)} unbaselined (need ≥ 8)"

    for name in defined:
        members = sum(1 for r in reqs if name in (r.get("baselines") or []))
        assert members >= 6, f"baseline {name!r} has only {members} members (need ≥ 6)"


def test_verification_case_statuses_varied(demo):
    """All four statuses appear, with the counts from §4."""
    vcs = demo.list_verification_cases()
    counts = {"failed": 0, "pending": 0, "in_progress": 0, "passed": 0}
    for vc in vcs:
        s = vc.get("status", "pending")
        counts[s] = counts.get(s, 0) + 1

    missing = [s for s, c in counts.items() if c == 0]
    assert missing == [], f"verification statuses never used: {missing}"

    assert counts["passed"] >= 3, f"need ≥ 3 passed, got {counts['passed']}"
    assert counts["failed"] >= 1, f"need ≥ 1 failed, got {counts['failed']}"
    assert counts["in_progress"] >= 2, f"need ≥ 2 in_progress, got {counts['in_progress']}"


def test_verification_case_results_where_expected(demo):
    """passed and failed carry a result; pending and in_progress do not."""
    vcs = demo.list_verification_cases()
    for vc in vcs:
        s = vc.get("status", "pending")
        if s in ("passed", "failed"):
            assert vc.get("result"), f"{vc['id']} is {s} but has no result"
        else:
            assert vc.get("result") is None, f"{vc['id']} is {s} but has a result"


def test_reviewed_fingerprints_on_settled_work(demo):
    """SRR/PDR requirements have a reviewed fingerprint; the rest do not."""
    from app.services.fingerprint import compute_fingerprint

    meta = demo.read_meta()
    baselines = meta.get("baselines", [])
    # Determine which baseline names represent SRR/PDR
    srr_pdr = {b["name"] for b in baselines if b["name"] in ("SRR", "PDR")}

    reqs = demo.list_requirements()
    for r in reqs:
        in_srr_pdr = bool(set(r.get("baselines", [])) & srr_pdr)
        if in_srr_pdr:
            stored = r.get("reviewed")
            assert stored is not None, f"{r['id']} in SRR/PDR but reviewed is None"
            current = compute_fingerprint(r)
            assert stored == current, (
                f"{r['id']} reviewed fingerprint {stored!r} != current {current!r}"
            )
        else:
            assert r.get("reviewed") is None, f"{r['id']} not in SRR/PDR but has a reviewed fingerprint"


def test_frozen_baselines(demo):
    """SRR and PDR exist as frozen items; CDR and TRR do not."""
    srr = demo.get_item("baselines", "SRR")
    pdr = demo.get_item("baselines", "PDR")
    cdr = demo.get_item("baselines", "CDR")
    trr = demo.get_item("baselines", "TRR")

    assert srr is not None, "SRR baseline is not frozen"
    assert pdr is not None, "PDR baseline is not frozen"
    assert cdr is None, "CDR should not be frozen"
    assert trr is None, "TRR should not be frozen"

    for frozen in (srr, pdr):
        assert frozen.get("frozen") is True, f"{frozen['name']} is not marked frozen"
        assert frozen.get("frozen_at"), f"{frozen['name']} has no frozen_at"
        snapshot = frozen.get("snapshot", {})
        reqs = demo.list_requirements()
        assert len(snapshot) == len(reqs), (
            f"{frozen['name']} snapshot has {len(snapshot)} reqs, expected {len(reqs)}"
        )


def test_srr_snapshot_drift(demo):
    """The SRR snapshot differs from the live requirements for exactly four ids."""
    srr = demo.get_item("baselines", "SRR")
    assert srr is not None, "SRR baseline missing"

    snapshot = srr["snapshot"]
    reqs = {r["id"]: r for r in demo.list_requirements()}

    diffs = []
    for rid, snap in snapshot.items():
        live = reqs.get(rid)
        if live is None:
            continue
        for field in ["status", "priority", "name", "description"]:
            if snap.get(field) != live.get(field):
                diffs.append(rid)
                break

    changed_ids = sorted(set(diffs))
    assert len(changed_ids) == 4, (
        f"expected 4 drifted ids in SRR snapshot, got {len(changed_ids)}: {changed_ids}"
    )


def test_attributes_on_requirements(demo):
    """At least 6 requirements carry attributes (§7)."""
    reqs = demo.list_requirements()
    with_attrs = [r for r in reqs if r.get("attributes")]
    assert len(with_attrs) >= 6, (
        f"only {len(with_attrs)} requirements have attributes (need ≥ 6)"
    )


def test_scores_are_zero_to_five_and_not_all_identical(demo):
    """Every priority score is in 0..5, and the demo shows a spread."""
    reqs = demo.list_requirements()
    scores: set[int] = set()
    for r in reqs:
        for name, score in (r.get("priorities") or {}).items():
            assert isinstance(score, int), (
                f"{r['id']} priorities[{name!r}] = {score!r} is not an int"
            )
            assert 0 <= score <= 5, (
                f"{r['id']} priorities[{name!r}] = {score} is outside 0..5"
            )
            scores.add(score)
    # The demo must still show a spread — not every score the same.
    assert len(scores) >= 3, (
        f"demo priority scores are too uniform: only values {sorted(scores)}"
    )
