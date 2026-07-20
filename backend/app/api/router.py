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
from app.models.requirement import RequirementCreate, RequirementUpdate
from app.models.specification import SpecificationCreate, SpecificationUpdate
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


@router.patch("/projects/{project_id}")
async def update_project_settings(project_id: str, data: ProjectSettings, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    meta = store.read_meta()
    updates = {}
    for field in ("name", "naming", "quality", "workflow", "git"):
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
    return _build_tree(reqs, None)


@router.get("/projects/{project_id}/requirements/next-uid")
async def next_uid(project_id: str, parent: str | None = None):
    store = get_store(project_id)
    reqs = store.list_requirements()

    prefix = None
    if parent:
        parent_req = store.get_requirement(parent)
        if parent_req:
            prefix = _parse_uid_prefix(parent_req["id"])
            if not prefix:
                m = re.match(r"([A-Z]{4})", parent_req["id"])
                prefix = m.group(1) if m else parent_req["id"][:4].upper()

    if not prefix:
        used = {r["id"][:4].upper() for r in reqs if r.get("id")}
        prefix = next(
            ("".join(c) for c in itertools.product(string.ascii_uppercase, repeat=4) if "".join(c) not in used),
            "REQ0",
        )

    max_num = 0
    for r in reqs:
        if _parse_uid_prefix(r["id"]) == prefix:
            max_num = max(max_num, int(r["id"][4:]))
    return {"prefix": prefix, "next_id": f"{prefix}{max_num + 1:04d}"}


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
async def update_requirement(project_id: str, req_id: str, data: RequirementUpdate, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    update_dict = data.model_dump(mode="json", exclude_unset=True)

    before = store.get_requirement(req_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Requirement not found")

    # Validate workflow transition if status is changing.
    if "status" in update_dict and before.get("status") != update_dict["status"]:
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
async def list_specifications(project_id: str):
    store = get_store(project_id)
    return store.list_specifications()


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
        bl = r.get("baseline")
        if bl:
            baselines.setdefault(bl, []).append(r["id"])
    return [{"name": k, "requirements": v, "count": len(v)} for k, v in sorted(baselines.items())]


@router.post("/projects/{project_id}/baselines")
async def create_baseline(project_id: str, data: BaselineCreate, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    name = safe_id(data.name, "baseline name")
    updated = 0
    for req_id in data.requirements:
        if store.update_requirement(req_id, {"baseline": name}):
            updated += 1
    return {"name": name, "requirements_assigned": updated}


@router.patch("/projects/{project_id}/baselines/{name}")
async def rename_baseline(project_id: str, name: str, data: dict, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    safe_id(name, "baseline name")
    new_name = data.get("name")
    if not new_name:
        raise HTTPException(status_code=400, detail="New name is required")
    safe_id(new_name, "baseline name")
    if store.get_item("baselines", new_name) is not None:
        raise HTTPException(status_code=409, detail="A baseline with that name already exists")
    updated = 0
    for r in store.list_requirements():
        if r.get("baseline") == name:
            store.update_requirement(r["id"], {"baseline": new_name})
            updated += 1
    # Carry any frozen snapshot across to the new name.
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
        if r.get("baseline") == name:
            store.update_requirement(r["id"], {"baseline": None})
            updated += 1
    return {"name": name, "requirements_cleared": updated}


# ── Verification Cases ───────────────────────────────────────────────────────

@router.get("/projects/{project_id}/verification")
async def list_verification_cases(project_id: str):
    store = get_store(project_id)
    return store.list_verification_cases()


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


# ── Requirement Tree ──────────────────────────────────────────────────────────

def _build_tree(reqs: list[dict], parent_id: str | None) -> list[dict]:
    children = []
    for req in reqs:
        if req.get("parent") == parent_id:
            children.append({
                "id": req["id"],
                "name": req.get("name", ""),
                "type": req.get("type", "functional"),
                "status": req.get("status", "proposed"),
                "priority": req.get("priority", "medium"),
                "children": _build_tree(reqs, req["id"]),
            })
    return children


# ── Auto UID ──────────────────────────────────────────────────────────────────

def _parse_uid_prefix(req_id: str) -> str | None:
    m = re.match(r"^([A-Z]{4})\d{4}$", req_id or "")
    return m.group(1) if m else None
