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
