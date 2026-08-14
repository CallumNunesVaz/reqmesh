"""Tests for PATCH /projects/{id}/baselines/{name} (rename_baseline)."""

from pathlib import Path

from app.core.config import settings
from tests.conftest import make_req


def _create_baseline(client, project_id, name, symbol=""):
    res = client.post(
        f"/api/projects/{project_id}/baselines",
        json={"name": name, "symbol": symbol, "description": ""},
    )
    assert res.status_code == 200, res.text
    return res.json()


def _rename(client, project_id, old_name, new_name, **fields):
    return client.patch(
        f"/api/projects/{project_id}/baselines/{old_name}",
        json={"name": new_name, **fields},
    )


# ── Bug 1: the false 404 ───────────────────────────────────────────────────


def test_edit_symbol_of_unfrozen_empty_baseline(client, project):
    """Editing the symbol of a just-created baseline (no members, not frozen)
    returns 200 and the new symbol is visible afterwards — the reported bug."""
    _create_baseline(client, project, "SRR", "S")

    res = _rename(client, project, "SRR", "SRR", symbol="SYMBO")
    assert res.status_code == 200, res.text

    listed = client.get(f"/api/projects/{project}/baselines").json()
    srr = next(b for b in listed if b["name"] == "SRR")
    assert srr["symbol"] == "SYMBO"


# ── Bug 2: the self-collision 409 ──────────────────────────────────────────


def test_edit_symbol_of_frozen_baseline_same_name(client, project):
    """Editing only the symbol of a frozen baseline (name unchanged) is 200,
    not a 409 against itself."""
    _create_baseline(client, project, "SRR", "S")
    client.post(f"/api/projects/{project}/baselines/SRR/freeze")

    res = _rename(client, project, "SRR", "SRR", symbol="SYMBO")
    assert res.status_code == 200, res.text

    # The frozen snapshot is updated in place, not deleted.
    assert client.get(f"/api/projects/{project}/baselines/SRR/diff").status_code == 200


def test_rename_onto_another_frozen_baseline_is_409(client, project):
    _create_baseline(client, project, "SRR", "S")
    client.post(f"/api/projects/{project}/baselines/SRR/freeze")
    _create_baseline(client, project, "PDR", "P")

    res = _rename(client, project, "PDR", "SRR")
    assert res.status_code == 409


def test_rename_onto_another_unfrozen_baseline_is_409(client, project):
    _create_baseline(client, project, "SRR", "S")
    _create_baseline(client, project, "PDR", "P")

    res = _rename(client, project, "PDR", "SRR")
    assert res.status_code == 409


# ── 404 leaves _meta.yaml byte-identical ───────────────────────────────────


def test_rename_missing_baseline_leaves_meta_untouched(client, project):
    _create_baseline(client, project, "SRR", "S")
    meta_path = Path(settings.data_root) / project / "_meta.yaml"
    before = meta_path.read_bytes()

    res = _rename(client, project, "NOPE", "NEW")
    assert res.status_code == 404
    assert meta_path.read_bytes() == before


# ── Renaming with members still cascades ───────────────────────────────────


def test_rename_with_members_rewrites_requirements_and_components(client, project):
    make_req(client, project, "SYST0001", baselines=["SRR"])
    res = client.post(f"/api/projects/{project}/components",
                      json={"id": "C-001", "name": "Pump", "baselines": ["SRR"]})
    assert res.status_code == 201, res.text
    _create_baseline(client, project, "SRR", "S")

    res = _rename(client, project, "SRR", "PDR")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["old_name"] == "SRR"
    assert body["new_name"] == "PDR"
    assert body["requirements_updated"] == 1

    req = client.get(f"/api/projects/{project}/requirements/SYST0001").json()
    assert "PDR" in req["baselines"]
    assert "SRR" not in req["baselines"]
    comp = client.get(f"/api/projects/{project}/components/C-001").json()
    assert "PDR" in comp["baselines"]
    assert "SRR" not in comp["baselines"]
