from __future__ import annotations

import itertools
import re
import string
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Depends, Request, Response
from pydantic import BaseModel

from app.core.dependencies import get_store, require_maintain, require_maintain_global, require_admin
from app.core.ids import safe_id
from app.core.tree_utils import build_flat_tree
from app.models.requirement import RequirementCreate, RequirementUpdate
from app.services.load_guard import is_safe_id, validate_on_load
from app.models.specification import SpecificationCreate, SpecificationUpdate
from app.models.definition import DefinitionCreate, DefinitionUpdate
from app.models.analysis import AnalysisCaseCreate, AnalysisCaseUpdate
from app.models.trace import TraceMatrix
from app.models.verification import VerificationCaseCreate, VerificationCaseUpdate
from app.services.yaml_store import YamlStore
from app.services.search import search_requirements
from app.services.history import record_change


class ProjectCreate(BaseModel):
    id: str
    name: str


class BaselineDefItem(BaseModel):
    """A baseline definition — name, optional short symbol, and rich-text description."""
    name: str
    symbol: str = ""
    description: str = ""


def normalize_baseline_defs(baselines: list) -> list[dict]:
    """Normalize baseline definitions from either legacy string format or
    the object format to a uniform list of {name, symbol, description}."""
    result: list[dict] = []
    for item in (baselines or []):
        if isinstance(item, str):
            result.append({"name": item, "symbol": "", "description": ""})
        elif isinstance(item, dict):
            result.append({
                "name": item.get("name", ""),
                "symbol": item.get("symbol", ""),
                "description": item.get("description", ""),
            })
    return result


def _baseline_def_by_name(baselines: list, name: str) -> dict | None:
    for b in normalize_baseline_defs(baselines):
        if b["name"] == name:
            return b
    return None


class BaselineCreate(BaseModel):
    name: str
    symbol: str = ""
    description: str = ""
    requirements: list[str] = []


class RunVerification(BaseModel):
    status: str
    notes: str = ""
    step_results: dict[str, str] | None = None


class BreakCascade(BaseModel):
    break_children: bool = False

class RenameBaseline(BaseModel):
    name: str
    symbol: Optional[str] = None
    description: Optional[str] = None


router = APIRouter()


@router.get("/version")
def api_version():
    """Build metadata for this instance (also served at /version for probes)."""
    from app.core.version import get_build_info
    return get_build_info()


# ── Projects ────────────────────────────────────────────────────────────────

@router.get("/projects")
def list_projects():
    from app.core.config import settings

    root = Path(settings.data_root)
    if not root.exists():
        return []
    projects = []
    for d in sorted(root.iterdir()):
        if d.is_dir() and (d / "_meta.yaml").exists():
            store = YamlStore(d)
            meta = store.read_meta()
            projects.append({"id": d.name, "name": meta.get("name", d.name), "path": str(d)})
    return projects


@router.post("/projects", status_code=201)
def create_project(data: ProjectCreate, user: dict = Depends(require_maintain_global)):
    from app.core.config import settings

    project_id = safe_id(data.id, "project id")
    project_root = Path(settings.data_root) / project_id
    if project_root.exists():
        raise HTTPException(status_code=409, detail="Project already exists")
    store = YamlStore(project_root)
    store.ensure_dirs()
    store.write_meta({"name": data.name or project_id})
    return {"id": project_id, "name": data.name or project_id, "path": str(project_root)}


@router.get("/projects/{project_id}")
def get_project(project_id: str, request: Request,
                      authorization: Optional[str] = Header(None)):
    store = get_store(project_id)
    meta = store.read_meta()
    naming = meta.get("naming", {})
    out = {
        "id": project_id,
        "name": meta.get("name", project_id),
        "path": str(store.root),
        "workflow": meta.get("workflow"),
        "naming": naming,
        "quality": meta.get("quality"),
        "baselines": normalize_baseline_defs(meta.get("baselines", [])),
    }
    # Git settings can hold a credentialed remote URL, so unlike the rest of
    # the project metadata they are only shown to those who manage settings
    # (the maintainer tier that the settings page itself requires).
    # Resolved through get_current_user so the HttpOnly session cookie counts —
    # checking only the Authorization header stopped working for the UI when
    # auth moved to cookies, silently hiding git settings from maintainers.
    from app.core.dependencies import get_current_user
    user = get_current_user(request=request, authorization=authorization)
    if user.get("role") in ("maintainer", "admin"):
        out["git"] = meta.get("git", {})
    return out


