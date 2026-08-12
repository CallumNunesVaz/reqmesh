"""GET-one routes for the kinds that lacked them.

Requirements, components, specifications and verification cases always had a
fetch-one route; risks, change requests, decisions, definitions, analysis and
system-states did not, so their detail views fetched the whole list. These
routes close that gap and must match the existing four's conventions exactly:
same path shape, 404 body, response model and (absence of) auth.
"""

from __future__ import annotations


def _mk_risk(client, project_id, risk_id="RSK-1"):
    res = client.post(f"/api/projects/{project_id}/risks", json={"id": risk_id})
    assert res.status_code == 201, res.text
    return res.json()


def _mk_cr(client, project_id, cr_id="CR-1"):
    res = client.post(f"/api/projects/{project_id}/change-requests", json={"id": cr_id})
    assert res.status_code == 201, res.text
    return res.json()


def _mk_decision(client, project_id, dec_id="DEC-1"):
    res = client.post(f"/api/projects/{project_id}/decisions", json={"id": dec_id})
    assert res.status_code == 201, res.text
    return res.json()


def _mk_definition(client, project_id, def_id="DEF-1"):
    res = client.post(
        f"/api/projects/{project_id}/definitions",
        json={"id": def_id, "type": "constraint", "expr": "a <= b"},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _mk_analysis(client, project_id, case_id="AN-1"):
    res = client.post(f"/api/projects/{project_id}/analysis", json={"id": case_id})
    assert res.status_code == 201, res.text
    return res.json()


def _mk_system_state(client, project_id, name="ST-1"):
    res = client.post(
        f"/api/projects/{project_id}/system-states",
        json={"name": name, "description": "desc"},
    )
    assert res.status_code == 201, res.text
    return res.json()


# ── risks ─────────────────────────────────────────────────────────────────────

def test_get_risk_hit(client, project):
    _mk_risk(client, project, "RSK-1")
    body = client.get(f"/api/projects/{project}/risks/RSK-1")
    assert body.status_code == 200
    assert body.json()["id"] == "RSK-1"
    # Rated like the list endpoint, not a bare store read.
    assert "rating" in body.json()


def test_get_risk_miss(client, project):
    assert client.get(f"/api/projects/{project}/risks/nope").status_code == 404


# ── change requests ──────────────────────────────────────────────────────────

def test_get_change_request_hit(client, project):
    _mk_cr(client, project, "CR-1")
    body = client.get(f"/api/projects/{project}/change-requests/CR-1")
    assert body.status_code == 200
    assert body.json()["id"] == "CR-1"


def test_get_change_request_miss(client, project):
    assert client.get(f"/api/projects/{project}/change-requests/nope").status_code == 404


# ── decisions ─────────────────────────────────────────────────────────────────

def test_get_decision_hit(client, project):
    _mk_decision(client, project, "DEC-1")
    body = client.get(f"/api/projects/{project}/decisions/DEC-1")
    assert body.status_code == 200
    assert body.json()["id"] == "DEC-1"


def test_get_decision_miss(client, project):
    assert client.get(f"/api/projects/{project}/decisions/nope").status_code == 404


# ── definitions ───────────────────────────────────────────────────────────────

def test_get_definition_hit(client, project):
    _mk_definition(client, project, "DEF-1")
    body = client.get(f"/api/projects/{project}/definitions/DEF-1")
    assert body.status_code == 200
    assert body.json()["id"] == "DEF-1"
    assert body.json()["expr"] == "a <= b"


def test_get_definition_miss(client, project):
    assert client.get(f"/api/projects/{project}/definitions/nope").status_code == 404


# ── analysis ──────────────────────────────────────────────────────────────────

def test_get_analysis_case_hit(client, project):
    _mk_analysis(client, project, "AN-1")
    body = client.get(f"/api/projects/{project}/analysis/AN-1")
    assert body.status_code == 200
    assert body.json()["id"] == "AN-1"


def test_get_analysis_case_miss(client, project):
    assert client.get(f"/api/projects/{project}/analysis/nope").status_code == 404


# ── system states ─────────────────────────────────────────────────────────────

def test_get_system_state_hit(client, project):
    _mk_system_state(client, project, "ST-1")
    body = client.get(f"/api/projects/{project}/system-states/ST-1")
    assert body.status_code == 200
    assert body.json()["name"] == "ST-1"
    assert body.json()["description"] == "desc"


def test_get_system_state_miss(client, project):
    assert client.get(f"/api/projects/{project}/system-states/nope").status_code == 404


# ── auth: these are read routes, matching their list siblings (no guard) ──────

def test_get_one_routes_are_public_like_their_siblings(_real_role_client, guest_client):
    admin = _real_role_client("admin", "getone_admin")
    with admin as a:
        assert a.post("/api/projects", json={"id": "pub", "name": "Pub"}).status_code == 201
        p = "pub"
        _mk_risk(a, p, "RSK-1")
        _mk_cr(a, p, "CR-1")
        _mk_decision(a, p, "DEC-1")
        _mk_definition(a, p, "DEF-1")
        _mk_analysis(a, p, "AN-1")
        _mk_system_state(a, p, "ST-1")

    for path in ("risks/RSK-1", "change-requests/CR-1", "decisions/DEC-1",
                 "definitions/DEF-1", "analysis/AN-1", "system-states/ST-1"):
        res = guest_client.get(f"/api/projects/pub/{path}")
        assert res.status_code == 200, f"{path} gated: {res.status_code}"
