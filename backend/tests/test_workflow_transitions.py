"""Tests for workflow transition enforcement — validate_transition and its call sites."""


def test_no_workflow_allows_any_transition(client, project):
    """A project with no custom workflow allows any status change — the
    backward-compatibility guarantee."""
    from .conftest import make_req

    make_req(client, project, "R-1", status="proposed")
    # Jumping to an arbitrary status must succeed.
    res = client.put(f"/api/projects/{project}/requirements/R-1",
                     json={"status": "verified"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "verified"


def test_undeclared_transition_rejected_and_status_unchanged(client, project):
    """A declared workflow rejects an undeclared transition with 409, and a
    follow-up GET shows the status unchanged."""
    from .conftest import make_req

    # Declare a restricted workflow.
    client.patch(f"/api/projects/{project}", json={
        "workflow": {
            "states": ["proposed", "in_review", "approved", "implemented",
                       "verified", "rejected", "deprecated"],
            "transitions": {
                "proposed": ["in_review"],
            },
        },
    })
    make_req(client, project, "R-1", status="proposed")
    # approved is NOT reachable from proposed.
    res = client.put(f"/api/projects/{project}/requirements/R-1",
                     json={"status": "approved"})
    assert res.status_code == 409, res.text
    assert "not allowed" in res.json()["detail"]
    # Status must be unchanged.
    get_res = client.get(f"/api/projects/{project}/requirements/R-1")
    assert get_res.status_code == 200
    assert get_res.json()["status"] == "proposed"


def test_declared_allowed_transition_succeeds(client, project):
    """A declared, allowed transition succeeds."""
    from .conftest import make_req

    client.patch(f"/api/projects/{project}", json={
        "workflow": {
            "states": ["proposed", "in_review", "approved"],
            "transitions": {
                "proposed": ["in_review"],
                "in_review": ["approved", "proposed"],
                "approved": [],
            },
        },
    })
    make_req(client, project, "R-1", status="proposed")
    res = client.put(f"/api/projects/{project}/requirements/R-1",
                     json={"status": "in_review"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "in_review"


def test_same_status_always_allowed_even_terminal(client, project):
    """Setting status to its current value is always allowed, even if the state
    is terminal (current == new short-circuits)."""
    from .conftest import make_req

    client.patch(f"/api/projects/{project}", json={
        "workflow": {
            "states": ["deprecated"],
            "transitions": {
                "deprecated": [],
            },
        },
    })
    make_req(client, project, "R-1", status="deprecated")
    res = client.put(f"/api/projects/{project}/requirements/R-1",
                     json={"status": "deprecated"})
    assert res.status_code == 200, res.text


def test_terminal_state_rejects_everything_with_terminal_message(client, project):
    """A terminal state (deprecated: []) rejects everything, and the message says
    'terminal'."""
    from .conftest import make_req

    client.patch(f"/api/projects/{project}", json={
        "workflow": {
            "states": ["proposed", "deprecated"],
            "transitions": {
                "proposed": ["deprecated"],
                "deprecated": [],
            },
        },
    })
    make_req(client, project, "R-1", status="deprecated")
    res = client.put(f"/api/projects/{project}/requirements/R-1",
                     json={"status": "proposed"})
    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert "terminal" in detail


def test_bulk_one_violation_rejects_whole_batch_none_changed(client, project):
    """A bulk update where one requirement violates the workflow leaves none of
    them changed."""
    from .conftest import make_req

    client.patch(f"/api/projects/{project}", json={
        "workflow": {
            "states": ["proposed", "approved", "deprecated"],
            "transitions": {
                "proposed": ["approved"],
                "approved": [],
                "deprecated": [],
            },
        },
    })
    # R-1: valid transition (proposed -> approved)
    make_req(client, project, "R-1", status="proposed")
    # R-2: in a terminal state, any transition is forbidden
    make_req(client, project, "R-2", status="deprecated")
    # R-3: valid transition (proposed -> approved)
    make_req(client, project, "R-3", status="proposed")

    res = client.post(f"/api/projects/{project}/requirements/bulk", json={
        "ids": ["R-1", "R-2", "R-3"],
        "updates": {"status": "approved"},
    })
    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert "R-2" in detail
    assert "terminal" in detail

    # None of them should have changed.
    for rid in ("R-1", "R-2", "R-3"):
        r = client.get(f"/api/projects/{project}/requirements/{rid}")
        assert r.status_code == 200
        if rid == "R-1":
            assert r.json()["status"] == "proposed"
        elif rid == "R-2":
            assert r.json()["status"] == "deprecated"
        else:
            assert r.json()["status"] == "proposed"