class ProjectSettings(BaseModel):
    name: Optional[str] = None
    naming: Optional[dict] = None
    quality: Optional[dict] = None
    workflow: Optional[dict] = None
    git: Optional[dict] = None
    baselines: Optional[list] = None  # list of BaselineDefItem-compatible dicts or legacy strings
    permissions: Optional[dict] = None


_ALLOWED_REMOTE_SCHEMES = ("https://", "ssh://", "git@")


def _guard_git_settings(new_git: dict, existing_git: dict, user: dict) -> None:
    """Changing where a project pushes to is an admin decision.

    ``remote_url`` decides where the entire project history is shipped, so a
    maintainer being able to set it freely is an exfiltration primitive (and a
    blind SSRF probe against internal hosts). Everything else under ``git`` —
    identity, push cadence, autocommit — stays at the maintainer tier.
    """
    incoming = (new_git or {}).get("remote_url")
    current = (existing_git or {}).get("remote_url")
    if incoming == current:
        return
    if user.get("role") != "admin":
        raise HTTPException(status_code=403,
                            detail="Only an admin can change the git remote URL")
    if incoming and not str(incoming).startswith(_ALLOWED_REMOTE_SCHEMES):
        raise HTTPException(
            status_code=400,
            detail="git remote URL must start with https://, ssh:// or git@ "
                   "(file:// and http:// are refused)",
        )


@router.patch("/projects/{project_id}")
def update_project_settings(project_id: str, data: ProjectSettings, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    meta = store.read_meta()
    updates = {}
    for field in ("name", "naming", "quality", "workflow", "git", "baselines", "permissions"):
        val = getattr(data, field, None)
        if val is not None:
            updates[field] = val
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "git" in updates:
        _guard_git_settings(updates["git"], meta.get("git", {}), user)
    if "baselines" in updates and updates["baselines"] is not None:
        defs = normalize_baseline_defs(updates["baselines"])
        # Baseline names become filenames when a baseline is frozen
        # (`store.get_item("baselines", name)`), so they need the same
        # validation `create_baseline` applies. Without it this endpoint
        # accepted `../../etc/passwd`, and every later GET /baselines then
        # raised 400 from `_item_path` — breaking the whole listing for the
        # project until someone hand-edited _meta.yaml.
        for d in defs:
            safe_id(d["name"], "baseline name")
        updates["baselines"] = [
            {k: v for k, v in d.items() if k == "name" or v} for d in defs
        ]
    meta.update(updates)
    store.write_meta(meta)
    return meta


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, user: dict = Depends(require_admin)):
    import shutil

    store = get_store(project_id)
    shutil.rmtree(store.root)
    return {"ok": True}


@router.get("/projects/{project_id}/workflow")
def get_workflow_config(project_id: str):
    """Return the project's workflow configuration (states, transitions, default)."""
    store = get_store(project_id)
    from app.services.workflow import get_workflow
    return get_workflow(store.read_meta())


# ── Requirements ─────────────────────────────────────────────────────────────
# NOTE: static paths (tree, next-uid) must be registered before the
# /requirements/{req_id} route or they are shadowed by it.

@router.get("/projects/{project_id}/requirements/tree")
def get_requirement_tree(project_id: str):
    store = get_store(project_id)
    reqs = store.list_requirements()
    return build_flat_tree(reqs, project=lambda r: {
        "id": r["id"],
        "name": r.get("name", ""),
        "type": r.get("type", "functional"),
        "status": r.get("status", "proposed"),
        "priority": r.get("priority", "medium"),
    })


