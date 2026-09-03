"""The parametric evaluation chain: expressions, derivation, rollups,
constraint verdicts and measured verdicts."""
import pytest

from app.services.evaluation import (
    Evaluator, EvalError, UnknownValue, MAX_DERIVATION_DEPTH, MAX_EXPR_CHARS,
    _resolve_safe,
)
from tests.conftest import make_req


# ---- expression engine (no API needed) -----------------------------------

def ev(reqs=None, comps=None, overrides=None):
    return Evaluator(reqs or [], comps or [], overrides=overrides)


def req(rid, params=None, constraints=None):
    return {"id": rid, "parameters": params or [], "constraints": constraints or []}


def param(name, value=None, expr=None, unit=""):
    return {"name": name, "value": value, "expr": expr, "unit": unit}


class TestExpressions:
    def test_arithmetic(self):
        e = ev([req("R1", [param("a", 6), param("b", 4)])])
        assert e.eval_expr("a * b + 1", "R1") == 25
        assert e.eval_expr("(a - b) ** 2", "R1") == 4
        assert e.eval_expr("a / b", "R1") == 1.5

    def test_comparisons_and_bool(self):
        e = ev([req("R1", [param("x", 5)])])
        assert e.eval_expr("x <= 5", "R1") is True
        assert e.eval_expr("0 < x < 5", "R1") is False  # chained
        assert e.eval_expr("x > 0 and x < 10", "R1") is True
        assert e.eval_expr("not x > 4", "R1") is False

    def test_cross_requirement_reference(self):
        e = ev([req("R1", [param("gross", 1157)]), req("R2", [param("empty", 767)])])
        assert e.eval_expr("R1.gross - R2.empty", "R2") == 390

    def test_functions(self):
        e = ev([req("R1", [param("a", 9)])])
        assert e.eval_expr("sqrt(a)", "R1") == 3
        assert e.eval_expr("max(a, 100)", "R1") == 100
        assert e.eval_expr("abs(-a)", "R1") == 9

    def test_unknown_parameter_is_unknown_not_error(self):
        e = ev([req("R1", [])])
        with pytest.raises(UnknownValue):
            e.eval_expr("missing + 1", "R1")
        with pytest.raises(UnknownValue):
            e.eval_expr("R9.x", "R1")

    def test_division_by_zero(self):
        e = ev([req("R1", [param("z", 0)])])
        with pytest.raises(EvalError):
            e.eval_expr("1 / z", "R1")

    def test_dangerous_syntax_rejected(self):
        e = ev([req("R1", [param("a", 1)])])
        for expr in [
            "__import__('os')",
            "().__class__",
            "[1,2][0]",
            "a if a else 0",
            "'text'",
            "lambda: 1",
            "a.__class__.b",  # attribute base must be a bare name → R-style ref only
        ]:
            with pytest.raises((EvalError, UnknownValue)):
                e.eval_expr(expr, "R1")

    def test_syntax_error(self):
        with pytest.raises(EvalError):
            ev().eval_expr("1 +", "R1")

    def test_long_expression_raises_eval_error_not_recursion(self):
        """`'1' + '+1'*20000` used to raise RecursionError inside ``ast.parse``,
        which is neither EvalError nor UnknownValue and so escaped every caller
        as a 500."""
        e = ev()
        with pytest.raises(EvalError):
            e.eval_expr('1' + '+1' * 20000, "X")

    def test_expression_length_cap(self):
        e = ev()
        with pytest.raises(EvalError, match="exceeds"):
            e.eval_expr('1' * (MAX_EXPR_CHARS + 1), "X")

    def test_expression_at_the_cap_still_evaluates(self):
        e = ev()
        # "min(" + "1" + ",1"*k + ")" is exactly MAX_EXPR_CHARS characters long.
        k = (MAX_EXPR_CHARS - 6) // 2
        expr = "min(" + "1" + ",1" * k + ")"
        assert len(expr) == MAX_EXPR_CHARS
        assert e.eval_expr(expr, "X") == 1.0

    def test_deep_nesting_within_the_cap_still_evaluates(self):
        e = ev()
        assert e.eval_expr('(' * 200 + '1' + ')' * 200, "X") == 1.0

    def test_near_cap_deep_expression_evaluates(self):
        """A left-nested chain just under the cap is the deepest tree the length
        limit can admit. The old 2000-char cap left a band (~1810-2000 chars)
        where ``_eval`` recursed past the frame limit and escaped as a 500."""
        e = ev()
        n = (MAX_EXPR_CHARS - 1) // 2
        expr = '1' + '+1' * n
        assert len(expr) < MAX_EXPR_CHARS
        assert e.eval_expr(expr, "X") == float(n + 1)

    def test_at_cap_from_a_deep_call_stack(self):
        """How much stack remains depends on the caller, so the cap alone cannot
        guarantee safety — the catch in ``eval_expr`` is what actually guards the
        walk. From ~60 frames deep an at-cap left-nested expression must still
        not raise RecursionError."""
        e = ev()
        n = (MAX_EXPR_CHARS - 1) // 2
        expr = '1' + '+1' * n

        def descend(depth):
            if depth == 0:
                return e.eval_expr(expr, "X")
            return descend(depth - 1)

        assert descend(60) == float(n + 1)


