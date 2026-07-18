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
                 overrides: Optional[dict[str, float]] = None):
        self.overrides = overrides or {}
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
        expr = param.get("expr")
        if expr:
            owner = ref.rsplit(".", 1)[0]
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

    def eval_expr(self, text: str, owner: str, stack: frozenset[str] = frozenset()):
        try:
            tree = ast.parse(text, mode="eval")
        except SyntaxError as e:
            raise EvalError(f"syntax error: {e.msg}")
        return self._eval(tree.body, owner, stack)

    def _eval(self, node: ast.AST, owner: str, stack: frozenset[str]):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise EvalError(f"literal {node.value!r} is not a number")
            return float(node.value)

        if isinstance(node, ast.Name):
            return self.resolve(f"{owner}.{node.id}", stack)

        if isinstance(node, ast.Attribute):
            if not isinstance(node.value, ast.Name):
                raise EvalError("only ENTITY.parameter references are allowed")
            return self.resolve(f"{node.value.id}.{node.attr}", stack)

        if isinstance(node, ast.BinOp):
            op = _BIN_OPS.get(type(node.op))
            if op is None:
                raise EvalError(f"operator {type(node.op).__name__} is not allowed")
            left = self._eval(node.left, owner, stack)
            right = self._eval(node.right, owner, stack)
            try:
                return op(left, right)
            except ZeroDivisionError:
                raise EvalError("division by zero")

        if isinstance(node, ast.UnaryOp):
            operand = self._eval(node.operand, owner, stack)
            if isinstance(node.op, ast.USub):
                return -operand
            if isinstance(node.op, ast.UAdd):
                return +operand
            if isinstance(node.op, ast.Not):
                return not operand
            raise EvalError(f"operator {type(node.op).__name__} is not allowed")

        if isinstance(node, ast.Compare):
            left = self._eval(node.left, owner, stack)
            for op_node, comparator in zip(node.ops, node.comparators):
                op = _CMP_OPS.get(type(op_node))
                if op is None:
                    raise EvalError(f"comparison {type(op_node).__name__} is not allowed")
                right = self._eval(comparator, owner, stack)
                if not op(left, right):
                    return False
                left = right
            return True

        if isinstance(node, ast.BoolOp):
            values = [self._eval(v, owner, stack) for v in node.values]
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
            args = [self._eval(a, owner, stack) for a in node.args]
            try:
                return func(*args)
            except (ValueError, TypeError) as e:
                raise EvalError(f"{fname}: {e}")

        raise EvalError(f"disallowed syntax: {type(node).__name__}")


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
    expr = constraint.get("expr") or ""
    assume = constraint.get("assume")
    out: dict = {"expr": expr, "assume": assume}
    try:
        if assume:
            held = evaluator.eval_expr(assume, owner)
            if not held:
                out["status"] = "not_applicable"
                out["detail"] = "assumption does not hold"
                return out
        result = evaluator.eval_expr(expr, owner)
        out["status"] = "pass" if result else "fail"
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


def evaluate_project(store) -> dict:
    requirements = store.list_requirements()
    components = store.list_components()
    vcs = store.list_verification_cases()

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

    design = Evaluator(requirements, components)
    as_measured = Evaluator(requirements, components, overrides=measured)

    items = []
    summary = {"pass": 0, "fail": 0, "unknown": 0, "error": 0, "none": 0}
    measured_summary = {"pass": 0, "fail": 0, "unmeasured": 0}

    for req in requirements:
        rid = req["id"]
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
            params_out.append(entry)

        constraints_out = [_constraint_verdict(design, c, rid)
                           for c in req.get("constraints", []) or []]
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
