"""Slice 3: reusable constraint/calc definitions with binding."""

from app.services.yaml_store import YamlStore
from app.services.evaluation import evaluate_project


def _verdict(store, rid):
    result = evaluate_project(store)
    return next(r for r in result["requirements"] if r["id"] == rid)


def test_constraint_def_reused_across_requirements(tmp_path):
    store = YamlStore(tmp_path / "p")
    store.ensure_dirs()
    store.write_meta({"name": "d"})
    # One reusable budget constraint: actual <= limit.
    store.write_item("definitions", "MassBudget", {
        "id": "MassBudget", "type": "constraint",
        "parameters": ["actual", "limit"], "expr": "actual <= limit",
    })
    store.create_requirement({
        "id": "R1", "name": "wing",
        "parameters": [{"name": "mass", "value": 100.0, "unit": "kg"},
                       {"name": "cap", "value": 120.0, "unit": "kg"}],
        "constraints": [{"constraint_def": "MassBudget",
                         "bindings": {"actual": "R1.mass", "limit": "R1.cap"}}],
    })
    store.create_requirement({
        "id": "R2", "name": "tail",
        "parameters": [{"name": "mass", "value": 200.0, "unit": "kg"},
                       {"name": "cap", "value": 150.0, "unit": "kg"}],
        "constraints": [{"constraint_def": "MassBudget",
                         "bindings": {"actual": "R2.mass", "limit": "R2.cap"}}],
    })
    assert _verdict(store, "R1")["verdict"] == "pass"   # 100 <= 120
    assert _verdict(store, "R2")["verdict"] == "fail"   # 200 <= 150
    # Display shows the definition usage, not a bare expr.
    assert "MassBudget(" in _verdict(store, "R1")["constraints"][0]["expr"]


def test_calc_def_derives_parameter(tmp_path):
    store = YamlStore(tmp_path / "p2")
    store.ensure_dirs()
    store.write_meta({"name": "d"})
    store.write_item("definitions", "Area", {
        "id": "Area", "type": "calc", "parameters": ["w", "h"], "expr": "w * h", "unit": "m2",
    })
    store.create_requirement({
        "id": "R1", "name": "panel",
        "parameters": [
            {"name": "width", "value": 3.0, "unit": "m"},
            {"name": "height", "value": 4.0, "unit": "m"},
            {"name": "area", "calc_def": "Area", "unit": "m2",
             "bindings": {"w": "R1.width", "h": "R1.height"}},
        ],
        "constraints": [{"expr": "area >= 10"}],
    })
    req = _verdict(store, "R1")
    area = next(p for p in req["parameters"] if p["name"] == "area")
    assert area["value"] == 12.0
    assert req["verdict"] == "pass"


def test_missing_def_reports_error(tmp_path):
    store = YamlStore(tmp_path / "p3")
    store.ensure_dirs()
    store.write_meta({"name": "d"})
    store.create_requirement({
        "id": "R1", "name": "x",
        "constraints": [{"constraint_def": "Nope", "bindings": {}}],
    })
    assert _verdict(store, "R1")["constraints"][0]["status"] == "error"


def test_definition_crud_api(client, project):
    body = {"id": "Budget", "type": "constraint", "parameters": ["a", "b"], "expr": "a <= b"}
    res = client.post(f"/api/projects/{project}/definitions", json=body)
    assert res.status_code == 201
    assert client.get(f"/api/projects/{project}/definitions").json()[0]["id"] == "Budget"
    res = client.put(f"/api/projects/{project}/definitions/Budget", json={"expr": "a < b"})
    assert res.json()["expr"] == "a < b"
    assert client.delete(f"/api/projects/{project}/definitions/Budget").json() == {"ok": True}
    assert client.get(f"/api/projects/{project}/definitions").json() == []
