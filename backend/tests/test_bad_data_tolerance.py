"""Hand-edited YAML with unparseable values must degrade gracefully."""

import pytest

from app.services.evaluation import (
    evaluate_project,
    run_analysis_case,
    build_impact,
    coerce_number,
    _same_value,
)
from app.services.integrity import IntegrityChecker


class FakeStore:
    """Stub that returns the data-driven collections evaluate_project needs."""

    def __init__(self, reqs=None, comps=None, vcs=None, defs=None):
        self._reqs = reqs or []
        self._comps = comps or []
        self._vcs = vcs or []
        self._defs = defs or []

    def list_requirements(self):
        return list(self._reqs)

    def list_components(self):
        return list(self._comps)

    def list_verification_cases(self):
        return list(self._vcs)

    def list_items(self, name):
        if name == "definitions":
            return list(self._defs)
        return []


# ── coerce_number ───────────────────────────────────────────────────────────

class TestCoerceNumber:
    def test_none_is_absence_not_corruption(self):
        issues: list = []
        assert coerce_number(None, kind="non_numeric_measurement",
                              ref="R1.a", source="VC1", issues=issues) is None
        assert issues == []

    def test_boolean_treated_as_non_numeric(self):
        issues: list = []
        assert coerce_number(True, kind="non_numeric_measurement",
                              ref="R1.a", source="VC1", issues=issues) is None
        assert len(issues) == 1
        assert issues[0]["kind"] == "non_numeric_measurement"
        assert issues[0]["ref"] == "R1.a"
        assert "True" in issues[0]["value"]

    def test_floatable_string_returns_float(self):
        issues: list = []
        assert coerce_number("42.5", kind="non_numeric_measurement",
                              ref="R1.a", source="VC1", issues=issues) == 42.5
        assert issues == []

    def test_unparseable_string_records_issue(self):
        issues: list = []
        assert coerce_number("n/a", kind="non_numeric_measurement",
                              ref="R1.a", source="VC1", issues=issues) is None
        assert len(issues) == 1
        assert issues[0]["kind"] == "non_numeric_measurement"
        assert issues[0]["ref"] == "R1.a"
        assert issues[0]["source"] == "VC1"
        assert issues[0]["value"] == "n/a"

    def test_nan_records_issue(self):
        issues: list = []
        assert coerce_number(float("nan"), kind="non_numeric_measurement",
                              ref="R1.x", source="VC1", issues=issues) is None
        assert len(issues) == 1

    def test_inf_records_issue(self):
        issues: list = []
        assert coerce_number(float("inf"), kind="non_numeric_measurement",
                              ref="R1.x", source="VC1", issues=issues) is None
        assert len(issues) == 1

    def test_value_truncated_to_120_chars(self):
        issues: list = []
        long_val = "x" * 200
        assert coerce_number(long_val, kind="non_numeric_measurement",
                              ref="R1.a", source="VC1", issues=issues) is None
        assert len(issues[0]["value"]) == 120


# ── evaluate_project: measurement tolerance ──────────────────────────────────