class TestDerivation:
    def test_derived_parameter(self):
        e = ev([req("R1", [param("empty", 767), param("gross", 1157),
                           param("useful", expr="gross - empty")])])
        assert e.resolve("R1.useful") == 390

    def test_derivation_chain_across_requirements(self):
        e = ev([
            req("R1", [param("a", 10)]),
            req("R2", [param("b", expr="R1.a * 2")]),
            req("R3", [param("c", expr="R2.b + 5")]),
        ])
        assert e.resolve("R3.c") == 25

    def test_cycle_detected(self):
        e = ev([req("R1", [param("a", expr="R1.b")]),
                req("R1b", [])])
        e.params["R1.b"] = param("b", expr="R1.a")
        with pytest.raises(EvalError, match="circular"):
            e.resolve("R1.a")


class TestRollup:
    def comps(self):
        return [
            {"id": "AC", "parent": None, "quantity": 1,
             "parameters": [param("mass", 100)]},
            {"id": "WING", "parent": "AC", "quantity": 2,
             "parameters": [param("mass", 50)]},
            {"id": "RIB", "parent": "WING", "quantity": 10,
             "parameters": [param("mass", 1)]},
            {"id": "TAIL", "parent": "AC", "quantity": 1, "parameters": []},
        ]

    def test_quantities_multiply_down_the_tree(self):
        e = ev([], self.comps())
        # AC: 100 + 2×(WING 50) + 2×10×(RIB 1) = 220; TAIL has no mass param.
        assert e.rollup("AC", "mass", frozenset()) == 220
        # Root's own quantity is out of scope: WING contributes once here.
        assert e.rollup("WING", "mass", frozenset()) == 60

    def test_rollup_in_expression(self):
        e = ev([req("R1", [param("limit", 250)])], self.comps())
        assert e.eval_expr("rollup('AC', 'mass') <= limit", "R1") is True

    def test_unknown_component_and_empty_rollup(self):
        e = ev([], self.comps())
        with pytest.raises(UnknownValue):
            e.rollup("NOPE", "mass", frozenset())
        with pytest.raises(UnknownValue):
            e.rollup("AC", "cost", frozenset())

    def test_rollup_args_must_be_strings(self):
        e = ev([], self.comps())
        with pytest.raises(EvalError):
            e.eval_expr("rollup(AC, 'mass')", "R1")

    def test_deep_component_chain_does_not_blow_the_stack(self):
        """A chain deeper than Python's frame limit must still roll up.

        `rollup` walked the tree recursively, so ~2000 levels raised
        RecursionError — neither EvalError nor UnknownValue, so it escaped
        every caller's handling and surfaced as a 500 rather than a result.
        """
        n = 5000
        comps = [
            {"id": f"C{i}", "parent": (f"C{i - 1}" if i else None), "quantity": 1,
             "parameters": [param("mass", 1)]}
            for i in range(n)
        ]
        assert ev([], comps).rollup("C0", "mass", frozenset()) == float(n)

    def test_deep_chain_still_detects_a_cycle(self):
        """Depth and cycles are separate concerns — fixing one must not lose
        the other. The iterative walk keeps `visiting` as the current path."""
        comps = [
            {"id": "A", "parent": "B", "quantity": 1, "parameters": [param("m", 1)]},
            {"id": "B", "parent": "A", "quantity": 1, "parameters": [param("m", 1)]},
        ]
        with pytest.raises(EvalError, match="circular"):
            ev([], comps).rollup("A", "m", frozenset())

    def test_shared_child_under_two_parents_is_not_a_cycle(self):
        """`visiting` is the path, not a global seen-set: a diamond is legal."""
        comps = [
            {"id": "R", "parent": None, "quantity": 1, "parameters": []},
            {"id": "L", "parent": "R", "quantity": 1, "parameters": []},
            {"id": "M", "parent": "R", "quantity": 1, "parameters": []},
            {"id": "X", "parent": "L", "quantity": 1, "parameters": [param("m", 7)]},
        ]
        assert ev([], comps).rollup("R", "m", frozenset()) == 7


