"""Tests for the optional date-bounded changelog ("diff report") section."""

from datetime import datetime, timedelta, timezone

from app.services.publisher import Publisher
from app.services.yaml_store import YamlStore

from .conftest import make_req


def _store(client, project) -> YamlStore:
    from app.core.config import settings
    from pathlib import Path
    return YamlStore(Path(settings.data_root) / project)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%d")


class TestChangelogCollection:
    def test_captures_create_update_delete(self, client, project):
        make_req(client, project, "CL01", name="First")
        client.put(f"/api/projects/{project}/requirements/CL01", json={"priority": "high"})
        make_req(client, project, "CL02", name="Second")
        client.delete(f"/api/projects/{project}/requirements/CL02")

        log = Publisher(_store(client, project)).changelog(_days_ago(1), _today())
        actions = log["counts"]
        assert actions.get("create") == 2
        assert actions.get("update") == 1
        assert actions.get("delete") == 1
        assert log["items"] == 2
        assert len(log["entries"]) == 4

    def test_entries_are_newest_first(self, client, project):
        make_req(client, project, "CL10", name="Ordered")
        client.put(f"/api/projects/{project}/requirements/CL10", json={"priority": "high"})
        entries = Publisher(_store(client, project)).changelog(_days_ago(1), _today())["entries"]
        stamps = [e["timestamp"] for e in entries]
        assert stamps == sorted(stamps, reverse=True)

    def test_update_carries_before_and_after(self, client, project):
        make_req(client, project, "CL20", name="Fields", priority="low")
        client.put(f"/api/projects/{project}/requirements/CL20", json={"priority": "critical"})
        entries = Publisher(_store(client, project)).changelog(_days_ago(1), _today())["entries"]
        upd = next(e for e in entries if e["action"] == "update")
        prio = next(f for f in upd["fields"] if f["field"] == "priority")
        assert prio["before"] == "low"
        assert prio["after"] == "critical"

    def test_create_and_delete_omit_field_noise(self, client, project):
        """A create/delete diffs the whole record; listing every field would
        bury the real edits, so only updates carry field detail."""
        make_req(client, project, "CL30", name="Noisy")
        client.delete(f"/api/projects/{project}/requirements/CL30")
        entries = Publisher(_store(client, project)).changelog(_days_ago(1), _today())["entries"]
        for e in entries:
            if e["action"] in ("create", "delete"):
                assert e["fields"] == []

    def test_deleted_item_keeps_its_name(self, client, project):
        """The record is gone, so the name must come from the audit entry."""
        make_req(client, project, "CL40", name="Gone But Named")
        client.delete(f"/api/projects/{project}/requirements/CL40")
        entries = Publisher(_store(client, project)).changelog(_days_ago(1), _today())["entries"]
        deleted = next(e for e in entries if e["action"] == "delete")
        assert deleted["name"] == "Gone But Named"


class TestChangelogDateWindow:
    def test_end_date_includes_the_whole_day(self, client, project):
        """A bare end date must not exclude changes made later that same day."""
        make_req(client, project, "CL50", name="Today")
        log = Publisher(_store(client, project)).changelog(_today(), _today())
        assert len(log["entries"]) >= 1

    def test_window_excludes_outside_changes(self, client, project):
        make_req(client, project, "CL60", name="Recent")
        log = Publisher(_store(client, project)).changelog("2000-01-01", "2000-01-31")
        assert log["entries"] == []
        assert log["counts"] == {}


class TestChangelogExport:
    def test_absent_sections_param_yields_full_report(self, client, project):
        make_req(client, project, "CL70", name="Full")
        res = client.get(f"/api/projects/{project}/publish/download?format=latex")
        assert res.status_code == 200
        body = res.text
        assert "\\section{Requirements by Type}" in body
        assert "\\section{Changelog}" not in body  # opt-in only

    def test_empty_sections_param_yields_no_sections(self, client, project):
        """Explicitly empty means "none" — not "fall back to everything"."""
        make_req(client, project, "CL80", name="Empty")
        res = client.get(f"/api/projects/{project}/publish/download?format=latex&sections=")
        assert res.status_code == 200
        assert "\\section{Requirements by Type}" not in res.text

    def test_changelog_only_export_is_a_diff_report(self, client, project):
        make_req(client, project, "CL90", name="Diffed")
        client.put(f"/api/projects/{project}/requirements/CL90", json={"priority": "high"})
        res = client.get(
            f"/api/projects/{project}/publish/download"
            f"?format=latex&sections=changelog&changelog_from={_days_ago(1)}&changelog_to={_today()}"
        )
        assert res.status_code == 200
        body = res.text
        assert "\\section{Changelog}" in body
        # The point of the feature: none of the bulk report comes along.
        assert "\\section{Requirements by Type}" not in body
        assert "\\section{Components}" not in body

    def test_changelog_reports_an_empty_period_cleanly(self, client, project):
        make_req(client, project, "CL95", name="Quiet")
        res = client.get(
            f"/api/projects/{project}/publish/download"
            "?format=latex&sections=changelog&changelog_from=2000-01-01&changelog_to=2000-01-31"
        )
        assert res.status_code == 200
        assert "No changes were recorded in this period." in res.text

    def test_html_export_includes_changelog(self, client, project):
        make_req(client, project, "CLA0", name="HtmlLogged")
        res = client.get(
            f"/api/projects/{project}/publish/download"
            f"?format=html&sections=changelog&changelog_from={_days_ago(1)}&changelog_to={_today()}"
        )
        assert res.status_code == 200
        assert 'id="sec-changelog"' in res.text
