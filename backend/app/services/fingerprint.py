from __future__ import annotations

import hashlib
import json
from base64 import urlsafe_b64encode
from datetime import datetime, timezone


NORMATIVE_FIELDS = (
    "type", "name", "description", "rationale", "priority",
    "verification_method", "verification_cases", "parent", "source",
)


def _canonical(req: dict, include_links: bool = False) -> str:
    parts: dict = {}
    for field in NORMATIVE_FIELDS:
        val = req.get(field, "")
        if isinstance(val, list):
            parts[field] = sorted([v for v in val if v is not None])
        elif val is None:
            parts[field] = ""
        else:
            parts[field] = val
    if include_links:
        relations = req.get("relations", [])
        parts["relations"] = sorted(
            (rel.get("type", ""), rel.get("target", "")) for rel in relations
        )
    return json.dumps(parts, sort_keys=True, ensure_ascii=False)


def compute_fingerprint(req: dict) -> str:
    canonical = _canonical(req, include_links=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).digest()
    return urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def compute_link_fingerprint(rel: dict, target_req: dict | None) -> str | None:
    if target_req is None:
        return None
    return compute_fingerprint(target_req)


def check_unreviewed(store) -> list[dict]:
    reqs = store.list_requirements()
    unreviewed = []
    for r in reqs:
        if r.get("reviewed") is None:
            continue
        current = compute_fingerprint(r)
        if r["reviewed"] != current:
            unreviewed.append({
                "id": r["id"],
                "name": r.get("name", ""),
                "reviewed": r.get("reviewed"),
                "current_fingerprint": current,
            })
    return unreviewed


def check_suspect_links(store) -> list[dict]:
    reqs = store.list_requirements()
    req_map = {r["id"]: r for r in reqs}
    suspect = []
    for r in reqs:
        for rel in r.get("relations", []):
            target = req_map.get(rel.get("target", ""))
            if target is None:
                continue
            stored = rel.get("reviewed_fingerprint")
            current = compute_fingerprint(target)
            if stored and stored != current:
                suspect.append({
                    "source": r["id"],
                    "target": rel["target"],
                    "type": rel.get("type", ""),
                    "stored_fingerprint": stored,
                    "current_fingerprint": current,
                    "reason": "Target content changed since review",
                })
    return suspect


def review_item(store, req_id: str, reviewer: str = "", comment: str = "") -> dict | None:
    req = store.get_requirement(req_id)
    if req is None:
        return None

    reqs = store.list_requirements()
    req_map = {r["id"]: r for r in reqs}

    fp = compute_fingerprint(req)
    req["reviewed"] = fp

    relations = []
    for rel in req.get("relations", []):
        target = req_map.get(rel.get("target", ""))
        link_fp = compute_link_fingerprint(rel, target)
        rel_copy = dict(rel)
        rel_copy["reviewed_fingerprint"] = link_fp
        relations.append(rel_copy)
    req["relations"] = relations

    result = store.update_requirement(req_id, req)
    return result


def review_all(store, user: str = "") -> dict:
    reqs = store.list_requirements()
    reviewed = 0
    for r in reqs:
        result = review_item(store, r["id"], reviewer=user)
        if result is not None:
            reviewed += 1
    return {"reviewed": reviewed, "total": len(reqs)}
