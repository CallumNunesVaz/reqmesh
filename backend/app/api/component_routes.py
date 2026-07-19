"""Component CRUD — the synthesised design tree.

Components mirror the requirement hierarchy's shape (self-referential `parent`,
a /tree endpoint) but carry the design→function mapping: which requirements a
component satisfies, and which verification cases exercise it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.dependencies import get_store, require_edit
from app.core.ids import safe_id
from app.models.component import ComponentCreate, ComponentUpdate
from app.services.yaml_store import YamlStore
from app.services.history import record_change
from app.services.yaml_store import YamlStore

router = APIRouter()


def _build_tree(components: list[dict], parent_id: str | None) -> list[dict]:
    children = []
    for c in components:
        if c.get("parent") == parent_id:
            children.append({
                "id": c["id"],
                "name": c.get("name", ""),
                "type": c.get("type", "assembly"),
                "quantity": c.get("quantity", 1),
                "satisfies": list(c.get("satisfies") or []),
                "children": _build_tree(components, c["id"]),
            })
    return children


def _validate_parent(store: YamlStore, component_id: str, parent_id: str | None) -> None:
    """Reject a parent that is missing, self-referential, or cyclic.

    Without the walk a component could be reparented under its own descendant,
    which detaches that whole branch from the tree — the /tree endpoint would
    silently stop returning it.
    """
    if parent_id is None:
        return
    if parent_id == component_id:
        raise HTTPException(status_code=400, detail="A component cannot be its own parent")
    if store.get_component(parent_id) is None:
        raise HTTPException(status_code=400, detail=f"Parent component not found: {parent_id}")

    by_id = {c["id"]: c for c in store.list_components()}
    seen = {component_id}
    cursor = parent_id
    while cursor is not None:
        if cursor in seen:
            raise HTTPException(status_code=400, detail="Circular parent reference")
        seen.add(cursor)
        cursor = (by_id.get(cursor) or {}).get("parent")


def _validate_links(store: YamlStore, satisfies: list[str] | None, vcs: list[str] | None) -> None:
    """A link to something that does not exist is a silent hole in traceability."""
    for req_id in satisfies or []:
        if store.get_requirement(req_id) is None:
            raise HTTPException(status_code=400, detail=f"Requirement not found: {req_id}")
    for vc_id in vcs or []:
        if store.get_verification_case(vc_id) is None:
            raise HTTPException(status_code=400, detail=f"Verification case not found: {vc_id}")


# NOTE: static paths (tree) must be registered before the /{component_id}
# catch-all, or "tree" is parsed as a component id.

@router.get("/projects/{project_id}/components/tree")
async def get_component_tree(project_id: str):
    store = get_store(project_id)
    return _build_tree(store.list_components(), None)


@router.get("/projects/{project_id}/components")
async def list_components(
    project_id: str,
    search: str | None = Query(None),
    type: str | None = Query(None),
    satisfies: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=2000),
):
    store = get_store(project_id)
    items = store.list_components()
    if type:
        items = [c for c in items if c.get("type") == type]
    if satisfies:
        items = [c for c in items if satisfies in (c.get("satisfies") or [])]
    if search:
        needle = search.lower()
        items = [
            c for c in items
            if needle in f"{c.get('id', '')} {c.get('name', '')} {c.get('part_number', '')} "
                         f"{c.get('supplier', '')} {c.get('description', '')}".lower()
        ]
    items = sorted(items, key=lambda c: c.get("id", ""))
    total = len(items)
    return {"items": items[offset:offset + limit], "total": total, "offset": offset, "limit": limit}


@router.get("/projects/{project_id}/components/{component_id}")
async def get_component(project_id: str, component_id: str):
    store = get_store(project_id)
    component = store.get_component(component_id)
    if component is None:
        raise HTTPException(status_code=404, detail="Component not found")
    return component


@router.post("/projects/{project_id}/components", status_code=201)
async def create_component(project_id: str, data: ComponentCreate, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    safe_id(data.id, "component id")
    if store.get_component(data.id):
        raise HTTPException(status_code=409, detail="Component already exists")
    _validate_parent(store, data.id, data.parent)
    _validate_links(store, data.satisfies, data.verification_cases)
    result = store.create_component(data.model_dump(mode="json"))
    record_change(store, result["id"], "create", None, result, user.get("username", ""))
    return result


@router.put("/projects/{project_id}/components/{component_id}")
async def update_component(
    project_id: str, component_id: str, data: ComponentUpdate, user: dict = Depends(require_edit)
):
    store = get_store(project_id)
    before = store.get_component(component_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Component not found")

    update = data.model_dump(mode="json", exclude_unset=True)
    if "parent" in update:
        _validate_parent(store, component_id, update["parent"])
    _validate_links(store, update.get("satisfies"), update.get("verification_cases"))

    result = store.update_component(component_id, update)
    if result is None:
        raise HTTPException(status_code=404, detail="Component not found")
    record_change(store, component_id, "update", before, result, user.get("username", ""))
    return result


@router.delete("/projects/{project_id}/components/{component_id}")
async def delete_component(project_id: str, component_id: str, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    doomed = store.get_component(component_id)
    if doomed is None:
        raise HTTPException(status_code=404, detail="Component not found")

    # Promote children to the removed component's parent. Orphaning them would
    # leave a dangling `parent` and drop the whole branch out of /tree.
    promoted = []
    for child in store.list_components():
        if child.get("parent") == component_id:
            store.update_component(child["id"], {"parent": doomed.get("parent")})
            promoted.append(child["id"])

    store.delete_component(component_id)
    record_change(store, component_id, "delete", doomed, None, user.get("username", ""))
    return {"ok": True, "promoted_children": promoted}


# ── Reverse lookups ──────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/requirements/{req_id}/components")
async def components_for_requirement(project_id: str, req_id: str):
    """Which parts of the design claim to realise this requirement."""
    store = get_store(project_id)
    if store.get_requirement(req_id) is None:
        raise HTTPException(status_code=404, detail="Requirement not found")
    return [c for c in store.list_components() if req_id in (c.get("satisfies") or [])]


@router.get("/projects/{project_id}/verification/{vc_id}/components")
async def components_for_verification_case(project_id: str, vc_id: str):
    """Which parts of the design this verification case exercises."""
    store = get_store(project_id)
    if store.get_verification_case(vc_id) is None:
        raise HTTPException(status_code=404, detail="Verification case not found")
    return [c for c in store.list_components() if vc_id in (c.get("verification_cases") or [])]
