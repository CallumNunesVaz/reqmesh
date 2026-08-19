"""Cross-entity link integrity: the registry, delete protection, backlinks and
the single-owner verify relationship.

The two defects at the top were both reproducible through the public API on
seeded data before this work; they are the reason the rest of it exists.
"""

import pytest

from app.services import link_registry as lr
from app.services.verification_links import cases_for, repair_asymmetry


@pytest.fixture
def wired(client, project):
    """A project with one requirement cited from every direction."""
    p = project
    client.post(f"/api/projects/{p}/requirements", json={"id": "R1", "name": "Load case"})
    client.post(f"/api/projects/{p}/requirements", json={"id": "R2", "name": "Other"})
    # The *Create* models don't all accept their link field, so the links are
    # set with a follow-up update — which is how the UI does it too.
    client.post(f"/api/projects/{p}/verification", json={"id": "VC1", "name": "Static test"})
    client.put(f"/api/projects/{p}/verification/VC1", json={"verified_requirements": ["R1"]})
    client.post(f"/api/projects/{p}/specifications", json={"id": "SP1", "name": "Spec"})
    client.put(f"/api/projects/{p}/specifications/SP1", json={"requirements": ["R1"]})
    client.post(f"/api/projects/{p}/risks", json={"id": "RK1", "title": "Risk"})
    client.put(f"/api/projects/{p}/risks/RK1", json={"linked_requirements": ["R1"]})
    client.post(f"/api/projects/{p}/decisions", json={"id": "DC1", "title": "Decision"})
    client.put(f"/api/projects/{p}/decisions/DC1", json={"linked_requirements": ["R1"]})
    client.post(f"/api/projects/{p}/change-requests", json={"id": "CR1", "title": "CR"})
    client.put(f"/api/projects/{p}/change-requests/CR1", json={"affected_requirements": ["R1"]})
    return p


# ── The two defects from the design note ─────────────────────────────────────

def test_deleting_a_cited_requirement_is_refused(client, wired):
    """Was: DELETE returned 200 and left five records pointing at a dead id,
    of which only the component ones were ever reported."""
    res = client.delete(f"/api/projects/{wired}/requirements/R1")
    assert res.status_code == 409

    detail = res.json()["detail"]
    holders = {r["holder"] for r in detail["referrers"]}
    assert holders == {"verification_cases", "specifications", "risks",
                       "decisions", "change_requests"}
    assert "force=true" in detail["message"]
    # and it is still there
    assert client.get(f"/api/projects/{wired}/requirements/R1").status_code == 200


def test_force_deletes_and_the_result_is_reported_as_dangling(client, wired):
    assert client.delete(f"/api/projects/{wired}/requirements/R1?force=true").status_code == 200
    assert client.get(f"/api/projects/{wired}/requirements/R1").status_code == 404

    issues = client.get(f"/api/projects/{wired}/validate").json()["issues"]
    dangling = [i for i in issues if i["type"] == "dangling_reference" and i["target"] == "R1"]
    assert {d["holder"] for d in dangling} == {
        "verification_cases", "specifications", "risks", "decisions", "change_requests"}


def test_uncited_requirement_deletes_without_force(client, wired):
    assert client.delete(f"/api/projects/{wired}/requirements/R2").status_code == 200


def test_the_verify_link_cannot_be_desynced_from_the_requirement_side(client, wired):
    """Was: PUT verification_cases=[] returned 200, cleared the requirement's
    list, left the case still claiming it, and no check reported the mismatch."""
    assert client.get(f"/api/projects/{wired}/requirements/R1").json()["verification_cases"] == ["VC1"]

    client.put(f"/api/projects/{wired}/requirements/R1", json={"verification_cases": []})

    req = client.get(f"/api/projects/{wired}/requirements/R1").json()
    vc = client.get(f"/api/projects/{wired}/verification/VC1").json()
    assert req["verification_cases"] == []
    assert vc["verified_requirements"] == []          # the owner changed too