class TestMeasurementTolerance:
    def test_non_numeric_measurement_no_raise(self):
        store = FakeStore(
            reqs=[{"id": "R1", "name": "Req 1",
                   "parameters": [{"name": "a", "value": 100}],
                   "constraints": [{"expr": "a <= 110"}]}],
            vcs=[{"id": "VC1", "measurements": [
                {"parameter": "R1.a", "value": "n/a"}]}],
        )
        result = evaluate_project(store)
        assert result["measurement_count"] == 0
        assert len(result["data_issues"]) == 1
        issue = result["data_issues"][0]
        assert issue["kind"] == "non_numeric_measurement"
        assert issue["ref"] == "R1.a"
        assert issue["source"] == "VC1"

        req = result["requirements"][0]
        assert req["verdict"] == "pass"  # design verdict unaffected
        # No measured key on parameter since measurement was skipped.
        assert "measured" not in req["parameters"][0]

    def test_bad_measurement_requirement_is_unmeasured(self):
        store = FakeStore(
            reqs=[{"id": "R1", "name": "Req 1",
                   "parameters": [{"name": "a", "value": 100}],
                   "constraints": [{"expr": "a <= 110"}]}],
            vcs=[{"id": "VC1", "measurements": [
                {"parameter": "R1.a", "value": "n/a"}]}],
        )
        result = evaluate_project(store)
        assert result["measured_summary"]["unmeasured"] == 1

    def test_good_and_bad_measurement_in_same_case(self):
        store = FakeStore(
            reqs=[{"id": "R1", "name": "Req 1",
                   "parameters": [{"name": "a", "value": 100},
                                  {"name": "b", "value": 200}],
                   "constraints": [{"expr": "a <= 110"}]}],
            vcs=[{"id": "VC1", "measurements": [
                {"parameter": "R1.a", "value": "n/a"},
                {"parameter": "R1.b", "value": 250.0},
            ]}],
        )
        result = evaluate_project(store)
        assert result["measurement_count"] == 1  # only b
        assert len(result["data_issues"]) == 1  # only a bad
        # Good param has measured key, bad param does not.
        params = {p["name"]: p for p in result["requirements"][0]["parameters"]}
        assert "measured" not in params["a"]
        assert params["b"]["measured"] == 250.0

    def test_null_value_is_absence_not_corruption(self):
        store = FakeStore(
            reqs=[{"id": "R1", "name": "Req 1",
                   "parameters": [{"name": "a", "value": 100}],
                   "constraints": [{"expr": "a <= 110"}]}],
            vcs=[{"id": "VC1", "measurements": [
                {"parameter": "R1.a", "value": None}]}],
        )
        result = evaluate_project(store)
        assert result["data_issues"] == []
        assert result["measurement_count"] == 0
        assert "measured" not in result["requirements"][0]["parameters"][0]

    def test_boolean_is_not_a_measurement(self):
        store = FakeStore(
            reqs=[{"id": "R1", "name": "Req 1",
                   "parameters": [{"name": "a", "value": 100}],
                   "constraints": [{"expr": "a <= 110"}]}],
            vcs=[{"id": "VC1", "measurements": [
                {"parameter": "R1.a", "value": True}]}],
        )
        result = evaluate_project(store)
        assert len(result["data_issues"]) == 1
        assert result["data_issues"][0]["kind"] == "non_numeric_measurement"
        assert result["measurement_count"] == 0

    def test_clean_project_data_issues_empty(self):
        store = FakeStore(
            reqs=[{"id": "R1", "name": "Req 1",
                   "parameters": [{"name": "a", "value": 100}],
                   "constraints": [{"expr": "a <= 110"}]}],
            vcs=[{"id": "VC1", "measurements": [
                {"parameter": "R1.a", "value": 105.0}]}],
        )
        result = evaluate_project(store)
        assert result["data_issues"] == []
        assert result["measurement_count"] == 1


# ── run_analysis_case ────────────────────────────────────────────────────────

class TestAnalysisCaseTolerance:
    def test_non_numeric_override_no_raise(self):
        store = FakeStore(
            reqs=[{"id": "R1", "name": "Req 1",
                   "parameters": [{"name": "a", "value": 100}],
                   "constraints": [{"expr": "a <= 110"}]}],
        )
        case = {"id": "AC1", "name": "Bad override",
                "scope": ["R1"], "overrides": {"R1.a": "tbd"}}
        result = run_analysis_case(store, case)
        assert len(result["data_issues"]) == 1
        assert result["data_issues"][0]["kind"] == "non_numeric_override"
        assert result["data_issues"][0]["ref"] == "R1.a"
        assert result["data_issues"][0]["source"] == "AC1"
        # Raw overrides echoed verbatim.
        assert result["case"]["overrides"] == {"R1.a": "tbd"}

    def test_good_and_bad_override_together(self):
        store = FakeStore(
            reqs=[{"id": "R1", "name": "Req 1",
                   "parameters": [{"name": "a", "value": 100},
                                  {"name": "b", "value": 200}],
                   "constraints": [{"expr": "a <= 110"},
                                   {"expr": "b <= 210"}]}],
        )
        case = {"id": "AC1", "name": "Mixed",
                "scope": ["R1"],
                "overrides": {"R1.a": "tbd", "R1.b": 205.0}}
        result = run_analysis_case(store, case)
        # Good override applied: b <= 210 should still pass at 205.
        req = result["requirements"][0]
        assert req["verdict"] == "pass"
        # Raw overrides echoed verbatim.
        assert result["case"]["overrides"] == {"R1.a": "tbd", "R1.b": 205.0}
        assert len(result["data_issues"]) == 1


