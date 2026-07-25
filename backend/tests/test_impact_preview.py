from tests.conftest import make_req

BASE_PROJECT = "impactdemo"


def _setup(client):
    """Create a project with: one literal param, one derived param, and a
    constraint — so overriding the literal flows through the derived to the
    constraint verdict."""
    client.post("/api/projects", json={"id": BASE_PROJECT, "name": "Impact Test"})

    make_req(client, BASE_PROJECT, "REQ0001",
             name="Gross",
             parameters=[{"name": "mass", "value": 1157, "unit": "kg"}],
             constraints=[{"expr": "mass <= 1160"}])

    cf = make_req(client, BASE_PROJECT, "REQ0002",
                   name="Useful",
                   parameters=[{"name": "payload", "expr": "REQ0001.mass - 750"}],
                   constraints=[{"expr": "payload >= 400"},
                                {"expr": "payload <= 410"}])

    return cf


class TestImpactEndpoint:
    def test_response_shape(self, client):
        _setup(client)
        res = client.post(f"/api/projects/{BASE_PROJECT}/evaluation/impact",
                          json={"overrides": {"REQ0001.mass": 1140}})
        assert res.status_code == 200
        body = res.json()
        assert "evaluation" in body
        assert "steps" in body
        assert "affected" in body
        assert "roots" in body
        assert body["roots"] == ["REQ0001.mass"]

    def test_override_flows_to_derived_and_constraint(self, client):
        _setup(client)
        res = client.post(f"/api/projects/{BASE_PROJECT}/evaluation/impact",
                          json={"overrides": {"REQ0001.mass": 1110}})
        assert res.status_code == 200
        body = res.json()
        steps = body["steps"]

        param_steps = [s for s in steps if s["kind"] == "param"]
        assert any(s["ref"] == "REQ0002.payload" and s["before"] == 407.0
                   and s["after"] == 360.0 for s in param_steps)

    def test_breaking_override_shows_fail_verdict(self, client):
        _setup(client)
        res = client.post(f"/api/projects/{BASE_PROJECT}/evaluation/impact",
                          json={"overrides": {"REQ0001.mass": 1100}})
        assert res.status_code == 200
        body = res.json()
        constraint_steps = [s for s in body["steps"] if s["kind"] == "constraint"]
        assert any(s["before"]["status"] == "pass" and s["after"]["status"] == "fail"
                   for s in constraint_steps), constraint_steps

    def test_no_op_override_empty_impact(self, client):
        _setup(client)
        res = client.post(f"/api/projects/{BASE_PROJECT}/evaluation/impact",
                          json={"overrides": {"REQ0001.mass": 1157}})
        assert res.status_code == 200
        body = res.json()
        assert body["affected"] == []
        assert len(body["steps"]) == 0

    def test_unknown_ref_ignored(self, client):
        _setup(client)
        res = client.post(f"/api/projects/{BASE_PROJECT}/evaluation/impact",
                          json={"overrides": {"NOPE.xyz": 999}})
        assert res.status_code == 200

    def test_malformed_value_ignored(self, client):
        _setup(client)
        res = client.post(f"/api/projects/{BASE_PROJECT}/evaluation/impact",
                          json={"overrides": {"REQ0001.mass": "hello"}})
        assert res.status_code == 200

    def test_empty_body(self, client):
        _setup(client)
        res = client.post(f"/api/projects/{BASE_PROJECT}/evaluation/impact",
                          json={})
        assert res.status_code == 200


class TestRefsIn:
    def test_collects_references(self, client):
        from app.services.evaluation import _refs_in_expr
        refs = _refs_in_expr("a + BC.x - COMP.mass", "OWNER", {}, {}, set(), frozenset())
        assert "OWNER.a" in refs
        assert "BC.x" in refs
        assert "COMP.mass" in refs

    def test_rollup_reference(self, client):
        from app.services.evaluation import _refs_in_expr
        refs = _refs_in_expr("rollup('WING', 'mass')", "OWNER", {}, {}, set(), frozenset())
        assert "WING.mass" in refs

    def test_env_binding(self, client):
        from app.services.evaluation import _refs_in_expr
        refs = _refs_in_expr("fuel + air", "OWNER",
                             {"fuel": "TANK.mass", "air": "ENG.mass"},
                             {}, set(), frozenset())
        assert "TANK.mass" in refs
        assert "ENG.mass" in refs
