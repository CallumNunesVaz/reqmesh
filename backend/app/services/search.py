from __future__ import annotations

"""In-memory search over the YAML store.

Projects are directories of small YAML files that are fully loaded for most
operations anyway, so search filters the loaded documents directly. This
keeps the project directory free of derived artifacts (no _search.db to
commit or drift out of sync) and removes the need for index maintenance.
"""

FILTERABLE_FIELDS = ("type", "priority", "status", "verification_status")


def _searchable_text(req: dict) -> str:
    parts = [v for v in req.values() if isinstance(v, str)]
    for attr in req.get("attributes") or []:
        if isinstance(attr, dict):
            parts.append(str(attr.get("value", "")))
    return " ".join(parts).lower()


def search_requirements(reqs: list[dict], query: str = "", filters: dict | None = None) -> list[dict]:
    query = (query or "").strip().lower()
    results = []
    for req in reqs:
        if filters and any(
            req.get(field) != value
            for field, value in filters.items()
            if value and field in FILTERABLE_FIELDS
        ):
            continue
        if query and query not in _searchable_text(req):
            continue
        results.append(req)
    results.sort(key=lambda r: r.get("modified", ""), reverse=True)
    return results