def test_the_verify_link_can_be_set_from_the_requirement_side(client, wired):
    client.put(f"/api/projects/{wired}/requirements/R2", json={"verification_cases": ["VC1"]})
    vc = client.get(f"/api/projects/{wired}/verification/VC1").json()
    assert set(vc["verified_requirements"]) == {"R1", "R2"}


def test_requirement_side_follows_an_edit_to_the_owning_case(client, wired):
    client.put(f"/api/projects/{wired}/verification/VC1",
               json={"verified_requirements": ["R2"]})
    assert client.get(f"/api/projects/{wired}/requirements/R1").json()["verification_cases"] == []
    assert client.get(f"/api/projects/{wired}/requirements/R2").json()["verification_cases"] == ["VC1"]


# ── Registry ─────────────────────────────────────────────────────────────────

def test_every_link_names_a_real_collection():
    from app.services.yaml_store import COLLECTIONS
    for ln in lr.LINKS:
        assert ln.holder in COLLECTIONS, ln
        assert ln.target in COLLECTIONS, ln


def test_targets_of_tolerates_hand_edited_yaml():
    link = next(ln for ln in lr.LINKS if ln.holder == "risks")
    assert lr.targets_of({}, link) == []
    assert lr.targets_of({"linked_requirements": None}, link) == []
    assert lr.targets_of({"linked_requirements": "R1"}, link) == ["R1"]      # bare string
    assert lr.targets_of({"linked_requirements": ["R1", "", "  "]}, link) == ["R1"]


def test_find_referrers_ignores_self_reference(client, project):
    client.post(f"/api/projects/{project}/requirements", json={"id": "S1", "name": "x"})
    from app.core.dependencies import get_store
    store = get_store(project)
    assert lr.find_referrers(store, "requirements", "S1") == []


def test_a_clean_project_has_no_dangling_references(client, wired):
    from app.core.dependencies import get_store
    assert lr.find_dangling(get_store(wired)) == []


# ── Backlinks ────────────────────────────────────────────────────────────────

def test_backlinks_groups_referrers_by_kind(client, wired):
    data = client.get(f"/api/projects/{wired}/entities/R1/backlinks").json()
    assert data["collection"] == "requirements"
    assert data["total"] == 5
    by_coll = {g["collection"]: g for g in data["groups"]}
    assert by_coll["risks"]["items"][0]["id"] == "RK1"
    assert by_coll["risks"]["items"][0]["label"] == "threatens"
    assert by_coll["specifications"]["label"] == "specification"


def test_backlinks_404s_for_an_unknown_entity(client, wired):
    assert client.get(f"/api/projects/{wired}/entities/NOPE/backlinks").status_code == 404


def test_backlinks_works_for_a_verification_case(client, wired):
    client.post(f"/api/projects/{wired}/components", json={
        "id": "C1", "name": "Wing", "verification_cases": ["VC1"]})
    data = client.get(f"/api/projects/{wired}/entities/VC1/backlinks").json()
    assert data["collection"] == "verification_cases"
    assert [g["collection"] for g in data["groups"]] == ["components"]


# ── Asymmetry detection and repair ───────────────────────────────────────────

def test_asymmetric_allocation_is_reported(client, wired):
    """allocated_to is derived from component.satisfies; if a write path ever
    skips the sync the two disagree, and nothing used to notice."""
    client.post(f"/api/projects/{wired}/components", json={
        "id": "C1", "name": "Wing", "satisfies": ["R1"]})
    client.put(f"/api/projects/{wired}/requirements/R1", json={"allocated_to": "Nonsense"})

    issues = client.get(f"/api/projects/{wired}/validate").json()["issues"]
    asym = [i for i in issues if i["type"] == "asymmetric_link" and i["id"] == "R1"]
    assert len(asym) == 1
    assert asym[0]["found"] == ["Nonsense"]
    assert asym[0]["expected"] == ["Wing"]


