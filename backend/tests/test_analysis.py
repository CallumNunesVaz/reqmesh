"""Slice 4: analysis cases (scoped, parameterised evaluation) + subject."""

from app.services.yaml_store import YamlStore
from app.services.evaluation import run_analysis_case, evaluate_project


def _seed(tmp_path):
    store = YamlStore(tmp_path / "p")
    store.ensure_dirs()
    store.write_meta({"name": "a"})
    store.create_requirement({
        "id": "R1", "name": "wing", "subject": "WING",
        "parameters": [{"name": "mass", "value": 100.0, "unit": "kg"}],
        "constraints": [{"expr": "mass <= 120"}],
    })
    store.create_requirement({
        "id": "R2", "name": "tail",
        "parameters": [{"name": "mass", "value": 50.0, "unit": "kg"}],
        "constraints": [{"expr": "mass <= 60"}],
    })
    return store


def test_analysis_case_overrides_flip_verdict(tmp_path):
    store = _seed(tmp_path)
    # Baseline: both pass.
    base = {r["id"]: r["verdict"] for r in evaluate_project(store)["requirements"]}
    assert base == {"R1": "pass", "R2": "pass"}

    case = {"id": "heavy", "name": "Overweight wing",
            "scope": ["R1"], "overrides": {"R1.mass": 200.0}}
    result = run_analysis_case(store, case)
    # Scope limits the report to R1 only, and the override fails its constraint.
    ids = {r["id"] for r in result["requirements"]}
    assert ids == {"R1"}
    assert result["requirements"][0]["verdict"] == "fail"
    assert result["case"]["id"] == "heavy"


def test_analysis_case_api_and_run(client, project):
    from tests.conftest import make_req
    make_req(client, project, "R1", parameters=[{"name": "mass", "value": 100.0, "unit": "kg"}],
             constraints=[{"expr": "mass <= 120"}])

    body = {"id": "heavy", "name": "Heavy", "scope": ["R1"], "overrides": {"R1.mass": 200.0}}
    assert client.post(f"/api/projects/{project}/analysis", json=body).status_code == 201
    assert client.get(f"/api/projects/{project}/analysis").json()[0]["id"] == "heavy"

    run = client.get(f"/api/projects/{project}/analysis/heavy/run").json()
    assert run["requirements"][0]["verdict"] == "fail"

    assert client.delete(f"/api/projects/{project}/analysis/heavy").json() == {"ok": True}


def test_subject_persists_via_api(client, project):
    from tests.conftest import make_req
    make_req(client, project, "R1", subject="WING")
    assert client.get(f"/api/projects/{project}/requirements/R1").json()["subject"] == "WING"
