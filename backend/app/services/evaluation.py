"""SysML-style parametric evaluation.

Requirements and components carry typed numeric ``parameters``; requirements
carry boolean ``constraints`` over them. This module evaluates the whole
system:

- derived parameters (``expr``) are computed from other parameters, across
  entities (``GROS0001.mass - EMPT0001.mass``);
- ``rollup('COMP', 'mass')`` sums a parameter over a component subtree,
  multiplying by each child's ``quantity``;
- every constraint gets a verdict (pass / fail / unknown / not_applicable /
  error) plus a margin when the constraint is a single comparison;
- measurements recorded on verification cases are substituted into the owning
  requirement's constraints to compute a *measured* verdict — verification as
  evidence, not as a hand-set status.

Expressions are parsed with :mod:`ast` and walked against a strict whitelist:
numbers, arithmetic, comparisons, and/or/not, parameter references and a few
math functions. Nothing else evaluates, so YAML content can never execute
code.
"""
from __future__ import annotations

import ast
import math
from typing import Optional

ALLOWED_FUNCS = {
    "min": min,
    "max": max,
    "abs": abs,
    "sqrt": math.sqrt,
    "floor": math.floor,
    "ceil": math.ceil,
    "round": round,
}

_BIN_OPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Pow: lambda a, b: a ** b,
    ast.Mod: lambda a, b: a % b,
}

_CMP_OPS = {
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
}


class EvalError(Exception):
    """The expression itself is wrong (syntax, disallowed construct, ÷0)."""


