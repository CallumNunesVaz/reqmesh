"""Every project-scoped GET route must carry a read gate.

SEC-5 closed when ``require_view`` reached every ``GET`` route whose path has a
``{project_id}``. This walks the live route table rather than enumerating paths
by hand, so a newly added read route cannot silently skip the gate.
"""
from __future__ import annotations

import pytest

from app.main import app

#: The guard that the task adds, plus the stricter write-tier guards that must
#: not be loosened to ``view``.
GUARD_NAMES = {"require_view", "require_edit", "require_maintain", "require_admin"}


def _depend_names(dependant) -> set[str]:
    """Every callable reachable through ``dependant``'s dependency chain."""
    names: set[str] = set()
    stack = [dependant]
    while stack:
        dep = stack.pop()
        call = getattr(dep, "call", None)
        if call is not None:
            names.add(call.__name__)
        stack.extend(getattr(dep, "dependencies", None) or [])
    return names


def _iter_routes(routes):
    """Flatten the route table.

    ``app.include_router`` nests each included router inside an
    ``_IncludedRouter`` wrapper rather than splicing its routes into
    ``app.routes``, so the walk recurses through those wrappers. Leaf routes
    (``APIRoute`` / ``_EffectiveRouteContext``) carry ``.dependant``.
    """
    for route in routes:
        if hasattr(route, "dependant"):
            yield route
            continue
        for method in ("effective_candidates", "effective_low_priority_routes"):
            fn = getattr(route, method, None)
            if fn is not None:
                yield from _iter_routes(fn())


def _project_read_routes() -> tuple[list[str], list[str]]:
    """Split project-scoped GET routes into (gated, ungated) by path."""
    gated: list[str] = []
    ungated: list[str] = []
    for route in _iter_routes(app.routes):
        methods = getattr(route, "methods", None)
        if not methods or "GET" not in methods:
            continue
        if "{project_id}" not in getattr(route, "path", ""):
            continue
        if _depend_names(route.dependant) & GUARD_NAMES:
            gated.append(route.path)
        else:
            ungated.append(route.path)
    return gated, ungated


def test_every_project_scoped_get_route_is_gated():
    gated, ungated = _project_read_routes()
    assert not ungated, (
        f"{len(ungated)} project-scoped GET route(s) are not gated by "
        f"require_view or a stricter guard:\n  "
        + "\n  ".join(sorted(ungated))
    )
    assert gated


def test_gate_covers_at_least_sixty_routes():
    gated, _ = _project_read_routes()
    assert len(gated) >= 60, (
        f"expected the gate on at least 60 project-scoped GET routes, "
        f"found {len(gated)} — the path predicate may have broken"
    )


def test_health_version_and_project_list_stay_ungated():
    for path in ("/health", "/version", "/api/projects"):
        matches = [r for r in _iter_routes(app.routes) if getattr(r, "path", None) == path]
        assert matches, f"no route found for {path}"
        for route in matches:
            names = _depend_names(route.dependant)
            assert not (names & GUARD_NAMES), f"{path} must not carry a read gate"


@pytest.fixture()
def admin_client(_real_role_client):
    with _real_role_client("admin", "view_gate_admin") as c:
        yield c


@pytest.fixture()
def project(admin_client):
    r = admin_client.post("/api/projects", json={"id": "vgp", "name": "VGP"})
    assert r.status_code == 201, r.text
    admin_client.patch("/api/projects/vgp", json={"naming": {"enforce": False}})
    return "vgp"


def test_analysis_read_gate_end_to_end(project, admin_client, contributor_client, maintainer_client):
    admin_client.patch(f"/api/projects/{project}",
                       json={"permissions": {"contributor": "none"}})
    assert contributor_client.get(f"/api/projects/{project}/gap-analysis").status_code == 403
    assert maintainer_client.get(f"/api/projects/{project}/gap-analysis").status_code == 200


def test_router_read_gate_end_to_end(project, admin_client, contributor_client, maintainer_client):
    admin_client.patch(f"/api/projects/{project}",
                       json={"permissions": {"contributor": "none"}})
    assert contributor_client.get(f"/api/projects/{project}/requirements").status_code == 403
    assert maintainer_client.get(f"/api/projects/{project}/requirements").status_code == 200
