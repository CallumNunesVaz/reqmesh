"""Tests for pugh_matrix — the Pugh-style comparison of requirements.

A Pugh matrix compares scored alternatives (requirements) against weighted
criteria (stakeholders) relative to a chosen datum. The datum's own column is
all zeroes — that is what a datum means.
"""

import pytest

from app.services.stakeholder_value import pugh_matrix


# ── helpers ────────────────────────────────────────────────────────────────────

def _req(rid: str, name: str = "", priorities: dict | None = None) -> dict:
    return {"id": rid, "name": name or rid, "priorities": priorities or {}}


def _stakeholders(*names_and_weights) -> list[dict]:
    """``("safety", 3.0), ("customers", 2.0)`` → [{name, weight}]."""
    return [{"name": n, "weight": w} for n, w in names_and_weights]


# ── empty matrix ───────────────────────────────────────────────────────────────

def test_no_scored_requirements_returns_empty_matrix():
    """With nothing scored, datum is None and columns is [] — not an error."""
    result = pugh_matrix(
        reqs=[_req("A"), _req("B")],
        stakeholders=_stakeholders(("s", 1.0)),
    )
    assert result["datum"] is None
    assert result["columns"] == []
    assert result["total_candidates"] == 0


def test_unscored_requirements_never_appear():
    """Requirements with value=None are excluded from every column."""
    result = pugh_matrix(
        reqs=[
            _req("R1", priorities={"a": 5}),
            _req("R2", priorities={}),     # unscored
        ],
        stakeholders=_stakeholders(("a", 1.0)),
    )
    ids = [c["id"] for c in result["columns"]]
    assert ids == ["R1"]


# ── datum ──────────────────────────────────────────────────────────────────────

def test_datum_column_is_all_zeroes():
    """The datum's own column has sign=0 for every stakeholder."""
    result = pugh_matrix(
        reqs=[
            _req("D", priorities={"a": 5}),
            _req("R1", priorities={"a": 4}),
        ],
        stakeholders=_stakeholders(("a", 1.0)),
        datum_id="D",
    )
    datum_col = next(c for c in result["columns"] if c["id"] == "D")
    for cell in datum_col["cells"].values():
        assert cell["sign"] == 0
    assert datum_col["plus"] == 0
    assert datum_col["minus"] == 0
    assert datum_col["weighted"] == 0.0


def test_datum_defaults_to_top_ranked():
    """With no datum_id given, the top-ranked candidate is the datum."""
    result = pugh_matrix(
        reqs=[
            _req("top", priorities={"a": 5}),
            _req("mid", priorities={"a": 3}),
        ],
        stakeholders=_stakeholders(("a", 1.0)),
    )
    assert result["datum"] == "top"


def test_explicit_datum_is_honoured():
    """An explicit datum_id is used when it names a candidate."""
    result = pugh_matrix(
        reqs=[
            _req("best", priorities={"a": 5}),
            _req("choose", priorities={"a": 3}),
        ],
        stakeholders=_stakeholders(("a", 1.0)),
        datum_id="choose",
    )
    assert result["datum"] == "choose"
    # "best" should score +1 against the datum "choose" (5 > 3)
    best_col = next(c for c in result["columns"] if c["id"] == "best")
    assert best_col["cells"]["a"]["sign"] == 1


def test_unknown_datum_falls_back_to_top_ranked():
    """An id that is not among the scored candidates uses the top-ranked."""
    result = pugh_matrix(
        reqs=[
            _req("top", priorities={"a": 5}),
            _req("other", priorities={"a": 3}),
        ],
        stakeholders=_stakeholders(("a", 1.0)),
        datum_id="NONEXISTENT",
    )
    assert result["datum"] == "top"


# ── signs ──────────────────────────────────────────────────────────────────────

def test_above_datum_sign_is_one():
    result = pugh_matrix(
        reqs=[
            _req("D", priorities={"a": 3}),
            _req("above", priorities={"a": 5}),
        ],
        stakeholders=_stakeholders(("a", 1.0)),
        datum_id="D",
    )
    above_col = next(c for c in result["columns"] if c["id"] == "above")
    assert above_col["cells"]["a"]["sign"] == 1
    assert above_col["plus"] == 1
    assert above_col["minus"] == 0


