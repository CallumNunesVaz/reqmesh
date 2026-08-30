from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Depends, Request, Response
from pydantic import BaseModel, ValidationError

from app.core.dependencies import get_store, require_maintain, require_maintain_global, require_admin, require_view
from app.core.filelock import file_lock
from app.core.ids import safe_id
from app.core.rate_limit import rate_limit
from app.core.tree_utils import build_flat_tree
from app.models.baseline import DUE_DATE_RE
from app.models.requirement import Requirement, RequirementCreate, RequirementUpdate
from app.services.load_guard import is_safe_id, validate_on_load
from app.services.meta_defs import (
    normalize_baseline_defs,
    normalize_stakeholders,
    normalize_system_states,
    serialize_meta_defs,
)
from app.services.rename import matches_scheme, rename_parameter, rename_requirement, suggest_id
from app.services.naming import KINDS, ids_for, next_id as generate_next_id
from app.api._utils import check_precondition, enforce_naming, paginate
from app.models.specification import SpecificationCreate, SpecificationUpdate
from app.models.definition import DefinitionCreate, DefinitionUpdate
from app.models.analysis import AnalysisCaseCreate, AnalysisCaseUpdate
from app.models.trace import TraceMatrix
from app.models.verification import VerificationCaseCreate, VerificationCaseUpdate
from app.services.yaml_store import YamlStore
from app.services.search import search_requirements
from app.services.history import record_change
from app.services.risk_matrix import normalize_matrix
from app.services.tracing import all_links
from app.services.verification_links import (
    attach as attach_verification_cases,
    sync_from_requirement as sync_verification_from_requirement,
)
from app.services.link_validation import first_missing, first_missing_relation


class ProjectCreate(BaseModel):
    id: str
    name: str


class BaselineDefItem(BaseModel):
    """A baseline definition — name, short symbol, description, and due date."""
    name: str
    symbol: str = ""
    description: str = ""
    due_date: str = ""


def _baseline_def_by_name(baselines: list, name: str) -> dict | None:
    for b in normalize_baseline_defs(baselines):
        if b["name"] == name:
            return b
    return None


def _validate_due_dates(baselines: list) -> None:
    """Validate every due date is ``YYYY-MM-DD`` or ``""`` and the sequence
    is monotonic (non-empty due dates must not go backwards).

    Raises ``HTTPException(400)`` on the first violation.

    The raw input is validated for individual date format/parseability, because
    ``normalize_baseline_defs`` degrades malformed dates on the read path.
    The monotonic check runs on the normalized form so it sees the sequence
    order.
    """
    # Phase 1: validate each individual due_date on the raw input.
    for item in (baselines or []):
        if isinstance(item, str):
            continue
        if not isinstance(item, dict):
            continue
        due = str(item.get("due_date", "") or "").strip()
        if not due:
            continue
        if not DUE_DATE_RE.match(due):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid due date: {due} (expected YYYY-MM-DD)",
            )
        try:
            datetime.date.fromisoformat(due)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid due date: {due} (expected YYYY-MM-DD)",
            ) from None

    # Phase 2: monotonic check on the normalized form which knows the order.
    defs = normalize_baseline_defs(baselines)
    prev_date = None
    prev_name = None
    for d in defs:
        due = d.get("due_date", "")
        if not due:
            continue
        if prev_date is not None and due < prev_date:
            raise HTTPException(
                status_code=400,
                detail=f"Due dates must not go backwards: {d['name']} ({due}) "
                       f"is due before {prev_name} ({prev_date})",
            )
        prev_date = due
        prev_name = d["name"]


class ReorderBaselines(BaseModel):
    names: list[str]


class BaselineCreate(BaseModel):
    name: str
    symbol: str = ""
    description: str = ""
    due_date: str = ""
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
    due_date: Optional[str] = None


router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/version", summary="Build metadata")
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
            projects.append({"id": d.name, "name": meta.get("name", d.name)})
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

    # A project that is not a repository silently discards every auto-commit:
    # auto_commit's is_repo guard returns False, which the caller cannot tell
    # apart from "nothing changed". Initialise it here so the setting means what
    # it says. Failure is not fatal — the project is still usable, just
    # unversioned — but it is logged rather than swallowed.
    if settings.git_autocommit:
        from app.services.git_service import init_repo
        if not init_repo(project_root, username=user.get("username", "")):
            logger.warning("Project %s created without a git repository — "
                           "auto-commit will not record changes", project_id)

    return {"id": project_id, "name": data.name or project_id, "path": str(project_root)}


@router.get("/projects/{project_id}")
def get_project(project_id: str, request: Request,
                      authorization: Optional[str] = Header(None),
                      user: dict = Depends(require_view)):
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
        "stakeholders": normalize_stakeholders(meta.get("stakeholders", [])),
        "system_states": normalize_system_states(meta.get("system_states", [])),
        "risk_matrix": normalize_matrix(meta.get("risk_matrix")),
    }
    # Git settings can hold a credentialed remote URL, so unlike the rest of
    # the project metadata they are only shown to those who manage settings
    # (the edit tier that the settings page itself requires). The check is
    # project-scoped through the same permissions map every other project check
    # uses, so a maintainer demoted to `view` on this project gets the payload
    # minus the `git` key.
    # Resolved through get_current_user so the HttpOnly session cookie counts —
    # checking only the Authorization header stopped working for the UI when
    # auth moved to cookies, silently hiding git settings from maintainers.
    from app.core.dependencies import PERMISSION_LEVELS, get_current_user, user_permission_level
    user = get_current_user(request=request, authorization=authorization)
    if user_permission_level(user, project_id) >= PERMISSION_LEVELS["edit"]:
        out["git"] = meta.get("git", {})
    return out


