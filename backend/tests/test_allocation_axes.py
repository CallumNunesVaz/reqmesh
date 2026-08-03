"""Requirements against components, verification cases, and risks.

All three are views of links already declared in ``services/link_registry.py``
whose target is ``requirements``, so they share one endpoint. These tests cover
what differs between the axes rather than re-testing the shared machinery: which
field is written, and which of them has a stored inverse to keep in step.
"""

import pytest


def make_req(client, project, rid, **fields):
    body = {"id": rid, "name": fields.pop("name", rid), "description": "x" * 30, **fields}
    assert client.post(f"/api/projects/{project}/requirements", json=body).status_code == 201


def matrix(client, project, axis, **params):
    res = client.get(f"/api/projects/{project}/allocation-matrix",
                     params={"axis": axis, **params})
    assert res.status_code == 200, res.text
    return res.json()


def toggle(client, project, axis, req_id, target_id, allocated=True):
    return client.post(f"/api/projects/{project}/allocation",
                       json={"req_id": req_id, "target_id": target_id,
                             "axis": axis, "allocated": allocated})


@pytest.fixture()
def populated(client, project):
    make_req(client, project, "SYST0001")
    make_req(client, project, "SYST0002")
    client.post(f"/api/projects/{project}/components", json={"id": "COMP1", "name": "Engine"})
    client.post(f"/api/projects/{project}/verification",
                json={"id": "VC1", "name": "Engine run-up", "method": "test"})
    client.post(f"/api/projects/{project}/risks",
                json={"id": "RSK1", "title": "Overheat", "severity": "high",
                      "likelihood": "possible"})
    return project


AXES = [
    ("components", "COMP1", "satisfies", "components"),
    ("verification", "VC1", "verified_requirements", "verification"),
    ("risks", "RSK1", "linked_requirements", "risks"),
]


@pytest.mark.parametrize("axis,target,field,collection", AXES)
def test_each_axis_toggles_the_link_the_registry_declares(
        client, populated, axis, target, field, collection):
    project = populated
    assert toggle(client, project, axis, "SYST0001", target).status_code == 200

    m = matrix(client, project, axis)
    row = next(r for r in m["rows"] if r["req_id"] == "SYST0001")
    assert row["cells"][target] is True
    assert m["allocated"] == 1
    assert m["unallocated"] == 1

    # The write lands on the holder's own field, which is what every other part
    # of the app reads — backlinks, integrity, publishing.
    listed = client.get(f"/api/projects/{project}/{collection}").json()
    items = listed if isinstance(listed, list) else listed["items"]
    holder = next(i for i in items if i["id"] == target)
    assert "SYST0001" in holder[field]

    assert toggle(client, project, axis, "SYST0001", target, allocated=False).status_code == 200
    m = matrix(client, project, axis)
    assert next(r for r in m["rows"] if r["req_id"] == "SYST0001")["cells"][target] is False


@pytest.mark.parametrize("axis,target,field,collection", AXES)
def test_each_axis_labels_itself(client, populated, axis, target, field, collection):
    """The UI takes its wording from the response rather than hardcoding three."""
    m = matrix(client, populated, axis)
    assert m["axis"] == axis
    assert m["verb"] and m["column_label"]
    assert m["total_columns"] == len(m["columns"])
    assert all(c["id"] and "name" in c for c in m["columns"])


def test_the_axes_are_independent(client, populated):
    """A cell set on one matrix must not appear on another."""
    project = populated
    toggle(client, project, "risks", "SYST0001", "RSK1")

    risks = matrix(client, project, "risks")
    assert next(r for r in risks["rows"] if r["req_id"] == "SYST0001")["cells"]["RSK1"] is True
    for other in ("components", "verification"):
        m = matrix(client, project, other)
        assert not any(any(r["cells"].values()) for r in m["rows"]), \
            f"{other} matrix picked up a link set on the risks matrix"


