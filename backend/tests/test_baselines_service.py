"""Baseline bookkeeping, extracted from the API router."""
import pytest

from app.services import baselines
from app.services.baselines import BaselineError
from app.services.yaml_store import YamlStore


def _store(tmp_path) -> YamlStore:
    s = YamlStore(tmp_path / "p")
    s.ensure_dirs()
    return s


def test_upsert_assigns_and_delete_clears(tmp_path):
    s = _store(tmp_path)
    s.create_requirement({"id": "R-1", "name": "r"})

    res = baselines.upsert(s, "BL1", "B1", "first", "2026-01-01", ["R-1"])
    assert res["requirements_assigned"] == 1
    assert "BL1" in (s.get_requirement("R-1").get("baselines") or [])

    baselines.delete(s, "BL1")
    assert "BL1" not in (s.get_requirement("R-1").get("baselines") or [])


def test_rename_moves_the_membership(tmp_path):
    s = _store(tmp_path)
    s.create_requirement({"id": "R-1", "name": "r"})
    baselines.upsert(s, "BL1", "", "", "", ["R-1"])

    res = baselines.rename(s, "BL1", "BL2", None, None, None)
    assert res["new_name"] == "BL2"
    assert "BL2" in (s.get_requirement("R-1").get("baselines") or [])


def test_rename_onto_an_existing_name_is_refused(tmp_path):
    s = _store(tmp_path)
    baselines.upsert(s, "BL1", "", "", "", [])
    baselines.upsert(s, "BL2", "", "", "", [])
    with pytest.raises(BaselineError) as exc:
        baselines.rename(s, "BL1", "BL2", None, None, None)
    assert exc.value.status == 409


def test_validate_due_dates_rejects_backwards():
    with pytest.raises(BaselineError):
        baselines.validate_due_dates([
            {"name": "A", "due_date": "2026-02-01"},
            {"name": "B", "due_date": "2026-01-01"},
        ])


def test_delete_missing_baseline_is_404(tmp_path):
    s = _store(tmp_path)
    with pytest.raises(BaselineError) as exc:
        baselines.delete(s, "NOPE")
    assert exc.value.status == 404
