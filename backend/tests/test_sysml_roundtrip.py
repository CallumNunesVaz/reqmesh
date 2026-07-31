"""The SysML v2 round-trip as a consistency oracle.

Export, re-import, and compare. Any relationship the model can hold but the
round-trip drops, duplicates or invents shows up as a difference here rather
than as a quietly wrong export weeks later.

This is the check that would have caught the verify-link divergence directly:
while ``requirement.verification_cases`` and
``verification_case.verified_requirements`` were written independently, the
exporter read both, so a desynced project exported a verify relationship the
requirement no longer claimed.
"""

from pathlib import Path

import pytest

from app.services.demo_seed import PROJECT_ID, seed_demo_project
from app.services.sysml_export import export_sysml_v2
from app.services.sysml_import import parse_sysml
from app.services.yaml_store import YamlStore


@pytest.fixture
def seeded(tmp_path):
    """The bundled demo project — 57 requirements, 80 components, 24 cases."""
    seed_demo_project(tmp_path, force=True)
    return YamlStore(tmp_path / PROJECT_ID)


def _verify_pairs(store):
    """(requirement, case) pairs the model holds, from the owning side."""
    return {
        (req_id, vc["id"])
        for vc in store.list_verification_cases()
        for req_id in (vc.get("verified_requirements") or [])
    }


def _satisfy_pairs(store):
    return {
        (req_id, c["id"])
        for c in store.list_components()
        for req_id in (c.get("satisfies") or [])
    }


def test_export_parses_back(seeded):
    parsed = parse_sysml(export_sysml_v2(seeded))
    assert parsed.get("requirements"), "export produced no re-importable requirements"


def test_every_requirement_survives_the_round_trip(seeded):
    before = {r["id"] for r in seeded.list_requirements()}
    after = {r["id"] for r in parse_sysml(export_sysml_v2(seeded)).get("requirements", [])}
    assert before - after == set(), f"dropped by the round trip: {sorted(before - after)}"


def test_the_export_emits_each_verify_relationship_exactly_once(seeded):
    """One line per relationship the model actually holds.

    The exporter used to emit each one twice: once correctly from the
    verification case, and once from inside the requirement as
    ``verify requirement <VC_ID>`` — backwards (in SysML a case verifies a
    requirement, not the reverse) and naming a verification case where a
    requirement id belongs. 34 relationships produced 68 lines, half of them
    pointing the wrong way at the wrong kind of entity.

    Line text may legitimately repeat across blocks, since two cases can
    verify the same requirement, so the count is what is asserted.
    """
    text = export_sysml_v2(seeded)
    emitted = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("verify ")]
    assert len(emitted) == len(_verify_pairs(seeded))

    # No verify line may name a verification case as its target.
    vc_ids = {vc["id"].replace("-", "_").replace(".", "_") for vc in seeded.list_verification_cases()}
    named = {ln.removeprefix("verify requirement ").rstrip(";") for ln in emitted}
    assert not (named & vc_ids), f"verify lines naming a verification case: {sorted(named & vc_ids)}"


def test_a_desynced_verify_link_cannot_reach_the_export(seeded):
    """Write a stale requirement-side list straight to the store, bypassing the
    API's sync, and confirm the export follows the owning case rather than the
    stale copy."""
    reqs = seeded.list_requirements()
    victim = next(r for r in reqs if r.get("verification_cases"))
    ghost = "VC-DOES-NOT-VERIFY-THIS"

    seeded.update_requirement(victim["id"], {"verification_cases": [ghost]})
    text = export_sysml_v2(seeded)

    assert ghost not in text, (
        "the export followed a stale requirement-side list instead of the "
        "verification case that owns the relationship"
    )


def test_satisfy_relationships_survive_the_round_trip(seeded):
    """part def X { satisfy requirement Y; } is how allocation is carried."""
    before = _satisfy_pairs(seeded)
    text = export_sysml_v2(seeded)
    assert before, "the demo project should have allocations to test"
    for req_id, comp_id in list(before)[:20]:
        assert req_id in text, f"{req_id} missing from the export entirely"


def test_round_trip_is_stable(seeded):
    """Exporting twice must produce identical text. An export that depends on
    dict or set iteration order produces spurious diffs in git, which is the
    thing a git-native tool can least afford."""
    assert export_sysml_v2(seeded) == export_sysml_v2(seeded)


def test_round_trip_does_not_invent_requirements(seeded):
    before = {r["id"] for r in seeded.list_requirements()}
    after = {r["id"] for r in parse_sysml(export_sysml_v2(seeded)).get("requirements", [])}
    assert after - before == set(), f"invented by the round trip: {sorted(after - before)}"
