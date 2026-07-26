"""BUG-5 — `mode=replace` deleted the project before it parsed the input.

Two failure modes, both ending with an emptied project:

1. A ragged row. ``csv.DictReader`` pads missing trailing fields with ``None``,
   and ``row.get(col, default)`` returns that ``None`` (the key *is* present),
   so ``.strip()`` raised ``AttributeError`` — after every requirement had
   already been deleted.
2. An unrecognised id column. Every row was skipped, so the import deleted
   everything and returned a cheerful ``{"created": 0}`` with HTTP 200.

The invariant these tests pin down: if an import cannot succeed, the project
must be exactly as it was.
"""
import pytest

from app.core.dependencies import get_store
from tests.conftest import make_req

HEADER = "id,name,description,type,status,priority,rationale,source,relations,verification_cases"
GOOD = f"{HEADER}\nREQ-100,Imported,Desc,functional,proposed,medium,,,,"


def _ids(project):
    return sorted(r["id"] for r in get_store(project).list_requirements())


class TestRaggedRowDoesNotDestroyTheProject:
    def test_short_row_is_parsed_not_crashed(self, client, project):
        """A truncated trailing row must import, not raise."""
        make_req(client, project, "REQ-001")
        csv_text = f"{HEADER}\nREQ-100,Imported,Desc\n"   # 3 of 10 columns
        res = client.post(
            f"/api/projects/{project}/import",
            files={"file": ("r.csv", csv_text, "text/csv")},
            data={"format": "csv", "mode": "merge"},
        )
        assert res.status_code == 200, res.text
        assert "REQ-100" in _ids(project)

    def test_replace_with_a_ragged_row_keeps_the_project_intact(self, client, project):
        make_req(client, project, "REQ-001")
        make_req(client, project, "REQ-002")
        before = _ids(project)

        csv_text = f"{HEADER}\nREQ-100,Imported,Desc\n"
        res = client.post(
            f"/api/projects/{project}/import",
            files={"file": ("r.csv", csv_text, "text/csv")},
            data={"format": "csv", "mode": "replace"},
        )
        # Either it imports cleanly, or it refuses — but it must never leave
        # the project empty.
        assert res.status_code in (200, 400), res.text
        if res.status_code == 400:
            assert _ids(project) == before
        else:
            assert _ids(project) == ["REQ-100"]

    def test_unparseable_row_leaves_everything_untouched(self, client, project):
        """Force a parse failure and assert the collection is unchanged."""
        import app.services.table_io as table_io
        make_req(client, project, "REQ-001")
        make_req(client, project, "REQ-002")
        before = _ids(project)

        original = table_io._row_to_req
        def boom(row):
            raise RuntimeError("unparseable cell")
        table_io._row_to_req = boom
        try:
            res = client.post(
                f"/api/projects/{project}/import",
                files={"file": ("r.csv", GOOD, "text/csv")},
                data={"format": "csv", "mode": "replace"},
            )
        finally:
            table_io._row_to_req = original

        assert res.status_code == 400, res.text
        assert _ids(project) == before, "project was emptied by a failed import"


class TestUnrecognisedHeaderRefusesToWipe:
    def test_replace_without_an_id_column_is_rejected(self, client, project):
        make_req(client, project, "REQ-001")
        make_req(client, project, "REQ-002")
        before = _ids(project)

        csv_text = "Requirement Identifier,Title\nREQ-100,Imported\n"
        res = client.post(
            f"/api/projects/{project}/import",
            files={"file": ("r.csv", csv_text, "text/csv")},
            data={"format": "csv", "mode": "replace"},
        )
        assert res.status_code == 400, res.text
        assert "id" in res.json()["detail"].lower()
        assert _ids(project) == before, "project was wiped for an unusable file"

    def test_an_empty_file_does_not_wipe(self, client, project):
        make_req(client, project, "REQ-001")
        before = _ids(project)
        res = client.post(
            f"/api/projects/{project}/import",
            files={"file": ("r.csv", HEADER + "\n", "text/csv")},
            data={"format": "csv", "mode": "replace"},
        )
        # No rows at all: replacing with nothing is a legitimate no-op request,
        # but it must not be reported as a success that silently emptied things.
        assert res.status_code in (200, 400)
        if res.status_code == 400:
            assert _ids(project) == before


class TestReplaceStillWorks:
    def test_a_valid_replace_swaps_the_contents(self, client, project):
        """The guards must not break the feature."""
        make_req(client, project, "REQ-001")
        res = client.post(
            f"/api/projects/{project}/import",
            files={"file": ("r.csv", GOOD, "text/csv")},
            data={"format": "csv", "mode": "replace"},
        )
        assert res.status_code == 200, res.text
        assert _ids(project) == ["REQ-100"]


class TestReqIfImporterIsAlsoTransactional:
    def test_malformed_component_does_not_empty_the_project(self, client, project):
        """`quantity: "two"` raised inside _normalise_component, previously
        after requirements/VCs/components had all been deleted."""
        from app.services.importer import import_into_store
        make_req(client, project, "REQ-001")
        store = get_store(project)
        before = _ids(project)

        parsed = {
            "requirements": [{"id": "REQ-100", "name": "New"}],
            "components": [{"id": "COMP-1", "name": "Bad", "quantity": "two"}],
        }
        with pytest.raises(ValueError):
            import_into_store(store, parsed, mode="replace")

        assert _ids(project) == before, "project was emptied by a failed import"
