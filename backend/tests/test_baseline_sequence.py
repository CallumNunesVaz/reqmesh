"""Tests for ordered baseline sequence and due-date validation."""
from pathlib import Path

from app.core.config import settings


# ── Ordering ──────────────────────────────────────────────────────────────────

def test_baselines_are_in_meta_order_not_alphabetical(client, project):
    """Baselines come back in ``_meta.yaml`` order, not sorted by name."""
    # SRR -> PDR -> CDR: alphabetical would be CDR, PDR, SRR.
    client.patch(f"/api/projects/{project}", json={"baselines": [
        {"name": "SRR"}, {"name": "PDR"}, {"name": "CDR"},
    ]})
    names = [b["name"] for b in client.get(f"/api/projects/{project}/baselines").json()]
    assert names == ["SRR", "PDR", "CDR"]


def test_order_is_1_based_and_contiguous(client, project):
    client.patch(f"/api/projects/{project}", json={"baselines": [
        {"name": "A"}, {"name": "B"}, {"name": "C"},
    ]})
    baselines = client.get(f"/api/projects/{project}/baselines").json()
    orders = [(b["name"], b["order"]) for b in baselines]
    assert orders == [("A", 1), ("B", 2), ("C", 3)]


def test_orphan_baseline_gets_order_zero_and_sorts_last(client, project):
    """A baseline only present on requirement.baselines gets order 0."""
    from .conftest import make_req

    # Define one baseline.
    client.patch(f"/api/projects/{project}", json={"baselines": [{"name": "Z"}]})
    # Assign another name directly on a requirement.
    make_req(client, project, "SYST0001", baselines=["X", "Z"])

    baselines = client.get(f"/api/projects/{project}/baselines").json()
    # Defined baseline Z comes first (order 1), then orphan X (order 0).
    assert [b["name"] for b in baselines] == ["Z", "X"]
    assert baselines[0]["order"] == 1
    assert baselines[1]["order"] == 0
    assert baselines[1]["due_date"] == ""


def test_order_is_never_written_to_meta_yaml(client, project):
    """``order`` is derived, not stored — assert on the file on disk."""
    from app.services.yaml_store import YamlStore

    client.patch(f"/api/projects/{project}", json={"baselines": [
        {"name": "SRR"}, {"name": "PDR"},
    ]})
    store = YamlStore(Path(settings.data_root) / project)
    meta = store.read_meta()
    stored = meta["baselines"]
    for d in stored:
        assert "order" not in d, f"order was written to _meta.yaml: {d}"


# ── Due-date reading (lenient) ───────────────────────────────────────────────

def test_malformed_due_date_on_disk_degrades_to_empty(client, project):
    """A bad date in hand-edited _meta.yaml degrades to '' on read."""
    from app.services.yaml_store import YamlStore

    store = YamlStore(Path(settings.data_root) / project)
    meta = store.read_meta()
    meta["baselines"] = [{"name": "BL1", "due_date": "not-a-date"}]
    store.write_meta(meta)

    baselines = client.get(f"/api/projects/{project}/baselines").json()
    assert baselines[0]["due_date"] == ""
    # The project endpoint normalizes it too.
    project_data = client.get(f"/api/projects/{project}").json()
    assert project_data["baselines"][0]["due_date"] == ""


# ── Due-date validation (write path, strict) ──────────────────────────────────

def _baselines_unchanged(client, project):
    """Snapshot the current baselines list for post-failure comparison."""
    return client.get(f"/api/projects/{project}/baselines").json()


def test_patch_projects_rejects_malformed_due_date(client, project):
    before = _baselines_unchanged(client, project)
    res = client.patch(f"/api/projects/{project}", json={"baselines": [
        {"name": "BL1", "due_date": "bad"},
    ]})
    assert res.status_code == 400
    assert "Invalid due date" in res.json()["detail"]
    # The stored baselines are untouched.
    assert client.get(f"/api/projects/{project}/baselines").json() == before


def test_patch_projects_rejects_backwards_due_date(client, project):
    before = _baselines_unchanged(client, project)
    res = client.patch(f"/api/projects/{project}", json={"baselines": [
        {"name": "BL1", "due_date": "2026-05-01"},
        {"name": "BL2", "due_date": "2026-04-01"},
    ]})
    assert res.status_code == 400
    assert "Due dates must not go backwards" in res.json()["detail"]
    assert client.get(f"/api/projects/{project}/baselines").json() == before


def test_create_baseline_rejects_malformed_due_date(client, project):
    before = _baselines_unchanged(client, project)
    res = client.post(f"/api/projects/{project}/baselines", json={
        "name": "BL1", "due_date": "nope",
    })
    assert res.status_code == 400
    assert "Invalid due date" in res.json()["detail"]
    assert client.get(f"/api/projects/{project}/baselines").json() == before


