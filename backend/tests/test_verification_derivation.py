"""Verify that verification_status, _method, and _methods are derived from the
owning verification cases on every path that returns a requirement."""

from collections import Counter
from pathlib import Path

from app.core.config import settings
from app.services.verification_links import attach


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_vc(client, project_id, vc_id, status="pending", method="test",
             verified_requirements=None):
    body = {"id": vc_id, "name": vc_id, "method": method}
    res = client.post(f"/api/projects/{project_id}/verification", json=body)
    assert res.status_code == 201, res.text
    if status != "pending" or verified_requirements is not None:
        update = {}
        if status != "pending":
            update["status"] = status
        if verified_requirements is not None:
            update["verified_requirements"] = verified_requirements
        res = client.put(
            f"/api/projects/{project_id}/verification/{vc_id}",
            json=update,
        )
        assert res.status_code == 200, res.text
    return res.json()


# ── Derivation on single-requirement GET ──────────────────────────────────────

def test_no_cases_gives_pending_and_empty_methods(client, project):
    from .conftest import make_req
    make_req(client, project, "REQ0001")
    req = client.get(f"/api/projects/{project}/requirements/REQ0001").json()
    assert req["verification_status"] == "pending"
    assert req["verification_methods"] == []
    assert req["verification_method"] == "test"


def test_one_passing_case_gives_passed(client, project):
    from .conftest import make_req
    make_req(client, project, "REQ0001")
    _make_vc(client, project, "VC-001", status="passed",
             verified_requirements=["REQ0001"])
    req = client.get(f"/api/projects/{project}/requirements/REQ0001").json()
    assert req["verification_status"] == "passed"
    assert req["verification_methods"] == ["test"]


def test_one_failing_case_gives_failed(client, project):
    from .conftest import make_req
    make_req(client, project, "REQ0001")
    _make_vc(client, project, "VC-001", status="failed",
             verified_requirements=["REQ0001"])
    req = client.get(f"/api/projects/{project}/requirements/REQ0001").json()
    assert req["verification_status"] == "failed"


def test_passed_and_failed_gives_failed(client, project):
    """The worst status wins — one failed case sinks the requirement."""
    from .conftest import make_req
    make_req(client, project, "REQ0001")
    _make_vc(client, project, "VC-001", status="passed",
             verified_requirements=["REQ0001"])
    _make_vc(client, project, "VC-002", status="failed",
             verified_requirements=["REQ0001"])
    req = client.get(f"/api/projects/{project}/requirements/REQ0001").json()
    assert req["verification_status"] == "failed"


def test_passed_passed_pending_gives_pending(client, project):
    """Pending is worse than passed — one pending means the answer isn't in."""
    from .conftest import make_req
    make_req(client, project, "REQ0001")
    _make_vc(client, project, "VC-001", status="passed",
             verified_requirements=["REQ0001"])
    _make_vc(client, project, "VC-002", status="passed",
             verified_requirements=["REQ0001"])
    _make_vc(client, project, "VC-003", status="pending",
             verified_requirements=["REQ0001"])
    req = client.get(f"/api/projects/{project}/requirements/REQ0001").json()
    assert req["verification_status"] == "pending"


def test_unrecognised_status_counts_as_pending(client, project):
    """'Banana' is not in the vocabulary — it is not evidence of success."""
    from .conftest import make_req
    make_req(client, project, "REQ0001")
    # Write a VC with status "banana" via a direct PUT so the API accepts it.
    _make_vc(client, project, "VC-001", status="passed",
             verified_requirements=["REQ0001"])
    # Override with an unrecognised status via PUT.
    res = client.put(
        f"/api/projects/{project}/verification/VC-001",
        json={"status": "banana"},
    )
    assert res.status_code == 200
    req = client.get(f"/api/projects/{project}/requirements/REQ0001").json()
    assert req["verification_status"] == "pending"


def test_two_methods_sorted(client, project):
    from .conftest import make_req
    make_req(client, project, "REQ0001")
    _make_vc(client, project, "VC-001", method="test",
             verified_requirements=["REQ0001"])
    _make_vc(client, project, "VC-002", method="analysis",
             verified_requirements=["REQ0001"])
    req = client.get(f"/api/projects/{project}/requirements/REQ0001").json()
    assert req["verification_methods"] == ["analysis", "test"]
    # verification_method is the alphabetically first
    assert req["verification_method"] == "analysis"


# ── Stale stored value is overridden ──────────────────────────────────────────

def test_stale_stored_value_overridden(client, project):
    """Write verification_status: verified into the YAML with no verifying
    case — the API must return pending, not the stale stored value."""
    from .conftest import make_req

    # Create the requirement normally so the store directory exists.
    make_req(client, project, "REQ0001")

    # Hand-edit the YAML to inject a stale verification_status.
    req_path = Path(settings.data_root) / project / "requirements" / "REQ0001.yaml"
    with open(req_path, "r") as f:
        raw = f.read()
    # Replace or insert the stale field
    if "verification_status:" in raw:
        raw = raw.replace(
            'verification_status: pending',
            'verification_status: verified',
        )
    else:
        raw = raw.rstrip() + "\nverification_status: verified\n"
    with open(req_path, "w") as f:
        f.write(raw)

    req = client.get(f"/api/projects/{project}/requirements/REQ0001").json()
    assert req["verification_status"] == "pending", \
        f"Expected 'pending' but got '{req['verification_status']}' — " \
        "stale stored value was not overridden by derivation"