class TestMeasuredOverride:
    def test_override_replaces_model_value(self):
        e = ev([req("R1", [param("speed", 52)])], overrides={"R1.speed": 48})
        assert e.resolve("R1.speed") == 48


# ---- API-level: the whole chain ------------------------------------------

def put_req(client, pid, rid, **fields):
    res = client.put(f"/api/projects/{pid}/requirements/{rid}", json=fields)
    assert res.status_code == 200, res.text
    return res.json()


def test_evaluation_endpoint_full_chain(client, project):
    # Two bounding requirements and one derived from them (the SysML case).
    make_req(client, project, "MASS0001")
    put_req(client, project, "MASS0001",
            parameters=[{"name": "gross", "value": 1157, "unit": "kg"}],
            constraints=[{"expr": "gross <= 1160"}])
    make_req(client, project, "MASS0002")
    put_req(client, project, "MASS0002",
            parameters=[{"name": "empty", "value": 767, "unit": "kg"}])
    make_req(client, project, "MASS0003")
    put_req(client, project, "MASS0003",
            parameters=[{"name": "useful", "unit": "kg",
                         "expr": "MASS0001.gross - MASS0002.empty"}],
            constraints=[{"expr": "useful >= 380"}])

    # A component tree feeding a budget rollup constraint.
    client.post(f"/api/projects/{project}/components",
                json={"id": "AC", "name": "Aircraft", "type": "system",
                      "parameters": [{"name": "mass", "value": 500}]})
    client.post(f"/api/projects/{project}/components",
                json={"id": "WING", "parent": "AC", "type": "assembly", "quantity": 2,
                      "parameters": [{"name": "mass", "value": 120}]})
    make_req(client, project, "MASS0004")
    put_req(client, project, "MASS0004",
            constraints=[{"expr": "rollup('AC', 'mass') <= MASS0002.empty"}])

    # Evidence: a verification case measures the gross mass.
    client.post(f"/api/projects/{project}/verification",
                json={"id": "VC-001", "name": "Weighing"})
    client.put(f"/api/projects/{project}/verification/VC-001",
               json={"verified_requirements": ["MASS0001"],
                     "measurements": [{"parameter": "MASS0001.gross",
                                       "value": 1163, "unit": "kg"}]})

    res = client.get(f"/api/projects/{project}/evaluation")
    assert res.status_code == 200
    data = res.json()
    by_id = {r["id"]: r for r in data["requirements"]}

    # Bounded requirement passes in the model with a margin of 3.
    m1 = by_id["MASS0001"]
    assert m1["verdict"] == "pass"
    assert m1["constraints"][0]["margin"]["value"] == 3
    # …but the measured value violates the bound.
    assert m1["measured_verdict"] == "fail"
    assert m1["parameters"][0]["measured"] == 1163
    assert m1["parameters"][0]["measured_by"] == "VC-001"

    # Derived value computed across requirements: 1157 - 767 = 390.
    m3 = by_id["MASS0003"]
    assert m3["parameters"][0]["value"] == 390
    assert m3["parameters"][0]["derived"] is True
    assert m3["verdict"] == "pass"

    # Rollup: 500 + 2×120 = 740 > 767? No — 740 <= 767 passes.
    assert by_id["MASS0004"]["verdict"] == "pass"

    assert data["summary"]["pass"] == 3
    assert data["measured_summary"]["pass"] == 0
    assert data["measured_summary"]["fail"] == 1
    assert data["parameter_count"] == 5
    assert data["measurement_count"] == 1


