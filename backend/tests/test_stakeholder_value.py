"""Weighted stakeholder value (see services/stakeholder_value.py)."""

from app.services.meta_defs import normalize_stakeholders
from app.services.stakeholder_value import compute_value, rank_requirements

SH = [
    {"name": "Safety", "weight": 0.5},
    {"name": "Customers", "weight": 0.3},
    {"name": "Development", "weight": 0.2},
]


def test_weighted_mean_not_a_sum():
    """The old /backlog ranking summed the scores, so a requirement scored by
    more stakeholders outranked one they all agreed was more valuable."""
    everyone_mediocre = compute_value({"Safety": 5, "Customers": 5, "Development": 5}, SH)
    one_stakeholder_max = compute_value({"Safety": 10}, SH)

    assert everyone_mediocre["value"] == 5.0
    assert one_stakeholder_max["value"] == 10.0
    # A sum would have given 15 vs 10 and ranked them the other way round.
    assert sum({"Safety": 5, "Customers": 5, "Development": 5}.values()) > 10


def test_weighting_actually_applies():
    heavy = compute_value({"Safety": 10, "Development": 0}, SH)
    light = compute_value({"Safety": 0, "Development": 10}, SH)
    assert heavy["value"] > light["value"]
    # 0.5*10 / (0.5+0.2) vs 0.2*10 / (0.5+0.2)
    assert heavy["value"] == round(5.0 / 0.7, 2)
    assert light["value"] == round(2.0 / 0.7, 2)


def test_unscored_is_none_not_zero():
    """"Nobody has assessed this" and "everybody rated it zero" are different,
    and collapsing them would rank an unassessed requirement as worst."""
    result = compute_value({}, SH)
    assert result["value"] is None
    assert result["scored_count"] == 0
    assert result["stakeholder_count"] == 3


def test_adding_a_stakeholder_does_not_depress_existing_scores():
    """A mean over *all* defined stakeholders would treat the new one as a zero
    for every requirement already scored."""
    before = compute_value({"Safety": 10, "Customers": 10, "Development": 10}, SH)
    after = compute_value({"Safety": 10, "Customers": 10, "Development": 10},
                          SH + [{"name": "Regulator", "weight": 0.9}])
    assert before["value"] == after["value"] == 10.0
    assert after["stakeholder_count"] == 4
    assert after["scored_count"] == 3


def test_scores_for_unknown_stakeholders_are_surfaced():
    """Residue from a renamed or removed stakeholder must not be silently
    dropped — the requirement would look unscored while its data says otherwise."""
    result = compute_value({"Legal": 9}, SH)
    assert result["unknown_stakeholders"] == ["Legal"]
    assert result["value"] is None


def test_non_numeric_score_is_ignored_not_fatal():
    result = compute_value({"Safety": "high", "Customers": 6}, SH)
    assert result["value"] == 6.0
    assert result["scored_count"] == 1


def test_zero_weight_stakeholder_does_not_divide_by_zero():
    result = compute_value({"Ignored": 10}, [{"name": "Ignored", "weight": 0.0}])
    assert result["value"] is None


def test_rank_is_dense_and_unscored_is_unranked():
    reqs = [
        {"id": "A", "priorities": {"Safety": 10}},
        {"id": "B", "priorities": {"Safety": 10}},
        {"id": "C", "priorities": {"Safety": 1}},
        {"id": "D", "priorities": {}},
    ]
    by_id = {r["id"]: r for r in rank_requirements(reqs, SH)}
    assert by_id["A"]["rank"] == by_id["B"]["rank"] == 1
    assert by_id["C"]["rank"] == 3          # dense: two share rank 1
    assert by_id["D"]["rank"] is None       # unscored is unknown, not worst


# ── Project-level stakeholder definitions ────────────────────────────────────

def test_normalize_accepts_legacy_bare_strings():
    """Mirrors normalize_baseline_defs: a project that listed names before
    weights existed keeps working."""
    assert normalize_stakeholders(["Safety", "Customers"]) == [
        {"name": "Safety", "weight": 1.0},
        {"name": "Customers", "weight": 1.0},
    ]


def test_normalize_rejects_junk_and_clamps_negatives():
    assert normalize_stakeholders([{"weight": 2}]) == []          # no name
    assert normalize_stakeholders([{"name": "X", "weight": "abc"}]) == [{"name": "X", "weight": 1.0}]
    assert normalize_stakeholders([{"name": "X", "weight": -5}]) == [{"name": "X", "weight": 0.0}]


def test_stakeholders_round_trip_through_project_settings(client, project):
    res = client.patch(f"/api/projects/{project}", json={
        "stakeholders": [{"name": "Safety", "weight": 0.5}, "Customers"],
    })
    assert res.status_code == 200

    got = client.get(f"/api/projects/{project}").json()["stakeholders"]
    assert got == [{"name": "Safety", "weight": 0.5}, {"name": "Customers", "weight": 1.0}]


def test_value_endpoint(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    client.patch(f"/api/projects/{project}", json={
        "stakeholders": [{"name": "Safety", "weight": 0.5}, {"name": "Dev", "weight": 0.5}],
    })
    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "VAL1", "name": "V1", "description": "x",
                              "priorities": {"Safety": 8, "Dev": 4}})
    store.create_requirement({"id": "VAL2", "name": "V2", "description": "x",
                              "priorities": {"Safety": 2, "Dev": 2}})

    res = client.get(f"/api/projects/{project}/requirements/VAL1/value")
    assert res.status_code == 200
    data = res.json()
    assert data["value"] == 6.0
    assert data["rank"] == 1
    assert data["scored_count"] == 2 and data["stakeholder_count"] == 2

    assert client.get(f"/api/projects/{project}/requirements/NOPE/value").status_code == 404


def test_backlog_uses_the_same_number_as_the_inspector(client, project):
    """The two used to disagree: /backlog summed, the inspector had nothing."""
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    client.patch(f"/api/projects/{project}", json={
        "stakeholders": [{"name": "Safety", "weight": 0.5}, {"name": "Dev", "weight": 0.5}],
    })
    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "BK1", "name": "B1", "description": "x",
                              "priorities": {"Safety": 8, "Dev": 4}})

    backlog = client.get(f"/api/projects/{project}/backlog").json()
    entry = next(i for i in backlog["items"] if i["id"] == "BK1")
    single = client.get(f"/api/projects/{project}/requirements/BK1/value").json()

    assert entry["value"] == single["value"] == 6.0
    assert entry["combined_priority"] == entry["value"]
