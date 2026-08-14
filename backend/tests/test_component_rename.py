"""Renaming a component rewrites everything that referred to it.

A component's id is its YAML filename, every child's ``parent`` pointer, and
the target of every link the registry declares against components. Changing it
in one place and not the others is how a project grows dangling references no
page surfaces. The inbound fields are derived from ``link_registry`` rather than
hand-listed, so a link added to the model later fails the rewrite test instead
of being silently missed.
"""
from app.core.dependencies import get_store
from app.services.link_registry import links_into, targets_of
from tests.conftest import make_req


def _make_component(client, project, cid, **fields):
    body = {"id": cid, "name": fields.pop("name", cid), **fields}
    res = client.post(f"/api/projects/{project}/components", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _rename(client, project, cid, new_id=None):
    body = {} if new_id is None else {"new_id": new_id}
    return client.post(f"/api/projects/{project}/components/{cid}/rename", json=body)


def _referrer(client, project, link, target_id, idx):
    """Create one record pointing at *target_id* through *link*.

    Returns ``(holder, item_id)``. Creation routes differ per holder, and some
    link fields live on the ``*Update`` model rather than ``*Create``, so the
    record is created bare and the link written with a PUT where needed.
    """
    holder = link.holder
    if holder == "requirements":
        make_req(client, project, f"RQ{idx:03d}", subject=target_id)
        return holder, f"RQ{idx:03d}"
    if holder == "components":
        _make_component(client, project, f"CC{idx:03d}", parent=target_id)
        return holder, f"CC{idx:03d}"
    if holder == "specifications":
        client.post(f"/api/projects/{project}/specifications",
                    json={"id": f"SP{idx:03d}", "name": "s"})
        client.put(f"/api/projects/{project}/specifications/SP{idx:03d}",
                   json={"components": [target_id]})
        return holder, f"SP{idx:03d}"
    if holder == "change_requests":
        client.post(f"/api/projects/{project}/change-requests",
                    json={"id": f"CR{idx:03d}", "title": "c"})
        client.put(f"/api/projects/{project}/change-requests/CR{idx:03d}",
                   json={"affected_components": [target_id]})
        return holder, f"CR{idx:03d}"
    if holder == "analysis_cases":
        client.post(f"/api/projects/{project}/analysis",
                    json={"id": f"AC{idx:03d}", "name": "a", "scope_components": [target_id]})
        return holder, f"AC{idx:03d}"
    if holder == "decisions":
        client.post(f"/api/projects/{project}/decisions",
                    json={"id": f"DC{idx:03d}", "title": "d"})
        client.put(f"/api/projects/{project}/decisions/DC{idx:03d}",
                   json={"linked_components": [target_id]})
        return holder, f"DC{idx:03d}"
    if holder == "risks":
        field = link.field
        client.post(f"/api/projects/{project}/risks",
                    json={"id": f"RK{idx:03d}", "title": "r"})
        client.put(f"/api/projects/{project}/risks/RK{idx:03d}",
                   json={field: [target_id]})
        return holder, f"RK{idx:03d}"
    if holder == "comments":
        res = client.post(f"/api/projects/{project}/comments",
                          json={"entity_kind": "components", "entity_id": target_id,
                                "text": "x"})
        assert res.status_code == 201, res.text
        return holder, res.json()["id"]
    raise AssertionError(f"unhandled holder {holder}")


def test_rename_moves_the_record_and_children_follow(client, project):
    store = get_store(project)
    _make_component(client, project, "C-PARENT", name="Parent")
    _make_component(client, project, "C-CHILD", name="Child", parent="C-PARENT")

    r = _rename(client, project, "C-PARENT", "C-PARENT-NEW")
    assert r.status_code == 200, r.text
    assert r.json()["id"] == "C-PARENT-NEW"
    assert r.json()["children"] == ["C-CHILD"]

    assert store.get_component("C-PARENT") is None
    assert store.get_component("C-PARENT-NEW")["name"] == "Parent"
    assert store.get_component("C-CHILD")["parent"] == "C-PARENT-NEW"


def test_every_inbound_reference_is_rewritten(client, project):
    """Each registry link that can point at a component is repointed.

    Driven from ``links_into("components")`` so a newly declared link appears
    here automatically and fails the test if the rewrite misses it.
    """
    store = get_store(project)
    _make_component(client, project, "C-TARGET", name="Target")

    links = links_into("components")
    assert links, "the registry should declare inbound component links"
    referrers = []
    for idx, link in enumerate(links):
        referrers.append(_referrer(client, project, link, "C-TARGET", idx))

    r = _rename(client, project, "C-TARGET", "C-TARGET-NEW")
    assert r.status_code == 200, r.text

    for link, (holder, item_id) in zip(links, referrers, strict=True):
        item = store.get_item(holder, item_id)
        assert item is not None, f"{holder}/{item_id} vanished"
        targets = targets_of(item, link)
        assert "C-TARGET-NEW" in targets, f"{holder}.{link.field} not repointed"
        assert "C-TARGET" not in targets, f"{holder}.{link.field} still names the old id"


def test_rename_onto_an_existing_component_is_refused_and_nothing_moves(client, project):
    store = get_store(project)
    _make_component(client, project, "C-ONE", name="One")
    _make_component(client, project, "C-TWO", name="Two")

    r = _rename(client, project, "C-ONE", "C-TWO")
    assert r.status_code == 409
    assert "already exists" in r.json()["detail"]

    assert store.get_component("C-ONE")["name"] == "One"
    assert store.get_component("C-TWO")["name"] == "Two"


def test_a_path_traversal_id_is_refused(client, project):
    store = get_store(project)
    _make_component(client, project, "C-ONE", name="One")

    r = _rename(client, project, "C-ONE", "../../etc/passwd")
    assert r.status_code == 400
    assert store.get_component("C-ONE") is not None


def test_renaming_an_unknown_component_is_a_404(client, project):
    r = _rename(client, project, "GHOST", "C-NEW")
    assert r.status_code == 404


def test_rename_is_recorded_in_history(client, project):
    _make_component(client, project, "C-ONE", name="One")

    _rename(client, project, "C-ONE", "C-TWO")

    hist = client.get(f"/api/projects/{project}/history/C-TWO").json()
    assert any(e.get("action") == "rename" for e in hist), hist


def test_get_old_is_404_and_get_new_is_the_record(client, project):
    _make_component(client, project, "C-ONE", name="One")

    assert _rename(client, project, "C-ONE", "C-TWO").status_code == 200

    assert client.get(f"/api/projects/{project}/components/C-ONE").status_code == 404
    got = client.get(f"/api/projects/{project}/components/C-TWO")
    assert got.status_code == 200
    assert got.json()["name"] == "One"


def test_frozen_baseline_snapshot_is_repointed(client, project):
    """A frozen snapshot keyed by component id moves with the rename.

    Live membership carries baseline *names*, so it is untouched; the frozen
    snapshot's ``component_snapshot`` key — and any ``parent`` inside it — are
    the parts that hold the component id.
    """
    from pathlib import Path
    from app.core.config import settings
    from app.services.yaml_store import YamlStore

    client.patch(f"/api/projects/{project}", json={"baselines": [{"name": "BL1"}]})
    _make_component(client, project, "C-PARENT", name="Parent", baselines=["BL1"])
    _make_component(client, project, "C-CHILD", name="Child", parent="C-PARENT", baselines=["BL1"])
    client.post(f"/api/projects/{project}/baselines/BL1/freeze")

    assert _rename(client, project, "C-PARENT", "C-PARENT-NEW").status_code == 200

    store = YamlStore(Path(settings.data_root) / project)
    frozen = store.get_item("baselines", "BL1")
    snap = frozen["component_snapshot"]
    assert "C-PARENT" not in snap
    assert "C-PARENT-NEW" in snap
    assert snap["C-CHILD"]["parent"] == "C-PARENT-NEW"
