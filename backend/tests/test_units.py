"""Slice 2: SI dimension algebra + non-fatal dimensional checking."""

import pytest

from app.services import units
from app.services.evaluation import evaluate_project
from app.services.yaml_store import YamlStore


def test_dimension_of():
    assert units.dimension_of("kg") == (0, 1, 0, 0, 0, 0, 0)
    assert units.dimension_of("m") == (1, 0, 0, 0, 0, 0, 0)
    assert units.dimension_of("N") == (1, 1, -2, 0, 0, 0, 0)
    assert units.dimension_of("") is None          # dimensionless-empty → wildcard
    assert units.dimension_of("bananas") is None    # unknown → wildcard


def test_combine_and_compare():
    kg = units.dimension_of("kg")
    m = units.dimension_of("m")
    s = units.dimension_of("s")
    # like quantities add fine; result keeps the dimension
    assert units.combine(kg, "+", kg) == kg
    # unlike quantities can't be added
    with pytest.raises(units.DimensionError):
        units.combine(kg, "+", m)
    # multiplication/division compose exponents
    assert units.combine(m, "/", s) == units.dimension_of("m/s")
    # wildcard (literal / unknown) never clashes
    assert units.combine(kg, "+", None) == kg
    with pytest.raises(units.DimensionError):
        units.compare_dims(kg, s)
    units.compare_dims(kg, None)  # no raise


def _store(tmp_path, name="u"):
    s = YamlStore(tmp_path / name)
    s.ensure_dirs()
    s.write_meta({"name": name})
    return s


def test_evaluation_flags_unit_mismatch(tmp_path):
    s = _store(tmp_path)
    s.create_requirement({
        "id": "R1", "name": "mix",
        "parameters": [
            {"name": "mass", "value": 10.0, "unit": "kg"},
            {"name": "span", "value": 2.0, "unit": "m"},
            {"name": "bad", "expr": "mass + span", "unit": "kg"},
        ],
        "constraints": [{"expr": "mass <= 1157"}],  # quantity vs bare number: no warning
    })
    result = evaluate_project(s)
    req = next(r for r in result["requirements"] if r["id"] == "R1")
    bad = next(p for p in req["parameters"] if p["name"] == "bad")
    assert "unit_warning" in bad          # kg + m flagged
    # the plain "mass <= 1157" constraint must NOT warn (literal is wildcard)
    assert "unit_warning" not in req["constraints"][0]


def test_evaluation_no_warning_for_consistent_units(tmp_path):
    s = _store(tmp_path, "ok")
    s.create_requirement({
        "id": "R2", "name": "ok",
        "parameters": [
            {"name": "a", "value": 10.0, "unit": "kg"},
            {"name": "b", "value": 5.0, "unit": "kg"},
            {"name": "total", "expr": "a + b", "unit": "kg"},
        ],
        "constraints": [{"expr": "total <= 20"}],
    })
    result = evaluate_project(s)
    req = next(r for r in result["requirements"] if r["id"] == "R2")
    assert all("unit_warning" not in p for p in req["parameters"])
    assert all("unit_warning" not in c for c in req["constraints"])