class UnknownValue(Exception):
    """A referenced parameter has no value yet — verdict is unknown, not failed."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class Evaluator:
    """Resolves parameter values and evaluates expressions over them.

    ``overrides`` maps fully-qualified parameter refs (``"RID.name"``) to
    measured values; when present they replace the modelled value, which is
    how the measured verdict pass works.
    """

    def __init__(self, requirements: list[dict], components: list[dict],
                 overrides: Optional[dict[str, float]] = None,
                 definitions: Optional[list[dict]] = None):
        self.overrides = overrides or {}
        self.definitions = {d["id"]: d for d in (definitions or []) if d.get("id")}
        self.params: dict[str, dict] = {}
        for entity in [*requirements, *components]:
            for p in entity.get("parameters", []) or []:
                name = p.get("name")
                if name:
                    self.params[f"{entity['id']}.{name}"] = p
        self.components = {c["id"]: c for c in components}
        self.children: dict[str, list[dict]] = {}
        for c in components:
            self.children.setdefault(c.get("parent"), []).append(c)
        self._cache: dict[str, float] = {}

    # ---- parameter resolution -------------------------------------------

    def resolve(self, ref: str, stack: frozenset[str] = frozenset()) -> float:
        if ref in self.overrides:
            return float(self.overrides[ref])
        if ref in self._cache:
            return self._cache[ref]
        if ref in stack:
            raise EvalError(f"circular parameter derivation involving '{ref}'")
        param = self.params.get(ref)
        if param is None:
            raise UnknownValue(f"unknown parameter '{ref}'")
        owner = ref.rsplit(".", 1)[0]
        expr = param.get("expr")
        if param.get("calc_def"):
            definition = self.definitions.get(param["calc_def"])
            if definition is None:
                raise EvalError(f"parameter '{ref}' references unknown calc def '{param['calc_def']}'")
            value = self.eval_expr(definition.get("expr", ""), owner, stack | {ref},
                                   env=param.get("bindings") or {})
            if isinstance(value, bool):
                raise EvalError(f"parameter '{ref}' derives to a boolean, not a number")
        elif expr:
            value = self.eval_expr(expr, owner, stack | {ref})
            if isinstance(value, bool):
                raise EvalError(f"parameter '{ref}' derives to a boolean, not a number")
        elif param.get("value") is not None:
            value = float(param["value"])
        else:
            raise UnknownValue(f"parameter '{ref}' has no value")
        self._cache[ref] = value
        return value

    # ---- rollup over the component tree ---------------------------------

    def rollup(self, comp_id: str, name: str, stack: frozenset[str]) -> float:
        if comp_id not in self.components:
            raise UnknownValue(f"unknown component '{comp_id}' in rollup")
        total = 0.0
        found = 0

        def walk(cid: str, multiplier: float, visiting: set[str]):
            nonlocal total, found
            if cid in visiting:
                raise EvalError(f"circular component hierarchy at '{cid}'")
            visiting.add(cid)
            ref = f"{cid}.{name}"
            if ref in self.params or ref in self.overrides:
                total += self.resolve(ref, stack) * multiplier
                found += 1
            for child in self.children.get(cid, []):
                walk(child["id"], multiplier * (child.get("quantity") or 1), visiting)
            visiting.remove(cid)

        # The root's own quantity is relative to *its* parent — outside the
        # scope of this rollup — so the root contributes exactly once.
        walk(comp_id, 1.0, set())
        if found == 0:
            raise UnknownValue(f"no component under '{comp_id}' has parameter '{name}'")
        return total

    # ---- expression evaluation ------------------------------------------

    def eval_expr(self, text: str, owner: str, stack: frozenset[str] = frozenset(),
                  env: Optional[dict[str, str]] = None):
        try:
            tree = ast.parse(text, mode="eval")
        except SyntaxError as e:
            raise EvalError(f"syntax error: {e.msg}")
        return self._eval(tree.body, owner, stack, env or {})

    def _eval(self, node: ast.AST, owner: str, stack: frozenset[str],
              env: dict[str, str] = {}):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise EvalError(f"literal {node.value!r} is not a number")
            return float(node.value)

        if isinstance(node, ast.Name):
            # A bound formal resolves to its actual ref; otherwise own-parameter.
            if node.id in env:
                return self.resolve(env[node.id], stack)
            return self.resolve(f"{owner}.{node.id}", stack)

        if isinstance(node, ast.Attribute):
            if not isinstance(node.value, ast.Name):
                raise EvalError("only ENTITY.parameter references are allowed")
            return self.resolve(f"{node.value.id}.{node.attr}", stack)

        if isinstance(node, ast.BinOp):
            op = _BIN_OPS.get(type(node.op))
            if op is None:
                raise EvalError(f"operator {type(node.op).__name__} is not allowed")
            left = self._eval(node.left, owner, stack, env)
            right = self._eval(node.right, owner, stack, env)
            try:
                return op(left, right)
            except ZeroDivisionError:
                raise EvalError("division by zero")

        if isinstance(node, ast.UnaryOp):
            operand = self._eval(node.operand, owner, stack, env)
            if isinstance(node.op, ast.USub):
                return -operand
            if isinstance(node.op, ast.UAdd):
                return +operand
            if isinstance(node.op, ast.Not):
                return not operand
            raise EvalError(f"operator {type(node.op).__name__} is not allowed")

        if isinstance(node, ast.Compare):
            left = self._eval(node.left, owner, stack, env)
            for op_node, comparator in zip(node.ops, node.comparators):
                op = _CMP_OPS.get(type(op_node))
                if op is None:
                    raise EvalError(f"comparison {type(op_node).__name__} is not allowed")
                right = self._eval(comparator, owner, stack, env)
                if not op(left, right):
                    return False
                left = right
            return True

        if isinstance(node, ast.BoolOp):
            values = [self._eval(v, owner, stack, env) for v in node.values]
            return all(values) if isinstance(node.op, ast.And) else any(values)

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.keywords:
                raise EvalError("only plain calls to whitelisted functions are allowed")
            fname = node.func.id
            if fname == "rollup":
                if (len(node.args) != 2
                        or not all(isinstance(a, ast.Constant) and isinstance(a.value, str)
                                   for a in node.args)):
                    raise EvalError("rollup takes two string arguments: rollup('COMP', 'param')")
                return self.rollup(node.args[0].value, node.args[1].value, stack)
            func = ALLOWED_FUNCS.get(fname)
            if func is None:
                raise EvalError(f"function '{fname}' is not allowed")
            args = [self._eval(a, owner, stack, env) for a in node.args]
            try:
                return func(*args)
            except (ValueError, TypeError) as e:
                raise EvalError(f"{fname}: {e}")

        raise EvalError(f"disallowed syntax: {type(node).__name__}")


# ---- dimensional checking (non-fatal) -----------------------------------

class DimensionEvaluator:
    """Infers the SI dimension of an expression from parameter units, so the
    project evaluation can flag dimensionally inconsistent parameters and
    constraints as *warnings*. Unknown units and numeric literals are wildcards,
    so this only ever fires on genuinely inconsistent, known quantities.
    """

    def __init__(self, params: dict[str, dict]):
        from app.services import units
        self._units = units
        self.params = params
        self._cache: dict[str, object] = {}

    def dim_of_ref(self, ref: str, stack: frozenset[str] = frozenset()):
        if ref in self._cache:
            return self._cache[ref]
        if ref in stack:
            return None
        param = self.params.get(ref)
        if param is None:
            return None
        unit = param.get("unit")
        if unit:
            dim = self._units.dimension_of(unit)
        elif param.get("expr"):
            dim = self.dim_of_expr(param["expr"], ref.rsplit(".", 1)[0], stack | {ref})
        else:
            dim = None
        self._cache[ref] = dim
        return dim

    def dim_of_expr(self, text: str, owner: str, stack: frozenset[str] = frozenset()):
        try:
            tree = ast.parse(text, mode="eval")
        except SyntaxError:
            return None
        return self._walk(tree.body, owner, stack)

    def _walk(self, node, owner, stack):
        if isinstance(node, ast.Constant):
            return None  # bare number: dimension-agnostic
        if isinstance(node, ast.Name):
            return self.dim_of_ref(f"{owner}.{node.id}", stack)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            return self.dim_of_ref(f"{node.value.id}.{node.attr}", stack)
        if isinstance(node, ast.BinOp):
            op = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}.get(type(node.op))
            left = self._walk(node.left, owner, stack)
            right = self._walk(node.right, owner, stack)
            if op is None:
                return None
            return self._units.combine(left, op, right)
        if isinstance(node, ast.UnaryOp):
            return self._walk(node.operand, owner, stack)
        if isinstance(node, ast.Compare):
            left = self._walk(node.left, owner, stack)
            for comparator in node.comparators:
                right = self._walk(comparator, owner, stack)
                self._units.compare_dims(left, right)  # raises DimensionError on clash
                left = right
            return None
        if isinstance(node, ast.BoolOp):
            for v in node.values:
                self._walk(v, owner, stack)
            return None
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in ("min", "max", "abs"):
                dim = None
                for a in node.args:
                    d = self._walk(a, owner, stack)
                    if d is not None:
                        dim = d
                return dim
            for a in node.args:
                self._walk(a, owner, stack)
            return None
        return None


def _dimension_warning(dim_eval: "DimensionEvaluator", expr: str, owner: str) -> Optional[str]:
    """Return a human message if ``expr`` mixes incompatible units, else None."""
    from app.services.units import DimensionError
    try:
        dim_eval.dim_of_expr(expr, owner)
    except DimensionError as e:
        return str(e)
    return None


# ---- margins ------------------------------------------------------------

def _margin(evaluator: Evaluator, expr: str, owner: str) -> Optional[dict]:
    """For a single-comparison constraint, how far from the bound we sit.

    Positive margin means headroom; negative means violation depth. Only
    <, <=, >, >= produce a margin — equality and compound expressions don't
    have a meaningful distance.
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return None
    node = tree.body
    if not isinstance(node, ast.Compare) or len(node.ops) != 1:
        return None
    op = node.ops[0]
    try:
        left = evaluator._eval(node.left, owner, frozenset())
        right = evaluator._eval(node.comparators[0], owner, frozenset())
    except (EvalError, UnknownValue):
        return None
    if isinstance(op, (ast.Lt, ast.LtE)):
        margin, bound = right - left, right
    elif isinstance(op, (ast.Gt, ast.GtE)):
        margin, bound = left - right, right
    else:
        return None
    out = {"value": round(margin, 6)}
    if bound:
        out["pct"] = round(margin / abs(bound) * 100, 2)
    return out


