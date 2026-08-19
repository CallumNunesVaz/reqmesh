"""Regression tests for the bulk-edit priority scale.

``PriorityScore`` (``backend/app/models/requirement.py``) bounds a stakeholder
score to 0-5 on the **write** models only. A score above 5 failed
``RequirementUpdate.model_validate`` inside ``bulk_update_requirements``, which
422ed the **whole batch** with none of it applied — while the bulk-edit modal's
own placeholder taught users to type ``safety: 10``. The fix is client-side (the
modal can no longer produce an out-of-range score); these tests pin the server
behaviour the client must respect: an out-of-range score rejects everything, a
score of 5 lands.
"""
from __future__ import annotations

from tests.conftest import make_req


def test_priority_score_above_5_422s_and_updates_nothing(client, project):
    make_req(client, project, "SYST0001", priorities={"safety": 1})

    res = client.post(
        f"/api/projects/{project}/requirements/bulk",
        json={"ids": ["SYST0001"], "updates": {"priorities": {"safety": 10}}},
    )

    assert res.status_code == 422, res.text
    body = res.json()
    # Structured envelope, not a bare string — the client switches on `error`.
    assert body["detail"]["error"] == "validation"
    assert body["detail"]["message"]

    # Nothing was written: the requirement still carries its pre-edit score.
    after = client.get(f"/api/projects/{project}/requirements/SYST0001").json()
    assert after["priorities"] == {"safety": 1}


def test_priority_score_of_5_succeeds(client, project):
    make_req(client, project, "SYST0001", priorities={"safety": 1})

    res = client.post(
        f"/api/projects/{project}/requirements/bulk",
        json={"ids": ["SYST0001"], "updates": {"priorities": {"safety": 5}}},
    )

    assert res.status_code == 200, res.text
    assert res.json()["updated"] == 1
    after = client.get(f"/api/projects/{project}/requirements/SYST0001").json()
    assert after["priorities"]["safety"] == 5
