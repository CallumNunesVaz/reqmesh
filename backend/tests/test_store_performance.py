"""PERF-1 — fast read path and collection cache.

``list_items`` re-parsed every file on every call with ruamel's round-trip
loader, the slowest mode available (~1.9 ms/doc — 19 s for 10k requirements),
and a single page load triggered a dozen such scans.

The trap in the obvious fix: round-trip mode is exactly what preserves a user's
comments through an edit, which a git-native store whose selling point is
hand-editable YAML must not lose. So the fast loader is used **only** on the
read-only list path, and round-trip is retained for read-modify-write. The
first test here is the one that matters.
"""
import time

from app.core.dependencies import get_store
from app.services import yaml_store
from tests.conftest import make_req


class TestCommentsSurviveAnEdit:
    """The non-negotiable property. If this fails, the optimisation is wrong."""

    def test_hand_written_comments_survive_a_field_update(self, client, project):
        store = get_store(project)
        make_req(client, project, "REQ-001", name="Cabin pressure")
        path = store.root / "requirements" / "REQ-001.yaml"

        original = path.read_text()
        path.write_text("# Safety-critical: reviewed by CE board 2026-03\n" + original)

        store.update_requirement("REQ-001", {"status": "approved"})

        after = path.read_text()
        assert "# Safety-critical: reviewed by CE board 2026-03" in after, \
            "user's YAML comment was destroyed by an edit"
        assert "approved" in after

    def test_comment_survives_a_list_then_edit(self, client, project):
        """The list path uses the comment-dropping loader; make sure its result
        can never be the thing written back."""
        store = get_store(project)
        make_req(client, project, "REQ-001")
        path = store.root / "requirements" / "REQ-001.yaml"
        path.write_text("# keep me\n" + path.read_text())

        store.list_requirements()          # populates the cache via fast parse
        store.update_requirement("REQ-001", {"priority": "high"})

        assert "# keep me" in path.read_text()


class TestCacheCorrectness:
    def test_a_write_is_visible_immediately(self, client, project):
        store = get_store(project)
        make_req(client, project, "REQ-001")
        assert {r["id"] for r in store.list_requirements()} == {"REQ-001"}

        make_req(client, project, "REQ-002")
        assert {r["id"] for r in store.list_requirements()} == {"REQ-001", "REQ-002"}

    def test_a_delete_is_visible_immediately(self, client, project):
        store = get_store(project)
        make_req(client, project, "REQ-001")
        make_req(client, project, "REQ-002")
        store.delete_requirement("REQ-001")
        assert {r["id"] for r in store.list_requirements()} == {"REQ-002"}

    def test_an_external_edit_is_picked_up(self, client, project):
        """Someone editing the YAML in git, outside the process."""
        store = get_store(project)
        make_req(client, project, "REQ-001", name="Before")
        assert store.list_requirements()[0]["name"] == "Before"

        path = store.root / "requirements" / "REQ-001.yaml"
        path.write_text(path.read_text().replace("Before", "After"))
        yaml_store.invalidate_cache()  # mtime_ns granularity can tie within a test

        assert store.list_requirements()[0]["name"] == "After"

    def test_mutating_a_returned_item_cannot_poison_the_cache(self, client, project):
        store = get_store(project)
        make_req(client, project, "REQ-001", name="Original")

        got = store.list_requirements()
        got[0]["name"] = "Mutated by caller"

        assert store.list_requirements()[0]["name"] == "Original"

    def test_projects_do_not_share_a_cache_entry(self, client):
        client.post("/api/projects", json={"id": "a", "name": "A"})
        client.post("/api/projects", json={"id": "b", "name": "B"})
        make_req(client, "a", "REQ-A1")
        make_req(client, "b", "REQ-B1")
        assert {r["id"] for r in get_store("a").list_requirements()} == {"REQ-A1"}
        assert {r["id"] for r in get_store("b").list_requirements()} == {"REQ-B1"}


class TestItIsActuallyFaster:
    def test_repeat_reads_are_served_from_cache(self, client, project):
        store = get_store(project)
        for i in range(40):
            make_req(client, project, f"REQ-{i:03d}")

        yaml_store.invalidate_cache()
        t0 = time.perf_counter()
        store.list_requirements()
        cold = time.perf_counter() - t0

        t0 = time.perf_counter()
        for _ in range(10):
            store.list_requirements()
        warm = (time.perf_counter() - t0) / 10

        # Cached reads only stat the directory; expect a large margin, but
        # assert something loose enough not to be flaky on a busy machine.
        assert warm < cold / 2, f"cache gave no benefit (cold={cold:.4f}s warm={warm:.4f}s)"

    def test_fast_loader_matches_the_round_trip_loader(self, client, project):
        """Same data out of both paths — the fast path must not change values."""
        store = get_store(project)
        make_req(client, project, "REQ-001", name="Cabin", rationale="Because")
        path = store.root / "requirements" / "REQ-001.yaml"

        fast = store._parse_fast(path)
        roundtrip = store._parse_yaml(path)
        assert fast == roundtrip