def test_only_the_components_axis_writes_the_stored_inverse(client, populated):
    """``allocated_to`` is persisted; the other inverses are derived on read.

    Writing a mirror for those would create a second copy of the truth that can
    disagree with the first — the thing risk ratings and verification links are
    deliberately computed to avoid.
    """
    project = populated
    res = toggle(client, project, "components", "SYST0001", "COMP1")
    assert res.json()["allocated_to"] == "Engine"
    assert client.get(f"/api/projects/{project}/requirements/SYST0001").json()["allocated_to"] == "Engine"

    res = toggle(client, project, "verification", "SYST0002", "VC1")
    assert res.json()["allocated_to"] == ""
    req = client.get(f"/api/projects/{project}/requirements/SYST0002").json()
    assert req["allocated_to"] == ""
    # …but the derived link is still visible on the requirement.
    assert "VC1" in req["verification_cases"]


def test_a_risk_link_shows_up_as_a_backlink(client, populated):
    """The matrix writes the same field the rest of the app already reads."""
    project = populated
    toggle(client, project, "risks", "SYST0001", "RSK1")
    data = client.get(f"/api/projects/{project}/entities/SYST0001/backlinks").json()
    holders = {g["collection"] for g in data["groups"]}
    assert "risks" in holders


def test_an_unknown_axis_is_refused_rather_than_silently_defaulting(client, populated):
    res = client.get(f"/api/projects/{populated}/allocation-matrix", params={"axis": "nonsense"})
    assert res.status_code == 400
    assert "nonsense" in res.json()["detail"]


def test_a_missing_column_entity_is_a_404_naming_its_kind(client, populated):
    res = toggle(client, populated, "risks", "SYST0001", "NOPE")
    assert res.status_code == 404
    assert "risk" in res.json()["detail"].lower()


def test_search_and_type_filters_apply_on_every_axis(client, populated):
    project = populated
    make_req(client, project, "PERF0001", name="Throughput", type="non_functional_performance")

    m = matrix(client, project, "risks", filter_type="non_functional_performance")
    assert [r["req_id"] for r in m["rows"]] == ["PERF0001"]

    m = matrix(client, project, "verification", search="throughput")
    assert [r["req_id"] for r in m["rows"]] == ["PERF0001"]


def test_the_components_axis_keeps_its_original_response_shape(client, populated):
    """Existing callers read comp_id/comp_name/total_components."""
    m = matrix(client, populated, "components")
    assert m["total_components"] == m["total_columns"]
    col = m["columns"][0]
    assert col["comp_id"] == col["id"]
    assert col["comp_name"] == col["name"]


def test_the_default_axis_is_still_components(client, populated):
    res = client.get(f"/api/projects/{populated}/allocation-matrix")
    assert res.json()["axis"] == "components"


# ── Baselines axis ────────────────────────────────────────────────────────────

def test_baselines_axis_returns_columns_in_sequence_order(client, project):
    """Columns come from metadata definitions, in sequence order, with due_date/order."""
    client.patch(f"/api/projects/{project}", json={"baselines": [
        {"name": "SRR", "symbol": "S", "due_date": "2026-01-01"},
        {"name": "PDR", "symbol": "P", "due_date": "2026-06-01"},
    ]})
    make_req(client, project, "SYST0001")
    make_req(client, project, "SYST0002")

    m = matrix(client, project, "baselines")
    assert m["axis"] == "baselines"
    assert m["verb"] == "is baselined in"
    assert m["column_label"] == "Baselines"

    cols = m["columns"]
    assert len(cols) == 2
    assert [c["id"] for c in cols] == ["SRR", "PDR"]
    assert cols[0]["due_date"] == "2026-01-01"
    assert cols[1]["due_date"] == "2026-06-01"
    assert cols[0]["order"] == 1
    assert cols[1]["order"] == 2
    assert cols[0]["kind"] == "S"