def test_poisoned_constraint_degrades_gracefully(client, project):
    """A poisoned (over-long) constraint must error as one row, not 500 the
    whole request — the valid requirement's verdict is still computed."""
    make_req(client, project, "R-POISON")
    put_req(client, project, "R-POISON",
            constraints=[{"expr": '1' + '+1' * 20000}])
    make_req(client, project, "R-OK")
    put_req(client, project, "R-OK",
            parameters=[{"name": "x", "value": 5}],
            constraints=[{"expr": "x > 0"}])

    res = client.get(f"/api/projects/{project}/evaluation")
    assert res.status_code == 200
    data = res.json()
    by_id = {r["id"]: r for r in data["requirements"]}
    assert by_id["R-POISON"]["constraints"][0]["status"] == "error"
    assert by_id["R-OK"]["verdict"] == "pass"


def test_unknown_and_error_verdicts(client, project):
    make_req(client, project, "R-UNK")
    put_req(client, project, "R-UNK",
            constraints=[{"expr": "nothing_here > 0"}])
    make_req(client, project, "R-ERR")
    put_req(client, project, "R-ERR",
            parameters=[{"name": "a", "value": 1}],
            constraints=[{"expr": "__import__('os').system('true')"}])

    data = client.get(f"/api/projects/{project}/evaluation").json()
    by_id = {r["id"]: r for r in data["requirements"]}
    assert by_id["R-UNK"]["verdict"] == "unknown"
    assert by_id["R-ERR"]["verdict"] == "error"
    assert "allowed" in by_id["R-ERR"]["constraints"][0]["detail"]


def test_assume_gates_the_constraint(client, project):
    make_req(client, project, "R-ASM")
    put_req(client, project, "R-ASM",
            parameters=[{"name": "alt", "value": 2000},
                        {"name": "roc", "value": 500}],
            constraints=[{"expr": "roc >= 700", "assume": "alt < 1000"}])
    data = client.get(f"/api/projects/{project}/evaluation").json()
    item = next(r for r in data["requirements"] if r["id"] == "R-ASM")
    # Assumption fails → constraint out of scope, not violated.
    assert item["constraints"][0]["status"] == "not_applicable"
    assert item["verdict"] == "none"


def test_requirements_without_parametrics_are_omitted(client, project):
    make_req(client, project, "PLAIN")
    data = client.get(f"/api/projects/{project}/evaluation").json()
    assert data["requirements"] == []
    assert data["summary"]["none"] == 0 or "PLAIN" not in [
        r["id"] for r in data["requirements"]
    ]


