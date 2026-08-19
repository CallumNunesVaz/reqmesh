"""Renaming a requirement rewrites everything that referred to it.

An id here is the YAML filename, every child's parent pointer, and every
relation target in the project. Changing one and not the others is how a project
grows dangling traces that no page surfaces.
"""
from app.core.dependencies import get_store
from app.services.link_registry import links_into, targets_of
from tests.conftest import make_req


def _rename(client, project, req_id, new_id=None, cascade=None, dry_run=None):
    body = {} if new_id is None else {"new_id": new_id}
    if cascade is not None:
        body["cascade"] = cascade
    if dry_run is not None:
        body["dry_run"] = dry_run
    return client.post(f"/api/projects/{project}/requirements/{req_id}/rename", json=body)


def test_suggests_the_parents_prefix_and_next_free_slot(client, project):
    store = get_store(project)
    make_req(client, project, "SYST0001", name="Parent")
    make_req(client, project, "SYST0002", name="Taken")
    make_req(client, project, "OTHER0001", name="Moving")
    store.update_requirement("OTHER0001", {"parent": "SYST0001"})

    r = _rename(client, project, "OTHER0001")
    assert r.status_code == 200, r.text
    # SYST0001 and SYST0002 exist, so the next free slot is 3.
    assert r.json()["suggested"] == "SYST0003"


def test_rename_moves_the_record(client, project):
    make_req(client, project, "SYST0001", name="Original")

    r = _rename(client, project, "SYST0001", "SYST0042")
    assert r.status_code == 200, r.text
    assert r.json()["id"] == "SYST0042"

    store = get_store(project)
    assert store.get_requirement("SYST0001") is None
    assert store.get_requirement("SYST0042")["name"] == "Original"


def test_children_follow_the_new_id(client, project):
    store = get_store(project)
    make_req(client, project, "SYST0001", name="Parent")
    make_req(client, project, "SYST0002", name="Child")
    store.update_requirement("SYST0002", {"parent": "SYST0001"})

    r = _rename(client, project, "SYST0001", "SYST0099")
    assert r.status_code == 200, r.text
    assert r.json()["children"] == ["SYST0002"]
    assert store.get_requirement("SYST0002")["parent"] == "SYST0099"


def test_relations_pointing_at_the_old_id_are_rewritten(client, project):
    make_req(client, project, "SYST0001", name="Target")
    make_req(client, project, "SYST0002", name="Referrer",
             relations=[{"type": "refines", "target": "SYST0001"}])

    r = _rename(client, project, "SYST0001", "SYST0077")
    assert r.status_code == 200, r.text
    assert r.json()["relinked"] == ["SYST0002"]

    store = get_store(project)
    targets = {rel["target"] for rel in store.get_requirement("SYST0002")["relations"]}
    assert targets == {"SYST0077"}


def test_rename_onto_an_existing_id_is_refused(client, project):
    make_req(client, project, "SYST0001", name="One")
    make_req(client, project, "SYST0002", name="Two")

    r = _rename(client, project, "SYST0001", "SYST0002")
    assert r.status_code == 400
    assert "already exists" in r.json()["detail"]

    store = get_store(project)
    assert store.get_requirement("SYST0001")["name"] == "One"
    assert store.get_requirement("SYST0002")["name"] == "Two"


def test_renaming_to_the_same_id_is_a_no_op(client, project):
    make_req(client, project, "SYST0001", name="One")

    r = _rename(client, project, "SYST0001", "SYST0001")
    assert r.status_code == 200
    assert get_store(project).get_requirement("SYST0001")["name"] == "One"


def test_an_id_that_would_break_the_suffix_arithmetic_is_refused(client, project):
    make_req(client, project, "SYST0001", name="One")

    r = _rename(client, project, "SYST0001", "NOTRAILINGNUMBER")
    assert r.status_code == 400
    assert "number" in r.json()["detail"].lower()
    assert get_store(project).get_requirement("SYST0001") is not None


