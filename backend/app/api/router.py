from __future__ import annotations

import itertools
import re
import string
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Depends
from pydantic import BaseModel

from app.core.dependencies import get_store, require_edit, require_admin
from app.core.ids import safe_id
from app.core.tree_utils import build_flat_tree
from app.models.requirement import RequirementCreate, RequirementUpdate
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


class BaselineCreate(BaseModel):
    name: str
    requirements: list[str] = []


class RunVerification(BaseModel):
    status: str
    notes: str = ""
    step_results: dict[str, str] | None = None


class BreakCascade(BaseModel):
    break_children: bool = False

class RenameBaseline(BaseModel):
    name: str


router = APIRouter()


@router.get("/version")
async def api_version():
    """Build metadata for this instance (also served at /version for probes)."""
    from app.core.version import get_build_info
    return get_build_info()


# ── Projects ────────────────────────────────────────────────────────────────

@router.get("/projects")
async def list_projects():
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
async def create_project(data: ProjectCreate, user: dict = Depends(require_edit)):
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
async def get_project(project_id: str, authorization: Optional[str] = Header(None)):
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
        "baselines": meta.get("baselines", []),
    }
    # Git settings can hold a credentialed remote URL, so unlike the rest of
    # the project metadata they are only shown to signed-in editors.
    if authorization and authorization.startswith("Bearer "):
        from app.core.auth import get_user_from_token
        user = get_user_from_token(authorization.removeprefix("Bearer "))
        if user and user.get("role") in ("editor", "admin"):
            out["git"] = meta.get("git", {})
    return out


class ProjectSettings(BaseModel):
    name: Optional[str] = None
    naming: Optional[dict] = None
    quality: Optional[dict] = None
    workflow: Optional[dict] = None
    git: Optional[dict] = None
    baselines: Optional[list[str]] = None


@router.patch("/projects/{project_id}")
async def update_project_settings(project_id: str, data: ProjectSettings, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    meta = store.read_meta()
    updates = {}
    for field in ("name", "naming", "quality", "workflow", "git", "baselines"):
        val = getattr(data, field, None)
        if val is not None:
            updates[field] = val
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    meta.update(updates)
    store.write_meta(meta)
    return meta


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str, user: dict = Depends(require_admin)):
    import shutil

    store = get_store(project_id)
    shutil.rmtree(store.root)
    return {"ok": True}


@router.get("/projects/{project_id}/workflow")
async def get_workflow_config(project_id: str):
    """Return the project's workflow configuration (states, transitions, default)."""
    store = get_store(project_id)
    from app.services.workflow import get_workflow
    return get_workflow(store.read_meta())


# ── Requirements ─────────────────────────────────────────────────────────────
# NOTE: static paths (tree, next-uid) must be registered before the
# /requirements/{req_id} route or they are shadowed by it.

@router.get("/projects/{project_id}/requirements/tree")
async def get_requirement_tree(project_id: str):
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
async def next_uid(project_id: str, parent: str | None = None):
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
            chars = string.ascii_uppercase if prefix_type == "alpha" else string.ascii_uppercase + string.digits
            prefix = None
            for length in range(prefix_len, prefix_len + 3):
                for combo in itertools.product(chars, repeat=length):
                    candidate = "".join(combo)
                    if candidate not in used:
                        prefix = candidate
                        break
                if prefix:
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
async def list_requirements(
    project_id: str,
    search: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=2000),
):
    store = get_store(project_id)
    reqs = store.list_requirements()
    if search or type or status or priority:
        filters = {k: v for k, v in [("type", type), ("status", status), ("priority", priority)] if v}
        reqs = search_requirements(reqs, search or "", filters)
    total = len(reqs)
    return {"items": reqs[offset:offset + limit], "total": total, "offset": offset, "limit": limit}


