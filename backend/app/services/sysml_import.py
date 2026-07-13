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
_DOC_RE = re.compile(r"doc\s*/\*(.*?)\*/", re.DOTALL)
_TEXT_RE = re.compile(r"text\s*/\*\s*\"(.*?)\"\s*\*/", re.DOTALL)
_ASSIGN_RE = re.compile(r":>>\s*(\w+)\s*=\s*(.+?);")
_REL_RE = re.compile(r"^(refine|satisfy|derive|verify)\s+requirement\s+([A-Za-z0-9_]+)\s*;")

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
    verification_cases: list[dict] = []
    traces: list[dict] = []

    # Stack of currently-open requirement dicts; the top is the innermost block
    # and provides the ``parent`` for any requirement def opened inside it.
    stack: list[dict] = []
    in_vc_section = False
    current: dict | None = None
    saw_req = False

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        if "Verification Cases" in line:
            in_vc_section = True
            continue

        m = _REQ_DEF_RE.match(line)
        if m:
            saw_req = True
            rid = m.group(1)
            if in_vc_section:
                current = {"id": rid, "name": rid, "verified_requirements": []}
                verification_cases.append(current)
                stack.append(current)
            else:
                parent = stack[-1]["id"] if stack else None
                current = {
                    "id": rid,
                    "name": rid,
                    "attributes": [],
                    "relations": [],
                    "verification_cases": [],
                }
                if parent:
                    current["parent"] = parent
                requirements.append(current)
                stack.append(current)
            # A doc comment may sit on the same line; fall through to grab it.

        if current is None:
            continue

        doc = _DOC_RE.search(line)
        if doc:
            name = doc.group(1).strip()
            if name:
                current["name"] = name

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

        rel = _REL_RE.match(line)
        if rel:
            kw, target = rel.group(1), rel.group(2)
            if kw == "verify":
                if in_vc_section:
                    current.setdefault("verified_requirements", []).append(target)
                else:
                    current.setdefault("verification_cases", []).append(target)
                    traces.append({"source": current["id"], "target": target, "type": "verifies"})
            else:
                rtype = _REL_KEYWORDS[kw]
                current.setdefault("relations", []).append({"type": rtype, "target": target})
                traces.append({"source": current["id"], "target": target, "type": rtype})

        if line.startswith("}"):
            if stack:
                stack.pop()
            current = stack[-1] if stack else None

    if not saw_req:
        raise SysMLParseError("No `requirement def` blocks found — is this a SysML v2 model?")

    return {
        "requirements": requirements,
        "verification_cases": verification_cases,
        "traces": traces,
    }
