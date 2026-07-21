from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone
from typing import Optional

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False


_HTML_TAG = re.compile(r"<[^>]*>")


def _strip_html(text: str) -> str:
    return _HTML_TAG.sub("", text).strip()


def _flat_columns(meta: dict | None = None) -> list[str]:
    cols = [
        "id", "type", "name", "description", "status", "priority",
        "verification_method", "parent", "relations", "verification_cases",
        "rationale", "source", "allocated_to", "baselines",
    ]
    if meta and "attributes" in meta and "publish" in meta["attributes"]:
        for attr in meta["attributes"]["publish"]:
            if attr not in cols:
                cols.append(attr)
    return cols


def _req_to_row(req: dict, meta: dict | None = None) -> dict:
    row = {
        "id": req.get("id", ""),
        "type": req.get("type", "functional"),
        "name": req.get("name", ""),
        "description": _strip_html(req.get("description", "")),
        "status": req.get("status", "proposed"),
        "priority": req.get("priority", "medium"),
        "verification_method": req.get("verification_method", "test"),
        "parent": req.get("parent") or "",
        "relations": "; ".join(
            f"{r['type']}:{r['target']}" for r in req.get("relations", [])
        ),
        "verification_cases": "; ".join(req.get("verification_cases", [])),
        "rationale": req.get("rationale", ""),
        "source": req.get("source", ""),
        "allocated_to": req.get("allocated_to", ""),
        "baselines": ", ".join(req.get("baselines", [])),
    }
    for attr in req.get("attributes", []):
        row[attr["key"]] = attr["value"]
    return row


_HEADER_ALIASES: dict[str, str] = {
    "requirement_id": "id",
    "req_id": "id",
    "req id": "id",
    "requirement type": "type",
    "priority_level": "priority",
    "verification": "verification_method",
    "verification method": "verification_method",
    "v_cases": "verification_cases",
    "test_cases": "verification_cases",
    "linked_to": "relations",
    "linked requirements": "relations",
    "parent_id": "parent",
    "justification": "rationale",
    "allocated_to": "allocated_to",
    "allocated": "allocated_to",
    "system_element": "allocated_to",
    "baseline": "baselines",
}


def _row_to_req(row: dict) -> dict:
    names = {n.lower().strip().replace(" ", "_"): n for n in row}
    get = lambda key, default: row.get(
        names.get(key) or names.get(_HEADER_ALIASES.get(key, "")), default
    )

    relations = []
    rel_str = get("relations", "")
    if rel_str.strip():
        for part in rel_str.split(";"):
            part = part.strip()
            if ":" in part:
                rtype, target = part.split(":", 1)
                relations.append({"type": rtype.strip(), "target": target.strip()})

    vcs = [v.strip() for v in get("verification_cases", "").split(";") if v.strip()]

    attributes = []
    for col_key, col_name in names.items():
        if col_key in {
            "id", "type", "name", "description", "status", "priority",
            "verification_method", "parent", "relations", "verification_cases",
            "rationale", "source", "allocated_to", "baselines", "created", "modified",
        }:
            continue
        val = row.get(col_name, "")
        if val:
            attributes.append({"key": col_name, "value": str(val)})

    req = {
        "id": get("id", ""),
        "type": get("type", "functional"),
        "name": get("name", ""),
        "description": get("description", ""),
        "status": get("status", "proposed"),
        "priority": get("priority", "medium"),
        "verification_method": get("verification_method", "test"),
        "parent": get("parent", "") or None,
        "relations": relations,
        "verification_cases": vcs,
        "rationale": get("rationale", ""),
        "source": get("source", ""),
        "allocated_to": get("allocated_to", ""),
        "baselines": [b.strip() for b in get("baselines", "").split(",") if b.strip()] or [],
        "attributes": attributes,
    }
    return req