def test_baselines_axis_toggle_on_then_off(client, project):
    """Toggling a cell on then off leaves requirement.baselines as it started."""
    client.patch(f"/api/projects/{project}", json={"baselines": [
        {"name": "SRR"}, {"name": "PDR"},
    ]})
    make_req(client, project, "SYST0001")

    # Before: empty
    req = client.get(f"/api/projects/{project}/requirements/SYST0001").json()
    assert req.get("baselines") or [] == []

    # Toggle on
    assert toggle(client, project, "baselines", "SYST0001", "SRR").status_code == 200
    req = client.get(f"/api/projects/{project}/requirements/SYST0001").json()
    assert "SRR" in (req.get("baselines") or [])

    # Toggle off
    assert toggle(client, project, "baselines", "SYST0001", "SRR", allocated=False).status_code == 200
    req = client.get(f"/api/projects/{project}/requirements/SYST0001").json()
    assert (req.get("baselines") or []) == []


def test_baselines_toggle_does_not_set_other_cells(client, project):
    """Toggling one baseline must NOT set any other cell in that row
    (the no-cascade rule)."""
    client.patch(f"/api/projects/{project}", json={"baselines": [
        {"name": "SRR"}, {"name": "PDR"}, {"name": "CDR"},
    ]})
    make_req(client, project, "SYST0001")

    toggle(client, project, "baselines", "SYST0001", "SRR")

    m = matrix(client, project, "baselines")
    row = next(r for r in m["rows"] if r["req_id"] == "SYST0001")
    assert row["cells"]["SRR"] is True
    assert row["cells"]["PDR"] is False
    assert row["cells"]["CDR"] is False


def test_baselines_unknown_name_is_404(client, project):
    """An unknown baseline name → 404, checked against metadata definitions."""
    client.patch(f"/api/projects/{project}", json={"baselines": [{"name": "SRR"}]})
    make_req(client, project, "SYST0001")

    res = toggle(client, project, "baselines", "SYST0001", "NOPE")
    assert res.status_code == 404
    assert "Baseline not found" in res.json()["detail"]


def test_baselines_toggle_leaves_allocated_to_untouched(client, project):
    """Toggling on the baselines axis leaves allocated_to untouched."""
    client.patch(f"/api/projects/{project}", json={"baselines": [{"name": "SRR"}]})
    make_req(client, project, "SYST0001")

    res = toggle(client, project, "baselines", "SYST0001", "SRR")
    assert res.json()["allocated_to"] == ""

    req = client.get(f"/api/projects/{project}/requirements/SYST0001").json()
    assert "SRR" in (req.get("baselines") or [])
    # allocated_to is unchanged from whatever it was.
    assert req.get("allocated_to", "") == ""


def test_baselines_columns_are_metadata_defs_not_frozen_snapshots(client, project):
    """Columns are the metadata definitions even when no baseline has been frozen."""
    client.patch(f"/api/projects/{project}", json={"baselines": [
        {"name": "SRR"}, {"name": "PDR"},
    ]})
    make_req(client, project, "SYST0001")

    # No freeze — yet the columns still appear.
    m = matrix(client, project, "baselines")
    assert len(m["columns"]) == 2
    assert [c["id"] for c in m["columns"]] == ["SRR", "PDR"]


def test_baselines_axis_search_filters(client, project):
    """The search filter applies to columns by name."""
    client.patch(f"/api/projects/{project}", json={"baselines": [
        {"name": "SRR"}, {"name": "PDR"},
    ]})
    make_req(client, project, "SYST0001")
    make_req(client, project, "SYST0002")

    m = matrix(client, project, "baselines", search="SRR")
    assert len(m["columns"]) == 1
    assert m["columns"][0]["id"] == "SRR"


def test_baselines_axis_type_filter(client, project):
    """filter_type works on the baselines axis."""
    client.patch(f"/api/projects/{project}", json={"baselines": [{"name": "SRR"}]})
    make_req(client, project, "SYST0001", type="functional")
    make_req(client, project, "SYST0002", type="non_functional_performance")

    m = matrix(client, project, "baselines", filter_type="functional")
    assert [r["req_id"] for r in m["rows"]] == ["SYST0001"]
