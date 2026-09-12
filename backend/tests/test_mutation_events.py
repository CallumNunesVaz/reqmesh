"""The mutation event's entity attribution.

The SPA uses the `collection` on each mutation event to invalidate only the
collection that changed, instead of re-fetching and re-solving the whole
project. These pin the path→collection mapping so a new route cannot silently
start broadcasting a wrong (or missing) kind.
"""
from app.main import _mutation_target


def test_project_scoped_collection_is_extracted():
    assert _mutation_target("/api/projects/p/requirements") == ("requirements", None)
    assert _mutation_target("/api/projects/p/requirements/R-1") == ("requirements", "R-1")
    assert _mutation_target("/api/projects/p/change-requests/CR-1") == ("change-requests", "CR-1")
    assert _mutation_target("/api/projects/p/system-states") == ("system-states", None)


def test_bulk_and_subroutes_keep_their_collection():
    assert _mutation_target("/api/projects/p/requirements/bulk") == ("requirements", "bulk")
    assert _mutation_target("/api/projects/p/verification/VC-1") == ("verification", "VC-1")


def test_unattributable_paths_fall_back_to_global():
    # An import or scan writes many collections; a bare project mutation has no
    # collection. Both must report None so the client refreshes everything.
    assert _mutation_target("/api/projects/p/import") == (None, None)
    assert _mutation_target("/api/projects/p/scan") == (None, None)
    assert _mutation_target("/api/projects/p") == (None, None)
    assert _mutation_target("/api/system/update/bundle") == (None, None)