def test_create_baseline_rejects_backwards_due_date(client, project):
    client.patch(f"/api/projects/{project}", json={"baselines": [
        {"name": "BL1", "due_date": "2026-05-01"},
    ]})
    before = client.get(f"/api/projects/{project}/baselines").json()
    res = client.post(f"/api/projects/{project}/baselines", json={
        "name": "BL2", "due_date": "2026-04-01",
    })
    assert res.status_code == 400
    assert "Due dates must not go backwards" in res.json()["detail"]
    assert client.get(f"/api/projects/{project}/baselines").json() == before


def test_rename_baseline_rejects_malformed_due_date(client, project):
    from .conftest import make_req

    client.patch(f"/api/projects/{project}", json={"baselines": [{"name": "BL1"}]})
    # The rename endpoint requires at least one requirement tagged or a frozen
    # snapshot, otherwise it returns 404. Tag a requirement.
    make_req(client, project, "SYST0001", baselines=["BL1"])
    before = client.get(f"/api/projects/{project}/baselines").json()
    res = client.patch(f"/api/projects/{project}/baselines/BL1", json={
        "name": "BL1", "due_date": "bad!",
    })
    assert res.status_code == 400
    assert "Invalid due date" in res.json()["detail"]
    assert client.get(f"/api/projects/{project}/baselines").json() == before


def test_reorder_rejects_backwards_due_date(client, project):
    client.patch(f"/api/projects/{project}", json={"baselines": [
        {"name": "BL1", "due_date": "2026-05-01"},
        {"name": "BL2", "due_date": "2026-03-01"},
    ]})
    before = client.get(f"/api/projects/{project}/baselines").json()
    # Swapping them would put BL2 (03-01) after BL1 (05-01) — that's fine.
    # But ordering BL2 first — it's already first. We need a case where
    # reordering makes the dates go backwards. Let's create three.
    client.patch(f"/api/projects/{project}", json={"baselines": [
        {"name": "A", "due_date": "2026-01-01"},
        {"name": "B", "due_date": "2026-06-01"},
        {"name": "C", "due_date": "2026-03-01"},
    ]})
    before = client.get(f"/api/projects/{project}/baselines").json()
    # Current order is A, B, C. B(06-01) then C(03-01) is already backwards,
    # but the write was accepted (no validation yet on creation order with
    # patch). Now reorder: if we put C before B but after A, C(03-01) <
    # B(06-01) would be fine if C were before B. Wait, the current order A,
    # B, C has B(06-01) then C(03-01) -> backwards. But we created them
    # with patch which validates... Actually patch does validate now. Let me
    # use a valid initial order and then reorder badly.
    client.patch(f"/api/projects/{project}", json={"baselines": [
        {"name": "A", "due_date": "2026-01-01"},
        {"name": "B", "due_date": "2026-03-01"},
        {"name": "C", "due_date": "2026-06-01"},
    ]})
    before = client.get(f"/api/projects/{project}/baselines").json()
    # Reorder: C, B, A — C(06-01) then B(03-01) goes backwards.
    res = client.put(f"/api/projects/{project}/baselines/order", json={
        "names": ["C", "B", "A"],
    })
    assert res.status_code == 400
    assert "Due dates must not go backwards" in res.json()["detail"]
    assert client.get(f"/api/projects/{project}/baselines").json() == before


def test_date_2026_13_45_rejected(client, project):
    """Regex passes (YYYY-MM-DD shape), but date parse fails."""
    res = client.patch(f"/api/projects/{project}", json={"baselines": [
        {"name": "BL1", "due_date": "2026-13-45"},
    ]})
    assert res.status_code == 400
    assert "Invalid due date" in res.json()["detail"]


def test_empty_due_dates_skipped_by_monotonic_check(client, project):
    """Empty due dates are skipped, not treated as position zero."""
    # A then B(2026-01-01) then C("") then D(2025-12-31) — D is before B.
    # This should be rejected even though C is in between.
    res = client.patch(f"/api/projects/{project}", json={"baselines": [
        {"name": "A", "due_date": ""},
        {"name": "B", "due_date": "2026-01-01"},
        {"name": "C", "due_date": ""},
        {"name": "D", "due_date": "2025-12-31"},
    ]})
    assert res.status_code == 400
    assert "Due dates must not go backwards" in res.json()["detail"]
    assert "D" in res.json()["detail"]

    # But equal non-empty dates are allowed.
    res = client.patch(f"/api/projects/{project}", json={"baselines": [
        {"name": "B1", "due_date": "2026-01-01"},
        {"name": "B2", "due_date": "2026-01-01"},
    ]})
    assert res.status_code == 200

    # And all-empty is fine.
    res = client.patch(f"/api/projects/{project}", json={"baselines": [
        {"name": "X", "due_date": ""},
        {"name": "Y", "due_date": ""},
    ]})
    assert res.status_code == 200