def test_below_datum_sign_is_minus_one():
    result = pugh_matrix(
        reqs=[
            _req("D", priorities={"a": 5}),
            _req("below", priorities={"a": 3}),
        ],
        stakeholders=_stakeholders(("a", 1.0)),
        datum_id="D",
    )
    below_col = next(c for c in result["columns"] if c["id"] == "below")
    assert below_col["cells"]["a"]["sign"] == -1
    assert below_col["plus"] == 0
    assert below_col["minus"] == 1


def test_equal_sign_is_zero():
    result = pugh_matrix(
        reqs=[
            _req("D", priorities={"a": 3}),
            _req("same", priorities={"a": 3}),
        ],
        stakeholders=_stakeholders(("a", 1.0)),
        datum_id="D",
    )
    same_col = next(c for c in result["columns"] if c["id"] == "same")
    assert same_col["cells"]["a"]["sign"] == 0
    assert same_col["plus"] == 0
    assert same_col["minus"] == 0


# ── unscored stakeholders ──────────────────────────────────────────────────────

def test_unscored_datum_stakeholder_gives_none_sign():
    """When the datum has no score for a stakeholder, every comparison is None."""
    result = pugh_matrix(
        reqs=[
            _req("D", priorities={"a": 3}),           # no "b" score
            _req("cand", priorities={"a": 3, "b": 5}),  # has "b"
        ],
        stakeholders=_stakeholders(("a", 1.0), ("b", 1.0)),
        datum_id="D",
    )
    cand_col = next(c for c in result["columns"] if c["id"] == "cand")
    assert cand_col["cells"]["a"]["sign"] == 0   # a: 3 == 3
    assert cand_col["cells"]["b"]["sign"] is None  # b: datum unscored
    assert cand_col["plus"] == 0
    assert cand_col["minus"] == 0


def test_unscored_candidate_stakeholder_gives_none_sign():
    """When the candidate has no score, sign is None."""
    result = pugh_matrix(
        reqs=[
            _req("D", priorities={"a": 3, "b": 5}),
            _req("cand", priorities={"a": 3}),        # no "b"
        ],
        stakeholders=_stakeholders(("a", 1.0), ("b", 1.0)),
        datum_id="D",
    )
    cand_col = next(c for c in result["columns"] if c["id"] == "cand")
    assert cand_col["cells"]["b"]["sign"] is None


def test_none_sign_excluded_from_plus_minus_and_weighted():
    """None signs do not contribute to plus, minus, or weighted."""
    result = pugh_matrix(
        reqs=[
            _req("D", priorities={"a": 3, "b": 4}),
            _req("cand", priorities={"a": 5}),         # no "b" → sign=None
        ],
        stakeholders=_stakeholders(("a", 1.0), ("b", 1.0)),
        datum_id="D",
    )
    cand_col = next(c for c in result["columns"] if c["id"] == "cand")
    # a: 5 > 3 → sign=1; b: unscored → sign=None
    assert cand_col["plus"] == 1
    assert cand_col["minus"] == 0
    assert cand_col["weighted"] == 1.0  # only from "a"


# ── weighted ───────────────────────────────────────────────────────────────────

def test_weighted_reflects_stakeholder_weights():
    """A heavier stakeholder moves weighted more than a light one."""
    result = pugh_matrix(
        reqs=[
            _req("D", priorities={"heavy": 0, "light": 0}),
            _req("cand", priorities={"heavy": 5, "light": 5}),
        ],
        stakeholders=_stakeholders(("heavy", 10.0), ("light", 1.0)),
        datum_id="D",
    )
    cand_col = next(c for c in result["columns"] if c["id"] == "cand")
    # Both signs are +1, but heavy's weight (10) dominates
    expected_weighted = 10.0 * 1 + 1.0 * 1
    assert cand_col["weighted"] == expected_weighted
    assert cand_col["plus"] == 2


def test_weighted_is_zero_when_datum():
    result = pugh_matrix(
        reqs=[
            _req("D", priorities={"a": 5}),
        ],
        stakeholders=_stakeholders(("a", 1.0)),
        datum_id="D",
    )
    assert result["columns"][0]["weighted"] == 0.0


# ── limit ──────────────────────────────────────────────────────────────────────