class ProjectSettings(BaseModel):
    name: Optional[str] = None
    naming: Optional[dict] = None
    quality: Optional[dict] = None
    workflow: Optional[dict] = None
    git: Optional[dict] = None
    baselines: Optional[list] = None  # list of BaselineDefItem-compatible dicts or legacy strings
    stakeholders: Optional[list] = None  # [{name, weight}]; bare strings tolerated
    risk_matrix: Optional[dict] = None  # {severities, likelihoods, bands, cells}
    permissions: Optional[dict] = None


# Single definition, shared with git_service.test_remote — see the note there.
from app.services.git_service import ALLOWED_REMOTE_SCHEMES as _ALLOWED_REMOTE_SCHEMES
from app.services.git_service import REMOTE_SCHEME_ERROR as _REMOTE_SCHEME_ERROR
from app.services.delete_guard import check_deletable
from app.core.filelock import project_lock


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
            detail=_REMOTE_SCHEME_ERROR,
        )


@router.patch("/projects/{project_id}")
def update_project_settings(project_id: str, data: ProjectSettings, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    with store.meta_lock():
        meta = store.read_meta()
        updates = {}
        for field in ("name", "naming", "quality", "workflow", "git", "baselines",
                      "permissions", "stakeholders", "risk_matrix"):
            val = getattr(data, field, None)
            if val is not None:
                updates[field] = val
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        if "git" in updates:
            _guard_git_settings(updates["git"], meta.get("git", {}), user)
        if "baselines" in updates and updates["baselines"] is not None:
            # Validate due dates on the raw input before normalization, which
            # degrades bad dates on the read path. A rejected write must leave
            # _meta.yaml untouched.
            _validate_due_dates(updates["baselines"])
            defs = normalize_baseline_defs(updates["baselines"])
            # Baseline names become filenames when a baseline is frozen
            # (`store.get_item("baselines", name)`), so they need the same
            # validation `create_baseline` applies. Without it this endpoint
            # accepted `../../etc/passwd`, and every later GET /baselines then
            # raised 400 from `_item_path` — breaking the whole listing for the
            # project until someone hand-edited _meta.yaml.
            for d in defs:
                safe_id(d["name"], "baseline name")
            updates["baselines"] = serialize_meta_defs(defs)
        if "stakeholders" in updates and updates["stakeholders"] is not None:
            updates["stakeholders"] = normalize_stakeholders(updates["stakeholders"])
        if "risk_matrix" in updates and updates["risk_matrix"] is not None:
            # Normalized on write as well as on read: a matrix stored with a
            # mis-sized cell grid would silently re-rate risks against fallback
            # bands every time it was read back.
            updates["risk_matrix"] = normalize_matrix(updates["risk_matrix"])
        meta.update(updates)
        store._write_meta_unlocked(meta)
    return meta


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, user: dict = Depends(require_admin)):
    import shutil

    store = get_store(project_id)
    shutil.rmtree(store.root)
    return {"ok": True}


@router.get("/projects/{project_id}/workflow")
def get_workflow_config(project_id: str, user: dict = Depends(require_view)):
    """Return the project's workflow configuration (states, transitions, default)."""
    store = get_store(project_id)
    from app.services.workflow import get_workflow
    return get_workflow(store.read_meta())


# ── Requirements ─────────────────────────────────────────────────────────────
# NOTE: static paths (tree, next-uid) must be registered before the
# /requirements/{req_id} route or they are shadowed by it.

@router.get("/projects/{project_id}/requirements/tree")
def get_requirement_tree(project_id: str, user: dict = Depends(require_view)):
    store = get_store(project_id)
    reqs = store.list_requirements()
    vcs = store.list_verification_cases()
    attach_verification_cases(store, reqs, vcs)
    return build_flat_tree(reqs, project=lambda r: {
        "id": r["id"],
        "name": r.get("name", ""),
        "type": r.get("type", "functional"),
        "status": r.get("status", "proposed"),
        "priority": r.get("priority", "medium"),
    })


