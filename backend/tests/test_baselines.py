"""Tests for baseline diff, including the baseline-against-baseline path."""

from __future__ import annotations

from tests.conftest import make_req


def _create_baseline(client, project_id, name, symbol=""):
    res = client.post(
        f"/api/projects/{project_id}/baselines",
        json={"name": name, "symbol": symbol, "description": ""},
    )
    assert res.status_code == 200, res.text
    return res.json()


def _tick(client, project_id, req_id, baseline_name):
    res = client.put(
        f"/api/projects/{project_id}/requirements/{req_id}",
        json={"baselines": [baseline_name]},
    )
    assert res.status_code == 200, res.text
    return res.json()


def _freeze(client, project_id, name):
    res = client.post(f"/api/projects/{project_id}/baselines/{name}/freeze")
    assert res.status_code == 200, res.text
    return res.json()


def _diff(client, project_id, name, against=None):
    url = f"/api/projects/{project_id}/baselines/{name}/diff"
    if against:
        url += f"?against={against}"
    return client.get(url)


# ── baseline-against-baseline ─────────────────────────────────────────────


def test_diff_two_baselines_differing_field(client, project):
    """Two frozen baselines with a differing field on a shared requirement
    produce a diff naming that field, with before/after the right way round."""
    make_req(client, project, "R-1", name="First", status="proposed")
    _create_baseline(client, project, "SRR", "S")
    _tick(client, project, "R-1", "SRR")
    _freeze(client, project, "SRR")

    # Update the requirement before freezing the second baseline.
    client.put(
        f"/api/projects/{project}/requirements/R-1",
        json={"status": "approved"},
    )
    _create_baseline(client, project, "PDR", "P")
    _tick(client, project, "R-1", "PDR")
    _freeze(client, project, "PDR")

    res = _diff(client, project, "SRR", against="PDR")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["baseline"] == "SRR"
    assert data["against"] == "PDR"

    changes = {c["id"]: c for c in data["changes"]}
    assert "R-1" in changes
    c = changes["R-1"]
    assert c["type"] == "modified"
    assert "status" in c["diffs"]
    # SRR is "before" (snap_val), PDR is "after" (after_val).
    assert c["diffs"]["status"]["before"] == "proposed"
    assert c["diffs"]["status"]["after"] == "approved"


def test_diff_added_side_of_second_baseline(client, project):
    """A requirement in the second baseline but not the first is 'added'."""
    make_req(client, project, "R-1")
    _create_baseline(client, project, "SRR", "S")
    _tick(client, project, "R-1", "SRR")
    _freeze(client, project, "SRR")

    # Create a new requirement and freeze a second baseline that includes it.
    make_req(client, project, "R-2")
    _create_baseline(client, project, "PDR", "P")
    _tick(client, project, "R-2", "PDR")
    _freeze(client, project, "PDR")

    # SRR against PDR: R-2 is added (absent from SRR, present in PDR).
    res = _diff(client, project, "SRR", against="PDR")
    assert res.status_code == 200, res.text
    data = res.json()
    changes = {c["id"]: c for c in data["changes"]}
    assert changes["R-2"]["type"] == "added"


def test_diff_removed_side_of_second_baseline(client, project):
    """A requirement in the first baseline but not the second is 'removed'."""
    make_req(client, project, "R-1")
    make_req(client, project, "R-2")
    _create_baseline(client, project, "SRR", "S")
    _tick(client, project, "R-1", "SRR")
    _tick(client, project, "R-2", "SRR")
    _freeze(client, project, "SRR")

    _create_baseline(client, project, "PDR", "P")
    _tick(client, project, "R-1", "PDR")
    _freeze(client, project, "PDR")

    # SRR against PDR: R-2 is removed (present in SRR, absent from PDR).
    res = _diff(client, project, "SRR", against="PDR")
    assert res.status_code == 200, res.text
    data = res.json()
    changes = {c["id"]: c for c in data["changes"]}
    assert changes["R-2"]["type"] == "removed"


def test_diff_against_nonexistent_baseline_404(client, project):
    """`against` naming a baseline that does not exist is a 404."""
    _create_baseline(client, project, "SRR", "S")
    make_req(client, project, "R-1")
    _tick(client, project, "R-1", "SRR")
    _freeze(client, project, "SRR")

    res = _diff(client, project, "SRR", against="NOPEX")
    assert res.status_code == 404
    detail = res.json().get("detail", "")
    assert "NOPEX" in detail


def test_diff_against_unsafe_id_rejected(client, project):
    """`against` naming an unsafe id (../etc/passwd) is rejected."""
    _create_baseline(client, project, "SRR", "S")
    make_req(client, project, "R-1")
    _tick(client, project, "R-1", "SRR")
    _freeze(client, project, "SRR")

    res = _diff(client, project, "SRR", against="../etc/passwd")
    assert res.status_code == 400


def test_diff_baseline_against_itself_returns_no_changes(client, project):
    """A baseline against itself returns no changes."""
    make_req(client, project, "R-1")
    _create_baseline(client, project, "SRR", "S")
    _tick(client, project, "R-1", "SRR")
    _freeze(client, project, "SRR")

    res = _diff(client, project, "SRR", against="SRR")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["changed_count"] == 0
    assert data["changes"] == []


# ── no-against path still works, unchanged ────────────────────────────────


def test_diff_against_current_types_are_unchanged(client, project):
    """The no-against diff still classifies every entry, and only ever as one of
    the three known kinds — the `against` branch must not have disturbed it."""
    make_req(client, project, "R-1", priority="medium")
    _create_baseline(client, project, "SRR", "S")
    _tick(client, project, "R-1", "SRR")
    _freeze(client, project, "SRR")

    # Create a new requirement not in the snapshot so we have something to diff.
    make_req(client, project, "R-2", priority="medium")

    res = _diff(client, project, "SRR")
    assert res.status_code == 200, res.text
    data = res.json()
    for c in data["changes"]:
        assert c["type"] in ("modified", "added", "removed"), c
    assert data["changed_count"] > 0


def test_diff_against_current_reports_an_edit(client, project):
    """An edit since the freeze is `modified`, with the snapshot as the before."""
    make_req(client, project, "R-1", name="Old")
    _create_baseline(client, project, "SRR", "S")
    _tick(client, project, "R-1", "SRR")
    _freeze(client, project, "SRR")

    # Change the requirement name.
    client.put(
        f"/api/projects/{project}/requirements/R-1",
        json={"name": "New"},
    )

    res = _diff(client, project, "SRR")
    assert res.status_code == 200, res.text
    data = res.json()
    changes = {c["id"]: c for c in data["changes"]}
    assert changes["R-1"]["type"] == "modified"
    assert changes["R-1"]["diffs"]["name"]["before"] == "Old"
    assert changes["R-1"]["diffs"]["name"]["after"] == "New"


def test_diff_against_current_reports_a_new_requirement(client, project):
    """A requirement created since the freeze is `added` — the classification the
    UI needs, and the reason a separate `presence` field would only duplicate
    `type` and be free to disagree with it."""
    make_req(client, project, "R-1")
    _create_baseline(client, project, "SRR", "S")
    _tick(client, project, "R-1", "SRR")
    _freeze(client, project, "SRR")

    # Create a new requirement not in the snapshot.
    make_req(client, project, "R-2")

    res = _diff(client, project, "SRR")
    assert res.status_code == 200, res.text
    data = res.json()
    changes = {c["id"]: c for c in data["changes"]}
    assert changes["R-2"]["type"] == "added"