@router.get("/projects/{project_id}/requirements/next-uid")
def next_uid(project_id: str, parent: str | None = None):
    store = get_store(project_id)
    reqs = store.list_requirements()
    meta = store.read_meta()
    naming = meta.get("naming", {}).get("requirements", {})
    prefix_len = int(naming.get("prefix_length", 4) or 4)
    prefix_type = naming.get("prefix_type", "alpha")
    prefix_hint = naming.get("prefix_hint", "REQ")
    separator = naming.get("separator", "")
    suffix_len = int(naming.get("suffix_length", 4) or 4)
    suffix_type = naming.get("suffix_type", "numeric")

    prefix = None
    if parent:
        parent_req = store.get_requirement(parent)
        if parent_req:
            pid = parent_req["id"]
            if separator and separator in pid:
                prefix = pid.split(separator)[0]
            elif separator:
                prefix = pid[:prefix_len].upper()
            else:
                prefix = pid[:prefix_len].upper()

    if not prefix:
        used = set()
        for r in reqs:
            rid = r.get("id", "")
            if separator and separator in rid:
                used.add(rid.split(separator)[0].upper())
            else:
                used.add(rid[:prefix_len].upper())
        if prefix_hint.upper() not in used:
            prefix = prefix_hint.upper()
        else:
            # Walk sequentially from the hint instead of generating all
            # combinations up front (itertools.product over 26^4 = 457k).
            # This finds the first available prefix in the same sorted order
            # without materialising the entire space.
            chars = string.ascii_uppercase if prefix_type == "alpha" else string.ascii_uppercase + string.digits
            _prefix_iter = _make_prefix_iter(chars, prefix_len)
            for candidate in _prefix_iter:
                if candidate not in used:
                    prefix = candidate
                    break
            if not prefix:
                prefix = prefix_hint.upper() + "0"

    base = prefix + separator if separator else prefix
    max_suffix = -1
    suffix_pattern = re.escape(base)
    for r in reqs:
        rid = r.get("id", "")
        if rid.startswith(base):
            rest = rid[len(base):]
            if suffix_type == "numeric":
                try:
                    max_suffix = max(max_suffix, int(rest))
                except ValueError:
                    pass
            else:
                if len(rest) == suffix_len:
                    max_suffix = max(max_suffix, int(rest, 36) if rest.isalnum() else -1)

    next_val = max_suffix + 1 if max_suffix >= 0 else 1
    if suffix_type == "numeric":
        suffix = str(next_val).zfill(suffix_len)
    else:
        suffix = _int_to_base36(next_val).zfill(suffix_len)

    return {"prefix": prefix, "next_id": f"{base}{suffix}"}


def _make_prefix_iter(chars: str, start_len: int):
    """Yield prefix candidates in length-first lexicographic order, bounded at
    ``start_len + 2``.  Unlike ``itertools.product(chars, repeat=…)`` this does
    not materialise the full Cartesian product (worst-case 457k tuples)."""
    for length in range(start_len, start_len + 3):
        yield from _product_gen(chars, length)


def _product_gen(chars: str, length: int):
    """Recursive generator over the characters in ``chars``."""
    if length == 0:
        yield ""
        return
    for rest in _product_gen(chars, length - 1):
        for c in chars:
            yield c + rest


def _int_to_base36(n: int) -> str:
    chars = string.digits + string.ascii_lowercase
    if n == 0:
        return "0"
    result = ""
    while n > 0:
        n, r = divmod(n, 36)
        result = chars[r] + result
    return result


@router.get("/projects/{project_id}/requirements")
def list_requirements(
    project_id: str,
    search: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=2000),
):
    store = get_store(project_id)
    # No validate-on-load call here: the store applies it at the cache-fill
    # path, so it covers the evaluator and publisher too and runs once per
    # directory generation rather than once per request.
    reqs = store.list_requirements()
    if search or type or status or priority:
        filters = {k: v for k, v in [("type", type), ("status", status), ("priority", priority)] if v}
        reqs = search_requirements(reqs, search or "", filters)
    total = len(reqs)
    return {"items": reqs[offset:offset + limit], "total": total, "offset": offset, "limit": limit}