@router.post("/projects/{project_id}/requirements/{req_id}/rename", summary="Rename a requirement")
def rename_requirement_route(project_id: str, req_id: str, data: dict,
                             user: dict = Depends(require_maintain)):
    """Rename a requirement, repointing children and references project-wide.

    Registered before the ``/{req_id}`` catch-all for the same reason next-uid
    is: otherwise "rename" is swallowed as a requirement id.

    Without ``new_id`` this only *suggests* one — the parent's prefix and the
    next free slot — so the dialog can prefill without a second endpoint.

    ``cascade`` is ``self`` (default) | ``children`` | ``descendants`` and
    controls how far the new prefix reaches. ``dry_run`` returns the planned
    ``renames`` and the records that would be relinked without writing anything,
    so the dialog can preview each choice before committing.
    """
    store = get_store(project_id)
    req = store.get_requirement(safe_id(req_id, "requirement id"))
    if req is None:
        raise HTTPException(status_code=404, detail="Requirement not found")

    meta = store.read_meta()
    reqs = store.list_requirements()

    new_id = (data.get("new_id") or "").strip()
    if not new_id:
        return {"suggested": suggest_id(reqs, meta, req.get("parent"))}

    new_id = safe_id(new_id, "requirement id")
    reason = matches_scheme(new_id, meta, "requirements")
    if reason:
        raise HTTPException(status_code=400, detail=reason)

    cascade = (data.get("cascade") or "self")
    dry_run = bool(data.get("dry_run"))

    try:
        result = rename_requirement(
            store, req["id"], new_id, user.get("username", ""),
            cascade=cascade, dry_run=dry_run,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.post("/projects/{project_id}/parameters/{owner_id}/rename", summary="Rename a parameter")
def rename_parameter_route(project_id: str, owner_id: str, data: dict,
                           user: dict = Depends(require_maintain)):
    """Rename a parameter, repointing every reference project-wide.

    A parameter is addressed by its owner (a requirement or component id) and
    its current name. Every ``owner.old`` / bare-name reference in expressions
    and every ``[[owner.old]]`` / ``owner.old`` mention in text is rewritten,
    the way the requirement and component renames rewrite their references.
    """
    store = get_store(project_id)
    owner_id = safe_id(owner_id, "owner id")

    old_name = (data.get("old_name") or "").strip()
    new_name = (data.get("new_name") or "").strip()
    if not old_name or not new_name:
        raise HTTPException(status_code=400, detail="old_name and new_name are required")

    try:
        result = rename_parameter(store, owner_id, old_name, new_name,
                                  user.get("username", ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.get("/projects/{project_id}/requirements/next-uid", summary="Next free UID")
def next_uid(project_id: str, parent: str | None = None, user: dict = Depends(require_view)):
    store = get_store(project_id)
    meta = store.read_meta()
    parent_id = None
    if parent:
        parent_req = store.get_requirement(parent)
        if parent_req:
            parent_id = parent_req["id"]
    # Delegate to the shared generator so this legacy path and the generic
    # /{kind}/next-id route cannot disagree about what the next id is.
    return generate_next_id(ids_for(store, "requirements"), meta, "requirements", parent_id)


@router.get("/projects/{project_id}/{kind}/next-id", summary="Next free id for a kind")
def next_id(project_id: str, kind: str, user: dict = Depends(require_view)):
    if kind not in KINDS:
        raise HTTPException(status_code=404, detail=f"Unknown kind: {kind}")
    store = get_store(project_id)
    return generate_next_id(ids_for(store, kind), store.read_meta(), kind)


@router.get("/projects/{project_id}/requirements")
def list_requirements(
    project_id: str,
    search: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=2000),
    user: dict = Depends(require_view),
):
    store = get_store(project_id)
    # No validate-on-load call here: the store applies it at the cache-fill
    # path, so it covers the evaluator and publisher too and runs once per
    # directory generation rather than once per request.
    reqs = store.list_requirements()
    # verification_cases is derived from verification_case.verified_requirements
    # (services/verification_links.py), which owns the relationship.
    attach_verification_cases(store, reqs)
    if search or type or status or priority:
        filters = {k: v for k, v in [("type", type), ("status", status), ("priority", priority)] if v}
        reqs = search_requirements(reqs, search or "", filters)
    total = len(reqs)
    return {"items": reqs[offset:offset + limit], "total": total, "offset": offset, "limit": limit}


@router.get("/projects/{project_id}/requirements/{req_id}")
def get_requirement(project_id: str, req_id: str, user: dict = Depends(require_view)):
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
    attach_verification_cases(store, [checked])
    return checked


@router.post("/projects/{project_id}/requirements", status_code=201)
def create_requirement(project_id: str, data: RequirementCreate, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    safe_id(data.id, "requirement id")
    enforce_naming(store, "requirements", data.id)
    if store.get_requirement(data.id):
        raise HTTPException(status_code=409, detail="Requirement already exists")
    reason = first_missing_relation(store, data.relations)
    if reason:
        raise HTTPException(status_code=400, detail=reason)
    req_dict = data.model_dump(mode="json")
    req_dict.setdefault("attributes", [])
    req_dict.setdefault("relations", [])
    req_dict.setdefault("verification_cases", [])
    req_dict.setdefault("verification_status", "pending")
    result = store.create_requirement(req_dict)
    if req_dict.get("verification_cases"):
        sync_verification_from_requirement(store, data.id, req_dict["verification_cases"])
    attach_verification_cases(store, [result])
    record_change(store, data.id, "create", None, result, user.get("username", ""))
    return result


@router.put("/projects/{project_id}/requirements/{req_id}")
def update_requirement(project_id: str, req_id: str, data: RequirementUpdate,
                       request: Request, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    update_dict = data.model_dump(mode="json", exclude_unset=True)

    before = store.get_requirement(req_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Requirement not found")
    check_precondition(request, before)

    reason = first_missing_relation(store, data.relations)
    if reason:
        raise HTTPException(status_code=400, detail=reason)

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

    # A write arriving on the requirement side is applied to the owning
    # verification cases, so setting the list actually changes the
    # relationship rather than leaving the two sides disagreeing.
    if "verification_cases" in update_dict:
        sync_verification_from_requirement(store, req_id, update_dict["verification_cases"])

    if "status" in update_dict and before.get("status") != update_dict["status"]:
        from app.services.workflow import validate_transition
        err = validate_transition(store.read_meta(),
                                  before.get("status", "proposed"),
                                  update_dict["status"])
        if err:
            raise HTTPException(status_code=409, detail=err)

    result = store.update_requirement(req_id, update_dict)
    if result is None:
        raise HTTPException(status_code=404, detail="Requirement not found")
    attach_verification_cases(store, [result])
    record_change(store, req_id, "update", before, result, user.get("username", ""))

    # verification_method is not propagated: it is derived from the cases that
    # verify each requirement, and a cascaded child has its own cases (usually
    # none yet). Copying the parent's would assert a verification the child has
    # not had.
    propagated_fields = {"name", "description", "priority", "status", "type", "rationale", "source", "allocated_to"}
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

        seen = {req_id}
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
def delete_requirement(project_id: str, req_id: str, force: bool = False, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    with project_lock(store.root):
        check_deletable(store, "requirements", req_id, force)
        before = store.get_requirement(req_id)
        if not store.delete_requirement(req_id):
            raise HTTPException(status_code=404, detail="Requirement not found")
    record_change(store, req_id, "delete", before, None, user.get("username", ""))
    return {"ok": True}


@router.post("/projects/{project_id}/requirements/{req_id}/history/{entry_id}/restore")
def restore_requirement_version(project_id: str, req_id: str, entry_id: str,
                                user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    safe_id(req_id, "requirement id")
    safe_id(entry_id, "entry id")

    history = store.list_history(req_id)
    entry = None
    for h in history:
        if h.get("id") == entry_id:
            entry = h
            break

    if entry is None:
        raise HTTPException(status_code=404, detail="History entry not found")

    if entry.get("action") != "update":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot restore a {entry.get('action')} entry — only update entries can be restored",
        )

    req = store.get_requirement(req_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Requirement not found")

    changes = entry.get("changes", {})
    patch = {}
    for field, diff in changes.items():
        if "before" not in diff:
            continue
        value = diff["before"]
        if value is None:
            # The field did not exist before this change. Writing null back
            # would leave a requirement whose `rationale` is None where every
            # reader expects a string, so restore the model's own empty value.
            model_field = Requirement.model_fields.get(field)
            if model_field is None:
                continue
            value = model_field.get_default(call_default_factory=True)
        patch[field] = value

    if not patch:
        raise HTTPException(status_code=400, detail="No fields to restore")

    # History files are hand-editable and arrive by git pull, so a recorded
    # `before` is not trusted input. The normal PUT validates through this
    # model; a restore that skipped it could write a status no enum allows.
    # Dumping back out in json mode also flattens enum defaults to their plain
    # values — the YAML writer cannot represent an enum member.
    try:
        patch = RequirementUpdate.model_validate(patch).model_dump(mode="json", exclude_unset=True)
    except ValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"History entry holds a value this requirement cannot take: {exc.errors()[0]['msg']}",
        ) from None

    if not patch:
        raise HTTPException(status_code=400, detail="No restorable fields in that entry")

    before = dict(req)
    result = store.update_requirement(req_id, patch)
    if result is None:
        raise HTTPException(status_code=404, detail="Requirement not found")

    attach_verification_cases(store, [result])
    record_change(store, req_id, "update", before, result, user.get("username", ""))
    return result


# ── Cascade Operations ───────────────────────────────────────────────────────

@router.post("/projects/{project_id}/requirements/{req_id}/cascade")
def cascade_requirement(project_id: str, req_id: str, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    source = store.get_requirement(req_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Requirement not found")

    all_reqs = store.list_requirements()
    meta = store.read_meta()
    # See the note on propagated_fields: verification is derived per requirement.
    cascade_fields = ["name", "description", "priority", "status", "type"]

    # `known` grows as copies are allocated so the next suggestion sees the
    # previous one — suggest_id picks the next free slot by scanning the list,
    # and cascading to several child groups allocates several ids in one pass.
    known = list(all_reqs)

    created = []
    for child in all_reqs:
        if child.get("parent") == req_id and child.get("cascade_from") is None:
            # Follow the project's naming scheme rather than a synthetic
            # `{source}-C-{hex}`: a cascaded copy is an ordinary requirement in
            # its group, and the old shape also sanitised into a noisier SysML
            # name on export.
            new_id = suggest_id(known, meta, child["id"])
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
            known.append(new_req)
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
    user: dict = Depends(require_view),
):
    store = get_store(project_id)
    items = store.list_specifications()
    return paginate(items, offset, limit)


@router.get("/projects/{project_id}/specifications/{spec_id}")
def get_specification(project_id: str, spec_id: str, user: dict = Depends(require_view)):
    store = get_store(project_id)
    spec = store.get_specification(spec_id)
    if spec is None:
        raise HTTPException(status_code=404, detail="Specification not found")
    return spec


@router.post("/projects/{project_id}/specifications", status_code=201)
def create_specification(project_id: str, data: SpecificationCreate, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    safe_id(data.id, "specification id")
    enforce_naming(store, "specifications", data.id)
    if store.get_specification(data.id):
        raise HTTPException(status_code=409, detail="Specification already exists")
    spec_dict = data.model_dump(mode="json")
    spec_dict.setdefault("requirements", [])
    spec_dict.setdefault("children", [])
    result = store.create_specification(spec_dict)
    record_change(store, result["id"], "create", None, result, user.get("username", ""))
    return result


@router.put("/projects/{project_id}/specifications/{spec_id}")
def update_specification(project_id: str, spec_id: str, data: SpecificationUpdate,
                         request: Request, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    before = store.get_specification(spec_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Specification not found")
    check_precondition(request, before)
    update_dict = data.model_dump(mode="json", exclude_unset=True)
    with project_lock(store.root):
        reason = first_missing(store, [("requirements", data.requirements)])
        if reason:
            raise HTTPException(status_code=400, detail=reason)
        result = store.update_specification(spec_id, update_dict)
    if result is None:
        raise HTTPException(status_code=404, detail="Specification not found")
    record_change(store, spec_id, "update", before, result, user.get("username", ""))
    return result


@router.delete("/projects/{project_id}/specifications/{spec_id}")
def delete_specification(project_id: str, spec_id: str, force: bool = False, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    with project_lock(store.root):
        check_deletable(store, "specifications", spec_id, force)
        before = store.get_specification(spec_id)
        if not store.delete_specification(spec_id):
            raise HTTPException(status_code=404, detail="Specification not found")
    record_change(store, spec_id, "delete", before, None, user.get("username", ""))
    return {"ok": True}


# ── Baselines ──────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/baselines")
def list_baselines(project_id: str, user: dict = Depends(require_view)):
    store = get_store(project_id)
    meta = store.read_meta()
    defs = normalize_baseline_defs(meta.get("baselines", []))
    # Aggregate requirements per baseline from their .baselines arrays
    baselines: dict[str, list[str]] = {}
    for r in store.list_requirements():
        for bl in (r.get("baselines") or []):
            if bl:
                baselines.setdefault(bl, []).append(r["id"])
    # Aggregate components per baseline from their .baselines arrays
    comp_baselines: dict[str, list[str]] = {}
    for c in store.list_components():
        for bl in (c.get("baselines") or []):
            if bl:
                comp_baselines.setdefault(bl, []).append(c["id"])
    # Also surface baseline definitions that have no requirements yet
    seen = set()
    result = []
    for d in defs:
        name = d["name"]
        reqs = baselines.get(name, [])
        comps = comp_baselines.get(name, [])
        # A name that can't be a filename can't have a frozen snapshot. Checked
        # rather than passed to get_item, which raises 400 and would take the
        # whole listing down for one bad entry — _meta.yaml is hand-editable
        # and reachable by git pull, so this can arrive without the API.
        frozen = store.get_item("baselines", name) if is_safe_id(name) else None
        result.append({
            "name": name,
            "symbol": d["symbol"],
            "description": d["description"],
            "due_date": d["due_date"],
            "order": d["order"],
            "requirements": reqs,
            "count": len(reqs),
            "components": comps,
            "component_count": len(comps),
            "frozen": frozen is not None,
            "frozen_at": (frozen or {}).get("frozen_at", ""),
            "frozen_count": len((frozen or {}).get("snapshot", {})),
            "frozen_component_count": len((frozen or {}).get("component_snapshot", {})),
        })
        seen.add(name)
    for name in set(baselines.keys()) | set(comp_baselines.keys()):
        if name not in seen:
            reqs = baselines.get(name, [])
            comps = comp_baselines.get(name, [])
            result.append({
                "name": name, "symbol": "", "description": "",
                "due_date": "", "order": 0,
                "requirements": reqs, "count": len(reqs),
                "components": comps, "component_count": len(comps),
                "frozen": False, "frozen_at": "", "frozen_count": 0,
                "frozen_component_count": 0,
            })
    # Defined baselines first (sequence order), then undefined orphans sorted by name.
    orphans = [r for r in result if r["order"] == 0]
    orphans.sort(key=lambda x: x["name"])
    defined = [r for r in result if r["order"] != 0]
    return defined + orphans


@router.post("/projects/{project_id}/baselines")
# This is an upsert (creates or updates an existing baseline definition), not a
# pure create, so the status code intentionally stays 200 rather than 201.
def create_baseline(project_id: str, data: BaselineCreate, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    name = safe_id(data.name, "baseline name")
    # Upsert the baseline definition into project metadata.
    with store.meta_lock():
        meta = store.read_meta()
        defs = normalize_baseline_defs(meta.get("baselines", []))
        existing = next((d for d in defs if d["name"] == name), None)
        if existing:
            existing["symbol"] = data.symbol or existing["symbol"]
            existing["description"] = data.description or existing["description"]
            if data.due_date:
                existing["due_date"] = data.due_date
        else:
            defs.append({"name": name, "symbol": data.symbol, "description": data.description,
                         "due_date": data.due_date})
        serialized = serialize_meta_defs(defs)
        # Validate the proposed list before writing — a rejected write must
        # leave _meta.yaml untouched.
        _validate_due_dates(serialized)
        meta["baselines"] = serialized
        store._write_meta_unlocked(meta)
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
            "due_date": data.due_date, "requirements_assigned": updated}


@router.put("/projects/{project_id}/baselines/order")
def reorder_baselines(project_id: str, data: ReorderBaselines, user: dict = Depends(require_maintain)):
    """Rewrite the baseline sequence."""
    store = get_store(project_id)
    with store.meta_lock():
        meta = store.read_meta()
        current_defs = normalize_baseline_defs(meta.get("baselines", []))
        defined_names = [d["name"] for d in current_defs]

        # Must be exactly the same set — a permutation, no duplicates, no missing.
        if set(data.names) != set(defined_names) or len(data.names) != len(defined_names):
            raise HTTPException(
                status_code=400,
                detail="names must list every defined baseline exactly once",
            )

        # Build the new list in the requested order, preserving other fields.
        by_name = {d["name"]: d for d in current_defs}
        # `order` is left alone here: serialize_meta_defs is the one place it is
        # dropped, and duplicating that responsibility is how the derived value and
        # the list position start to disagree.
        reordered = [dict(by_name[nm]) for nm in data.names]

        serialized = serialize_meta_defs(reordered)
        # Validate due dates in the new order before writing.
        _validate_due_dates(serialized)
        meta["baselines"] = serialized
        store._write_meta_unlocked(meta)

    return {"baselines": normalize_baseline_defs(serialized)}


@router.patch("/projects/{project_id}/baselines/{name}")
def rename_baseline(project_id: str, name: str, data: RenameBaseline, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    safe_id(name, "baseline name")
    new_name = data.name
    if not new_name:
        raise HTTPException(status_code=400, detail="New name is required")
    safe_id(new_name, "baseline name")
    # A rename onto an existing frozen snapshot is a collision. Skipped when the
    # name is unchanged, so a symbol/description/due-date edit on a frozen
    # baseline is not refused as a duplicate of itself.
    if new_name != name and store.get_item("baselines", new_name) is not None:
        raise HTTPException(status_code=409, detail="A baseline with that name already exists")
    found = False
    # Update the baseline definition in project metadata.
    with store.meta_lock():
        meta = store.read_meta()
        defs = normalize_baseline_defs(meta.get("baselines", []))
        # A rename onto an existing *unfrozen* definition is also a collision —
        # without this check, renaming onto one would silently merge two
        # definitions under one name.
        if new_name != name and any(d["name"] == new_name for d in defs):
            raise HTTPException(status_code=409, detail="A baseline with that name already exists")
        for d in defs:
            if d["name"] == name:
                found = True
                d["name"] = new_name
                if data.symbol is not None:
                    d["symbol"] = data.symbol
                if data.description is not None:
                    d["description"] = data.description
                if data.due_date is not None:
                    d["due_date"] = data.due_date
        if found:
            serialized = serialize_meta_defs(defs)
            # Validate before writing — a rejected write must leave _meta.yaml untouched.
            _validate_due_dates(serialized)
            meta["baselines"] = serialized
            store._write_meta_unlocked(meta)
    # Rename on all requirements
    updated = 0
    for r in store.list_requirements():
        blist = list(r.get("baselines") or [])
        if name in blist:
            blist = [new_name if b == name else b for b in blist]
            store.update_requirement(r["id"], {"baselines": blist})
            updated += 1
    # Rename on all components
    comps_updated = 0
    for c in store.list_components():
        blist = list(c.get("baselines") or [])
        if name in blist:
            blist = [new_name if b == name else b for b in blist]
            store.update_item("components", c["id"], {"baselines": blist})
            comps_updated += 1
    frozen = store.get_item("baselines", name)
    if frozen is not None:
        if data.symbol is not None:
            frozen["symbol"] = data.symbol
        if data.description is not None:
            frozen["description"] = data.description
        if new_name != name:
            frozen["name"] = new_name
            store.write_item("baselines", new_name, frozen)
            store.delete_item("baselines", name)
        else:
            store.write_item("baselines", name, frozen)
    elif not found and updated == 0 and comps_updated == 0:
        raise HTTPException(status_code=404, detail="Baseline not found")
    return {"old_name": name, "new_name": new_name, "requirements_updated": updated}


@router.delete("/projects/{project_id}/baselines/{name}")
def delete_baseline(project_id: str, name: str, user: dict = Depends(require_maintain)):
    # No `check_deletable` here, deliberately: `links_into("baselines")` is
    # empty because `requirement.baselines` holds baseline *names*, not ids, and
    # the link registry excludes it on purpose (see its module docstring). A
    # guard here could never fire — it would read as protection that isn't
    # there. Membership is cleared from every requirement below instead.
    store = get_store(project_id)
    baseline = store.get_item("baselines", name)
    meta = store.read_meta()
    defs = normalize_baseline_defs(meta.get("baselines", []))
    in_defs = any(d["name"] == name for d in defs)
    if baseline is None and not in_defs:
        raise HTTPException(status_code=404, detail="Baseline not found")
    store.delete_item("baselines", name)
    # Remove the baseline definition from project metadata.
    with store.meta_lock():
        meta = store.read_meta()
        defs = normalize_baseline_defs(meta.get("baselines", []))
        defs = [d for d in defs if d["name"] != name]
        serialized = serialize_meta_defs(defs)
        meta["baselines"] = serialized
        store._write_meta_unlocked(meta)
    updated = 0
    for r in store.list_requirements():
        blist = list(r.get("baselines") or [])
        if name in blist:
            blist.remove(name)
            store.update_requirement(r["id"], {"baselines": blist})
            updated += 1
    for c in store.list_components():
        blist = list(c.get("baselines") or [])
        if name in blist:
            blist.remove(name)
            store.update_item("components", c["id"], {"baselines": blist})
    return {"name": name, "requirements_cleared": updated}


# ── System States ────────────────────────────────────────────────────────────

class SystemStateCreate(BaseModel):
    name: str
    description: str = ""


class SystemStateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class ReorderSystemStates(BaseModel):
    names: list[str]


@router.get("/projects/{project_id}/system-states")
def list_system_states(project_id: str, user: dict = Depends(require_view)):
    store = get_store(project_id)
    meta = store.read_meta()
    defs = normalize_system_states(meta.get("system_states", []))

    # Collect every name actually used on a requirement.
    used: set[str] = set()
    for r in store.list_requirements():
        for s in (r.get("system_states") or []):
            if s:
                used.add(s)

    defined = {d["name"] for d in defs}
    orphans = sorted(used - defined)

    return {"states": defs, "orphans": orphans}


@router.get("/projects/{project_id}/system-states/{name}")
def get_system_state(project_id: str, name: str, user: dict = Depends(require_view)):
    store = get_store(project_id)
    defs = normalize_system_states(store.read_meta().get("system_states", []))
    for d in defs:
        if d["name"] == name:
            return d
    raise HTTPException(status_code=404, detail="System state not found")


@router.post("/projects/{project_id}/system-states", status_code=201)
def create_system_state(project_id: str, data: SystemStateCreate,
                        user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="State name is required")

    with store.meta_lock():
        meta = store.read_meta()
        defs = normalize_system_states(meta.get("system_states", []))
        if any(d["name"] == name for d in defs):
            raise HTTPException(status_code=409,
                                detail="A system state with that name already exists")

        defs.append({"name": name, "description": data.description})
        meta["system_states"] = serialize_meta_defs(defs)
        store._write_meta_unlocked(meta)

    return {"name": name, "description": data.description, "order": len(defs)}


@router.put("/projects/{project_id}/system-states/order")
def reorder_system_states(project_id: str, data: ReorderSystemStates, user: dict = Depends(require_maintain)):
    """Rewrite the system-state sequence."""
    store = get_store(project_id)
    with store.meta_lock():
        meta = store.read_meta()
        current_defs = normalize_system_states(meta.get("system_states", []))
        defined_names = [d["name"] for d in current_defs]

        # Must be exactly the same set — a permutation, no duplicates, no missing.
        if set(data.names) != set(defined_names) or len(data.names) != len(defined_names):
            raise HTTPException(
                status_code=400,
                detail="names must list every defined system state exactly once",
            )

        # Build the new list in the requested order, preserving other fields.
        by_name = {d["name"]: d for d in current_defs}
        # `order` is left alone here: serialize_meta_defs is the one place it is
        # dropped, and duplicating that responsibility is how the derived value and
        # the list position start to disagree.
        reordered = [dict(by_name[nm]) for nm in data.names]

        serialized = serialize_meta_defs(reordered)
        meta["system_states"] = serialized
        store._write_meta_unlocked(meta)

    return {"states": normalize_system_states(serialized)}


@router.patch("/projects/{project_id}/system-states/{name}")
def update_system_state(project_id: str, name: str, data: SystemStateUpdate,
                        user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    new_name = data.name.strip() if data.name is not None else None
    if new_name == "":
        raise HTTPException(status_code=400, detail="State name is required")

    with store.meta_lock():
        meta = store.read_meta()
        defs = normalize_system_states(meta.get("system_states", []))

        target: dict | None = None
        for d in defs:
            if d["name"] == name:
                target = d
                break

        if target is None:
            raise HTTPException(status_code=404, detail="System state not found")

        if new_name is not None and new_name != name:
            if any(d["name"] == new_name for d in defs):
                raise HTTPException(status_code=409,
                                    detail="A system state with that name already exists")

        if new_name is not None and new_name != name:
            target["name"] = new_name
        if data.description is not None:
            target["description"] = data.description

        meta["system_states"] = serialize_meta_defs(defs)
        store._write_meta_unlocked(meta)

    # Rename cascades to every requirement that referenced the old name.
    requirements_updated = 0
    if new_name is not None and new_name != name:
        for r in store.list_requirements():
            states = list(r.get("system_states") or [])
            if name in states:
                states = [new_name if s == name else s for s in states]
                store.update_requirement(r["id"], {"system_states": states})
                requirements_updated += 1

    result = {k: v for k, v in target.items() if k in ("name", "description", "order")}
    if new_name is not None and new_name != name:
        result["old_name"] = name
        result["requirements_updated"] = requirements_updated
    return result


@router.delete("/projects/{project_id}/system-states/{name}")
def delete_system_state(project_id: str, name: str,
                        user: dict = Depends(require_maintain)):
    # No `check_deletable`: like baselines, nothing in the link registry targets
    # `system_states`, so the guard could never fire. Membership is cleared from
    # every requirement below.
    store = get_store(project_id)
    meta = store.read_meta()
    defs = normalize_system_states(meta.get("system_states", []))
    if not any(d["name"] == name for d in defs):
        raise HTTPException(status_code=404, detail="System state not found")
    with store.meta_lock():
        meta = store.read_meta()
        defs = normalize_system_states(meta.get("system_states", []))
        defs = [d for d in defs if d["name"] != name]
        meta["system_states"] = serialize_meta_defs(defs)
        store._write_meta_unlocked(meta)

    # Count how many requirements still carry the name — they become orphans.
    affected = 0
    for r in store.list_requirements():
        if name in (r.get("system_states") or []):
            affected += 1

    return {"name": name, "requirements_cleared": affected}


# ── Parametric definitions (reusable constraint / calc defs) ─────────────────

@router.get("/projects/{project_id}/definitions")
def list_definitions(
    project_id: str,
    offset: Optional[int] = Query(None, ge=0),
    limit: Optional[int] = Query(None, ge=1, le=2000),
    user: dict = Depends(require_view),
):
    store = get_store(project_id)
    items = store.list_items("definitions")
    return paginate(items, offset, limit)


@router.get("/projects/{project_id}/definitions/{def_id}")
def get_definition(project_id: str, def_id: str, user: dict = Depends(require_view)):
    store = get_store(project_id)
    item = store.get_item("definitions", def_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Definition not found")
    return item


@router.post("/projects/{project_id}/definitions", status_code=201)
def create_definition(project_id: str, data: DefinitionCreate, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    def_id = safe_id(data.id, "definition id")
    if store.get_item("definitions", def_id) is not None:
        raise HTTPException(status_code=409, detail="A definition with that id already exists")
    item = data.model_dump()
    item["id"] = def_id
    result = store.create_item("definitions", item)
    record_change(store, def_id, "create", None, result, user.get("username", ""))
    return result


@router.put("/projects/{project_id}/definitions/{def_id}")
def update_definition(project_id: str, def_id: str, data: DefinitionUpdate,
                      request: Request, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    existing = store.get_item("definitions", def_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Definition not found")
    check_precondition(request, existing)
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    result = store.update_item("definitions", def_id, updates)
    if result is None:
        raise HTTPException(status_code=404, detail="Definition not found")
    record_change(store, def_id, "update", existing, result, user.get("username", ""))
    return result


@router.delete("/projects/{project_id}/definitions/{def_id}")
def delete_definition(project_id: str, def_id: str, force: bool = False, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    with project_lock(store.root):
        check_deletable(store, "definitions", def_id, force)
        before = store.get_item("definitions", def_id)
        if not store.delete_item("definitions", def_id):
            raise HTTPException(status_code=404, detail="Definition not found")
    record_change(store, def_id, "delete", before, None, user.get("username", ""))
    return {"ok": True}


# ── Analysis cases (scoped, parameterised evaluation) ────────────────────────

@router.get("/projects/{project_id}/analysis")
def list_analysis_cases(
    project_id: str,
    offset: Optional[int] = Query(None, ge=0),
    limit: Optional[int] = Query(None, ge=1, le=2000),
    user: dict = Depends(require_view),
):
    store = get_store(project_id)
    items = store.list_items("analysis_cases")
    return paginate(items, offset, limit)


@router.get("/projects/{project_id}/analysis/{case_id}")
def get_analysis_case(project_id: str, case_id: str, user: dict = Depends(require_view)):
    store = get_store(project_id)
    item = store.get_item("analysis_cases", case_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Analysis case not found")
    return item


@router.post("/projects/{project_id}/analysis", status_code=201)
def create_analysis_case(project_id: str, data: AnalysisCaseCreate, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    case_id = safe_id(data.id, "analysis case id")
    if store.get_item("analysis_cases", case_id) is not None:
        raise HTTPException(status_code=409, detail="An analysis case with that id already exists")
    item = data.model_dump()
    item["id"] = case_id
    result = store.create_item("analysis_cases", item)
    record_change(store, case_id, "create", None, result, user.get("username", ""))
    return result


@router.put("/projects/{project_id}/analysis/{case_id}")
def update_analysis_case(project_id: str, case_id: str, data: AnalysisCaseUpdate,
                         request: Request, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    existing = store.get_item("analysis_cases", case_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Analysis case not found")
    check_precondition(request, existing)
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    result = store.update_item("analysis_cases", case_id, updates)
    if result is None:
        raise HTTPException(status_code=404, detail="Analysis case not found")
    record_change(store, case_id, "update", existing, result, user.get("username", ""))
    return result


@router.delete("/projects/{project_id}/analysis/{case_id}")
def delete_analysis_case(project_id: str, case_id: str, force: bool = False, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    with project_lock(store.root):
        check_deletable(store, "analysis_cases", case_id, force)
        before = store.get_item("analysis_cases", case_id)
        if not store.delete_item("analysis_cases", case_id):
            raise HTTPException(status_code=404, detail="Analysis case not found")
    record_change(store, case_id, "delete", before, None, user.get("username", ""))
    return {"ok": True}


@router.get("/projects/{project_id}/analysis/{case_id}/run", summary="Run an analysis case")
def run_analysis_case_endpoint(project_id: str, case_id: str, user: dict = Depends(require_view)):
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
    user: dict = Depends(require_view),
):
    store = get_store(project_id)
    items = store.list_verification_cases()
    return paginate(items, offset, limit)


@router.get("/projects/{project_id}/verification/{vc_id}")
def get_verification_case(project_id: str, vc_id: str, user: dict = Depends(require_view)):
    store = get_store(project_id)
    vc = store.get_verification_case(vc_id)
    if vc is None:
        raise HTTPException(status_code=404, detail="Verification case not found")
    return vc


@router.post("/projects/{project_id}/verification", status_code=201)
def create_verification_case(project_id: str, data: VerificationCaseCreate, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    safe_id(data.id, "verification case id")
    enforce_naming(store, "verification", data.id)
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
def update_verification_case(project_id: str, vc_id: str, data: VerificationCaseUpdate,
                             request: Request, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    before = store.get_verification_case(vc_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Verification case not found")
    check_precondition(request, before)
    update_dict = data.model_dump(mode="json", exclude_unset=True)
    result = store.update_verification_case(vc_id, update_dict)
    if result is None:
        raise HTTPException(status_code=404, detail="Verification case not found")
    record_change(store, vc_id, "update", before, result, user.get("username", ""))
    return result


@router.delete("/projects/{project_id}/verification/{vc_id}")
def delete_verification_case(project_id: str, vc_id: str, force: bool = False, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    with project_lock(store.root):
        check_deletable(store, "verification_cases", vc_id, force)
        before = store.get_verification_case(vc_id)
        if not store.delete_verification_case(vc_id):
            raise HTTPException(status_code=404, detail="Verification case not found")
    record_change(store, vc_id, "delete", before, None, user.get("username", ""))
    return {"ok": True}


@router.post("/projects/{project_id}/verification/{vc_id}/run")
def run_verification(project_id: str, vc_id: str, data: RunVerification, user: dict = Depends(require_maintain)):
    """Record a test execution run with optional step results and new status."""
    from datetime import datetime, timezone

    store = get_store(project_id)
    new_status = data.status
    notes = data.notes
    executed_by = user.get("username", "unknown")
    step_results = data.step_results

    path = store._item_path("verification_cases", vc_id)
    # Hold the item lock across the read-append-write so two concurrent
    # runs cannot lose an execution record — `update_item` covers only the
    # write half.  `_update_item_unlocked` is used to avoid deadlocking the
    # non-re-entrant `file_lock`.
    with file_lock(path):
        vc = store.get_verification_case(vc_id)
        if vc is None:
            raise HTTPException(status_code=404, detail="Verification case not found")

        # Update step actual results if provided.
        steps = list(vc.get("steps") or [])
        if step_results and isinstance(step_results, dict):
            for idx_str, actual in step_results.items():
                try:
                    idx = int(idx_str)
                    if 0 <= idx < len(steps):
                        steps[idx] = {**steps[idx], "actual_result": actual}
                except (ValueError, TypeError):
                    pass

        # Append execution record.
        history = list(vc.get("execution_history") or [])
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
        }
        result = store._update_item_unlocked("verification_cases", vc_id, update)
    record_change(store, vc_id, "execute", vc, result, user.get("username", ""))
    return result


# ── Traces ───────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/traces")
def get_traces(project_id: str, response: Response, user: dict = Depends(require_view)):
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


@router.get("/projects/{project_id}/trace-model")
def get_trace_model(project_id: str, user: dict = Depends(require_view), _rate: None = Depends(rate_limit(20, 60))):
    """Every declared relationship: registry-derived edges + hand-authored traces."""
    store = get_store(project_id)
    links = all_links(store)
    return {"links": links, "total": len(links)}
