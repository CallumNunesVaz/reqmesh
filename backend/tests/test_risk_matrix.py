"""Risk rating derived from the project matrix (see services/risk_matrix.py)."""

from app.services.risk_matrix import (
    DEFAULT_BANDS,
    apply_rating,
    default_matrix,
    normalize_matrix,
    rate,
    resolve_likelihood,
)

M = default_matrix()


def test_rating_is_the_matrix_cell_not_the_severity():
    """The whole point of the matrix: a critical risk that almost never happens
    is not automatically the same band as one that happens constantly."""
    rare = rate({"severity": "critical", "likelihood": "rare"}, M)
    certain = rate({"severity": "critical", "likelihood": "almost_certain"}, M)
    assert rare["band"] == "medium"
    assert certain["band"] == "extreme"
    assert rare["severity"] == certain["severity"]


def test_low_severity_certain_outranks_high_severity_rare():
    frequent_nuisance = rate({"severity": "medium", "likelihood": "almost_certain"}, M)
    rare_disaster = rate({"severity": "high", "likelihood": "rare"}, M)
    order = [b["key"] for b in DEFAULT_BANDS]
    assert order.index(frequent_nuisance["band"]) > order.index(rare_disaster["band"])


def test_rating_carries_a_colour():
    """A band with no colour cannot be drawn as a matrix, which is the feature."""
    r = rate({"severity": "critical", "likelihood": "likely"}, M)
    assert r["color"].startswith("#")
    assert r["label"] == "Extreme"


def test_unknown_level_is_unrated_not_defaulted():
    """Defaulting an unrateable risk into a band would show a fabricated
    assessment that reads exactly like a real one."""
    r = rate({"severity": "showstopper", "likelihood": "likely"}, M)
    assert r["band"] is None
    assert "showstopper" in r["unrated_reason"]


def test_missing_likelihood_is_unrated():
    r = rate({"severity": "high"}, M)
    assert r["band"] is None
    assert "likelihood is not set" in r["unrated_reason"]


def test_legacy_probability_still_rates():
    """Risks written before the likelihood axis existed carry `probability`."""
    assert resolve_likelihood({"probability": "low"}, M["likelihoods"]) == "unlikely"
    r = rate({"severity": "critical", "probability": "low"}, M)
    # 'low' maps to 'unlikely', not 'rare' — the legacy three-band scale sat in
    # the middle of the five-band one rather than at its bottom.
    assert r["band"] == "high"
    assert r["likelihood"] == "unlikely"


def test_likelihood_wins_over_legacy_probability():
    r = rate({"severity": "critical", "likelihood": "almost_certain", "probability": "low"}, M)
    assert r["band"] == "extreme"


def test_level_matching_is_case_and_space_insensitive():
    assert rate({"severity": " Critical ", "likelihood": "Almost_Certain"}, M)["band"] == "extreme"


# ── Matrix normalization ─────────────────────────────────────────────────────

def test_a_half_edited_matrix_does_not_take_the_register_down():
    """Each field degrades to its default independently."""
    m = normalize_matrix({"severities": ["minor", "major"], "cells": "not a grid"})
    assert m["severities"] == ["minor", "major"]
    assert m["likelihoods"] == default_matrix()["likelihoods"]
    assert len(m["cells"]) == 2
    assert all(len(row) == len(m["likelihoods"]) for row in m["cells"])


def test_cells_are_resized_to_the_axes():
    """Adding a severity must not leave a row missing, which would raise on read."""
    m = normalize_matrix({**default_matrix(), "severities": ["a", "b", "c", "d", "e"]})
    assert len(m["cells"]) == 5
    assert all(len(row) == 5 for row in m["cells"])


def test_cell_naming_an_undefined_band_falls_back():
    m = normalize_matrix({**default_matrix(), "cells": [["nope"] * 5] * 4})
    assert m["cells"][0][0] == "low"


def test_duplicate_level_names_are_collapsed():
    """Two levels with one name would make a cell unaddressable."""
    m = normalize_matrix({"severities": ["low", "low", "high"]})
    assert m["severities"] == ["low", "high"]


def test_garbage_matrix_returns_the_default():
    assert normalize_matrix(None) == default_matrix()
    assert normalize_matrix("nonsense") == default_matrix()


def test_apply_rating_tags_every_risk():
    risks = [{"id": "R1", "severity": "low", "likelihood": "rare"},
             {"id": "R2", "severity": "critical", "likelihood": "almost_certain"}]
    out = apply_rating(risks, None)
    assert out[0]["rating"]["band"] == "low"
    assert out[1]["rating"]["band"] == "extreme"


# ── Through the API ──────────────────────────────────────────────────────────

def test_risks_are_served_with_a_rating(client, project):
    client.post(f"/api/projects/{project}/risks", json={
        "id": "RSK1", "title": "Wing flutter", "severity": "critical",
        "likelihood": "rare"})

    listed = client.get(f"/api/projects/{project}/risks").json()
    entry = next(r for r in listed if r["id"] == "RSK1")
    assert entry["rating"]["band"] == "medium"
    assert entry["rating"]["color"].startswith("#")


def test_retuning_the_matrix_rerates_existing_risks(client, project):
    """Ratings are derived, not stored — the point of computing on read."""
    client.post(f"/api/projects/{project}/risks", json={
        "id": "RSK2", "title": "T", "severity": "critical", "likelihood": "rare"})
    before = next(r for r in client.get(f"/api/projects/{project}/risks").json()
                  if r["id"] == "RSK2")["rating"]["band"]

    m = default_matrix()
    m["cells"][3][0] = "extreme"          # critical + rare -> extreme
    assert client.patch(f"/api/projects/{project}", json={"risk_matrix": m}).status_code == 200

    after = next(r for r in client.get(f"/api/projects/{project}/risks").json()
                 if r["id"] == "RSK2")["rating"]["band"]
    assert before == "medium" and after == "extreme"


def test_matrix_round_trips_through_project_settings(client, project):
    m = default_matrix()
    m["severities"] = ["minor", "major"]
    res = client.patch(f"/api/projects/{project}", json={"risk_matrix": m})
    assert res.status_code == 200

    got = client.get(f"/api/projects/{project}").json()["risk_matrix"]
    assert got["severities"] == ["minor", "major"]
    assert len(got["cells"]) == 2          # resized on write, not left ragged

    endpoint = client.get(f"/api/projects/{project}/risk-matrix").json()
    assert endpoint == got


def test_project_without_a_matrix_gets_the_default(client, project):
    got = client.get(f"/api/projects/{project}").json()["risk_matrix"]
    assert got == default_matrix()


def test_legacy_risk_on_disk_still_rates(client, project):
    """A risk file written before this feature has probability and no likelihood."""
    from pathlib import Path

    from app.core.config import settings
    from app.services.yaml_store import YamlStore

    store = YamlStore(Path(settings.data_root) / project)
    store.create_item("risks", {"id": "OLD1", "title": "Legacy",
                                "severity": "high", "probability": "medium"})

    entry = next(r for r in client.get(f"/api/projects/{project}/risks").json()
                 if r["id"] == "OLD1")
    assert entry["rating"]["likelihood"] == "possible"
    assert entry["rating"]["band"] == "high"