# ── sorting ───────────────────────────────────────────────────────────────────

class TestIssueSorting:
    def test_issues_sorted_by_kind_ref_source(self):
        issues = [
            {"kind": "non_numeric_override", "ref": "R1.b", "source": "VC2"},
            {"kind": "non_numeric_measurement", "ref": "R1.a", "source": "VC1"},
            {"kind": "non_numeric_measurement", "ref": "R1.a", "source": "VC2"},
        ]
        issues.sort(key=lambda i: (i["kind"], i["ref"], i["source"]))
        assert issues == [
            {"kind": "non_numeric_measurement", "ref": "R1.a", "source": "VC1"},
            {"kind": "non_numeric_measurement", "ref": "R1.a", "source": "VC2"},
            {"kind": "non_numeric_override", "ref": "R1.b", "source": "VC2"},
        ]


# ── Impact endpoint ───────────────────────────────────────────────────────────

class TestImpactEndpoint:
    def test_non_numeric_override_returns_200(self, client):
        """POST /evaluation/impact with non-numeric override still 200s."""
        client.post("/api/projects", json={"id": "impactbad", "name": "Impact Test"})
        from tests.conftest import make_req
        make_req(client, "impactbad", "R1",
                 parameters=[{"name": "a", "value": 100}],
                 constraints=[{"expr": "a <= 110"}])

        res = client.post("/api/projects/impactbad/evaluation/impact",
                          json={"overrides": {"R1.a": "n/a"}})
        assert res.status_code == 200, res.text
        body = res.json()
        # The dropped override should appear in data_issues with empty source.
        issues = body["evaluation"]["data_issues"]
        assert len(issues) == 1
        assert issues[0]["kind"] == "non_numeric_override"
        assert issues[0]["ref"] == "R1.a"
        assert issues[0]["source"] == ""


# ── _same_value / float-tolerant build_impact ────────────────────────────────

class TestSameValue:
    def test_none_both_none_is_same(self):
        assert _same_value(None, None) is True

    def test_none_vs_float_is_not_same(self):
        assert _same_value(None, 1.0) is False
        assert _same_value(1.0, None) is False

    def test_close_values_are_same(self):
        a = 100.0 + 1e-16
        b = 100.0
        assert _same_value(a, b) is True

    def test_real_change_is_not_same(self):
        assert _same_value(100.0, 100.001) is False


class TestBuildImpactFloatTolerance:
    def test_tiny_drift_not_listed_as_impacted(self):
        """A parameter that drifts by ~1e-16 should not appear in impact steps."""
        store = FakeStore(
            reqs=[{"id": "R1", "name": "R1",
                   "parameters": [{"name": "a", "value": 100.0}]},
                  {"id": "R2", "name": "R2",
                   "parameters": [{"name": "b", "expr": "R1.a + 100.0"}]},
                  {"id": "R3", "name": "R3",
                   "parameters": [{"name": "c", "expr": "R1.a"}]},
                  ],
        )
        # Override R1.a to a value indistinguishable from 100.0
        # (the solver might produce 100.0 + epsilon from float arithmetic).
        impact = build_impact(store, {"R1.a": 100.0 + 1e-16})
        # R3.c is derived from R1.a — it should be "the same" after
        # tolerance comparison, so it should not appear as a step.
        refs_in_steps = [s.get("ref") for s in impact["steps"] if s.get("kind") == "param"]
        assert "R3.c" not in refs_in_steps

    def test_real_change_is_listed(self):
        store = FakeStore(
            reqs=[{"id": "R1", "name": "R1",
                   "parameters": [{"name": "a", "value": 100.0}]},
                  {"id": "R2", "name": "R2",
                   "parameters": [{"name": "b", "expr": "R1.a + 100.0"}]},
            ],
        )
        impact = build_impact(store, {"R1.a": 100.001})
        refs_in_steps = [s.get("ref") for s in impact["steps"] if s.get("kind") == "param"]
        assert "R2.b" in refs_in_steps


