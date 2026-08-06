"""Ensure every API route is documented in README.md.

Walks the live FastAPI route table (the same recursive walk used by
test_permissions.py, because a flat scan silently misses every route inside
an ``include_router`` since Starlette 1.x).  For every APIRoute whose path
starts with ``/api``, this test asserts the path appears in README.md after
collapsing every ``{param}`` segment to ``{}`` — the README writes ``{id}``
where the route says ``{project_id}``, so the comparison must collapse both
to the same shape.
"""

import re

from fastapi.routing import APIRoute

from app.main import app


class _PrefixedRoute:
    """An APIRoute paired with its fully-qualified path.

    Starlette 1.x stopped flattening ``include_router`` into ``app.routes``:
    an included router now appears as a single wrapper object holding the
    original router plus the prefix it was mounted under, and the routes
    inside it keep their *unprefixed* paths.  This wrapper stores the full
    path so callers don't have to reconstruct it.
    """

    def __init__(self, route, path):
        self._route = route
        self.path = path

    def __getattr__(self, name):
        return getattr(self._route, name)


def _collect_api_routes():
    """Walk the live FastAPI route table and return every APIRoute under /api.

    This is a local copy of the recursion in test_permissions.py so that
    test_docs_currency stays self-contained — the guarantee that the README
    is up to date should not depend on a test in another module.
    """
    found: list[_PrefixedRoute] = []

    def walk(routes, prefix: str) -> None:
        for r in routes:
            if isinstance(r, APIRoute):
                found.append(_PrefixedRoute(r, prefix + r.path))
                continue
            # An included sub-router: descend, carrying its mount prefix.
            original = getattr(r, "original_router", None)
            context = getattr(r, "include_context", None)
            if original is not None and hasattr(original, "routes"):
                walk(original.routes, prefix + getattr(context, "prefix", ""))
            elif hasattr(r, "routes"):
                walk(r.routes, prefix + getattr(r, "path", ""))

    walk(app.routes, "")
    return [r for r in found if r.path.startswith("/api")]


def _normalise(path: str) -> str:
    """Collapse every ``{...}`` segment to ``{}`` so ``{project_id}`` and ``{id}``
    compare as equal."""
    return re.sub(r"\{[^}]+\}", "{}", path)


# Paths that are genuinely internal / utility endpoints that do not belong
# in the README's public API table.  Every entry must carry a comment
# explaining *why* it is excluded — a bare exclusion is the thing this test
# exists to prevent.
_RAW_UNDOCUMENTED = {
    # Auth flow internals — these are called by the login page, not by users
    # working with project data.
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/guest",
    "/api/auth/whoami",
    "/api/auth/logout",
    "/api/auth/logout-everywhere",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
    "/api/auth/verify-email",
    "/api/auth/resend-verification",

    # User-management detail routes — the README covers the four core CRUD
    # operations; the remaining actions (disable, unlock, force-logout, invite,
    # bulk, export CSV, import CSV, profile) are admin-step flows documented
    # in the prose, not the API table.
    "/api/auth/profile",
    "/api/auth/users/{username}/disable",
    "/api/auth/users/{username}/unlock",
    "/api/auth/users/{username}/logout",
    "/api/auth/users/invite",
    "/api/auth/users/bulk",
    "/api/auth/users/export",
    "/api/auth/users/import",

    # System/admin maintenance — documented in the prose (Settings page,
    # System page) and the deployment guide, not in the API reference.
    "/api/system/settings",
    "/api/system/settings/test-email",
    "/api/system/latex-status",
    "/api/system/info",
    "/api/system/update/check",
    "/api/system/update/status",
    "/api/system/update",
    "/api/system/update/upload",
    "/api/system/update/bundle",
    "/api/system/restart",
    "/api/system/update/dismiss",
    "/api/system/dependencies",
    "/api/system/dependencies/{dep_id}/test",

    # Public config is served unauthenticated for the login page; not a
    # project-data endpoint.
    "/api/system/public-config",

    # Utility lookups that the UI calls internally — the entity vocabulary
    # and per-requirement value are computed on-demand, not user-facing routes.
    "/api/coverage-needs",
    "/api/projects/{project_id}/entities/{entity_id}/backlinks",
    "/api/projects/{project_id}/requirements/{req_id}/value",

    # Allocation matrix helpers — the matrix is rendered on the Requirements
    # page; these are read by the matrix component, not by API consumers.
    "/api/projects/{project_id}/allocation-matrix",
    "/api/projects/{project_id}/allocation",

    # Component-lookup convenience endpoints — the UI calls these to populate
    # relation editors; users never hit them directly.
    "/api/projects/{project_id}/requirements/{req_id}/components",
    "/api/projects/{project_id}/verification/{vc_id}/components",

    # Test-results import — an integration helper, not a project-data route.
    "/api/projects/{project_id}/test-results/sample",
    "/api/projects/{project_id}/test-results/import",

    # Git restore — an internal called by the settings UI's history list; the
    # README covers the restore behaviour in prose rather than as a route.
    #
    # status/init/push/remote and the hook endpoints are deliberately NOT here:
    # they are the whole point of the git panel, and allowlisting the headline
    # routes of a feature is how the gate stops meaning anything.
    "/api/projects/{project_id}/git/restore",

    # Suspect-link clear — an admin utility on the Validation page.
    "/api/projects/{project_id}/suspect-links/clear",

    # WebSocket — APIRoute never picks this up, but list it for safety.
    "/api/projects/{project_id}/ws",

    # Bulk operations — every entity has a bulk update and bulk delete
    # endpoint.  These are UI helpers for multi-select actions, not public
    # API surfaces that belong in the reference table.
    "/api/projects/{project_id}/requirements/bulk",
    "/api/projects/{project_id}/requirements/bulk-delete",
    "/api/projects/{project_id}/requirements/bulk-reparent",
    "/api/projects/{project_id}/components/bulk",
    "/api/projects/{project_id}/components/bulk-delete",
    "/api/projects/{project_id}/components/bulk-reparent",
    "/api/projects/{project_id}/verification/bulk",
    "/api/projects/{project_id}/verification/bulk-delete",
    "/api/projects/{project_id}/specifications/bulk",
    "/api/projects/{project_id}/specifications/bulk-delete",
    "/api/projects/{project_id}/risks/bulk",
    "/api/projects/{project_id}/risks/bulk-delete",
    "/api/projects/{project_id}/change-requests/bulk",
    "/api/projects/{project_id}/change-requests/bulk-delete",

    # Internal version check — the UI calls this to display the build version;
    # it is not a project-data endpoint.
    "/api/version",
}

UNDOCUMENTED_ON_PURPOSE: set[str] = {_normalise(p) for p in _RAW_UNDOCUMENTED}


def test_every_api_route_is_in_the_readme():
    readme_path = __file__.replace("/backend/tests/test_docs_currency.py", "/README.md")
    with open(readme_path, "r") as f:
        readme_text = f.read()

    # Normalise the README too: collapse every {param} so a line written as
    # `/api/projects/{id}/requirements` matches the route
    # `/api/projects/{project_id}/requirements`.
    readme_normalised = _normalise(readme_text)

    # Collect route paths.  We only care about APIRoute instances; Mount and
    # WebSocket routes are not API routes.
    routes = _collect_api_routes()

    missing: list[str] = []
    for route in routes:
        norm = _normalise(route.path)
        if norm in UNDOCUMENTED_ON_PURPOSE:
            continue
        if norm not in readme_normalised:
            missing.append(route.path)

    assert not missing, (
        "Undocumented API routes: " + ", ".join(sorted(missing))
    )
