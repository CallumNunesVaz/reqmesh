"""Risk metrics on /metrics (see api/analysis_routes.py::_risk_metrics).

The register already derives ratings on read so a re-tuned matrix re-rates
everything at once. These metrics have to follow the same rule: a dashboard that
disagrees with the page it summarises is worse than no dashboard.
"""

from app.services.risk_matrix import default_matrix


def _add(client, project, rid, **fields):
    payload = {"id": rid, "title": fields.pop("title", rid),
               "severity": "medium", "likelihood": "possible", **fields}
    status = payload.pop("status", None)
    assert client.post(f"/api/projects/{project}/risks", json=payload).status_code == 201
    # status/mitigation/linked_requirements are update-only on the model.
    patch = {k: v for k, v in (("status", status),) if v is not None}
    for key in ("mitigation", "linked_requirements"):
        if key in fields:
            patch[key] = fields[key]
    if patch:
        assert client.put(f"/api/projects/{project}/risks/{rid}", json=patch).status_code == 200


def _risks(client, project):
    return client.get(f"/api/projects/{project}/metrics").json()["risks"]


def test_bands_are_counted_through_the_project_matrix(client, project):
    _add(client, project, "R1", severity="critical", likelihood="almost_certain")  # extreme
    _add(client, project, "R2", severity="low", likelihood="rare")                 # low

    r = _risks(client, project)
    assert r["total"] == 2
    assert r["by_band"]["extreme"] == 1
    assert r["by_band"]["low"] == 1
    # Every band is present even at zero, so a chart keeps stable columns.
    assert set(r["by_band"]) == {b["key"] for b in default_matrix()["bands"]}


def test_retuning_the_matrix_moves_the_metrics(client, project):
    """The regression that matters: metrics must not cache a rating."""
    _add(client, project, "R1", severity="critical", likelihood="rare")
    assert _risks(client, project)["by_band"]["medium"] == 1

    m = default_matrix()
    m["cells"][3][0] = "extreme"
    assert client.patch(f"/api/projects/{project}", json={"risk_matrix": m}).status_code == 200

    after = _risks(client, project)
    assert after["by_band"]["extreme"] == 1
    assert after["by_band"]["medium"] == 0


def test_closed_risks_leave_the_open_counts_but_stay_in_the_total(client, project):
    _add(client, project, "R1", severity="critical", likelihood="almost_certain")
    _add(client, project, "R2", severity="critical", likelihood="almost_certain", status="closed")

    r = _risks(client, project)
    assert r["total"] == 2
    assert r["open"] == 1
    assert r["by_band"]["extreme"] == 2
    assert r["open_by_band"]["extreme"] == 1
    assert r["severe_open"] == 1


def test_severe_is_the_top_two_bands_of_whatever_matrix_is_configured(client, project):
    """Not a hardcoded 'extreme' — the matrix is project-configurable."""
    m = default_matrix()
    m["bands"] = [{"key": "green", "label": "Green", "color": "#0f0"},
                  {"key": "amber", "label": "Amber", "color": "#fa0"},
                  {"key": "red", "label": "Red", "color": "#f00"}]
    m["cells"] = [["green"] * 5 for _ in range(4)]
    m["cells"][3][4] = "red"
    m["cells"][3][3] = "amber"
    assert client.patch(f"/api/projects/{project}", json={"risk_matrix": m}).status_code == 200

    _add(client, project, "R1", severity="critical", likelihood="almost_certain")  # red
    _add(client, project, "R2", severity="critical", likelihood="likely")          # amber
    _add(client, project, "R3", severity="low", likelihood="rare")                 # green

    r = _risks(client, project)
    assert r["severe_bands"] == ["amber", "red"]
    assert r["severe_open"] == 2
    assert [b["key"] for b in r["bands"]] == ["green", "amber", "red"]


def test_an_unrateable_risk_is_reported_not_defaulted_into_a_band(client, project):
    _add(client, project, "R1", severity="not-a-level", likelihood="possible")

    r = _risks(client, project)
    assert r["unrated"] == 1
    assert sum(r["by_band"].values()) == 0
    assert all(t["id"] != "R1" for t in r["top_open"])


def test_coverage_counts_mitigations_and_requirement_links(client, project):
    client.post(f"/api/projects/{project}/requirements",
                json={"id": "REQ1", "name": "R", "description": "d"})
    _add(client, project, "R1", mitigation="Add a guard")
    _add(client, project, "R2", linked_requirements=["REQ1"])
    _add(client, project, "R3")

    r = _risks(client, project)
    assert r["with_mitigation"] == 1
    assert r["with_requirements"] == 1
    assert r["mitigation_pct"] == 33
    assert r["linked_pct"] == 33


def test_top_open_is_ordered_most_serious_first_and_excludes_closed(client, project):
    _add(client, project, "LOW", severity="low", likelihood="rare")
    _add(client, project, "WORST", severity="critical", likelihood="almost_certain")
    _add(client, project, "SHUT", severity="critical", likelihood="almost_certain", status="closed")

    top = _risks(client, project)["top_open"]
    assert [t["id"] for t in top] == ["WORST", "LOW"]
    assert top[0]["band"] == "extreme"
    assert top[0]["color"].startswith("#")
    assert top[0]["mitigated"] is False


def test_a_project_with_no_requirements_still_reports_its_risks(client, project):
    """The empty-project path returns a short payload; risks ride along."""
    _add(client, project, "R1", severity="high", likelihood="likely")

    body = client.get(f"/api/projects/{project}/metrics").json()
    assert body["total"] == 0
    assert body["risks"]["total"] == 1


def test_a_project_with_no_risks_reports_zeroes_rather_than_omitting_the_block(client, project):
    r = _risks(client, project)
    assert r["total"] == 0
    assert r["mitigation_pct"] == 0
    assert r["top_open"] == []
    assert set(r["by_band"]) == {b["key"] for b in default_matrix()["bands"]}
