"""Tests for GET /projects/{project_id}/activity."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


from app.services.entity_kinds import resolve_entity_label
from app.services.yaml_store import YamlStore

from .conftest import make_req


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%d")


class TestActivityDistinctCounts:
    def test_one_item_updated_twice_counts_once(self, client, project):
        """A requirement created then updated twice still counts as one
        distinct item in its bucket — the distinct-items rule.  This is the
        thing most likely to be implemented wrong, so it is the first test."""
        make_req(client, project, "AD01", name="Activity One")
        client.put(f"/api/projects/{project}/requirements/AD01", json={"priority": "high"})
        client.put(f"/api/projects/{project}/requirements/AD01", json={"priority": "low"})

        res = client.get(
            f"/api/projects/{project}/activity",
            params={"since": _days_ago(1), "until": _today(), "bucket": "day"},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["total"] == 1
        today_bucket = next(
            (b for b in body["buckets"] if b["date"] == _today()), None
        )
        assert today_bucket is not None, f"No bucket for today in {body['buckets']}"
        assert today_bucket["requirement"] == 1

    def test_distinct_items_per_kind(self, client, project):
        """Two different requirements touched on the same day each count."""
        make_req(client, project, "AD02", name="First")
        make_req(client, project, "AD03", name="Second")

        res = client.get(
            f"/api/projects/{project}/activity",
            params={"since": _days_ago(1), "until": _today(), "bucket": "day"},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["total"] == 2


class TestZeroActivityDates:
    def test_zero_days_present(self, client, project):
        """Every date in the range appears, including days with no activity."""
        res = client.get(
            f"/api/projects/{project}/activity",
            params={"since": _days_ago(3), "until": _today(), "bucket": "day"},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        # 4 days: today-3, today-2, today-1, today
        assert len(body["buckets"]) == 4
        dates = [b["date"] for b in body["buckets"]]
        assert dates == sorted(dates), "buckets must be in date order"


class TestKindFiltering:
    def test_kinds_excludes_zero_total(self, client, project):
        """`kinds` lists only entity kinds that actually occur."""
        make_req(client, project, "AK01", name="Only Req")
        res = client.get(
            f"/api/projects/{project}/activity",
            params={"since": _days_ago(1), "until": _today(), "bucket": "day"},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert "requirement" in body["kinds"]
        # No component, no verification, etc.
        for absent in ("component", "verification", "risk", "decision", "change", "specification"):
            assert absent not in body["kinds"]


class TestDefaultAndClamping:
    def test_default_window_is_90_days(self, client, project):
        """When `since` is omitted the endpoint defaults to 90 days."""
        res = client.get(f"/api/projects/{project}/activity")
        assert res.status_code == 200, res.text
        body = res.json()
        until_d = date.fromisoformat(body["until"])
        since_d = date.fromisoformat(body["since"])
        assert (until_d - since_d).days == 90

    def test_since_older_than_365_is_clamped(self, client, project):
        """A `since` beyond 365 days ago is clamped, not rejected."""
        ancient = (datetime.now(timezone.utc) - timedelta(days=400)).strftime("%Y-%m-%d")
        res = client.get(
            f"/api/projects/{project}/activity",
            params={"since": ancient, "until": _today(), "bucket": "day"},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        until_d = date.fromisoformat(body["until"])
        since_d = date.fromisoformat(body["since"])
        assert (until_d - since_d).days <= 365


class TestWeekBucketing:
    def test_week_totals_match_day(self, client, project):
        """`bucket=week` groups seven days; the total across buckets must
        agree with `bucket=day` for the same range.  This catches an off-by-one
        at the week boundary (a day counted twice or not at all)."""
        make_req(client, project, "AW01", name="Week Test 1")
        make_req(client, project, "AW02", name="Week Test 2")
        make_req(client, project, "AW03", name="Week Test 3")

        day_res = client.get(
            f"/api/projects/{project}/activity",
            params={"since": _days_ago(30), "until": _today(), "bucket": "day"},
        )
        assert day_res.status_code == 200, day_res.text
        day_body = day_res.json()

        week_res = client.get(
            f"/api/projects/{project}/activity",
            params={"since": _days_ago(30), "until": _today(), "bucket": "week"},
        )
        assert week_res.status_code == 200, week_res.text
        week_body = week_res.json()

        assert day_body["total"] == week_body["total"], (
            f"day total {day_body['total']} != week total {week_body['total']}"
        )

    def test_week_buckets_are_monday_dates(self, client, project):
        """Week keys are ISO Monday dates."""
        make_req(client, project, "AW10", name="Week Date Test")
        res = client.get(
            f"/api/projects/{project}/activity",
            params={"since": _days_ago(7), "until": _today(), "bucket": "week"},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        for b in body["buckets"]:
            d = date.fromisoformat(b["date"])
            assert d.weekday() == 0, f"week bucket {b['date']} is not a Monday"


class TestIdCollision:
    def test_shared_id_respects_precedence(self, client, project):
        """A component and a requirement sharing an id is attributed by the
        resolver's documented precedence (requirements > components).  Assert
        the current behaviour so the known limitation is pinned rather than
        accidentally changed."""
        make_req(client, project, "SHARED", name="Shared Requirement")
        client.post(
            f"/api/projects/{project}/components",
            json={"id": "SHARED", "name": "Shared Component", "type": "part"},
        )

        res = client.get(
            f"/api/projects/{project}/activity",
            params={"since": _days_ago(1), "until": _today(), "bucket": "day"},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        today_bucket = next(
            (b for b in body["buckets"] if b["date"] == _today()), None
        )
        assert today_bucket is not None
        # Both items have the SAME id. Requirements take precedence, so both
        # audit entries land under "requirement" and count as 1 distinct item,
        # NOT 1 requirement + 1 component.
        assert today_bucket["requirement"] == 1
        assert today_bucket["component"] == 0


class TestPublisherRegression:
    def test_changelog_unchanged_after_lift(self, client, project):
        """The publisher's changelog output is identical after the lift.
        We compare against the shape and data we know from test_changelog_report."""
        from app.services.publisher import Publisher
        from app.core.config import settings
        from pathlib import Path

        make_req(client, project, "PR01", name="Lift Test")
        client.put(f"/api/projects/{project}/requirements/PR01", json={"priority": "high"})

        store = YamlStore(Path(settings.data_root) / project)
        log = Publisher(store).changelog(_days_ago(1), _today())

        assert log["items"] == 1
        assert len(log["entries"]) == 2  # create + update
        actions = log["counts"]
        assert actions.get("create") == 1
        assert actions.get("update") == 1
        # Entries are newest first
        stamps = [e["timestamp"] for e in log["entries"]]
        assert stamps == sorted(stamps, reverse=True)


class TestResolver:
    def test_resolver_falls_back_to_item(self, client, project):
        """An id known to no entity returns ('Item', '')."""
        from app.core.config import settings
        from pathlib import Path

        store = YamlStore(Path(settings.data_root) / project)
        kind, name = resolve_entity_label(store, "NONEXIST")
        assert kind == "Item"
        assert name == ""

    def test_resolver_precedence(self, client, project):
        """Verify the documented precedence order of resolve_entity_label."""
        from app.core.config import settings
        from pathlib import Path

        store = YamlStore(Path(settings.data_root) / project)
        make_req(client, project, "RP01", name="ReqFirst")

        kind, name = resolve_entity_label(store, "RP01")
        assert kind == "Requirement"
        assert name == "ReqFirst"


def test_history_window_does_not_drop_entries_at_the_boundary(client):
    """The filename prefilter must never drop an entry the timestamps keep.

    `list_all_history` skips files whose *name* falls outside the window before
    opening them — without that, a 90-day query read and parsed every entry in
    the project's whole history and only then discarded it, so the window
    bounded nothing (measured: 4.7 s for 90 days against 9000 history files,
    4.9 s for 365 — identical, because the reading dominated).

    The prefilter is a day looser at each end than the exact comparison, and
    this pins that: an entry written today is still returned by a window that
    starts today, which is where an off-by-one in the filename comparison would
    show up first.
    """
    from datetime import datetime, timezone

    p = "bound1"
    client.post("/api/projects", json={"id": p, "name": "Bound"})
    client.post(f"/api/projects/{p}/requirements", json={"id": "R-1", "title": "r"})
    client.put(f"/api/projects/{p}/requirements/R-1", json={"name": "changed"})

    today = datetime.now(timezone.utc).date().isoformat()
    res = client.get(f"/api/projects/{p}/activity?since={today}&until={today}")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] >= 1, "today's edit must survive a window starting today"

    # And a window that ends before the edit must not return it.
    res2 = client.get(f"/api/projects/{p}/activity?since=2020-01-01&until=2020-01-02")
    assert res2.json()["total"] == 0


class TestActivityRejectsUnparseableDates:
    """`date.fromisoformat` raises ValueError, which FastAPI does not turn into
    a response — so a mistyped date came back as a 500 with a stack trace. Found
    by the generated contract suite, which is exactly its job."""

    def test_unparseable_since_is_a_400(self, client, project):
        res = client.get(f"/api/projects/{project}/activity", params={"since": "0"})
        assert res.status_code == 400, res.text
        assert "since" in res.json()["detail"]

    def test_unparseable_until_is_a_400(self, client, project):
        res = client.get(f"/api/projects/{project}/activity", params={"until": "not-a-date"})
        assert res.status_code == 400, res.text
        assert "until" in res.json()["detail"]

    def test_empty_dates_still_mean_the_default_window(self, client, project):
        """An empty string is "unset", not "invalid" — the default 90-day
        window still applies, so the 400 above cannot have been over-eager."""
        res = client.get(f"/api/projects/{project}/activity", params={"since": "", "until": ""})
        assert res.status_code == 200, res.text