# ---- project-level evaluation -------------------------------------------

def _constraint_verdict(evaluator: Evaluator, constraint: dict, owner: str) -> dict:
    assume = constraint.get("assume")
    env: dict[str, str] = {}
    if constraint.get("constraint_def"):
        definition = evaluator.definitions.get(constraint["constraint_def"])
        if definition is None:
            return {"expr": "", "assume": assume, "status": "error",
                    "detail": f"unknown constraint def '{constraint['constraint_def']}'"}
        expr = definition.get("expr", "")
        env = constraint.get("bindings") or {}
        display = f"{constraint['constraint_def']}({', '.join(f'{k}={v}' for k, v in env.items())})"
    else:
        expr = constraint.get("expr") or ""
        display = expr
    out: dict = {"expr": display, "assume": assume}
    try:
        if assume:
            held = evaluator.eval_expr(assume, owner)
            if not held:
                out["status"] = "not_applicable"
                out["detail"] = "assumption does not hold"
                return out
        result = evaluator.eval_expr(expr, owner, env=env)
        out["status"] = "pass" if result else "fail"
        if not env:  # margin is only meaningful for inline single-comparison exprs
            margin = _margin(evaluator, expr, owner)
            if margin is not None:
                out["margin"] = margin
    except UnknownValue as e:
        out["status"] = "unknown"
        out["detail"] = e.reason
    except EvalError as e:
        out["status"] = "error"
        out["detail"] = str(e)
    return out


