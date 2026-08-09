"""Bulk baseline membership is additive.

The bulk bar used to send ``{"baselines": [name]}``, which *replaces* the list.
Ticking twenty rows and picking one baseline silently dropped every other
baseline those rows carried, with no undo entry to recover them.
"""
from tests.conftest import make_req


def _meta_with_baselines(client, project, names):
    r = client.patch(f"/api/projects/{project}",
                     json={"baselines": [{"name": n} for n in names]})
    assert r.status_code == 200, r.text


def _baselines_of(client, project, req_id):
    return client.get(f"/api/projects/{project}/requirements/{req_id}").json()["baselines"]


def test_add_preserves_existing_memberships(client, project):
    _meta_with_baselines(client, project, ["SRR", "PDR", "CDR"])
    make_req(client, project, "R1", name="One", baselines=["SRR", "CDR"])
    make_req(client, project, "R2", name="Two", baselines=[])

    r = client.post(f"/api/projects/{project}/requirements/bulk",
                    json={"ids": ["R1", "R2"], "baselines_add": ["PDR"]})
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 2

    # The regression: SRR and CDR must still be there.
    assert set(_baselines_of(client, project, "R1")) == {"SRR", "CDR", "PDR"}
    assert _baselines_of(client, project, "R2") == ["PDR"]


def test_add_is_idempotent_and_reports_no_change(client, project):
    _meta_with_baselines(client, project, ["PDR"])
    make_req(client, project, "R1", name="One", baselines=["PDR"])

    r = client.post(f"/api/projects/{project}/requirements/bulk",
                    json={"ids": ["R1"], "baselines_add": ["PDR"]})
    assert r.status_code == 200
    # Nothing changed, so nothing is reported as touched — an undo built from
    # this must not strip PDR from a row that already had it.
    assert r.json()["updated"] == 0
    assert r.json()["ids"] == []
    assert _baselines_of(client, project, "R1") == ["PDR"]


def test_remove_takes_only_the_named_baseline(client, project):
    _meta_with_baselines(client, project, ["SRR", "PDR"])
    make_req(client, project, "R1", name="One", baselines=["SRR", "PDR"])

    r = client.post(f"/api/projects/{project}/requirements/bulk",
                    json={"ids": ["R1"], "baselines_remove": ["PDR"]})
    assert r.status_code == 200
    assert _baselines_of(client, project, "R1") == ["SRR"]


def test_remove_of_an_absent_baseline_is_a_no_op(client, project):
    _meta_with_baselines(client, project, ["SRR", "PDR"])
    make_req(client, project, "R1", name="One", baselines=["SRR"])

    r = client.post(f"/api/projects/{project}/requirements/bulk",
                    json={"ids": ["R1"], "baselines_remove": ["PDR"]})
    assert r.status_code == 200
    assert r.json()["updated"] == 0
    assert r.json()["removed"] == []
    assert _baselines_of(client, project, "R1") == ["SRR"]


def test_add_preserves_order_so_a_sequence_is_not_reshuffled(client, project):
    _meta_with_baselines(client, project, ["SRR", "PDR", "CDR"])
    make_req(client, project, "R1", name="One", baselines=["SRR", "PDR"])

    client.post(f"/api/projects/{project}/requirements/bulk",
                json={"ids": ["R1"], "baselines_add": ["CDR"]})
    assert _baselines_of(client, project, "R1") == ["SRR", "PDR", "CDR"]


def test_undefined_baseline_is_refused(client, project):
    """A typo used to create a phantom membership that only showed up as an
    orphan in the baselines listing."""
    _meta_with_baselines(client, project, ["SRR"])
    make_req(client, project, "R1", name="One")

    r = client.post(f"/api/projects/{project}/requirements/bulk",
                    json={"ids": ["R1"], "baselines_add": ["TYPO"]})
    assert r.status_code == 400
    assert "TYPO" in r.json()["detail"]
    assert _baselines_of(client, project, "R1") == []


def test_additive_and_replace_cannot_be_combined(client, project):
    _meta_with_baselines(client, project, ["SRR", "PDR"])
    make_req(client, project, "R1", name="One", baselines=["SRR"])

    r = client.post(f"/api/projects/{project}/requirements/bulk",
                    json={"ids": ["R1"], "baselines_add": ["PDR"],
                          "updates": {"baselines": ["CDR"]}})
    assert r.status_code == 409
    assert _baselines_of(client, project, "R1") == ["SRR"]


def test_add_and_remove_in_one_call(client, project):
    _meta_with_baselines(client, project, ["SRR", "PDR"])
    make_req(client, project, "R1", name="One", baselines=["SRR"])

    r = client.post(f"/api/projects/{project}/requirements/bulk",
                    json={"ids": ["R1"], "baselines_add": ["PDR"],
                          "baselines_remove": ["SRR"]})
    assert r.status_code == 200
    assert _baselines_of(client, project, "R1") == ["PDR"]


def test_membership_change_is_recorded_in_history(client, project):
    _meta_with_baselines(client, project, ["PDR"])
    make_req(client, project, "R1", name="One")

    client.post(f"/api/projects/{project}/requirements/bulk",
                json={"ids": ["R1"], "baselines_add": ["PDR"]})

    hist = client.get(f"/api/projects/{project}/history/R1").json()
    assert any("baselines" in str(entry) for entry in hist), hist


def test_replace_semantics_still_available_through_updates(client, project):
    """The edit modal deliberately replaces, and says so in its help text."""
    _meta_with_baselines(client, project, ["SRR", "PDR"])
    make_req(client, project, "R1", name="One", baselines=["SRR"])

    r = client.post(f"/api/projects/{project}/requirements/bulk",
                    json={"ids": ["R1"], "updates": {"baselines": ["PDR"]}})
    assert r.status_code == 200
    assert _baselines_of(client, project, "R1") == ["PDR"]
