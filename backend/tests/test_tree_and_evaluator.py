"""BUG-6 and BUG-9d.

* ``build_flat_tree`` only emitted items reachable from ``parent: None``, so
  deleting a parent made its children vanish from the nav while they still
  existed on disk — indistinguishable from corruption. A parent cycle took a
  whole subtree with it, and nothing stopped one being created.
* ``evaluation.py`` read ``c.get("expr", "")``, which yields ``None`` when the
  key exists but is null (a hand-edited ``expr:``). ``ast.parse(None)`` raises
  ``TypeError`` where only ``SyntaxError`` was caught → 500.
* ``build_impact`` seeded its topological sort from a ``set``, so the step order
  was hash-randomised per process and the what-if animation replayed
  differently after every restart.
"""
from app.core.tree_utils import build_flat_tree
from tests.conftest import make_req


def _ids(nodes, out=None):
    out = [] if out is None else out
    for n in nodes:
        out.append(n["id"])
        _ids(n.get("children", []), out)
    return out


class TestTreeNeverLosesItems:
    def test_orphan_surfaces_as_a_root(self):
        items = [{"id": "A", "parent": None}, {"id": "B", "parent": "GONE"}]
        assert sorted(_ids(build_flat_tree(items))) == ["A", "B"]

    def test_normal_nesting_still_works(self):
        items = [{"id": "A", "parent": None}, {"id": "B", "parent": "A"},
                 {"id": "C", "parent": "B"}]
        tree = build_flat_tree(items)
        assert len(tree) == 1 and tree[0]["id"] == "A"
        assert tree[0]["children"][0]["id"] == "B"
        assert tree[0]["children"][0]["children"][0]["id"] == "C"

    def test_parent_cycle_does_not_swallow_the_subtree(self):
        items = [{"id": "A", "parent": "B"}, {"id": "B", "parent": "A"},
                 {"id": "C", "parent": None}]
        got = _ids(build_flat_tree(items))
        assert sorted(set(got)) == ["A", "B", "C"]
        assert len(got) == len(set(got)), "an item was emitted twice"

    def test_self_parent_is_tolerated(self):
        assert _ids(build_flat_tree([{"id": "A", "parent": "A"}])) == ["A"]

    def test_deleting_a_parent_keeps_children_visible(self, client, project):
        make_req(client, project, "PARENT")
        make_req(client, project, "CHILD")
        client.put(f"/api/projects/{project}/requirements/CHILD", json={"parent": "PARENT"})
        client.delete(f"/api/projects/{project}/requirements/PARENT")

        tree = client.get(f"/api/projects/{project}/requirements/tree").json()
        assert "CHILD" in _ids(tree), "orphaned child disappeared from the tree"


class TestParentCycleIsRefused:
    def test_direct_cycle_rejected(self, client, project):
        make_req(client, project, "A")
        make_req(client, project, "B")
        client.put(f"/api/projects/{project}/requirements/B", json={"parent": "A"})
        res = client.put(f"/api/projects/{project}/requirements/A", json={"parent": "B"})
        assert res.status_code == 400, res.text

    def test_self_parent_rejected(self, client, project):
        make_req(client, project, "A")
        res = client.put(f"/api/projects/{project}/requirements/A", json={"parent": "A"})
        assert res.status_code == 400

    def test_deep_cycle_rejected(self, client, project):
        for rid in ("A", "B", "C"):
            make_req(client, project, rid)
        client.put(f"/api/projects/{project}/requirements/B", json={"parent": "A"})
        client.put(f"/api/projects/{project}/requirements/C", json={"parent": "B"})
        res = client.put(f"/api/projects/{project}/requirements/A", json={"parent": "C"})
        assert res.status_code == 400

    def test_legitimate_reparent_still_allowed(self, client, project):
        make_req(client, project, "A")
        make_req(client, project, "B")
        assert client.put(f"/api/projects/{project}/requirements/B",
                          json={"parent": "A"}).status_code == 200


class TestEvaluatorNullExpr:
    def test_null_expr_does_not_500(self, client, project):
        from app.core.dependencies import get_store
        make_req(client, project, "REQ-001")
        store = get_store(project)
        # A hand-edited `expr:` parses to None; the API model would coerce it.
        store.update_requirement("REQ-001", {
            "parameters": [{"name": "m", "value": 5}],
            "constraints": [{"expr": None}],
        })
        assert client.get(f"/api/projects/{project}/evaluation").status_code == 200

    def test_ordinary_constraints_still_evaluate(self, client, project):
        from app.core.dependencies import get_store
        make_req(client, project, "REQ-001")
        get_store(project).update_requirement("REQ-001", {
            "parameters": [{"name": "m", "value": 5, "unit": "kg"}],
            "constraints": [{"expr": "m <= 10"}],
        })
        body = client.get(f"/api/projects/{project}/evaluation").json()
        verdicts = {r["id"]: r["verdict"] for r in body["requirements"]}
        assert verdicts["REQ-001"] == "pass"


class TestImpactOrderingIsDeterministic:
    def test_same_input_gives_the_same_step_order(self, client, project):
        from app.core.dependencies import get_store
        store = get_store(project)
        make_req(client, project, "SRC")
        store.update_requirement("SRC", {"parameters": [{"name": "base", "value": 10}]})
        for i in range(6):
            rid = f"D{i}"
            make_req(client, project, rid)
            store.update_requirement(rid, {
                "parameters": [{"name": "v", "expr": f"SRC.base * {i + 1}"}],
                "constraints": [{"expr": f"v <= {1000 + i}"}],
            })

        runs = []
        for _ in range(4):
            res = client.post(f"/api/projects/{project}/evaluation/impact",
                              json={"overrides": {"SRC.base": 20}})
            assert res.status_code == 200, res.text
            runs.append([s.get("ref") or f"{s['owner']}:{s['expr']}" for s in res.json()["steps"]])
        assert all(r == runs[0] for r in runs), f"step order varied: {runs}"
        assert runs[0], "expected at least one impact step"
