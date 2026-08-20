"""Per-project permission enforcement.

Unlike most tests, these exercise the *real* auth guards (the ``guest_client``
fixture installs no dependency overrides), driving them with genuine bearer
tokens so we can verify the propose/edit tiers and the per-project permissions
map actually gate requests.
"""
from app.core import auth
from app.core.dependencies import get_store


def _tok(username: str, role: str) -> dict:
    auth.register_user(username, "Password123!", role)
    return {"Authorization": f"Bearer {auth.create_token(username, role)}"}


def _make_project(client) -> None:
    r = client.post("/api/projects", json={"id": "p", "name": "P"},
                    headers=_tok("adm", "admin"))
    assert r.status_code == 201, r.text


def _new_cr(client, headers, cr_id="CR-1"):
    return client.post("/api/projects/p/change-requests",
                       json={"id": cr_id, "title": "x"}, headers=headers)


def _new_req(client, headers, req_id="R-1"):
    return client.post("/api/projects/p/requirements",
                       json={"id": req_id, "name": "x"}, headers=headers)


class TestDefaultTiers:
    def test_contributor_can_propose_but_not_edit(self, guest_client):
        _make_project(guest_client)
        cont = _tok("cont", "contributor")
        assert _new_cr(guest_client, cont).status_code == 201       # propose tier
        assert _new_req(guest_client, cont).status_code == 403      # edit tier

    def test_maintainer_can_edit(self, guest_client):
        _make_project(guest_client)
        maint = _tok("maint", "maintainer")
        assert _new_cr(guest_client, maint).status_code == 201
        assert _new_req(guest_client, maint).status_code == 201

    def test_guest_cannot_propose(self, guest_client):
        _make_project(guest_client)
        assert _new_cr(guest_client, {}).status_code == 403

    def test_contributor_cannot_create_project(self, guest_client):
        r = guest_client.post("/api/projects", json={"id": "q", "name": "Q"},
                              headers=_tok("cont", "contributor"))
        assert r.status_code == 403


class TestLegacyRolesHardened:
    def test_legacy_viewer_and_editor_are_blocked(self, guest_client):
        _make_project(guest_client)
        for role in ("viewer", "editor"):
            h = _tok(f"legacy_{role}", role)
            assert _new_cr(guest_client, h).status_code == 403, role
            assert _new_req(guest_client, h).status_code == 403, role


class TestProjectPermissionMap:
    def test_map_can_elevate_contributor_to_edit(self, guest_client):
        _make_project(guest_client)
        cont = _tok("cont", "contributor")
        assert _new_req(guest_client, cont).status_code == 403

        store = get_store("p")
        meta = store.read_meta()
        meta["permissions"] = {"guest": "view", "contributor": "edit",
                               "maintainer": "edit", "admin": "admin"}
        store.write_meta(meta)

        assert _new_req(guest_client, cont, "R-2").status_code == 201

    def test_map_cannot_demote_a_global_admin(self, guest_client):
        _make_project(guest_client)
        store = get_store("p")
        meta = store.read_meta()
        meta["permissions"] = {"admin": "view"}
        store.write_meta(meta)

        adm = {"Authorization": f"Bearer {auth.create_token('adm', 'admin')}"}
        assert _new_req(guest_client, adm, "R-3").status_code == 201


# ═══════════════════════════════════════════════════════════════════════════════
# Route-table-driven permission audit — generated from the live FastAPI route
# table so a new endpoint added without a permission dependency fails CI.
# ═══════════════════════════════════════════════════════════════════════════════

import re
import inspect
import pytest
from fastapi.routing import APIRoute

from app.main import app

_PERM_DEP_NAMES = frozenset({
    "require_edit", "require_maintain", "require_maintain_global", "require_admin",
})

_PROJECT_ID_RE = re.compile(r"^/api/projects/\{[^}]+\}(/.*)?$")


class _PrefixedRoute:
    """An APIRoute paired with its fully-qualified path.

    Starlette 1.x stopped flattening ``include_router`` into ``app.routes``:
    an included router now appears as a single wrapper object holding the
    original router plus the prefix it was mounted under, and the routes
    inside it keep their *unprefixed* paths.
    """

    def __init__(self, route, path):
        self._route = route
        self.path = path

    def __getattr__(self, name):
        return getattr(self._route, name)


