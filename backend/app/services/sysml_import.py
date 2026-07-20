"""SysML v2 textual-notation import.

Parses the ``.sysml`` files produced by :mod:`app.services.sysml_export` (and
similarly-shaped hand-written models) back into reqmesh entities.  The grammar
we consume is line-oriented — ``requirement def`` blocks delimited by braces —
which keeps the parser small without pulling in a full KerML grammar.

``parse_sysml`` returns::

    {"requirements": [...], "verification_cases": [...], "traces": [...]}
"""

from __future__ import annotations

import re

_REQ_DEF_RE = re.compile(r"^requirement\s+def\s+([A-Za-z0-9_]+)\s*\{")
_PART_DEF_RE = re.compile(r"^part\s+def\s+([A-Za-z0-9_]+)\s*\{")
_DOC_RE = re.compile(r"doc\s*/\*(.*?)\*/", re.DOTALL)
_TEXT_RE = re.compile(r"text\s*/\*\s*\"(.*?)\"\s*\*/", re.DOTALL)
_ASSIGN_RE = re.compile(r":>>\s*(\w+)\s*=\s*(.+?);")
_REL_RE = re.compile(r"^(refine|satisfy|derive|verify)\s+requirement\s+([A-Za-z0-9_]+)\s*;")
_ATTR_RE = re.compile(r"^attribute\s+([A-Za-z0-9_]+)\s*(?::\s*([\w:]+)\s*)?=\s*(.+?)\s*;")
_CONSTRAINT_RE = re.compile(r"^(assume|require)\s+constraint\s*\{\s*(.*?)\s*\}")
_SUBJECT_RE = re.compile(r"^subject\s+([A-Za-z0-9_]+)\s*;")
_UNIT_RE = re.compile(r"\[([^\]]+)\]\s*$")
_KIND_RE = re.compile(r"//\s*@kind=([A-Za-z]+)")


def _parse_attribute(line: str) -> dict | None:
    """Parse a SysML ``attribute`` line into a reqmesh parameter dict."""
    m = _ATTR_RE.match(line)
    if not m:
        return None
    name, value_type, rhs = m.group(1), m.group(2), m.group(3).strip()
    unit = ""
    um = _UNIT_RE.search(rhs)
    if um:
        unit = um.group(1).strip()
        rhs = rhs[: um.start()].strip()
    param: dict = {"name": name, "unit": unit}
    if value_type:
        param["value_type"] = value_type
    try:
        param["value"] = float(rhs)
    except ValueError:
        param["expr"] = rhs
    km = _KIND_RE.search(line)
    if km:
        param["kind"] = km.group(1)
    return param

# SysML keyword -> reqmesh relation type. ``verify`` is handled separately as a
# verification-case link rather than a relation.
_REL_KEYWORDS = {"refine": "refines", "satisfy": "satisfies", "derive": "derives"}


class SysMLParseError(ValueError):
    """Raised when the supplied text is not usable SysML."""


def _unquote(value: str) -> str:
    value = value.strip()
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        value = value[1:-1]
    return value.replace('\\"', '"').replace("\\n", "\n")


def parse_sysml(content: str | bytes) -> dict:
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")

    lines = content.splitlines()
    requirements: list[dict] = []
    components: list[dict] = []
    verification_cases: list[dict] = []
    traces: list[dict] = []

    # Stack of (kind, dict) for currently-open blocks; the innermost provides the
    # parent for a same-kind block opened inside it (reqs nest in reqs, parts in
    # parts). ``kind`` is one of "requirement" | "component" | "vc".
    stack: list[tuple[str, dict]] = []
    in_vc_section = False
    saw_req = False

    def nearest(kind: str) -> str | None:
        for k, entry in reversed(stack):
            if k == kind:
                return entry["id"]
        return None

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        if "Verification Cases" in line:
            in_vc_section = True
            continue

        # --- block openers ---
        rm = _REQ_DEF_RE.match(line)
        pm = _PART_DEF_RE.match(line)
        if rm:
            saw_req = True
            rid = rm.group(1)
            if in_vc_section:
                entry = {"id": rid, "name": rid, "verified_requirements": []}
                verification_cases.append(entry)
                stack.append(("vc", entry))
            else:
                entry = {"id": rid, "name": rid, "attributes": [], "relations": [],
                         "verification_cases": [], "parameters": [], "constraints": []}
                parent = nearest("requirement")
                if parent:
                    entry["parent"] = parent
                requirements.append(entry)
                stack.append(("requirement", entry))
        elif pm:
            cid = pm.group(1)
            entry = {"id": cid, "name": cid, "parameters": [], "satisfies": []}
            parent = nearest("component")
            if parent:
                entry["parent"] = parent
            components.append(entry)
            stack.append(("component", entry))

        if not stack:
            continue
        kind, current = stack[-1]

        doc = _DOC_RE.search(line)
        if doc and doc.group(1).strip():
            current["name"] = doc.group(1).strip()

        text = _TEXT_RE.search(line)
        if text and not in_vc_section:
            desc = _unquote(text.group(1))
            if desc:
                current["description"] = f"<p>{desc}</p>"

        assign = _ASSIGN_RE.search(line)
        if assign:
            key, value = assign.group(1), _unquote(assign.group(2))
            if key == "verificationMethod":
                current["verification_method"] = value
            elif key in ("status", "priority", "rationale", "source", "method"):
                current[key] = value

        sm = _SUBJECT_RE.match(line)
        if sm and kind == "requirement":
            current["subject"] = sm.group(1)

        if line.startswith("attribute"):
            attr = _parse_attribute(line)
            if attr:
                if kind == "component" and attr["name"] == "quantity" and "value" in attr:
                    current["quantity"] = int(attr["value"])
                else:
                    current.setdefault("parameters", []).append(attr)

        cm = _CONSTRAINT_RE.match(line)
        if cm:
            kw, expr = cm.group(1), cm.group(2).strip()
            if kw == "assume":
                current["_pending_assume"] = expr
            else:
                constraint: dict = {"expr": expr}
                if current.get("_pending_assume"):
                    constraint["assume"] = current.pop("_pending_assume")
                km = _KIND_RE.search(line)
                if km:
                    constraint["kind"] = km.group(1)
                current.setdefault("constraints", []).append(constraint)

        rel = _REL_RE.match(line)
        if rel:
            kw, target = rel.group(1), rel.group(2)
            if kw == "verify":
                if in_vc_section:
                    current.setdefault("verified_requirements", []).append(target)
                else:
                    current.setdefault("verification_cases", []).append(target)
                    traces.append({"source": current["id"], "target": target, "type": "verifies"})
            elif kw == "satisfy" and kind == "component":
                current.setdefault("satisfies", []).append(target)
                traces.append({"source": current["id"], "target": target, "type": "satisfies"})
            else:
                rtype = _REL_KEYWORDS[kw]
                current.setdefault("relations", []).append({"type": rtype, "target": target})
                traces.append({"source": current["id"], "target": target, "type": rtype})

        if line.startswith("}") and stack:
            stack.pop()

    if not saw_req:
        raise SysMLParseError("No `requirement def` blocks found — is this a SysML v2 model?")

    for entry in requirements:
        entry.pop("_pending_assume", None)

    return {
        "requirements": requirements,
        "components": components,
        "verification_cases": verification_cases,
        "traces": traces,
    }