# ── Reorder endpoint ──────────────────────────────────────────────────────────

def test_reorder_happy_path(client, project):
    client.patch(f"/api/projects/{project}", json={"baselines": [
        {"name": "SRR"}, {"name": "PDR"}, {"name": "CDR"},
    ]})
    res = client.put(f"/api/projects/{project}/baselines/order", json={
        "names": ["CDR", "SRR", "PDR"],
    })
    assert res.status_code == 200
    returned = [b["name"] for b in res.json()["baselines"]]
    assert returned == ["CDR", "SRR", "PDR"]

    # Reading back confirms the new order.
    baselines = client.get(f"/api/projects/{project}/baselines").json()
    assert [b["name"] for b in baselines] == ["CDR", "SRR", "PDR"]
    assert [b["order"] for b in baselines] == [1, 2, 3]


def test_reorder_missing_name(client, project):
    client.patch(f"/api/projects/{project}", json={"baselines": [
        {"name": "A"}, {"name": "B"},
    ]})
    res = client.put(f"/api/projects/{project}/baselines/order", json={
        "names": ["A"],  # missing B
    })
    assert res.status_code == 400
    assert "must list every defined baseline exactly once" in res.json()["detail"]


def test_reorder_duplicate_name(client, project):
    client.patch(f"/api/projects/{project}", json={"baselines": [
        {"name": "A"}, {"name": "B"},
    ]})
    res = client.put(f"/api/projects/{project}/baselines/order", json={
        "names": ["A", "B", "A"],
    })
    assert res.status_code == 400
    assert "must list every defined baseline exactly once" in res.json()["detail"]


def test_reorder_extra_unknown_name(client, project):
    client.patch(f"/api/projects/{project}", json={"baselines": [
        {"name": "A"}, {"name": "B"},
    ]})
    res = client.put(f"/api/projects/{project}/baselines/order", json={
        "names": ["A", "B", "C"],
    })
    assert res.status_code == 400
    assert "must list every defined baseline exactly once" in res.json()["detail"]


def test_reorder_rejects_bad_due_date_sequence(client, project):
    client.patch(f"/api/projects/{project}", json={"baselines": [
        {"name": "A", "due_date": "2026-01-01"},
        {"name": "B", "due_date": "2026-06-01"},
    ]})
    before = client.get(f"/api/projects/{project}/baselines").json()
    # Reversing puts B (06-01) before A (01-01) — backwards.
    res = client.put(f"/api/projects/{project}/baselines/order", json={
        "names": ["B", "A"],
    })
    assert res.status_code == 400
    assert "Due dates must not go backwards" in res.json()["detail"]
    assert client.get(f"/api/projects/{project}/baselines").json() == before


# ── Round-trip ────────────────────────────────────────────────────────────────

def test_create_with_due_date_round_trip(client, project):
    """Create with a due date, read it back, rename preserving it."""
    from .conftest import make_req

    res = client.post(f"/api/projects/{project}/baselines", json={
        "name": "BL1", "due_date": "2026-08-01",
    })
    assert res.status_code == 200
    assert res.json()["due_date"] == "2026-08-01"

    # Make a requirement tagged with BL1 so the rename finds something to
    # update (otherwise it 404s when no requirements or frozen snapshots
    # reference the baseline).
    make_req(client, project, "SYST0001", baselines=["BL1"])

    # Rename with due_date=None leaves it alone.
    res = client.patch(f"/api/projects/{project}/baselines/BL1", json={
        "name": "BL2", "due_date": None,
    })
    assert res.status_code == 200
    baselines = client.get(f"/api/projects/{project}/baselines").json()
    bl2 = next(b for b in baselines if b["name"] == "BL2")
    assert bl2["due_date"] == "2026-08-01"

    # Tag another requirement for the next rename.
    make_req(client, project, "SYST0002", baselines=["BL2"])

    # Rename with due_date="" clears it.
    res = client.patch(f"/api/projects/{project}/baselines/BL2", json={
        "name": "BL3", "due_date": "",
    })
    assert res.status_code == 200
    baselines = client.get(f"/api/projects/{project}/baselines").json()
    bl3 = next(b for b in baselines if b["name"] == "BL3")
    assert bl3["due_date"] == ""