def export_table(store, fmt: str) -> str:
    if fmt not in ("csv", "tsv"):
        raise ValueError(f"Unknown table format: {fmt}")
    meta = store.read_meta()
    reqs = store.list_requirements()
    columns = _flat_columns(meta)

    out = io.StringIO()
    delimiter = "\t" if fmt == "tsv" else ","
    writer = csv.DictWriter(out, fieldnames=columns, delimiter=delimiter, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    for r in reqs:
        row = _req_to_row(r, meta)
        writer.writerow(row)
    return out.getvalue()


def import_table(store, content: str, fmt: str = "csv", mode: str = "merge", dry_run: bool = False) -> dict:
    if fmt not in ("csv", "tsv"):
        raise ValueError(f"Unknown table format: {fmt}")
    if mode not in ("merge", "replace"):
        raise ValueError(f"Unknown mode: {mode}")

    delimiter = "\t" if fmt == "tsv" else ","
    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    rows = list(reader)

    created = 0
    updated = 0
    skipped = 0

    if mode == "replace":
        if dry_run:
            return {"created": 0, "updated": 0, "skipped": 0, "traces_added": 0,
                    "verification_cases": 0, "format": fmt,
                    "dry_run": True, "would_delete": len(store.list_requirements()),
                    "rows": len(rows)}
        for req in store.list_requirements():
            store.delete_requirement(req["id"])

    if dry_run:
        would_create = 0
        would_update = 0
        for row in rows:
            req_data = _row_to_req(row)
            rid = req_data.get("id", "").strip()
            if not rid:
                skipped += 1
                continue
            if store.get_requirement(rid):
                would_update += 1
            else:
                would_create += 1
        return {"created": 0, "updated": 0, "skipped": skipped, "traces_added": 0,
                "verification_cases": 0, "format": fmt,
                "dry_run": True, "would_create": would_create, "would_update": would_update,
                "rows": len(rows)}

    for row in rows:
        req_data = _row_to_req(row)
        rid = req_data.get("id", "").strip()
        if not rid:
            skipped += 1
            continue

        existing = store.get_requirement(rid)
        if existing:
            store.update_requirement(rid, req_data)
            updated += 1
        else:
            store.create_requirement(req_data)
            created += 1

    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "traces_added": 0,
        "verification_cases": 0,
        "format": fmt,
    }


def export_xlsx(store, path: str) -> None:
    if not HAS_OPENPYXL:
        raise ImportError("openpyxl is required for XLSX export. Install with: pip install openpyxl")

    wb = Workbook()
    ws = wb.active
    ws.title = "Requirements"

    header_font = Font(bold=True, size=11)
    header_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")

    meta = store.read_meta()
    columns = _flat_columns(meta)
    reqs = store.list_requirements()

    for col_idx, col_name in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.font = header_font
        cell.fill = header_fill

    for row_idx, r in enumerate(reqs, start=2):
        row_data = _req_to_row(r, meta)
        for col_idx, col_name in enumerate(columns, start=1):
            ws.cell(row=row_idx, column=col_idx, value=row_data.get(col_name, ""))

    wb.save(path)


def import_xlsx(store, content: bytes, mode: str = "merge", dry_run: bool = False) -> dict:
    if not HAS_OPENPYXL:
        raise ImportError("openpyxl is required for XLSX import. Install with: pip install openpyxl")
    if mode not in ("merge", "replace"):
        raise ValueError(f"Unknown mode: {mode}")

    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
    ws = wb.active
    headers = [str(cell.value or "").strip() for cell in next(ws.iter_rows(min_row=1, max_row=1))]
    created = 0
    updated = 0
    skipped = 0

    if mode == "replace":
        if dry_run:
            wb.close()
            return {"created": 0, "updated": 0, "skipped": 0, "traces_added": 0,
                    "verification_cases": 0, "format": "xlsx",
                    "dry_run": True, "would_delete": len(store.list_requirements()),
                    "rows": ws.max_row - 1 if ws.max_row else 0}
        for req in store.list_requirements():
            store.delete_requirement(req["id"])

    row_count = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not any(v is not None for v in row):
            continue
        row_count += 1
        row_dict = {headers[i]: str(v) if v is not None else "" for i, v in enumerate(row) if i < len(headers)}
        req_data = _row_to_req(row_dict)
        rid = req_data.get("id", "").strip()
        if not rid:
            skipped += 1
            continue
        if dry_run:
            if store.get_requirement(rid):
                updated += 1
            else:
                created += 1
        else:
            existing = store.get_requirement(rid)
            if existing:
                store.update_requirement(rid, req_data)
                updated += 1
            else:
                store.create_requirement(req_data)
                created += 1

    wb.close()
    return {
        "created": created, "updated": updated, "skipped": skipped,
        "traces_added": 0, "verification_cases": 0, "format": "xlsx",
        **({"dry_run": True, "rows": row_count} if dry_run else {}),
    }