def test_a_path_traversal_id_is_refused(client, project):
    """Ids become filenames, so this is the guard that matters most."""
    make_req(client, project, "SYST0001", name="One")

    r = _rename(client, project, "SYST0001", "../../etc/passwd0001")
    assert r.status_code == 400
    assert get_store(project).get_requirement("SYST0001") is not None


def test_rename_is_recorded_in_history(client, project):
    make_req(client, project, "SYST0001", name="One")

    _rename(client, project, "SYST0001", "SYST0055")

    hist = client.get(f"/api/projects/{project}/history/SYST0055").json()
    assert any(e.get("action") == "rename" for e in hist), hist


def test_renaming_an_unknown_requirement_is_a_404(client, project):
    r = _rename(client, project, "GHOST0001", "SYST0001")
    assert r.status_code == 404


# ── Registry-driven inbound sweep ─────────────────────────────────────────────


def _referrer(client, project, link, target_id, idx):
    """Create one record pointing at *target_id* through *link*.

    Returns ``(holder, item_id)``. Creation routes differ per holder, and some
    link fields live on the ``*Update`` model rather than ``*Create``, so those
    records are created bare and the link written with a PUT.
    """
    holder = link.holder
    if holder == "requirements":
        if link.tree:
            make_req(client, project, f"RQ{idx:03d}", parent=target_id)
        elif link.field == "cascade_from":
            make_req(client, project, f"RQ{idx:03d}", cascade_from=target_id)
        else:
            raise AssertionError(f"unhandled requirement link field {link.field}")
        return holder, f"RQ{idx:03d}"
    if holder == "components":
        res = client.post(f"/api/projects/{project}/components",
                          json={"id": f"CC{idx:03d}", "name": "c", "satisfies": [target_id]})
        assert res.status_code == 201, res.text
        return holder, f"CC{idx:03d}"
    if holder == "verification_cases":
        client.post(f"/api/projects/{project}/verification",
                    json={"id": f"VC{idx:03d}", "name": "v", "method": "test"})
        client.put(f"/api/projects/{project}/verification/VC{idx:03d}",
                   json={"verified_requirements": [target_id]})
        return holder, f"VC{idx:03d}"
    if holder == "specifications":
        client.post(f"/api/projects/{project}/specifications",
                    json={"id": f"SP{idx:03d}", "name": "s"})
        client.put(f"/api/projects/{project}/specifications/SP{idx:03d}",
                   json={"requirements": [target_id]})
        return holder, f"SP{idx:03d}"
    if holder == "change_requests":
        client.post(f"/api/projects/{project}/change-requests",
                    json={"id": f"CR{idx:03d}", "title": "c"})
        client.put(f"/api/projects/{project}/change-requests/CR{idx:03d}",
                   json={"affected_requirements": [target_id]})
        return holder, f"CR{idx:03d}"
    if holder == "analysis_cases":
        res = client.post(f"/api/projects/{project}/analysis",
                          json={"id": f"AC{idx:03d}", "name": "a", "scope": [target_id]})
        assert res.status_code == 201, res.text
        return holder, f"AC{idx:03d}"
    if holder == "decisions":
        client.post(f"/api/projects/{project}/decisions",
                    json={"id": f"DC{idx:03d}", "title": "d"})
        client.put(f"/api/projects/{project}/decisions/DC{idx:03d}",
                   json={"linked_requirements": [target_id]})
        return holder, f"DC{idx:03d}"
    if holder == "risks":
        client.post(f"/api/projects/{project}/risks",
                    json={"id": f"RK{idx:03d}", "title": "r"})
        client.put(f"/api/projects/{project}/risks/RK{idx:03d}",
                   json={link.field: [target_id]})
        return holder, f"RK{idx:03d}"
    if holder == "comments":
        res = client.post(f"/api/projects/{project}/comments",
                          json={"entity_kind": "requirements", "entity_id": target_id,
                                "text": "x"})
        assert res.status_code == 201, res.text
        return holder, res.json()["id"]
    raise AssertionError(f"unhandled holder {holder}")