# ── Iterative Tarjan ─────────────────────────────────────────────────────────

def _make_chain_reqs(n: int, close_cycle: bool = False):
    """Build n requirements where R{i} derives R{i+1}."""
    reqs = []
    for i in range(n):
        rels = []
        if i < n - 1:
            rels.append({"type": "derives", "target": f"R{i+1}"})
        elif close_cycle:
            # Tail points back to head.
            rels.append({"type": "derives", "target": "R0"})
        reqs.append({"id": f"R{i}", "relations": rels})
    return reqs


class FakeIntegrityStore:
    def __init__(self, reqs):
        self.reqs = reqs

    def list_requirements(self):
        return list(self.reqs)

    def list_verification_cases(self):
        return []

    def list_components(self):
        return []

    def list_items(self, name):
        return []


class TestTarjanIterative:
    def test_deep_chain_no_cycle(self):
        """3000-long derives chain with no cycle — no RecursionError, no issues."""
        reqs = _make_chain_reqs(3000, close_cycle=False)
        # IntegrityChecker needs at least these attrs; stub the rest.
        checker = IntegrityChecker.__new__(IntegrityChecker)
        checker.reqs = reqs
        checker.vcs = []
        checker.components = []
        checker.issues = []
        checker._req_ids = {r["id"] for r in reqs}
        checker._vc_ids = set()
        checker._component_ids = set()
        checker._parent_of = {}
        checker._check_relation_cycles()
        assert checker.issues == []

    def test_deep_chain_with_cycle(self):
        """3000-long chain whose tail closes to head → exactly one issue."""
        reqs = _make_chain_reqs(3000, close_cycle=True)
        checker = IntegrityChecker.__new__(IntegrityChecker)
        checker.reqs = reqs
        checker.vcs = []
        checker.components = []
        checker.issues = []
        checker._req_ids = {r["id"] for r in reqs}
        checker._vc_ids = set()
        checker._component_ids = set()
        checker._parent_of = {}
        checker._check_relation_cycles()
        assert len(checker.issues) == 1
        issue = checker.issues[0]
        assert issue["type"] == "circular_relation"
        assert issue["severity"] == "error"
        assert set(issue["ids"]) == {f"R{i}" for i in range(3000)}

    def test_self_loop_not_reported(self):
        """R0 → R0 is a 1-element SCC, not reported."""
        reqs = [{"id": "R0", "relations": [{"type": "derives", "target": "R0"}]}]
        checker = IntegrityChecker.__new__(IntegrityChecker)
        checker.reqs = reqs
        checker.vcs = []
        checker.components = []
        checker.issues = []
        checker._req_ids = {r["id"] for r in reqs}
        checker._vc_ids = set()
        checker._component_ids = set()
        checker._parent_of = {}
        checker._check_relation_cycles()
        assert checker.issues == []

    def test_two_disjoint_cycles(self):
        """A→B→A and C→D→C → exactly 2 issues."""
        reqs = [
            {"id": "A", "relations": [{"type": "derives", "target": "B"}]},
            {"id": "B", "relations": [{"type": "derives", "target": "A"}]},
            {"id": "C", "relations": [{"type": "derives", "target": "D"}]},
            {"id": "D", "relations": [{"type": "derives", "target": "C"}]},
        ]
        checker = IntegrityChecker.__new__(IntegrityChecker)
        checker.reqs = reqs
        checker.vcs = []
        checker.components = []
        checker.issues = []
        checker._req_ids = {r["id"] for r in reqs}
        checker._vc_ids = set()
        checker._component_ids = set()
        checker._parent_of = {}
        checker._check_relation_cycles()
        assert len(checker.issues) == 2
        for iss in checker.issues:
            assert iss["type"] == "circular_relation"
            assert iss["severity"] == "error"
        # One SCC contains {A, B}, the other {C, D}.
        scc_sets = [set(iss["ids"]) for iss in checker.issues]
        assert {"A", "B"} in scc_sets
        assert {"C", "D"} in scc_sets