# ── Derived values appear on the list endpoint ────────────────────────────────

def test_derived_values_on_list_endpoint(client, project):
    from .conftest import make_req
    make_req(client, project, "REQ0001")
    _make_vc(client, project, "VC-001", status="passed",
             verified_requirements=["REQ0001"])
    items = client.get(f"/api/projects/{project}/requirements").json()["items"]
    req = next(r for r in items if r["id"] == "REQ0001")
    assert req["verification_status"] == "passed"
    assert req["verification_methods"] == ["test"]


# ── PUT with verification fields is ignored ───────────────────────────────────

def test_put_verification_fields_ignored(client, project):
    from .conftest import make_req
    make_req(client, project, "REQ0001")
    # Send a PUT with verification fields — it should succeed (2xx) and
    # the values should remain the derived ones.
    res = client.put(
        f"/api/projects/{project}/requirements/REQ0001",
        json={
            "verification_status": "passed",
            "verification_method": "analysis",
        },
    )
    assert res.status_code == 200

    # Re-read: the fields should be the derived defaults (no VC covers it).
    req = client.get(f"/api/projects/{project}/requirements/REQ0001").json()
    assert req["verification_status"] == "pending"
    assert req["verification_method"] == "test"
    assert req["verification_methods"] == []


# ── Equivalence with the old per-requirement computation ──────────────────────

def _naive_derive(requirement_id, vcs):
    """The old per-requirement computation, written out explicitly so the
    assertion below does not just restate the implementation."""
    mine = [vc for vc in vcs if requirement_id in (vc.get("verified_requirements") or [])]
    if not mine:
        return {
            "verification_status": "pending",
            "verification_method": "test",
            "verification_methods": [],
        }
    statuses = {(vc.get("status") or "").strip().lower() for vc in mine}
    status = next(
        (s for s in ("failed", "pending", "in_progress", "passed") if s in statuses),
        "pending",
    )
    methods = sorted({(vc.get("method") or "").strip().lower() for vc in mine if vc.get("method")})
    return {
        "verification_status": status,
        "verification_method": methods[0] if methods else "test",
        "verification_methods": methods,
    }


def _overlapping_fixture():
    """Requirements and cases with overlapping and empty coverage on both sides."""
    n_reqs, n_cases = 30, 20
    requirements = [{"id": f"REQ{i:03d}"} for i in range(n_reqs)]
    statuses = ["passed", "failed", "pending", "in_progress", "banana"]
    methods = ["test", "analysis", "inspection", ""]
    vcs = []
    for i in range(n_cases):
        vc = {
            "id": f"VC{i:03d}",
            "status": statuses[i % len(statuses)],
            "method": methods[i % len(methods)],
            "verified_requirements": [],
        }
        if i != 5:  # VC-005 verifies nothing.
            vc["verified_requirements"] = sorted({f"REQ{i % n_reqs:03d}", f"REQ{(i + 7) % n_reqs:03d}"})
        vcs.append(vc)
    return requirements, vcs


def test_attach_matches_naive_computation():
    requirements, vcs = _overlapping_fixture()

    expected = []
    for r in requirements:
        entry = dict(r)
        entry["verification_cases"] = sorted(
            vc["id"] for vc in vcs
            if r["id"] in (vc.get("verified_requirements") or [])
        )
        entry.update(_naive_derive(r["id"], vcs))
        expected.append(entry)

    result = attach(
        None,
        [dict(r) for r in requirements],
        [dict(vc) for vc in vcs],
    )
    assert result == expected


# ── Complexity guard ──────────────────────────────────────────────────────────

def test_attach_inspects_each_case_linear_times():
    """attach() must not rescan the full case list per requirement.

    Each case's fields are read through a counting proxy; the total number of
    reads across one attach() call has to stay O(N+M). With N=200 and M=100 the
    old per-requirement rescan reads each case 200+ times (~20,000 reads); the
    grouped implementation stays well under 2,000.
    """
    n_reqs, n_cases = 200, 100
    reads = Counter()

    class CountingCase(dict):
        def __getitem__(self, key):
            reads[id(self)] += 1
            return super().__getitem__(key)

        def get(self, key, default=None):
            reads[id(self)] += 1
            return super().get(key, default)

    requirements = [{"id": f"REQ{i:03d}"} for i in range(n_reqs)]
    vcs = [
        CountingCase({
            "id": f"VC{i:03d}",
            "status": "passed",
            "method": "test",
            "verified_requirements": [f"REQ{i:03d}"],
        })
        for i in range(n_cases)
    ]

    attach(None, requirements, vcs)

    assert sum(reads.values()) < 2000, sum(reads.values())