@router.get("/projects/{project_id}/requirements/{req_id}")
def get_requirement(project_id: str, req_id: str):
    store = get_store(project_id)
    req = store.get_requirement(req_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Requirement not found")
    # Single-item reads bypass the collection cache (they use the round-trip
    # parser, for read-modify-write), so the guard is applied here instead.
    # Deliberately not inside the store: injecting defaults into the object an
    # edit later writes back would persist them into hand-written YAML.
    checked = validate_on_load("requirements", dict(req))
    if checked is None:
        raise HTTPException(status_code=404, detail="Requirement not found")
    return checked


@router.post("/projects/{project_id}/requirements", status_code=201)
def create_requirement(project_id: str, data: RequirementCreate, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    safe_id(data.id, "requirement id")
    if store.get_requirement(data.id):
        raise HTTPException(status_code=409, detail="Requirement already exists")
    req_dict = data.model_dump(mode="json")
    req_dict.setdefault("attributes", [])
    req_dict.setdefault("relations", [])
    req_dict.setdefault("verification_cases", [])
    req_dict.setdefault("verification_status", "pending")
    result = store.create_requirement(req_dict)
    record_change(store, data.id, "create", None, result, user.get("username", ""))
    return result


@router.put("/projects/{project_id}/requirements/{req_id}")
def update_requirement(project_id: str, req_id: str, data: RequirementUpdate, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    update_dict = data.model_dump(mode="json", exclude_unset=True)

    before = store.get_requirement(req_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Requirement not found")

    # Reparenting must not create a loop: nothing prevented A.parent=B and
    # B.parent=A, which made both (and everything under them) unreachable in
    # the tree and sent the old recursive walk in circles.
    if "parent" in update_dict and update_dict["parent"]:
        new_parent = update_dict["parent"]
        if new_parent == req_id:
            raise HTTPException(status_code=400, detail="A requirement cannot be its own parent")
        parent_of = {r["id"]: r.get("parent") for r in store.list_requirements()}
        parent_of[req_id] = new_parent
        seen, cursor = {req_id}, new_parent
        while cursor:
            if cursor in seen:
                raise HTTPException(
                    status_code=400,
                    detail=f"Setting parent to {new_parent} would create a parent cycle",
                )
            seen.add(cursor)
            cursor = parent_of.get(cursor)

    result = store.update_requirement(req_id, update_dict)
    if result is None:
        raise HTTPException(status_code=404, detail="Requirement not found")
    record_change(store, req_id, "update", before, result, user.get("username", ""))

    propagated_fields = {"name", "description", "priority", "status", "type", "verification_method", "rationale", "source", "allocated_to"}
    has_propagation = any(k in update_dict for k in propagated_fields)
    if has_propagation and result.get("cascade_from") is None:
        # Only the fields that actually changed. Writing back the whole `r`
        # snapshot re-applied every field as it looked *before* this request,
        # clobbering any concurrent edit to the child — the per-file lock can't
        # help when the stale data is already in the payload.
        patch = {f: update_dict[f] for f in propagated_fields if f in update_dict}
        changed = False
        # Walk transitively with a visited set: a REQ → C1 → C2 chain used to
        # stop at C1, leaving C2 permanently stale.
        all_reqs = store.list_requirements()
        children_of: dict[str, list[dict]] = {}
        for r in all_reqs:
            src = r.get("cascade_from")
            if src:
                children_of.setdefault(src, []).append(r)

        seen: set[str] = {req_id}
        queue = list(children_of.get(req_id, []))
        while queue:
            child = queue.pop(0)
            cid = child["id"]
            if cid in seen:
                continue
            seen.add(cid)
            child_before = dict(child)
            updated_child = store.update_requirement(cid, patch)
            if updated_child is not None:
                record_change(store, cid, "update", child_before, updated_child,
                              user.get("username", ""))
                changed = True
            queue.extend(children_of.get(cid, []))
        if changed:
            return {"cascaded": True, **result}
    return result


@router.delete("/projects/{project_id}/requirements/{req_id}")
def delete_requirement(project_id: str, req_id: str, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    before = store.get_requirement(req_id)
    if not store.delete_requirement(req_id):
        raise HTTPException(status_code=404, detail="Requirement not found")
    record_change(store, req_id, "delete", before, None, user.get("username", ""))
    return {"ok": True}


# ── Cascade Operations ───────────────────────────────────────────────────────

@router.post("/projects/{project_id}/requirements/{req_id}/cascade")
def cascade_requirement(project_id: str, req_id: str, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    source = store.get_requirement(req_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Requirement not found")

    all_reqs = store.list_requirements()
    cascade_fields = ["name", "description", "priority", "status", "type", "verification_method"]

    created = []
    for child in all_reqs:
        if child.get("parent") == req_id and child.get("cascade_from") is None:
            new_id = f"{req_id}-C-{uuid.uuid4().hex[:6].upper()}"
            new_req = {k: source[k] for k in cascade_fields}
            new_req["id"] = new_id
            new_req["parent"] = child["id"]
            new_req["cascade_from"] = req_id
            new_req["attributes"] = []
            new_req["relations"] = [{"type": "derives", "target": req_id}]
            new_req["verification_cases"] = []
            new_req["verification_status"] = "pending"
            store.create_requirement(new_req)
            record_change(store, new_id, "create", None, new_req, user.get("username", ""))
            created.append(new_id)

    if not created:
        raise HTTPException(status_code=400, detail="No child groups to cascade to")

    return {"cascaded": True, "created": created, "source": req_id}


@router.post("/projects/{project_id}/requirements/{req_id}/break-cascade")
def break_cascade(project_id: str, req_id: str, data: BreakCascade | None = None, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    req = store.get_requirement(req_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Requirement not found")
    if not req.get("cascade_from"):
        raise HTTPException(status_code=400, detail="Not a cascaded requirement")

    break_children = data.break_children if data else False
    source_id = req["cascade_from"]

    req["cascade_from"] = None
    store.update_requirement(req_id, req)

    if break_children:
        for r in store.list_requirements():
            if r.get("cascade_from") == req_id:
                r["cascade_from"] = None
                store.update_requirement(r["id"], r)

    return {"broken": True, "id": req_id, "was_cascaded_from": source_id}


# ── Specifications ───────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/specifications")
def list_specifications(
    project_id: str,
    offset: Optional[int] = Query(None, ge=0),
    limit: Optional[int] = Query(None, ge=1, le=2000),
):
    store = get_store(project_id)
    items = store.list_specifications()
    if offset is None and limit is None:
        return items[:2000]
    off = offset or 0
    lim = limit or 500
    total = len(items)
    return {"items": items[off:off + lim], "total": total, "offset": off, "limit": lim}


@router.get("/projects/{project_id}/specifications/{spec_id}")
def get_specification(project_id: str, spec_id: str):
    store = get_store(project_id)
    spec = store.get_specification(spec_id)
    if spec is None:
        raise HTTPException(status_code=404, detail="Specification not found")
    return spec


@router.post("/projects/{project_id}/specifications", status_code=201)
def create_specification(project_id: str, data: SpecificationCreate, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    safe_id(data.id, "specification id")
    if store.get_specification(data.id):
        raise HTTPException(status_code=409, detail="Specification already exists")
    spec_dict = data.model_dump(mode="json")
    spec_dict.setdefault("requirements", [])
    spec_dict.setdefault("children", [])
    result = store.create_specification(spec_dict)
    record_change(store, result["id"], "create", None, result, user.get("username", ""))
    return result


@router.put("/projects/{project_id}/specifications/{spec_id}")
def update_specification(project_id: str, spec_id: str, data: SpecificationUpdate, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    before = store.get_specification(spec_id)
    update_dict = data.model_dump(mode="json", exclude_unset=True)
    result = store.update_specification(spec_id, update_dict)
    if result is None:
        raise HTTPException(status_code=404, detail="Specification not found")
    record_change(store, spec_id, "update", before, result, user.get("username", ""))
    return result


@router.delete("/projects/{project_id}/specifications/{spec_id}")
def delete_specification(project_id: str, spec_id: str, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    before = store.get_specification(spec_id)
    if not store.delete_specification(spec_id):
        raise HTTPException(status_code=404, detail="Specification not found")
    record_change(store, spec_id, "delete", before, None, user.get("username", ""))
    return {"ok": True}


# ── Baselines ──────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/baselines")
def list_baselines(project_id: str):
    store = get_store(project_id)
    meta = store.read_meta()
    defs = normalize_baseline_defs(meta.get("baselines", []))
    # Aggregate requirements per baseline from their .baselines arrays
    baselines: dict[str, list[str]] = {}
    for r in store.list_requirements():
        for bl in (r.get("baselines") or []):
            if bl:
                baselines.setdefault(bl, []).append(r["id"])
    # Also surface baseline definitions that have no requirements yet
    seen = set()
    result = []
    for d in defs:
        name = d["name"]
        reqs = baselines.get(name, [])
        # A name that can't be a filename can't have a frozen snapshot. Checked
        # rather than passed to get_item, which raises 400 and would take the
        # whole listing down for one bad entry — _meta.yaml is hand-editable
        # and reachable by git pull, so this can arrive without the API.
        frozen = store.get_item("baselines", name) if is_safe_id(name) else None
        result.append({
            "name": name,
            "symbol": d["symbol"],
            "description": d["description"],
            "requirements": reqs,
            "count": len(reqs),
            "frozen": frozen is not None,
            "frozen_at": (frozen or {}).get("frozen_at", ""),
            "frozen_count": len((frozen or {}).get("snapshot", {})),
        })
        seen.add(name)
    for name, reqs in baselines.items():
        if name not in seen:
            result.append({
                "name": name, "symbol": "", "description": "",
                "requirements": reqs, "count": len(reqs),
                "frozen": False, "frozen_at": "", "frozen_count": 0,
            })
    return sorted(result, key=lambda x: x["name"])


@router.post("/projects/{project_id}/baselines")
def create_baseline(project_id: str, data: BaselineCreate, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    name = safe_id(data.name, "baseline name")
    # Upsert the baseline definition into project metadata
    meta = store.read_meta()
    defs = normalize_baseline_defs(meta.get("baselines", []))
    existing = next((d for d in defs if d["name"] == name), None)
    if existing:
        existing["symbol"] = data.symbol or existing["symbol"]
        existing["description"] = data.description or existing["description"]
    else:
        defs.append({"name": name, "symbol": data.symbol, "description": data.description})
    serialized = [{k: v for k, v in d.items() if k == "name" or v} for d in defs]
    meta["baselines"] = serialized
    store.write_meta(meta)
    # Assign the baseline to specified requirements
    updated = 0
    for req_id in data.requirements:
        req = store.get_requirement(req_id)
        if req is None:
            continue
        blist = list(req.get("baselines") or [])
        if name not in blist:
            blist.append(name)
            if store.update_requirement(req_id, {"baselines": blist}):
                updated += 1
    return {"name": name, "symbol": data.symbol, "description": data.description,
            "requirements_assigned": updated}


@router.patch("/projects/{project_id}/baselines/{name}")
def rename_baseline(project_id: str, name: str, data: RenameBaseline, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    safe_id(name, "baseline name")
    new_name = data.name
    if not new_name:
        raise HTTPException(status_code=400, detail="New name is required")
    safe_id(new_name, "baseline name")
    if store.get_item("baselines", new_name) is not None:
        raise HTTPException(status_code=409, detail="A baseline with that name already exists")
    # Update the baseline definition in project metadata
    meta = store.read_meta()
    defs = normalize_baseline_defs(meta.get("baselines", []))
    for d in defs:
        if d["name"] == name:
            d["name"] = new_name
            if data.symbol is not None:
                d["symbol"] = data.symbol
            if data.description is not None:
                d["description"] = data.description
    serialized = [{k: v for k, v in d.items() if k == "name" or v} for d in defs]
    meta["baselines"] = serialized
    store.write_meta(meta)
    # Rename on all requirements
    updated = 0
    for r in store.list_requirements():
        blist = list(r.get("baselines") or [])
        if name in blist:
            blist = [new_name if b == name else b for b in blist]
            store.update_requirement(r["id"], {"baselines": blist})
            updated += 1
    frozen = store.get_item("baselines", name)
    if frozen is not None:
        frozen["name"] = new_name
        if data.symbol is not None:
            frozen["symbol"] = data.symbol
        if data.description is not None:
            frozen["description"] = data.description
        store.write_item("baselines", new_name, frozen)
        store.delete_item("baselines", name)
    elif updated == 0:
        raise HTTPException(status_code=404, detail="Baseline not found")
    return {"old_name": name, "new_name": new_name, "requirements_updated": updated}


@router.delete("/projects/{project_id}/baselines/{name}")
def delete_baseline(project_id: str, name: str, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    store.delete_item("baselines", name)
    # Remove the baseline definition from project metadata
    meta = store.read_meta()
    defs = normalize_baseline_defs(meta.get("baselines", []))
    defs = [d for d in defs if d["name"] != name]
    serialized = [{k: v for k, v in d.items() if k == "name" or v} for d in defs]
    meta["baselines"] = serialized
    store.write_meta(meta)
    updated = 0
    for r in store.list_requirements():
        blist = list(r.get("baselines") or [])
        if name in blist:
            blist.remove(name)
            store.update_requirement(r["id"], {"baselines": blist})
            updated += 1
    return {"name": name, "requirements_cleared": updated}


# ── Parametric definitions (reusable constraint / calc defs) ─────────────────

@router.get("/projects/{project_id}/definitions")
def list_definitions(
    project_id: str,
    offset: Optional[int] = Query(None, ge=0),
    limit: Optional[int] = Query(None, ge=1, le=2000),
):
    store = get_store(project_id)
    items = store.list_items("definitions")
    if offset is None and limit is None:
        return items[:2000]
    off = offset or 0
    lim = limit or 500
    total = len(items)
    return {"items": items[off:off + lim], "total": total, "offset": off, "limit": lim}


@router.post("/projects/{project_id}/definitions", status_code=201)
def create_definition(project_id: str, data: DefinitionCreate, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    def_id = safe_id(data.id, "definition id")
    if store.get_item("definitions", def_id) is not None:
        raise HTTPException(status_code=409, detail="A definition with that id already exists")
    item = data.model_dump()
    item["id"] = def_id
    return store.write_item("definitions", def_id, item)


@router.put("/projects/{project_id}/definitions/{def_id}")
def update_definition(project_id: str, def_id: str, data: DefinitionUpdate, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    existing = store.get_item("definitions", def_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Definition not found")
    existing.update({k: v for k, v in data.model_dump().items() if v is not None})
    return store.write_item("definitions", def_id, existing)


@router.delete("/projects/{project_id}/definitions/{def_id}")
def delete_definition(project_id: str, def_id: str, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    store.delete_item("definitions", def_id)
    return {"ok": True}


# ── Analysis cases (scoped, parameterised evaluation) ────────────────────────

@router.get("/projects/{project_id}/analysis")
def list_analysis_cases(
    project_id: str,
    offset: Optional[int] = Query(None, ge=0),
    limit: Optional[int] = Query(None, ge=1, le=2000),
):
    store = get_store(project_id)
    items = store.list_items("analysis_cases")
    if offset is None and limit is None:
        return items[:2000]
    off = offset or 0
    lim = limit or 500
    total = len(items)
    return {"items": items[off:off + lim], "total": total, "offset": off, "limit": lim}


@router.post("/projects/{project_id}/analysis", status_code=201)
def create_analysis_case(project_id: str, data: AnalysisCaseCreate, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    case_id = safe_id(data.id, "analysis case id")
    if store.get_item("analysis_cases", case_id) is not None:
        raise HTTPException(status_code=409, detail="An analysis case with that id already exists")
    item = data.model_dump()
    item["id"] = case_id
    return store.write_item("analysis_cases", case_id, item)


@router.put("/projects/{project_id}/analysis/{case_id}")
def update_analysis_case(project_id: str, case_id: str, data: AnalysisCaseUpdate, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    existing = store.get_item("analysis_cases", case_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Analysis case not found")
    existing.update({k: v for k, v in data.model_dump().items() if v is not None})
    return store.write_item("analysis_cases", case_id, existing)


@router.delete("/projects/{project_id}/analysis/{case_id}")
def delete_analysis_case(project_id: str, case_id: str, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    store.delete_item("analysis_cases", case_id)
    return {"ok": True}


@router.get("/projects/{project_id}/analysis/{case_id}/run")
def run_analysis_case_endpoint(project_id: str, case_id: str):
    store = get_store(project_id)
    case = store.get_item("analysis_cases", case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Analysis case not found")
    from app.services.evaluation import run_analysis_case
    return run_analysis_case(store, case)


# ── Verification Cases ───────────────────────────────────────────────────────

@router.get("/projects/{project_id}/verification")
def list_verification_cases(
    project_id: str,
    offset: Optional[int] = Query(None, ge=0),
    limit: Optional[int] = Query(None, ge=1, le=2000),
):
    store = get_store(project_id)
    items = store.list_verification_cases()
    if offset is None and limit is None:
        return items[:2000]
    off = offset or 0
    lim = limit or 500
    total = len(items)
    return {"items": items[off:off + lim], "total": total, "offset": off, "limit": lim}


@router.get("/projects/{project_id}/verification/{vc_id}")
def get_verification_case(project_id: str, vc_id: str):
    store = get_store(project_id)
    vc = store.get_verification_case(vc_id)
    if vc is None:
        raise HTTPException(status_code=404, detail="Verification case not found")
    return vc


@router.post("/projects/{project_id}/verification", status_code=201)
def create_verification_case(project_id: str, data: VerificationCaseCreate, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    safe_id(data.id, "verification case id")
    if store.get_verification_case(data.id):
        raise HTTPException(status_code=409, detail="Verification case already exists")
    vc_dict = data.model_dump(mode="json")
    vc_dict.setdefault("status", "pending")
    vc_dict.setdefault("result", None)
    vc_dict.setdefault("verified_requirements", [])
    result = store.create_verification_case(vc_dict)
    record_change(store, result["id"], "create", None, result, user.get("username", ""))
    return result


@router.put("/projects/{project_id}/verification/{vc_id}")
def update_verification_case(project_id: str, vc_id: str, data: VerificationCaseUpdate, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    before = store.get_verification_case(vc_id)
    update_dict = data.model_dump(mode="json", exclude_unset=True)
    result = store.update_verification_case(vc_id, update_dict)
    if result is None:
        raise HTTPException(status_code=404, detail="Verification case not found")
    record_change(store, vc_id, "update", before, result, user.get("username", ""))
    return result


@router.delete("/projects/{project_id}/verification/{vc_id}")
def delete_verification_case(project_id: str, vc_id: str, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    before = store.get_verification_case(vc_id)
    if not store.delete_verification_case(vc_id):
        raise HTTPException(status_code=404, detail="Verification case not found")
    record_change(store, vc_id, "delete", before, None, user.get("username", ""))
    return {"ok": True}


@router.post("/projects/{project_id}/verification/{vc_id}/run")
def run_verification(project_id: str, vc_id: str, data: RunVerification, user: dict = Depends(require_maintain)):
    """Record a test execution run with optional step results and new status."""
    store = get_store(project_id)
    vc = store.get_verification_case(vc_id)
    if vc is None:
        raise HTTPException(status_code=404, detail="Verification case not found")

    from datetime import datetime, timezone
    new_status = data.status
    notes = data.notes
    executed_by = user.get("username", "unknown")
    step_results = data.step_results

    # Update step actual results if provided.
    steps = vc.get("steps") or []
    if step_results and isinstance(step_results, dict):
        for idx_str, actual in step_results.items():
            try:
                idx = int(idx_str)
                if 0 <= idx < len(steps):
                    steps[idx] = {**steps[idx], "actual_result": actual}
            except (ValueError, TypeError):
                pass

    # Append execution record.
    history = vc.get("execution_history") or []
    history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": new_status,
        "notes": notes,
        "executed_by": executed_by,
    })

    update = {
        "status": new_status,
        "result": new_status,
        "steps": steps,
        "execution_history": history,
        "modified": datetime.now(timezone.utc).isoformat(),
    }
    result = store.update_verification_case(vc_id, update)
    return result


# ── Traces ───────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/traces")
def get_traces(project_id: str, response: Response):
    store = get_store(project_id)
    # Handed back so a subsequent PUT can prove it is replacing the document it
    # actually read; see update_traces.
    response.headers["ETag"] = store.traces_version()
    return store.read_traces()


@router.put("/projects/{project_id}/traces")
def update_traces(project_id: str, data: TraceMatrix, response: Response,
                        if_match: Optional[str] = Header(None, alias="If-Match"),
                        user: dict = Depends(require_maintain)):
    """Replace the trace matrix.

    This is a whole-document write driven by a client-side snapshot, so two
    people editing the matrix an hour apart used to mean the later save silently
    erased the earlier one's links (traces have no history entry and no undo).
    Send the ETag from GET as ``If-Match`` to get a 409 instead of a silent
    overwrite; omitting it preserves the old last-writer-wins behaviour for
    existing clients.
    """
    store = get_store(project_id)
    store.write_traces(data.model_dump(mode="json"), expected_version=if_match)
    response.headers["ETag"] = store.traces_version()
    return data


# ── Auto UID ──────────────────────────────────────────────────────────────────

def _parse_uid_prefix(req_id: str) -> str | None:
    m = re.match(r"^([A-Z]{4})\d{4}$", req_id or "")
    return m.group(1) if m else None