def test_repair_recovers_a_requirement_side_link_rather_than_dropping_it(client, wired):
    """A project written before the case owned the link may hold entries only
    on the requirement. Truncating would delete real traceability."""
    from app.core.dependencies import get_store
    store = get_store(wired)
    store.update_requirement("R2", {"verification_cases": ["VC1"]})   # store-level, bypasses sync

    assert cases_for("R2", store.list_verification_cases()) == []
    result = repair_asymmetry(store)
    assert result == {"cases_updated": 1, "links_recovered": 1}
    assert cases_for("R2", store.list_verification_cases()) == ["VC1"]


# ── Suspect links across entity types ────────────────────────────────────────

def test_editing_a_reviewed_requirement_flags_the_documents_built_on_it(client, wired):
    """Only requirement-to-requirement relations were flagged before, so a
    specification containing a changed requirement was never marked stale."""
    client.post(f"/api/projects/{wired}/suspect-links/clear")      # review everything
    assert client.get(f"/api/projects/{wired}/suspect-links").json()["count"] == 0

    client.put(f"/api/projects/{wired}/requirements/R1", json={"description": "changed"})

    links = client.get(f"/api/projects/{wired}/suspect-links").json()["links"]
    assert {l["source"] for l in links} >= {"SP1", "RK1", "DC1", "CR1", "VC1"}
    spec = next(l for l in links if l["source"] == "SP1")
    assert spec["target"] == "R1" and spec["source_collection"] == "specifications"


def test_an_unreviewed_project_is_not_flagged_wholesale(client, wired):
    """Treating never-reviewed as suspect would flag every citation in a new
    project, and a signal that is always on is ignored."""
    assert client.get(f"/api/projects/{wired}/suspect-links").json()["count"] == 0


# ── Relations are polymorphic, so they are not registry rows ──────────────────
#
# A Relation.target may name a requirement *or* a verification case. The registry
# declares one fixed target collection per row, so relations cannot be a row:
# doing so makes the delete guard block on them and makes the integrity checker
# report a `verified_by` -> verification case link as dangling. Rename sweeps
# relation targets locally instead; these tests pin that the registry's other
# consumers did not change with it.

def test_deleting_a_relation_target_does_not_require_force(client, project):
    """Deleting a requirement cited only by a relation is a plain delete."""
    client.post(f"/api/projects/{project}/requirements", json={"id": "REQ-A", "name": "a"})
    client.post(f"/api/projects/{project}/requirements", json={"id": "REQ-B", "name": "b",
                "relations": [{"type": "refines", "target": "REQ-A"}]})

    res = client.delete(f"/api/projects/{project}/requirements/REQ-A")
    assert res.status_code == 200, res.text
    assert client.get(f"/api/projects/{project}/requirements/REQ-A").status_code == 404


def test_a_verified_by_relation_to_a_verification_case_is_not_dangling(client, project):
    """A relation to an existing verification case is valid, not a dangling
    requirement reference."""
    client.post(f"/api/projects/{project}/verification",
                json={"id": "VC-1", "name": "v", "method": "test"})
    client.post(f"/api/projects/{project}/requirements", json={"id": "REQ-A", "name": "a",
                "relations": [{"type": "verified_by", "target": "VC-1"}]})

    issues = client.get(f"/api/projects/{project}/validate").json()["issues"]
    assert not any(i["type"] == "dangling_reference" for i in issues), issues


def test_a_relation_to_an_id_in_no_collection_is_still_dangling(client, project):
    """Removing the relation row must not make relations invisible to the
    integrity checker — a target that resolves nowhere is still reported."""
    from app.core.dependencies import get_store
    store = get_store(project)
    client.post(f"/api/projects/{project}/requirements", json={"id": "REQ-A", "name": "a"})
    store.update_requirement("REQ-A", {"relations": [{"type": "refines", "target": "GHOST9999"}]})

    issues = client.get(f"/api/projects/{project}/validate").json()["issues"]
    assert any(i["type"] == "dangling_link" for i in issues), issues