def test_demo_seed_parametrics(tmp_path):
    """The shipped Cessna demo must exercise every parametric feature and
    evaluate to the intended verdicts."""
    from app.services.demo_seed import seed_demo_project
    from app.services.evaluation import evaluate_project
    from app.services.integrity import IntegrityChecker
    from app.services.yaml_store import YamlStore

    assert seed_demo_project(tmp_path) is True
    store = YamlStore(tmp_path / "cessna-172")

    # The component tree exists and its links are all valid.
    comps = store.list_components()
    assert len(comps) >= 15
    issues = IntegrityChecker(store).check_all()["issues"]
    assert [i for i in issues if i["type"].startswith("component_")] == []

    data = evaluate_project(store)
    by_id = {r["id"]: r for r in data["requirements"]}

    # Derived chain across requirements: 1157 - 767 = 390 useful load.
    acft = by_id["ACFT0000"]
    params = {p["name"]: p for p in acft["parameters"]}
    assert params["useful_load"]["value"] == 390
    # The intentional failure: full fuel leaves ~245 kg < 250 kg payload.
    assert acft["verdict"] == "fail"
    assert params["full_fuel_payload"]["value"] == pytest.approx(245.28)

    # Mass rollup over the design tree fits inside the empty weight. The rollup
    # now lives on a derived `design_mass` parameter, and the budget check reuses
    # the MassBudget constraint definition (bound to design_mass <= empty_mass).
    afrm = by_id["AFRM0000"]
    afrm_params = {p["name"]: p for p in afrm["parameters"]}
    assert afrm_params["design_mass"]["value"] < afrm_params["empty_mass"]["value"]
    budget_c = next(c for c in afrm["constraints"] if "MassBudget" in c["expr"])
    assert budget_c["status"] == "pass"

    # Current rollup: avionics + electrical loads < 48 A limit.
    elec = by_id["ELEC0001"]
    assert elec["constraints"][0]["status"] == "pass"
    assert elec["constraints"][0]["margin"]["value"] > 0  # positive margin

    # Chained comparison + measured evidence.
    assert by_id["PROP0001"]["verdict"] == "pass"
    assert by_id["PROP0001"]["measured_verdict"] == "pass"
    assert by_id["SAFE0001"]["verdict"] == "pass"
    assert by_id["SAFE0001"]["measured_verdict"] == "pass"
    assert by_id["AFRM0005"]["measured_verdict"] == "pass"
    assert by_id["PROP0006"]["measured_verdict"] == "pass"

    # Assume gating: arctic clause n/a, standard clause passes.
    envr = by_id["ENVR0001"]
    assert [c["status"] for c in envr["constraints"]] == ["pass", "not_applicable"]
    assert envr["verdict"] == "pass"

    # TBD parameter: honest unknown, not a failure.
    assert by_id["SAFE0003"]["verdict"] == "unknown"

    # Cross-requirement tank capacity bound.
    assert by_id["AFRM0006"]["verdict"] == "pass"

    assert data["measurement_count"] == 8


# ---- derivation depth and error narrowing --------------------------------


def _derivation_chain(n):
    """R.p0 = R.p1 + 0, R.p1 = R.p2 + 0, ... R.pn = 1 — a chain `n` deep."""
    params = [
        {"name": f"p{i}", "value": None, "expr": f"p{i + 1} + 0", "unit": ""}
        for i in range(n)
    ]
    params.append({"name": f"p{n}", "value": 1, "expr": None, "unit": ""})
    return Evaluator([{"id": "R", "parameters": params, "constraints": []}], [])


class TestDerivationDepth:
    """`resolve` recurses about four Python frames per derivation level, so a
    long enough chain raised RecursionError — not a domain error, so it reached
    the client as a 500. It is now bounded and reported as an EvalError."""

    def test_a_chain_within_the_limit_resolves(self):
        assert _derivation_chain(MAX_DERIVATION_DEPTH - 5).resolve("R.p0") == 1.0

    def test_an_over_deep_chain_is_a_domain_error_not_a_crash(self):
        with pytest.raises(EvalError, match="nested deeper than"):
            _derivation_chain(MAX_DERIVATION_DEPTH * 20).resolve("R.p0")

    def test_the_limit_leaves_headroom_under_the_frame_limit(self):
        """The guard is only useful if it fires *before* the interpreter does."""
        import sys
        assert MAX_DERIVATION_DEPTH * 4 < sys.getrecursionlimit()


class TestResolveSafeNarrowing:
    """`_resolve_safe` used to catch bare Exception, which made a broken
    expression indistinguishable from an absent value and hid real defects."""

    def test_returns_none_for_an_unknown_parameter(self):
        assert _resolve_safe(_derivation_chain(3), "R.nope") is None

    def test_returns_none_for_an_over_deep_chain(self):
        e = _derivation_chain(MAX_DERIVATION_DEPTH * 20)
        assert _resolve_safe(e, "R.p0") is None

    def test_a_genuine_defect_is_not_swallowed(self):
        class Broken(Evaluator):
            def resolve(self, ref, stack=frozenset()):
                raise TypeError("a real bug in the evaluator")

        with pytest.raises(TypeError, match="a real bug"):
            _resolve_safe(Broken([], []), "R.x")