@router.get("/projects/{project_id}/requirements/{req_id}")
async def get_requirement(project_id: str, req_id: str):
    store = get_store(project_id)
    req = store.get_requirement(req_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Requirement not found")
    return req


@router.post("/projects/{project_id}/requirements", status_code=201)
async def create_requirement(project_id: str, data: RequirementCreate, user: dict = Depends(require_edit)):
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
async def update_requirement(project_id: str, req_id: str, data: RequirementUpdate, user: dict = Depends(require_edit), skip_workflow: bool = Query(False)):
    store = get_store(project_id)
    update_dict = data.model_dump(mode="json", exclude_unset=True)

    before = store.get_requirement(req_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Requirement not found")

    # Validate workflow transition if status is changing (skip for undo).
    if not skip_workflow and "status" in update_dict and before.get("status") != update_dict["status"]:
        from app.services.workflow import validate_transition
        meta = store.read_meta()
        err = validate_transition(meta, before.get("status", "proposed"), update_dict["status"])
        if err:
            raise HTTPException(status_code=400, detail=err)

    result = store.update_requirement(req_id, update_dict)
    if result is None:
        raise HTTPException(status_code=404, detail="Requirement not found")
    record_change(store, req_id, "update", before, result, user.get("username", ""))

    propagated_fields = {"name", "description", "priority", "status", "type", "verification_method", "rationale", "source", "allocated_to"}
    has_propagation = any(k in update_dict for k in propagated_fields)
    if has_propagation and result.get("cascade_from") is None:
        changed = False
        for r in store.list_requirements():
            if r.get("cascade_from") == req_id:
                child_before = dict(r)
                for field in propagated_fields:
                    if field in update_dict:
                        r[field] = update_dict[field]
                store.update_requirement(r["id"], r)
                record_change(store, r["id"], "update", child_before, r, user.get("username", ""))
                changed = True
        if changed:
            return {"cascaded": True, **result}
    return result


@router.delete("/projects/{project_id}/requirements/{req_id}")
async def delete_requirement(project_id: str, req_id: str, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    before = store.get_requirement(req_id)
    if not store.delete_requirement(req_id):
        raise HTTPException(status_code=404, detail="Requirement not found")
    record_change(store, req_id, "delete", before, None, user.get("username", ""))
    return {"ok": True}


# ── Cascade Operations ───────────────────────────────────────────────────────

@router.post("/projects/{project_id}/requirements/{req_id}/cascade")
async def cascade_requirement(project_id: str, req_id: str, user: dict = Depends(require_edit)):
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
async def break_cascade(project_id: str, req_id: str, data: BreakCascade | None = None, user: dict = Depends(require_edit)):
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
async def list_specifications(
    project_id: str,
    offset: Optional[int] = Query(None, ge=0),
    limit: Optional[int] = Query(None, ge=1, le=2000),
):
    store = get_store(project_id)
    items = store.list_specifications()
    if offset is None and limit is None:
        return items
    off = offset or 0
    lim = limit or 500
    total = len(items)
    return {"items": items[off:off + lim], "total": total, "offset": off, "limit": lim}


@router.get("/projects/{project_id}/specifications/{spec_id}")
async def get_specification(project_id: str, spec_id: str):
    store = get_store(project_id)
    spec = store.get_specification(spec_id)
    if spec is None:
        raise HTTPException(status_code=404, detail="Specification not found")
    return spec


@router.post("/projects/{project_id}/specifications", status_code=201)
async def create_specification(project_id: str, data: SpecificationCreate, user: dict = Depends(require_edit)):
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
async def update_specification(project_id: str, spec_id: str, data: SpecificationUpdate, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    before = store.get_specification(spec_id)
    update_dict = data.model_dump(mode="json", exclude_unset=True)
    result = store.update_specification(spec_id, update_dict)
    if result is None:
        raise HTTPException(status_code=404, detail="Specification not found")
    record_change(store, spec_id, "update", before, result, user.get("username", ""))
    return result


@router.delete("/projects/{project_id}/specifications/{spec_id}")
async def delete_specification(project_id: str, spec_id: str, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    before = store.get_specification(spec_id)
    if not store.delete_specification(spec_id):
        raise HTTPException(status_code=404, detail="Specification not found")
    record_change(store, spec_id, "delete", before, None, user.get("username", ""))
    return {"ok": True}


# ── Baselines ──────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/baselines")
async def list_baselines(project_id: str):
    store = get_store(project_id)
    baselines: dict[str, list[str]] = {}
    for r in store.list_requirements():
        for bl in (r.get("baselines") or []):
            if bl:
                baselines.setdefault(bl, []).append(r["id"])
    return [{"name": k, "requirements": v, "count": len(v)} for k, v in sorted(baselines.items())]


@router.post("/projects/{project_id}/baselines")
async def create_baseline(project_id: str, data: BaselineCreate, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    name = safe_id(data.name, "baseline name")
    updated = 0
    for req_id in data.requirements:
        req = store.get_requirement(req_id)
        if req is None:
            continue
        baselines = list(req.get("baselines") or [])
        if name not in baselines:
            baselines.append(name)
            if store.update_requirement(req_id, {"baselines": baselines}):
                updated += 1
    return {"name": name, "requirements_assigned": updated}


@router.patch("/projects/{project_id}/baselines/{name}")
async def rename_baseline(project_id: str, name: str, data: RenameBaseline, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    safe_id(name, "baseline name")
    new_name = data.name
    if not new_name:
        raise HTTPException(status_code=400, detail="New name is required")
    safe_id(new_name, "baseline name")
    if store.get_item("baselines", new_name) is not None:
        raise HTTPException(status_code=409, detail="A baseline with that name already exists")
    updated = 0
    for r in store.list_requirements():
        baselines = list(r.get("baselines") or [])
        if name in baselines:
            baselines = [new_name if b == name else b for b in baselines]
            store.update_requirement(r["id"], {"baselines": baselines})
            updated += 1
    frozen = store.get_item("baselines", name)
    if frozen is not None:
        frozen["name"] = new_name
        store.write_item("baselines", new_name, frozen)
        store.delete_item("baselines", name)
    elif updated == 0:
        raise HTTPException(status_code=404, detail="Baseline not found")
    return {"old_name": name, "new_name": new_name, "requirements_updated": updated}


@router.delete("/projects/{project_id}/baselines/{name}")
async def delete_baseline(project_id: str, name: str, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    store.delete_item("baselines", name)
    updated = 0
    for r in store.list_requirements():
        baselines = list(r.get("baselines") or [])
        if name in baselines:
            baselines.remove(name)
            store.update_requirement(r["id"], {"baselines": baselines})
            updated += 1
    return {"name": name, "requirements_cleared": updated}


# ── Parametric definitions (reusable constraint / calc defs) ─────────────────

@router.get("/projects/{project_id}/definitions")
async def list_definitions(
    project_id: str,
    offset: Optional[int] = Query(None, ge=0),
    limit: Optional[int] = Query(None, ge=1, le=2000),
):
    store = get_store(project_id)
    items = store.list_items("definitions")
    if offset is None and limit is None:
        return items
    off = offset or 0
    lim = limit or 500
    total = len(items)
    return {"items": items[off:off + lim], "total": total, "offset": off, "limit": lim}


@router.post("/projects/{project_id}/definitions", status_code=201)
async def create_definition(project_id: str, data: DefinitionCreate, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    def_id = safe_id(data.id, "definition id")
    if store.get_item("definitions", def_id) is not None:
        raise HTTPException(status_code=409, detail="A definition with that id already exists")
    item = data.model_dump()
    item["id"] = def_id
    return store.write_item("definitions", def_id, item)


@router.put("/projects/{project_id}/definitions/{def_id}")
async def update_definition(project_id: str, def_id: str, data: DefinitionUpdate, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    existing = store.get_item("definitions", def_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Definition not found")
    existing.update({k: v for k, v in data.model_dump().items() if v is not None})
    return store.write_item("definitions", def_id, existing)


@router.delete("/projects/{project_id}/definitions/{def_id}")
async def delete_definition(project_id: str, def_id: str, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    store.delete_item("definitions", def_id)
    return {"ok": True}


# ── Analysis cases (scoped, parameterised evaluation) ────────────────────────

@router.get("/projects/{project_id}/analysis")
async def list_analysis_cases(
    project_id: str,
    offset: Optional[int] = Query(None, ge=0),
    limit: Optional[int] = Query(None, ge=1, le=2000),
):
    store = get_store(project_id)
    items = store.list_items("analysis_cases")
    if offset is None and limit is None:
        return items
    off = offset or 0
    lim = limit or 500
    total = len(items)
    return {"items": items[off:off + lim], "total": total, "offset": off, "limit": lim}


@router.post("/projects/{project_id}/analysis", status_code=201)
async def create_analysis_case(project_id: str, data: AnalysisCaseCreate, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    case_id = safe_id(data.id, "analysis case id")
    if store.get_item("analysis_cases", case_id) is not None:
        raise HTTPException(status_code=409, detail="An analysis case with that id already exists")
    item = data.model_dump()
    item["id"] = case_id
    return store.write_item("analysis_cases", case_id, item)


@router.put("/projects/{project_id}/analysis/{case_id}")
async def update_analysis_case(project_id: str, case_id: str, data: AnalysisCaseUpdate, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    existing = store.get_item("analysis_cases", case_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Analysis case not found")
    existing.update({k: v for k, v in data.model_dump().items() if v is not None})
    return store.write_item("analysis_cases", case_id, existing)


@router.delete("/projects/{project_id}/analysis/{case_id}")
async def delete_analysis_case(project_id: str, case_id: str, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    store.delete_item("analysis_cases", case_id)
    return {"ok": True}


@router.get("/projects/{project_id}/analysis/{case_id}/run")
async def run_analysis_case_endpoint(project_id: str, case_id: str):
    store = get_store(project_id)
    case = store.get_item("analysis_cases", case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Analysis case not found")
    from app.services.evaluation import run_analysis_case
    return run_analysis_case(store, case)


# ── Verification Cases ───────────────────────────────────────────────────────

@router.get("/projects/{project_id}/verification")
async def list_verification_cases(
    project_id: str,
    offset: Optional[int] = Query(None, ge=0),
    limit: Optional[int] = Query(None, ge=1, le=2000),
):
    store = get_store(project_id)
    items = store.list_verification_cases()
    if offset is None and limit is None:
        return items
    off = offset or 0
    lim = limit or 500
    total = len(items)
    return {"items": items[off:off + lim], "total": total, "offset": off, "limit": lim}


@router.get("/projects/{project_id}/verification/{vc_id}")
async def get_verification_case(project_id: str, vc_id: str):
    store = get_store(project_id)
    vc = store.get_verification_case(vc_id)
    if vc is None:
        raise HTTPException(status_code=404, detail="Verification case not found")
    return vc


@router.post("/projects/{project_id}/verification", status_code=201)
async def create_verification_case(project_id: str, data: VerificationCaseCreate, user: dict = Depends(require_edit)):
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
async def update_verification_case(project_id: str, vc_id: str, data: VerificationCaseUpdate, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    before = store.get_verification_case(vc_id)
    update_dict = data.model_dump(mode="json", exclude_unset=True)
    result = store.update_verification_case(vc_id, update_dict)
    if result is None:
        raise HTTPException(status_code=404, detail="Verification case not found")
    record_change(store, vc_id, "update", before, result, user.get("username", ""))
    return result


@router.delete("/projects/{project_id}/verification/{vc_id}")
async def delete_verification_case(project_id: str, vc_id: str, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    before = store.get_verification_case(vc_id)
    if not store.delete_verification_case(vc_id):
        raise HTTPException(status_code=404, detail="Verification case not found")
    record_change(store, vc_id, "delete", before, None, user.get("username", ""))
    return {"ok": True}


@router.post("/projects/{project_id}/verification/{vc_id}/run")
async def run_verification(project_id: str, vc_id: str, data: RunVerification, user: dict = Depends(require_edit)):
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
async def get_traces(project_id: str):
    store = get_store(project_id)
    return store.read_traces()


@router.put("/projects/{project_id}/traces")
async def update_traces(project_id: str, data: TraceMatrix, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    store.write_traces(data.model_dump(mode="json"))
    return data


# ── Auto UID ──────────────────────────────────────────────────────────────────

def _parse_uid_prefix(req_id: str) -> str | None:
    m = re.match(r"^([A-Z]{4})\d{4}$", req_id or "")
    return m.group(1) if m else None