def test_every_inbound_reference_is_rewritten(client, project):
    """Each registry link that can point at a requirement is repointed.

    Driven from ``links_into("requirements")`` so a newly declared link appears
    here automatically and fails the test if the rewrite misses it.
    """
    store = get_store(project)
    make_req(client, project, "SYST0001", name="Target")

    links = links_into("requirements")
    assert links, "the registry should declare inbound requirement links"
    referrers = []
    for idx, link in enumerate(links):
        referrers.append(_referrer(client, project, link, "SYST0001", idx))

    r = _rename(client, project, "SYST0001", "SYST0077")
    assert r.status_code == 200, r.text

    for link, (holder, item_id) in zip(links, referrers, strict=True):
        item = store.get_item(holder, item_id)
        assert item is not None, f"{holder}/{item_id} vanished"
        targets = targets_of(item, link)
        assert "SYST0077" in targets, f"{holder}.{link.field} not repointed"
        assert "SYST0001" not in targets, f"{holder}.{link.field} still names the old id"


def test_cascade_from_is_repointed(client, project):
    make_req(client, project, "SYST0001", name="Source")
    make_req(client, project, "SYST0002", name="Derived", cascade_from="SYST0001")

    r = _rename(client, project, "SYST0001", "SYST0099")
    assert r.status_code == 200, r.text
    assert get_store(project).get_requirement("SYST0002")["cascade_from"] == "SYST0099"


# ── Text and expression references the registry does not cover ────────────────


def test_parameter_and_description_references_are_rewritten(client, project):
    make_req(client, project, "SYST0001", name="Target")
    make_req(client, project, "REQ0001", name="Referrer",
             description="See [[SYST0001]] and SYST0001",
             parameters=[{"name": "mass", "expr": "SYST0001.mass - 10"}],
             constraints=[{"expr": "SYST0001.mass <= 100", "assume": "SYST0001.mass > 0"}])
    # A different id that merely *contains* the old id must be left alone.
    make_req(client, project, "REQ0002", name="Unrelated",
             description="SYST00012 is a different id",
             parameters=[{"name": "m", "expr": "SYST00012.mass"}])

    r = _rename(client, project, "SYST0001", "SYST0099")
    assert r.status_code == 200, r.text

    store = get_store(project)
    referrer = store.get_requirement("REQ0001")
    assert "SYST0099" in referrer["description"]
    assert "SYST0001" not in referrer["description"]
    assert referrer["parameters"][0]["expr"] == "SYST0099.mass - 10"
    assert referrer["constraints"][0]["expr"] == "SYST0099.mass <= 100"
    assert referrer["constraints"][0]["assume"] == "SYST0099.mass > 0"

    unrelated = store.get_requirement("REQ0002")
    assert "SYST00012" in unrelated["description"]
    assert unrelated["parameters"][0]["expr"] == "SYST00012.mass"


# ── Cascade modes ─────────────────────────────────────────────────────────────


def _cascade_tree(client, project):
    """REQ0001 (root) → REQ0002 (group) → REQ0003 (leaf); REQ0001 → REQ0004 (leaf)."""
    make_req(client, project, "REQ0001", name="Root")
    make_req(client, project, "REQ0002", name="Group", parent="REQ0001")
    make_req(client, project, "REQ0003", name="Grandchild", parent="REQ0002")
    make_req(client, project, "REQ0004", name="Leaf", parent="REQ0001")


def test_cascade_self_touches_nothing_else(client, project):
    _cascade_tree(client, project)

    r = _rename(client, project, "REQ0001", "SYS0001", cascade="self")
    assert r.status_code == 200, r.text

    store = get_store(project)
    assert store.get_requirement("REQ0001") is None
    assert store.get_requirement("SYS0001") is not None
    assert store.get_requirement("REQ0002") is not None
    assert store.get_requirement("REQ0003") is not None
    assert store.get_requirement("REQ0004") is not None
    assert store.get_requirement("REQ0002")["parent"] == "SYS0001"
    assert store.get_requirement("REQ0004")["parent"] == "SYS0001"