def _aggregate(statuses: list[str]) -> str:
    if not statuses:
        return "none"
    if "error" in statuses:
        return "error"
    if "fail" in statuses:
        return "fail"
    if "unknown" in statuses:
        return "unknown"
    if all(s == "not_applicable" for s in statuses):
        return "none"
    return "pass"


def evaluate_project(store, scope: Optional[set[str]] = None,
                     extra_overrides: Optional[dict[str, float]] = None) -> dict:
    """Evaluate the project's parametrics.

    ``scope`` limits which requirements are reported (None = all). ``extra_overrides``
    injects hypothetical parameter values into the design evaluation — this is how
    analysis cases explore what-if inputs while reusing the same solver.
    """
    requirements = store.list_requirements()
    components = store.list_components()
    vcs = store.list_verification_cases()
    try:
        definitions = store.list_items("definitions")
    except Exception:
        definitions = []

    # Measured values: later VCs win on conflict, and each substitution
    # remembers which case supplied the evidence.
    measured: dict[str, float] = {}
    measured_by: dict[str, str] = {}
    for vc in vcs:
        for m in vc.get("measurements", []) or []:
            ref = m.get("parameter")
            if ref and m.get("value") is not None:
                measured[ref] = float(m["value"])
                measured_by[ref] = vc["id"]

    design = Evaluator(requirements, components, overrides=extra_overrides, definitions=definitions)
    as_measured = Evaluator(requirements, components, overrides=measured, definitions=definitions)
    dim_eval = DimensionEvaluator(design.params)

    items = []
    summary = {"pass": 0, "fail": 0, "unknown": 0, "error": 0, "none": 0}
    measured_summary = {"pass": 0, "fail": 0, "unmeasured": 0}

    for req in requirements:
        rid = req["id"]
        if scope is not None and rid not in scope:
            continue
        params_out = []
        for p in req.get("parameters", []) or []:
            ref = f"{rid}.{p.get('name')}"
            entry = {"name": p.get("name"), "unit": p.get("unit", ""),
                     "expr": p.get("expr"), "derived": bool(p.get("expr"))}
            try:
                entry["value"] = round(design.resolve(ref), 6)
            except UnknownValue as e:
                entry["value"] = None
                entry["detail"] = e.reason
            except EvalError as e:
                entry["value"] = None
                entry["error"] = str(e)
            if ref in measured:
                entry["measured"] = measured[ref]
                entry["measured_by"] = measured_by[ref]
            if p.get("expr"):
                warning = _dimension_warning(dim_eval, p["expr"], rid)
                if warning:
                    entry["unit_warning"] = warning
            params_out.append(entry)

        constraints_out = []
        for c in req.get("constraints", []) or []:
            cv = _constraint_verdict(design, c, rid)
            warning = _dimension_warning(dim_eval, c.get("expr", ""), rid)
            if warning:
                cv["unit_warning"] = warning
            constraints_out.append(cv)
        verdict = _aggregate([c["status"] for c in constraints_out])
        summary[verdict] = summary.get(verdict, 0) + 1

        item = {"id": rid, "name": req.get("name", ""),
                "parameters": params_out, "constraints": constraints_out,
                "verdict": verdict}

        # A measured verdict only exists when evidence covers this
        # requirement's own parameters — measurements verify the requirement
        # that owns the parameter.
        if constraints_out and any(ref.startswith(f"{rid}.") for ref in measured):
            m_constraints = [_constraint_verdict(as_measured, c, rid)
                             for c in req.get("constraints", []) or []]
            m_verdict = _aggregate([c["status"] for c in m_constraints])
            item["measured_constraints"] = m_constraints
            item["measured_verdict"] = m_verdict
            if m_verdict in ("pass", "fail"):
                measured_summary[m_verdict] += 1
        elif constraints_out and verdict != "none":
            measured_summary["unmeasured"] += 1

        if params_out or constraints_out:
            items.append(item)

    return {
        "requirements": items,
        "summary": summary,
        "measured_summary": measured_summary,
        "parameter_count": len(design.params),
        "measurement_count": len(measured),
    }


def run_analysis_case(store, case: dict) -> dict:
    """Evaluate one analysis case: its scope + hypothetical overrides."""
    scope = set(case.get("scope") or []) or None
    overrides = {k: float(v) for k, v in (case.get("overrides") or {}).items()}
    result = evaluate_project(store, scope=scope, extra_overrides=overrides)
    result["case"] = {"id": case.get("id"), "name": case.get("name", ""),
                      "scope": case.get("scope") or [], "overrides": case.get("overrides") or {}}
    return result