def _collect_api_routes():
    """Walk the live FastAPI route table and return every APIRoute under /api.

    This must recurse. The flat ``app.routes`` scan it replaced silently
    stopped finding anything when fastapi/starlette were upgraded — it did not
    fail, it just parametrised zero routes, so the guarantee that every
    mutating endpoint carries a permission guard quietly went untested. Any
    future change to how routers are mounted must keep this returning a
    non-empty list; ``test_route_collection_is_not_silently_empty`` enforces
    that.
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


def _dep_name(dep):
    """Return the string name of a FastAPI dependency if resolvable."""
    if inspect.isfunction(dep):
        return dep.__name__
    if inspect.isclass(dep):
        return dep.__name__
    if hasattr(dep, "dependency") and inspect.isfunction(dep.dependency):
        return dep.dependency.__name__
    return None


def _has_perm_dep(route: APIRoute) -> bool:
    """True if *route* resolves at least one permission-guard dependency."""
    for dep in getattr(route, "dependencies", []) or []:
        name = _dep_name(dep)
        if name and name in _PERM_DEP_NAMES:
            return True
    if hasattr(route, "dependant") and route.dependant:
        for dd in getattr(route.dependant, "dependencies", []) or []:
            call = getattr(dd, "call", None)
            if call and hasattr(call, "__name__") and call.__name__ in _PERM_DEP_NAMES:
                return True
    return False


# Path suffixes for POST endpoints that are genuinely read-only computations —
# they take a request body because the query is too complex for a query string,
# but they touch no state.
#
# Keep this list minimal. `/import` and `/scan` were previously exempt here on
# the grounds of being "dry-run"; both can in fact mutate (`/import` in replace
# mode deletes every requirement), and exempting them meant the two most
# destructive routes in the API were the two the audit would never check.
_READONLY_POST_SUFFIXES = frozenset({
    "/evaluation/impact",
})


def _required_guard(route: APIRoute) -> str | None:
    """Return the guard class a mutating route *should* carry, or None if unguarded
    is acceptable."""
    path = route.path
    methods = route.methods or set()

    if path == "/api/projects":
        if "POST" in methods:
            return "require_maintain_global"
        return None

    if _PROJECT_ID_RE.match(path):
        if "DELETE" in methods and path == "/api/projects/{project_id}":
            return "require_admin"
        # Anything that configures or exercises the git remote is an admin
        # decision — the remote determines where the whole project history is
        # shipped. Kept in step with router._guard_git_settings, which refuses a
        # remote_url change from anyone below admin.
        if path.endswith("/git/test-remote") or path.endswith("/git/remote") \
                or path.endswith("/git/key") or path.endswith("/git/key/rotate"):
            return "require_admin"
        if methods & {"POST", "PUT", "PATCH", "DELETE"}:
            # Allow read-only computation endpoints to skip permission guards.
            if any(path.endswith(s) for s in _READONLY_POST_SUFFIXES):
                return None
            # Bulk operations need higher privilege regardless of entity type.
            if "/bulk" in path:
                return "require_maintain"
            if any(seg in path for seg in ("/change-requests", "/risks",
                    "/comments", "/decisions")):
                # Execute and reject are maintainer-tier — they write requirements.
                if path.endswith("/execute") or path.endswith("/reject"):
                    return "require_maintain"
                return "require_edit"
            return "require_maintain"
        return None

    if path.startswith("/api/auth/users"):
        if methods & {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            return "require_admin"
        return None

    if path.startswith("/api/system/") and path != "/api/system/public-config":
        if methods & {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            return "require_admin"
        return None

    if path.startswith("/api/auth/"):
        return None

    return None


def _describe_route(method: str, path: str) -> str:
    return f"{method} {path}"


_API_ROUTES = _collect_api_routes()
# Group routes so each gets its own parametrised test case.
_MUTATING_ROUTES = [
    (r, m) for r in _API_ROUTES
    for m in sorted(r.methods or set())
    if m in {"POST", "PUT", "PATCH", "DELETE"}
]


def test_route_collection_is_not_silently_empty():
    """The two tests below are parametrised over the live route table, so if
    collection breaks they pass vacuously rather than failing.

    That is exactly what happened on the fastapi 0.115 -> 0.141 upgrade:
    starlette 1.x stopped flattening included routers into ``app.routes``, the
    scan found 2 routes instead of 159, and 188 permission checks disappeared
    from the suite without a single failure. Assert the floor explicitly.
    """
    assert len(_API_ROUTES) > 100, (
        f"only {len(_API_ROUTES)} /api routes collected — _collect_api_routes "
        f"is no longer walking the route table correctly"
    )
    assert len(_MUTATING_ROUTES) > 80, (
        f"only {len(_MUTATING_ROUTES)} mutating route cases — permission "
        f"coverage has silently shrunk"
    )


@pytest.mark.parametrize("route,method", _MUTATING_ROUTES,
                         ids=[_describe_route(m, r.path) for r, m in _MUTATING_ROUTES])
def test_mutating_route_has_permission_dep(route, method):
    """Every mutating API route must carry a permission dependency.

    A route added without ``require_edit``, ``require_maintain``,
    ``require_maintain_global`` or ``require_admin`` fails this test.
    """
    guard = _required_guard(route)
    if guard is None:
        return
    assert _has_perm_dep(route), (
        f"{method} {route.path} has no permission dependency — "
        f"expected {guard}"
    )


@pytest.mark.parametrize("route,method", _MUTATING_ROUTES,
                         ids=[_describe_route(m, r.path) for r, m in _MUTATING_ROUTES])
def test_mutating_route_uses_correct_permission_dep(route, method):
    """Every mutating API route must use the *right* guard tier.

    A ``POST /api/projects/{id}/requirements`` carrying ``require_edit`` instead
    of ``require_maintain`` fails this test.
    """
    guard = _required_guard(route)
    if guard is None:
        return
    dep_names = set()
    for d in getattr(route, "dependencies", []) or []:
        name = _dep_name(d)
        if name:
            dep_names.add(name)
    if hasattr(route, "dependant") and route.dependant:
        for dd in getattr(route.dependant, "dependencies", []) or []:
            call = getattr(dd, "call", None)
            if call and hasattr(call, "__name__"):
                dep_names.add(call.__name__)
    assert guard in dep_names, (
        f"{method} {route.path} has dependencies {sorted(dep_names)} — "
        f"expected {guard}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# WRITE_TIER — the single source of truth for per-entity write tiers. Both the
# single-item and bulk write endpoints must agree with it, so the two paths
# cannot drift apart again.
# ═══════════════════════════════════════════════════════════════════════════════

from app.core.dependencies import WRITE_TIER

_TIER_LEVEL = {"propose": 1, "edit": 2}

_GUARD_LEVEL = {
    "require_edit": 1,            # propose tier
    "require_maintain": 2,        # edit tier
    "require_maintain_global": 2,
    "require_admin": 3,
}

_KIND_TO_SEGMENT = {
    "requirements": "requirements",
    "components": "components",
    "specifications": "specifications",
    "verification_cases": "verification",
    "risks": "risks",
    "change_requests": "change-requests",
    "comments": "comments",
    "decisions": "decisions",
}
_SEGMENT_TO_KIND = {seg: kind for kind, seg in _KIND_TO_SEGMENT.items()}


def _guard_names(route) -> set[str]:
    names = set()
    for d in getattr(route, "dependencies", []) or []:
        name = _dep_name(d)
        if name:
            names.add(name)
    if hasattr(route, "dependant") and route.dependant:
        for dd in getattr(route.dependant, "dependencies", []) or []:
            call = getattr(dd, "call", None)
            if call and hasattr(call, "__name__"):
                names.add(call.__name__)
    return names


def _write_routes_by_kind() -> dict[str, dict[str, list[set[str]]]]:
    """Classify each entity write route as (kind, category) -> guard names.

    ``category`` is ``single`` for the create/update endpoints, ``bulk`` for the
    ``/bulk*`` endpoints, and ``action`` for deeper sub-routes (execute/reject/
    cascade/review) that are stricter by design.
    """
    result: dict[str, dict[str, list[set[str]]]] = {
        kind: {"single": [], "bulk": [], "action": []} for kind in _KIND_TO_SEGMENT
    }
    for r in _API_ROUTES:
        methods = r.methods or set()
        if not (methods & {"POST", "PUT", "PATCH"}):
            continue
        m = re.match(r"^/api/projects/\{[^}]+\}/(.*)$", r.path)
        if not m:
            continue
        segs = m.group(1).split("/")
        kind = _SEGMENT_TO_KIND.get(segs[0])
        if kind is None:
            continue
        guards = _guard_names(r)
        if any(s.startswith("bulk") for s in segs[1:]):
            result[kind]["bulk"].append(guards)
        elif len(segs) <= 2:
            result[kind]["single"].append(guards)
        else:
            result[kind]["action"].append(guards)
    return result


def _max_guard_level(guards: set[str]) -> int:
    return max((_GUARD_LEVEL.get(g, 0) for g in guards), default=0)


def test_write_endpoints_agree_with_write_tier():
    """Each entity kind's bulk and single-item write endpoints agree with WRITE_TIER.

    The generic single-item create/update endpoints must be exactly the tier the
    table records; bulk and sub-action endpoints must never be *looser* than it
    (a bulk path that is stricter is safe, and is noted rather than widened).
    """
    by_kind = _write_routes_by_kind()
    for kind, tier in WRITE_TIER.items():
        assert kind in _KIND_TO_SEGMENT, f"WRITE_TIER key '{kind}' has no route segment"
        level = _TIER_LEVEL[tier]
        routes = by_kind[kind]

        assert routes["single"], f"no single-item write endpoint found for {kind}"
        for guards in routes["single"]:
            assert _max_guard_level(guards) == level, (
                f"{kind}: single-item write guard {sorted(guards)} "
                f"disagrees with WRITE_TIER '{tier}'"
            )

        for category in ("bulk", "action"):
            for guards in routes[category]:
                assert _max_guard_level(guards) >= level, (
                    f"{kind}: {category} guard {sorted(guards)} is looser "
                    f"than WRITE_TIER '{tier}'"
                )
