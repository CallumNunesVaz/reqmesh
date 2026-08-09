"""Renaming a requirement rewrites everything that referred to it.

An id here is the YAML filename, every child's parent pointer, and every
relation target in the project. Changing one and not the others is how a project
grows dangling traces that no page surfaces.
"""
from app.core.dependencies import get_store
from tests.conftest import make_req


def _rename(client, project, req_id, new_id=None):
    body = {} if new_id is None else {"new_id": new_id}
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

