"""Components as a row source on the baselines allocation matrix.

With ``rows=components`` the rows come from ``store.list_components()``
and membership is read from ``component.baselines``.
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


def toggle(client, project, axis, req_id, target_id, allocated=True,
           row_kind="requirements", row_id=None):
    body = {"req_id": req_id, "target_id": target_id,
            "axis": axis, "allocated": allocated, "row_kind": row_kind}
    if row_id:
        body["row_id"] = row_id
    return client.post(f"/api/projects/{project}/allocation",
                       json=body)


@pytest.fixture()
def baselines_project(client, project):
    """A project with baselines, requirements, and a component seeded."""
    client.patch(f"/api/projects/{project}", json={"baselines": [
        {"name": "SRR", "symbol": "S", "due_date": "2026-01-01"},
        {"name": "PDR", "symbol": "P", "due_date": "2026-06-01"},
    ]})
    make_req(client, project, "SYST0001")
    make_req(client, project, "SYST0002")
    client.post(f"/api/projects/{project}/components",
                json={"id": "COMP1", "name": "Engine", "type": "subsystem"})
    client.post(f"/api/projects/{project}/components",
                json={"id": "COMP2", "name": "Pylon", "type": "assembly"})
    return project


# ── rows=components returns component rows ────────────────────────────────────

def test_rows_components_returns_component_rows(client, baselines_project):
    """axis=baselines&rows=components returns component rows with
    row_kind == 'components', and their cells reflect component.baselines."""
    project = baselines_project

    # Seed a baseline membership on a component.
    toggle(client, project, "baselines", "COMP1", "SRR",
           row_kind="components", row_id="COMP1")

    m = matrix(client, project, "baselines", rows="components")
    assert m["row_kind"] == "components"
    assert m["total_rows"] == 2  # COMP1 + COMP2

    rows_by_id = {r["row_id"]: r for r in m["rows"]}
    comp1 = rows_by_id["COMP1"]
    assert comp1["row_name"] == "Engine"
    assert comp1["row_status"] == ""
    assert comp1["row_type"] == "subsystem"
    assert comp1["cells"]["SRR"] is True
    assert comp1["cells"]["PDR"] is False
    # No req-specific keys on component rows.
    assert "req_id" not in comp1
    assert "allocated_to" not in comp1


# ── rows=components rejected on non-baselines axes ─────────────────────────────

@pytest.mark.parametrize("axis", ["components", "verification", "risks"])
def test_rows_components_rejected_on_non_baselines_axis(client, baselines_project, axis):
    """rows=components with any axis other than baselines → 400."""
    res = client.get(f"/api/projects/{baselines_project}/allocation-matrix",
                     params={"axis": axis, "rows": "components"})
    assert res.status_code == 400
    assert axis in res.json()["detail"]


# ── Unrecognised rows value ────────────────────────────────────────────────────

def test_rows_nonsense_is_400(client, baselines_project):
    """An unrecognised rows value → 400."""
    res = client.get(f"/api/projects/{baselines_project}/allocation-matrix",
                     params={"axis": "baselines", "rows": "nonsense"})
    assert res.status_code == 400
    assert "nonsense" in res.json()["detail"]


# ── Default rows is requirements, backward-compatible ─────────────────────────

def test_default_rows_is_requirements_with_backward_compat(client, baselines_project):
    """Default rows is 'requirements', and the response still carries req_id
    and req_name — the backward-compatibility guarantee."""
    project = baselines_project

    m = matrix(client, project, "baselines")
    assert m["row_kind"] == "requirements"
    for row in m["rows"]:
        assert "req_id" in row
        assert "req_name" in row
        assert "row_id" in row
        assert "row_name" in row
        # req_id and row_id are the same for requirement rows.
        assert row["req_id"] == row["row_id"]
        assert row["req_name"] == row["row_name"]

    # Also check the components axis still works as before.
    m2 = matrix(client, project, "components")
    assert m2["row_kind"] == "requirements"
    for row in m2["rows"]:
        assert "req_id" in row
        assert "req_name" in row
        assert "row_id" in row
        assert "row_name" in row


# ── Cell write with row_kind="components" ─────────────────────────────────────

def test_cell_write_components_lands_in_component_baselines(client, baselines_project):
    """A cell write with row_kind='components' lands in component.baselines
    and does not touch any requirement."""
    project = baselines_project

    res = toggle(client, project, "baselines", "COMP1", "SRR",
                 row_kind="components", row_id="COMP1")
    assert res.status_code == 200
    body = res.json()
    assert body["row_kind"] == "components"
    assert body["row_id"] == "COMP1"

    # Component was updated.
    comp = client.get(f"/api/projects/{project}/components/COMP1").json()
    assert "SRR" in (comp.get("baselines") or [])

    # Requirements are untouched.
    req1 = client.get(f"/api/projects/{project}/requirements/SYST0001").json()
    assert (req1.get("baselines") or []) == []
    req2 = client.get(f"/api/projects/{project}/requirements/SYST0002").json()
    assert (req2.get("baselines") or []) == []


def test_cell_write_components_rejected_on_non_baselines(client, baselines_project):
    """row_kind='components' with axis='components' → 400."""
    res = toggle(client, baselines_project, "components", "COMP1", "COMP1",
                 row_kind="components", row_id="COMP1")
    assert res.status_code == 400
    assert "row_kind=components" in res.json()["detail"]


def test_cell_write_unknown_component_id_is_404(client, baselines_project):
    """An unknown component id → 404."""
    res = toggle(client, baselines_project, "baselines", "NOPE", "SRR",
                 row_kind="components", row_id="NOPE")
    assert res.status_code == 404
    assert "Component not found" in res.json()["detail"]


def test_cell_write_unknown_baseline_name_is_404(client, baselines_project):
    """An unknown baseline name → 404."""
    res = toggle(client, baselines_project, "baselines", "COMP1", "NOPE",
                 row_kind="components", row_id="COMP1")
    assert res.status_code == 404
    assert "Baseline not found" in res.json()["detail"]


# ── total_requirements vs total_rows ──────────────────────────────────────────

def test_total_requirements_and_total_rows(client, baselines_project):
    """total_requirements still counts requirements when rows='components',
    and total_rows counts the components."""
    project = baselines_project

    # baseline matrix with requirement rows.
    m = matrix(client, project, "baselines")
    assert m["row_kind"] == "requirements"
    assert m["total_requirements"] == 2  # SYST0001, SYST0002
    assert m["total_rows"] == 2

    # baseline matrix with component rows.
    m2 = matrix(client, project, "baselines", rows="components")
    assert m2["row_kind"] == "components"
    assert m2["total_requirements"] == 2  # still counts requirements
    assert m2["total_rows"] == 2           # counts components (COMP1, COMP2)

    # Add another component — total_rows should change, total_requirements
    # should stay the same.
    client.post(f"/api/projects/{project}/components",
                json={"id": "COMP3", "name": "Nozzle", "type": "part"})
    m3 = matrix(client, project, "baselines", rows="components")
    assert m3["total_requirements"] == 2
    assert m3["total_rows"] == 3


# ── filter_type and search on component rows ───────────────────────────────────

def test_filter_type_on_component_rows(client, baselines_project):
    """filter_type filters component type."""
    project = baselines_project

    m = matrix(client, project, "baselines", rows="components",
               filter_type="subsystem")
    assert len(m["rows"]) == 1
    assert m["rows"][0]["row_id"] == "COMP1"


def test_search_on_component_rows(client, baselines_project):
    """search matches component id or name."""
    project = baselines_project

    m = matrix(client, project, "baselines", rows="components", search="eng")
    assert len(m["rows"]) == 1
    assert m["rows"][0]["row_id"] == "COMP1"

    m2 = matrix(client, project, "baselines", rows="components", search="pyl")
    assert len(m2["rows"]) == 1
    assert m2["rows"][0]["row_id"] == "COMP2"
