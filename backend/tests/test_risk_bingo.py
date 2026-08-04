from app.services.risk_matrix import risk_bingo, normalize_matrix, default_matrix


def _matrix(**overrides):
    """Return a default matrix with optional overrides merged."""
    m = default_matrix()
    m.update(overrides)
    return m


def test_risk_lands_in_correct_cell():
    """A risk lands in the cell matching its severity and likelihood."""
    risks = [
        {"id": "R1", "severity": "low", "likelihood": "rare"},
        {"id": "R2", "severity": "critical", "likelihood": "almost_certain"},
    ]
    matrix = normalize_matrix(default_matrix())
    result = risk_bingo(risks, matrix)

    si_low = matrix["severities"].index("low")
    li_rare = matrix["likelihoods"].index("rare")
    si_crit = matrix["severities"].index("critical")
    li_ac = matrix["likelihoods"].index("almost_certain")

    assert result["counts"][si_low][li_rare] == 1
    assert result["counts"][si_crit][li_ac] == 1
    # All other cells are 0
    total_in_cells = sum(sum(row) for row in result["counts"])
    assert total_in_cells == 2


def test_sum_counts_plus_unrated_equals_total():
    """sum(counts) + unrated == total, for a register that includes both rated
    and unrated risks."""
    risks = [
        {"id": "R1", "severity": "low", "likelihood": "rare"},
        {"id": "R2", "severity": "low", "likelihood": "rare"},
        {"id": "R3", "severity": "bogus", "likelihood": "rare"},  # unrated
        {"id": "R4", "severity": "low", "likelihood": None},       # unrated
        {"id": "R5", "severity": None, "likelihood": "rare"},       # unrated
    ]
    result = risk_bingo(risks, normalize_matrix(default_matrix()))
    total_in_cells = sum(sum(row) for row in result["counts"])
    assert total_in_cells + result["unrated"] == result["total"]
    assert result["total"] == 5
    assert result["unrated"] == 3


def test_severity_outside_matrix_counts_as_unrated():
    """A risk with a severity outside the matrix counts as unrated and in no cell."""
    risks = [
        {"id": "R1", "severity": "extreme", "likelihood": "rare"},
    ]
    result = risk_bingo(risks, normalize_matrix(default_matrix()))
    assert result["unrated"] == 1
    total_in_cells = sum(sum(row) for row in result["counts"])
    assert total_in_cells == 0


def test_legacy_probability_fallback():
    """The legacy `probability` fallback still places a risk, via resolve_likelihood."""
    # "low" probability maps to "unlikely" likelihood via LEGACY_LIKELIHOOD
    risks = [
        {"id": "R1", "severity": "medium", "probability": "low"},
    ]
    matrix = normalize_matrix(default_matrix())
    result = risk_bingo(risks, matrix)

    si = matrix["severities"].index("medium")
    li = matrix["likelihoods"].index("unlikely")
    assert result["counts"][si][li] == 1


def test_bands_match_matrix_cells():
    """bands[i][j] matches matrix[\"cells\"][i][j]."""
    matrix = normalize_matrix(default_matrix())
    result = risk_bingo([], matrix)
    for si in range(len(matrix["severities"])):
        for li in range(len(matrix["likelihoods"])):
            assert result["bands"][si][li] == matrix["cells"][si][li]


def test_empty_register():
    """An empty register gives all-zero counts, unrated: 0, total: 0."""
    result = risk_bingo([], normalize_matrix(default_matrix()))
    assert result["total"] == 0
    assert result["unrated"] == 0
    assert len(result["counts"]) > 0
    assert len(result["likelihoods"]) > 0
    for row in result["counts"]:
        assert all(c == 0 for c in row)


def test_non_default_matrix_shape():
    """A non-default matrix (renamed levels, different size) produces a grid of
    the matching shape."""
    custom = {
        "severities": ["minor", "major", "catastrophic"],
        "likelihoods": ["improbable", "occasional", "frequent"],
        "detections": ["obvious", "obscure"],
        "bands": [
            {"key": "green", "label": "Green", "color": "#00ff00"},
            {"key": "amber", "label": "Amber", "color": "#ffcc00"},
            {"key": "red", "label": "Red", "color": "#ff0000"},
        ],
        "cells": [
            ["green", "green", "amber"],
            ["green", "amber", "red"],
            ["amber", "red", "red"],
        ],
    }
    matrix = normalize_matrix(custom)
    result = risk_bingo([], matrix)

    assert result["severities"] == ["minor", "major", "catastrophic"]
    assert result["likelihoods"] == ["improbable", "occasional", "frequent"]
    assert len(result["counts"]) == 3
    assert all(len(row) == 3 for row in result["counts"])
    assert len(result["bands"]) == 3
    assert all(len(row) == 3 for row in result["bands"])
