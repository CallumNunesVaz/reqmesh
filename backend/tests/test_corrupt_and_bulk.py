"""Regression tests for two shipped defects.

BUG-1: the bulk change-request routes addressed the collection as
``"change-requests"`` while the store registers ``"change_requests"``, so
``_item_path`` raised a bare ``ValueError`` and *every* call to both endpoints
returned 500. No test covered these routes.

BUG-2: ``_read_yaml`` swallowed parse errors and returned ``{}``, which
``list_items`` then appended to the collection. That empty dict flowed
downstream into ``item["id"]`` and took out /evaluation, /validate, /metrics,
/coverage and /quality with a 500 that never named the offending file — so a
single hand-edited YAML file (the documented workflow for a git-native tool)
broke the project with no diagnostic.
"""
from pathlib import Path

from tests.conftest import make_req


class TestBulkChangeRequests:
    """BUG-1 — these returned 500 on every call."""

    def _mk(self, client, project, cr_id="CR-1"):
        res = client.post(f"/api/projects/{project}/change-requests",
                          json={"id": cr_id, "title": "Tighten mass budget"})
        assert res.status_code == 201, res.text
        return res.json()

    def test_bulk_update_succeeds(self, client, project):
        self._mk(client, project, "CR-1")
        self._mk(client, project, "CR-2")
        res = client.post(f"/api/projects/{project}/change-requests/bulk",
                          json={"ids": ["CR-1", "CR-2"], "updates": {"status": "approved"}})
        assert res.status_code == 200, res.text
        assert res.json()["updated"] == 2
        listed = client.get(f"/api/projects/{project}/change-requests").json()["items"]
        assert {c["status"] for c in listed} == {"approved"}

    def test_bulk_delete_succeeds(self, client, project):
        self._mk(client, project, "CR-1")
        self._mk(client, project, "CR-2")
        res = client.post(f"/api/projects/{project}/change-requests/bulk-delete",
                          json={"ids": ["CR-1", "CR-2"]})
        assert res.status_code == 200, res.text
        assert res.json()["deleted"] == 2
        assert client.get(f"/api/projects/{project}/change-requests").json()["items"] == []

    def test_bulk_delete_records_history(self, client, project):
        self._mk(client, project, "CR-1")
        client.post(f"/api/projects/{project}/change-requests/bulk-delete",
                    json={"ids": ["CR-1"]})
        # The delete path reads `before` through the same collection name.
        from app.core.dependencies import get_store
        assert get_store(project).list_history("CR-1"), "delete was not audited"

    def test_unknown_collection_is_a_400_not_a_500(self, project):
        """A future typo must surface as a bad request, not a server error."""
        from fastapi import HTTPException
        from app.core.dependencies import get_store
        import pytest
        with pytest.raises(HTTPException) as exc:
            get_store(project).get_item("change-requests", "CR-1")
        assert exc.value.status_code == 400


class TestCorruptYamlIsSkippedNotFatal:
    """BUG-2 — one unparseable file used to 500 five endpoints."""

    def _corrupt(self, project, req_id="REQ-002"):
        from app.core.config import settings
        path = Path(settings.data_root) / project / "requirements" / f"{req_id}.yaml"
        path.write_text('id: REQ-002\nname: "unterminated\n')
        return path

    def test_list_skips_it_instead_of_yielding_an_empty_dict(self, client, project):
        make_req(client, project, "REQ-001")
        make_req(client, project, "REQ-002")
        make_req(client, project, "REQ-003")
        self._corrupt(project)

        from app.core.dependencies import get_store
        reqs = get_store(project).list_requirements()
        assert {} not in reqs, "corrupt file was coerced into an empty dict"
        assert [r["id"] for r in reqs] == ["REQ-001", "REQ-003"]

    def test_analysis_endpoints_stay_up(self, client, project):
        make_req(client, project, "REQ-001")
        make_req(client, project, "REQ-002")
        self._corrupt(project)

        for endpoint in ("evaluation", "validate", "metrics", "coverage",
                         "quality", "requirements", "gap-analysis"):
            res = client.get(f"/api/projects/{project}/{endpoint}")
            assert res.status_code == 200, f"/{endpoint} -> {res.status_code}"

    def test_corruption_is_reported_rather_than_silent(self, client, project):
        make_req(client, project, "REQ-001")
        make_req(client, project, "REQ-002")
        self._corrupt(project)

        issues = client.get(f"/api/projects/{project}/validate").json()["issues"]
        corrupt = [i for i in issues if i["type"] == "corrupt_file"]
        assert corrupt, "corrupt file vanished silently instead of being reported"
        assert "REQ-002.yaml" in corrupt[0]["id"]

    def test_a_file_without_an_id_is_also_skipped(self, client, project):
        """Parses fine, but has no `id` — same KeyError downstream."""
        make_req(client, project, "REQ-001")
        from app.core.config import settings
        (Path(settings.data_root) / project / "requirements" / "stray.yaml").write_text(
            "name: no id field here\n")

        from app.core.dependencies import get_store
        assert [r["id"] for r in get_store(project).list_requirements()] == ["REQ-001"]
        assert client.get(f"/api/projects/{project}/evaluation").status_code == 200

    def test_update_refuses_to_clobber_a_corrupt_file(self, client, project):
        """The merge path must not replace unparseable content with just the patch."""
        make_req(client, project, "REQ-002")
        path = self._corrupt(project)
        original = path.read_text()

        res = client.put(f"/api/projects/{project}/requirements/REQ-002",
                         json={"name": "renamed"})
        assert res.status_code == 409, res.text
        assert path.read_text() == original, "corrupt file was overwritten (data loss)"