def test_cascade_children_reprefixes_leaf_children_but_not_groups(client, project):
    _cascade_tree(client, project)

    r = _rename(client, project, "REQ0001", "SYS0001", cascade="children")
    assert r.status_code == 200, r.text

    store = get_store(project)
    # The root and the leaf child moved; the group (which has children) did not.
    assert store.get_requirement("REQ0001") is None
    assert store.get_requirement("SYS0001") is not None
    assert store.get_requirement("REQ0004") is None
    assert store.get_requirement("SYS0002") is not None
    assert store.get_requirement("REQ0002") is not None
    assert store.get_requirement("REQ0003") is not None
    assert store.get_requirement("REQ0002")["parent"] == "SYS0001"
    assert store.get_requirement("SYS0002")["parent"] == "SYS0001"
    assert store.get_requirement("REQ0003")["parent"] == "REQ0002"


def test_cascade_descendants_reprefixes_the_whole_subtree(client, project):
    _cascade_tree(client, project)

    r = _rename(client, project, "REQ0001", "SYS0001", cascade="descendants")
    assert r.status_code == 200, r.text

    store = get_store(project)
    for old in ("REQ0001", "REQ0002", "REQ0003", "REQ0004"):
        assert store.get_requirement(old) is None, old
    assert store.get_requirement("SYS0001") is not None
    assert store.get_requirement("SYS0002") is not None
    assert store.get_requirement("SYS0003") is not None
    assert store.get_requirement("SYS0004") is not None
    assert store.get_requirement("SYS0002")["parent"] == "SYS0001"
    assert store.get_requirement("SYS0003")["parent"] == "SYS0002"
    assert store.get_requirement("SYS0004")["parent"] == "SYS0001"


# ── Dry-run ────────────────────────────────────────────────────────────────────


def test_dry_run_returns_the_same_renames_and_writes_nothing(client, project):
    _cascade_tree(client, project)

    store = get_store(project)
    r = _rename(client, project, "REQ0001", "SYS0001", cascade="descendants", dry_run=True)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is True
    assert body["renames"] == [
        {"from": "REQ0001", "to": "SYS0001"},
        {"from": "REQ0002", "to": "SYS0002"},
        {"from": "REQ0003", "to": "SYS0003"},
        {"from": "REQ0004", "to": "SYS0004"},
    ]
    # Nothing was written.
    assert store.get_requirement("REQ0001") is not None
    assert store.get_requirement("REQ0002") is not None
    assert store.get_requirement("REQ0003") is not None
    assert store.get_requirement("REQ0004") is not None
    assert store.get_requirement("SYS0001") is None

    real = _rename(client, project, "REQ0001", "SYS0001", cascade="descendants")
    assert real.status_code == 200, real.text
    assert real.json()["renames"] == body["renames"]


# ── Frozen baseline snapshots ──────────────────────────────────────────────────


def test_frozen_baseline_requirement_snapshot_is_repointed(client, project):
    """A frozen ``snapshot`` keyed by requirement id moves with the rename.

    Live membership carries baseline *names*, so it is untouched; the frozen
    snapshot's ``snapshot`` key — and any ``parent`` / ``relations[].target``
    inside it — are the parts that hold the requirement id.
    """
    from pathlib import Path
    from app.core.config import settings
    from app.services.yaml_store import YamlStore

    client.patch(f"/api/projects/{project}", json={"baselines": [{"name": "BL1"}]})
    make_req(client, project, "SYST0001", name="Parent", baselines=["BL1"])
    make_req(client, project, "SYST0002", name="Child", parent="SYST0001",
             baselines=["BL1"], relations=[{"type": "refines", "target": "SYST0001"}])
    client.post(f"/api/projects/{project}/baselines/BL1/freeze")

    assert _rename(client, project, "SYST0001", "SYST0099").status_code == 200

    store = YamlStore(Path(settings.data_root) / project)
    frozen = store.get_item("baselines", "BL1")
    snap = frozen["snapshot"]
    assert "SYST0001" not in snap
    assert "SYST0099" in snap
    assert snap["SYST0002"]["parent"] == "SYST0099"
    assert snap["SYST0002"]["relations"][0]["target"] == "SYST0099"