def test_limit_caps_columns():
    """limit caps the column count."""
    result = pugh_matrix(
        reqs=[
            _req(f"R{i}", priorities={"a": i}) for i in range(1, 6)
        ],
        stakeholders=_stakeholders(("a", 1.0)),
        limit=3,
    )
    assert len(result["columns"]) == 3


def test_total_candidates_reports_count_before_limit():
    """total_candidates is the count before capping."""
    result = pugh_matrix(
        reqs=[
            _req(f"R{i}", priorities={"a": i}) for i in range(1, 6)
        ],
        stakeholders=_stakeholders(("a", 1.0)),
        limit=2,
    )
    assert result["total_candidates"] == 5
    assert len(result["columns"]) == 2


# ── multiple stakeholders ──────────────────────────────────────────────────────

def test_multiple_stakeholders_each_compared_independently():
    result = pugh_matrix(
        reqs=[
            _req("D", priorities={"a": 3, "b": 3, "c": 3}),
            _req("cand", priorities={"a": 5, "b": 3, "c": 1}),
        ],
        stakeholders=_stakeholders(("a", 2.0), ("b", 1.5), ("c", 1.0)),
        datum_id="D",
    )
    cand_col = next(c for c in result["columns"] if c["id"] == "cand")
    assert cand_col["cells"]["a"]["sign"] == 1   # 5 > 3
    assert cand_col["cells"]["b"]["sign"] == 0   # 3 == 3
    assert cand_col["cells"]["c"]["sign"] == -1  # 1 < 3
    assert cand_col["plus"] == 1
    assert cand_col["minus"] == 1
    # weighted = 2.0*1 + 1.5*0 + 1.0*(-1) = 2.0 - 1.0 = 1.0
    assert cand_col["weighted"] == 1.0


def test_stakeholders_are_in_defined_order():
    """The stakeholders list in the result keeps the project's order."""
    result = pugh_matrix(
        reqs=[_req("R1", priorities={"z": 5, "a": 5, "m": 5})],
        stakeholders=_stakeholders(("z", 1.0), ("a", 1.0), ("m", 1.0)),
    )
    names = [s["name"] for s in result["stakeholders"]]
    assert names == ["z", "a", "m"]


# ── integration-style: a worked example ────────────────────────────────────────

def test_worked_example_with_three_candidates():
    """A small but realistic scenario exercising every code path."""
    result = pugh_matrix(
        reqs=[
            _req("REQ-A", name="Autopilot", priorities={"safety": 5, "customers": 4, "development": 2}),
            _req("REQ-B", name="Landing Light", priorities={"safety": 3, "customers": 1, "development": 5}),
            _req("REQ-C", name="Fuel Gauge", priorities={"safety": 4, "customers": 3}),
        ],
        stakeholders=_stakeholders(
            ("safety", 3.0), ("customers", 2.0), ("development", 1.5),
        ),
        datum_id="REQ-C",
    )
    assert result["datum"] == "REQ-C"
    assert result["total_candidates"] == 3

    # REQ-A vs datum REQ-C (4,3): safety 5 > 4 → +1; customers 4 > 3 → +1;
    # development: datum has no score for development → None
    a = next(c for c in result["columns"] if c["id"] == "REQ-A")
    assert a["cells"]["safety"]["sign"] == 1
    assert a["cells"]["customers"]["sign"] == 1
    assert a["cells"]["development"]["sign"] is None
    assert a["plus"] == 2
    assert a["minus"] == 0
    # weighted = 3*1 + 2*1 = 5.0
    assert a["weighted"] == 5.0

    # REQ-B vs datum REQ-C (4,3): safety 3 < 4 → -1; customers 1 < 3 → -1;
    # development: datum unscored → None
    b = next(c for c in result["columns"] if c["id"] == "REQ-B")
    assert b["cells"]["safety"]["sign"] == -1
    assert b["cells"]["customers"]["sign"] == -1
    assert b["cells"]["development"]["sign"] is None
    assert b["plus"] == 0
    assert b["minus"] == 2
    # weighted = 3*(-1) + 2*(-1) = -5.0
    assert b["weighted"] == -5.0

    # REQ-C is the datum — all zeroes
    c = next(col for col in result["columns"] if col["id"] == "REQ-C")
    assert c["plus"] == 0
    assert c["minus"] == 0
    assert c["weighted"] == 0.0
    for cell in c["cells"].values():
        assert cell["sign"] == 0
