"""Naming standards: generation, enforcement, and the update/import carve-outs.

The naming standard (Project Settings → Naming Standards) defines an id pattern
for six entity kinds. This module covers the contract that makes the standard
real: a generator for every kind, enforcement on create only (with the
per-project ``enforce`` escape hatch), and the explicit exemptions (update,
import, the seeder) that keep legacy projects usable.

The shared ``project`` fixture in ``conftest.py`` disables enforcement so the
rest of the suite can keep its readable hand-written ids; the tests here that
care about enforcement turn it back on explicitly.
"""
from __future__ import annotations

import pytest

from app.core.dependencies import get_store
from app.services import naming


@pytest.fixture()
def enforced_project(client, project):
    """The shared fixture opts out of enforcement; turn it back on."""
    client.patch(f"/api/projects/{project}", json={"naming": {"enforce": True}})
    return project


# ── Enforcement: the carve-out that matters most ──────────────────────────────

def test_update_an_entity_with_a_legacy_id_succeeds(client, enforced_project):
    """Updating a record whose id predates the naming standard must keep working.

    Enforcement is create-only, so this succeeds *with* enforcement on. A
    migration that started 422-ing on every update of a legacy id is a far worse
    bug than the one being fixed, so this regression is the first test.
    """
    store = get_store(enforced_project)
    store.create_requirement({"id": "LEGACY-NO-NUMBER", "name": "Old name"})

    res = client.put(
        f"/api/projects/{enforced_project}/requirements/LEGACY-NO-NUMBER",
        json={"name": "Edited name"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["name"] == "Edited name"


def test_update_keeps_a_legacy_verification_id_after_edit(client, enforced_project):
    store = get_store(enforced_project)
    store.create_verification_case({"id": "LEGACYVC", "name": "Old"})

    res = client.put(
        f"/api/projects/{enforced_project}/verification/LEGACYVC",
        json={"status": "passed"},
    )
    assert res.status_code == 200, res.text


# ── Generator ─────────────────────────────────────────────────────────────────

def test_generator_defaults_for_all_six_kinds(client, project):
    """No per-kind ``naming`` config → the documented settings-page defaults."""
    store = get_store(project)
    meta = store.read_meta()
    expected = {
        "requirements": "REQ0001",
        "components": "COMP0001",
        "verification": "VC0001",
        "risks": "RSK00001",
        "change_requests": "CR000001",
        "specifications": "SPEC-aaaa",
    }
    for kind, want in expected.items():
        got = naming.next_id(naming.ids_for(store, kind), meta, kind)["next_id"]
        assert got == want, kind


def test_generator_honors_custom_prefix_separator_and_length(client, project):
    meta = {
        "naming": {
            "risks": {
                "prefix_hint": "HAZ", "prefix_length": 3, "separator": "-",
                "suffix_length": 3, "suffix_type": "numeric",
            }
        }
    }
    got = naming.next_id(["HAZ-001", "HAZ-002"], meta, "risks")
    assert got == {"prefix": "HAZ", "next_id": "HAZ-003"}


def test_alphanumeric_suffix_carries(client, project):
    """``aaaz`` → ``aaba`` — the lexical carry the settings preview implies."""
    meta = {}
    assert naming.next_id(["SPEC-aaaz"], meta, "specifications")["next_id"] == "SPEC-aaba"
    assert naming.next_id(["SPEC-aazz"], meta, "specifications")["next_id"] == "SPEC-abaa"


def test_alphanumeric_suffix_exhausts_the_configured_width(client, project):
    """Running out of width widens the id rather than colliding or erroring."""
    meta = {}
    assert naming.next_id(["SPEC-zzzz"], meta, "specifications")["next_id"] == "SPEC-baaaa"


def test_legacy_ids_do_not_push_the_counter(client, project):
    """Ids that do not match the scheme are ignored, not errors."""
    meta = {}
    got = naming.next_id(["REQ0001", "MIGRATED-LEGACY", "REQ-OLD", "X9"], meta, "requirements")
    assert got["next_id"] == "REQ0002"


def test_generator_never_returns_an_existing_id(client, project):
    meta = {}
    # A legacy id occupying the computed slot must not be re-suggested.
    got = naming.next_id(["REQ0001", "REQ0002", "REQ0003"], meta, "requirements")
    assert got["next_id"] == "REQ0004"


# ── Generator over the wire ───────────────────────────────────────────────────

@pytest.mark.parametrize("kind,want", [
    ("requirements", "REQ0001"),
    ("components", "COMP0001"),
    ("verification", "VC0001"),
    ("risks", "RSK00001"),
    ("change_requests", "CR000001"),
    ("specifications", "SPEC-aaaa"),
])
def test_next_id_route_for_each_kind(client, project, kind, want):
    res = client.get(f"/api/projects/{project}/{kind}/next-id")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["next_id"] == want
    assert "prefix" in body


def test_next_id_route_rejects_unknown_kind(client, project):
    assert client.get(f"/api/projects/{project}/decisions/next-id").status_code == 404


def test_next_uid_route_unchanged(client, project):
    from tests.conftest import make_req
    make_req(client, project, "SYST0001", name="Parent")
    make_req(client, project, "SYST0002", name="Taken")
    res = client.get(f"/api/projects/{project}/requirements/next-uid?parent=SYST0001")
    assert res.status_code == 200
    assert res.json() == {"prefix": "SYST", "next_id": "SYST0003"}


# ── Enforcement on create ─────────────────────────────────────────────────────

def test_enforcement_defaults_on_when_naming_is_absent(client):
    """Absent ``naming`` means enforcement is on — a legacy-shaped id is 422."""
    client.post("/api/projects", json={"id": "fresh", "name": "Fresh"})
    res = client.post("/api/projects/fresh/components", json={"id": "WING", "name": "x"})
    assert res.status_code == 422, res.text
    assert "number" in res.json()["detail"].lower()


def test_enforce_false_accepts_legacy_ids(client, project):
    """The escape hatch: a migrated project accepts its legacy ids on create."""
    res = client.post(f"/api/projects/{project}/components", json={"id": "WING", "name": "x"})
    assert res.status_code == 201, res.text


def test_enforce_true_rejects_a_wrong_shape(client, enforced_project):
    res = client.post(f"/api/projects/{enforced_project}/components", json={"id": "WING", "name": "x"})
    assert res.status_code == 422, res.text
    assert "number" in res.json()["detail"].lower()


def test_toggling_enforce_through_patch_persists(client, project):
    # Off via the shared fixture.
    assert client.post(f"/api/projects/{project}/components", json={"id": "WING", "name": "x"}).status_code == 201
    # On — takes effect without a restart.
    assert client.patch(f"/api/projects/{project}", json={"naming": {"enforce": True}}).status_code == 200
    assert client.post(f"/api/projects/{project}/components", json={"id": "FUSE", "name": "x"}).status_code == 422
    # Persisted: a fresh read still sees it off-then-on.
    assert (get_store(project).read_meta().get("naming") or {}).get("enforce") is True
    # And back off again.
    assert client.patch(f"/api/projects/{project}", json={"naming": {"enforce": False}}).status_code == 200
    assert client.post(f"/api/projects/{project}/components", json={"id": "GDC", "name": "x"}).status_code == 201


def test_create_with_conforming_id_succeeds(client, enforced_project):
    res = client.post(f"/api/projects/{enforced_project}/components", json={"id": "COMP0001", "name": "Pump"})
    assert res.status_code == 201, res.text


@pytest.mark.parametrize("path,body", [
    ("requirements", {"id": "NOT-A-NUMBER", "name": "x"}),
    ("components", {"id": "NOT-A-NUMBER", "name": "x"}),
    ("verification", {"id": "NOT-A-NUMBER", "name": "x"}),
    ("risks", {"id": "NOT-A-NUMBER", "title": "x"}),
    ("change-requests", {"id": "NOT-A-NUMBER", "title": "x"}),
    ("specifications", {"id": "SPECNODASH", "name": "x"}),
])
def test_create_with_nonconforming_id_is_rejected(client, enforced_project, path, body):
    res = client.post(f"/api/projects/{enforced_project}/{path}", json=body)
    assert res.status_code == 422, res.text
    detail = res.json()["detail"]
    assert "number" in detail.lower() or "separator" in detail.lower() or "'-'" in detail


def test_specification_create_requires_the_separator(client, enforced_project):
    res = client.post(f"/api/projects/{enforced_project}/specifications", json={"id": "SPECNODASH", "name": "x"})
    assert res.status_code == 422
    assert "'-'" in res.json()["detail"]


def test_conforming_specification_create_succeeds(client, enforced_project):
    res = client.post(f"/api/projects/{enforced_project}/specifications", json={"id": "SPEC-aaaa", "name": "x"})
    assert res.status_code == 201, res.text


# ── Import is exempt ──────────────────────────────────────────────────────────

def test_import_full_of_nonconforming_ids_succeeds(client, enforced_project):
    csv = 'id,name\n"LEGACY-ONE",One\n"LEGACY-TWO",Two\n"PLAINLEGACY",Three\n'
    res = client.post(
        f"/api/projects/{enforced_project}/import",
        data={"text": csv, "format": "csv", "mode": "merge"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["created"] == 3


# ── The demo project conforms ─────────────────────────────────────────────────

def test_seeded_demo_conforms_and_has_no_dangling_references(tmp_path):
    """The bundled example must demonstrate the standard, not violate it.

    Every seeded id across all six kinds satisfies ``matches_scheme`` for its
    kind, and the project validates with no dangling references — so the demo
    cannot drift out of conformance later without this test catching it.
    """
    from app.services.demo_seed import seed_demo_project
    from app.services.integrity import IntegrityChecker
    from app.services.yaml_store import YamlStore

    assert seed_demo_project(tmp_path) is True
    store = YamlStore(tmp_path / "cessna-172")
    meta = store.read_meta()

    # The demo configures the standard explicitly, with enforcement on.
    assert (meta.get("naming") or {}).get("enforce") is True

    for kind in naming.KINDS:
        for rid in naming.ids_for(store, kind):
            assert naming.matches_scheme(rid, meta, kind) is None, (kind, rid)

    issues = IntegrityChecker(store).check_all().get("issues", [])
    dangling = [i for i in issues if "dangl" in i.get("type", "")]
    assert dangling == []
