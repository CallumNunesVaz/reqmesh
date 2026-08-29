"""SysML v2 textual-notation import.

Parses the ``.sysml`` files produced by :mod:`app.services.sysml_export` (and
similarly-shaped hand-written models) back into reqmesh entities.  The grammar
we consume is line-oriented — ``requirement def`` blocks delimited by braces —
which keeps the parser small without pulling in a full KerML grammar.

``parse_sysml`` returns::

    {"requirements": [...], "components": [...], "verification_cases": [...],
     "traces": [...],
     "definitions": [{"id","type","name","parameters","expr","unit","doc"}],
     "analysis_cases": [{"id","name","doc","scope","scope_components","overrides"}],
     "ignored": {"lines": int, "constructs": dict[str, int]}}
"""

from __future__ import annotations

import re
from typing import Any

_SHORT = r"(?:<\s*'((?:[^'\\]|\\.)*)'\s*>\s*)?"
_REQ_DEF_RE = re.compile(r"^requirement\s+def\s+" + _SHORT + r"([A-Za-z0-9_]+)\s*\{")
_REQ_USAGE_RE = re.compile(r"^requirement\s+" + _SHORT + r"([A-Za-z0-9_]+)\s*:\s*([A-Za-z0-9_]+)\s*\{")
_PART_DEF_RE = re.compile(r"^part\s+def\s+" + _SHORT + r"([A-Za-z0-9_]+)\s*\{")
# constraint def / calc def / analysis case def — SysML-native entity blocks
_CONSTRAINT_DEF_RE = re.compile(r"^(constraint|calc)\s+def\s+" + _SHORT + r"([A-Za-z0-9_]+)\s*\{")
# _CONSTRAINT_DEF_RE groups: 1=constraint|calc, 2=short name, 3=declared name
_ANALYSIS_DEF_RE = re.compile(r"^analysis\s+case\s+def\s+" + _SHORT + r"([A-Za-z0-9_]+)\s*\{")
# _ANALYSIS_DEF_RE groups: 1=short name, 2=declared name
_IN_PARAM_RE = re.compile(r"^in\s+([A-Za-z_]\w*)\s*;")
_RETURN_RE = re.compile(r"^return\s*(?:\[([^\]]+)\])?\s*(.+?)\s*$")
# Annotation regexes for @def= / @bind= / @scope / @scope_components / @override
_DEF_USE_RE = re.compile(r"//.*?@def=([^\s]+)")
_BIND_RE = re.compile(r"//.*?@bind=([^\s]+)")
_SCOPE_RE = re.compile(r"//\s*@scope=(\S+)")
_SCOPE_COMP_RE = re.compile(r"//\s*@scope_components=(\S+)")
_OVERRIDE_RE = re.compile(r"//\s*@override=(\S+?)=([-\d.eE+]+)\s*$")
_DOC_RE = re.compile(r"doc\s*/\*(.*?)\*/", re.DOTALL)
_TEXT_RE = re.compile(r"text\s*/\*\s*\"(.*?)\"\s*\*/", re.DOTALL)
_ASSIGN_RE = re.compile(r":>>\s*(\w+)\s*=\s*(.+?);")
_REL_RE = re.compile(r"^(refine|satisfy|derive|verify)\s+requirement\s+([A-Za-z0-9_]+)\s*;")
_ATTR_RE = re.compile(r"^attribute\s+([A-Za-z0-9_]+)\s*(?::\s*([\w:]+)\s*)?=\s*(.+?)\s*;")
_CONSTRAINT_RE = re.compile(r"^(assume|require)\s+constraint\s*\{\s*(.*?)\s*\}")
_SUBJECT_RE = re.compile(r"^subject\s+([A-Za-z0-9_]+)\s*;")
_UNIT_RE = re.compile(r"\[([^\]]+)\]\s*$")
_KIND_RE = re.compile(r"//\s*@kind=([A-Za-z]+)")
_REL_ANNOT_RE = re.compile(r"//\s*@rel=([A-Za-z_]\w*)\s+([A-Za-z0-9_]+)\s*$")
_VC_DEF_RE = re.compile(r"^verification\s+case\s+def\s+" + _SHORT + r"([A-Za-z0-9_]+)\s*\{")
# `part def` is matched by _PART_DEF_RE; this is the usage form. The negative
# lookahead is what keeps the two from colliding.
_PART_USAGE_RE = re.compile(r"^part\s+(?!def\b)" + _SHORT + r"([A-Za-z0-9_]+)\s*(?::\s*([A-Za-z0-9_]+)\s*)?\{")
# package Name { — transparent wrapper that reqmesh emits around every export.
# Recognised so the round-trip is clean (ignored.lines == 0), but no entity is
# created — packages are out of scope.
_PACKAGE_RE = re.compile(r"^package\s+([A-Za-z0-9_]+)\s*\{")

# Keywords the parser does not import.  Lines whose first word matches one of
# these (when not already handled) are counted in the "ignored" report so the
# user knows exactly what was dropped.
_IGNORED_KEYWORDS = (
    "port", "connect", "interface", "flow", "binding", "state", "transition",
    "entry", "exit", "do", "action", "succession", "perform", "package",
    "import", "enum", "occurrence", "view", "viewpoint", "render", "allocate",
    "item", "metadata", "ref", "snapshot", "timeslice", "individual",
)


def _parse_bindings(raw: str) -> dict[str, str]:
    """Parse ``formal:actual`` pairs from a ``@bind=`` annotation value."""
    result: dict[str, str] = {}
    for pair in raw.split(","):
        if ":" in pair:
            k, v = pair.split(":", 1)
            if k and v:
                result[k] = v
    return result


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
    dm = _DEF_USE_RE.search(line)
    if dm:
        param["calc_def"] = dm.group(1)
    bm = _BIND_RE.search(line)
    if bm:
        bindings = _parse_bindings(bm.group(1))
        if bindings:
            param["bindings"] = bindings
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


def _unescape(s: str) -> str:
    """Turn ``\'`` back into ``'``."""
    return s.replace("\\'", "'")


def _check_ignored(line: str, constructs: dict[str, int]) -> None:
    """If *line*'s first word matches an :data:`_IGNORED_KEYWORDS` entry
    (followed by whitespace, ``{`` or ``;``), increment its count."""
    for kw in _IGNORED_KEYWORDS:
        if line.startswith(kw) and (len(line) == len(kw) or line[len(kw)] in (' ', '\t', '{', ';')):
            constructs[kw] = constructs.get(kw, 0) + 1
            return


def parse_sysml(content: str | bytes) -> dict:
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")

    lines = content.splitlines()
    requirements: list[dict] = []
    components: list[dict] = []
    verification_cases: list[dict] = []
    definitions: list[dict] = []
    analysis_cases: list[dict] = []
    traces: list[dict] = []

    # declared name -> entity id  (e.g. "REQ_001" -> "REQ-001")
    aliases: dict[str, str] = {}

    # Stack of (kind, dict) for currently-open blocks; the innermost provides the
    # parent for a same-kind block opened inside it (reqs nest in reqs, parts in
    # parts). ``kind`` is one of "requirement" | "component" | "vc" |
    # "definition" | "analysis_case".
    stack: list[tuple[str, dict]] = []
    in_vc_section = False
    ignored_constructs: dict[str, int] = {}

    def nearest(kind: str) -> str | None:
        for k, entry in reversed(stack):
            if k == kind:
                return entry["id"]
        return None

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        recognized = False

        if "Verification Cases" in line:
            in_vc_section = True
            recognized = True
            continue

        # --- block openers ---
        # A definition's expression is recognised by elimination — it is the body
        # line that is not `in`, `doc` or `return`. The opener itself also passes
        # that test, so it has to be excluded explicitly, or a def with no
        # expression line ends up storing its own `constraint def X {` header as
        # the expression, which importer.py's empty-expr guard cannot catch.
        opened_here = False
        cdm = _CONSTRAINT_DEF_RE.match(line)
        adm = _ANALYSIS_DEF_RE.match(line)
        vcm = _VC_DEF_RE.match(line)
        rm = _REQ_DEF_RE.match(line)
        rum = _REQ_USAGE_RE.match(line)
        pm = _PART_DEF_RE.match(line)
        pum = _PART_USAGE_RE.match(line)
        pkgm = _PACKAGE_RE.match(line)
        if cdm:
            # groups: 1=constraint|calc, 2=short name, 3=declared name
            dtype = cdm.group(1)
            short, declared = cdm.group(2), cdm.group(3)
            eid = _unescape(short) if short else declared
            aliases[declared] = eid
            entry: dict[str, Any] = {"id": eid, "type": dtype, "name": eid, "parameters": [],
                     "expr": "", "unit": "", "doc": ""}
            definitions.append(entry)
            stack.append(("definition", entry))
            opened_here = True
            recognized = True
        elif adm:
            # groups: 1=short name, 2=declared name
            short, declared = adm.group(1), adm.group(2)
            eid = _unescape(short) if short else declared
            aliases[declared] = eid
            entry = {"id": eid, "name": eid, "doc": "",
                     "scope": [], "scope_components": [], "overrides": {}}
            analysis_cases.append(entry)
            stack.append(("analysis_case", entry))
            opened_here = True
            recognized = True
        elif vcm:
            short, declared = vcm.group(1), vcm.group(2)
            eid = _unescape(short) if short else declared
            aliases[declared] = eid
            entry = {"id": eid, "name": eid, "verified_requirements": []}
            verification_cases.append(entry)
            stack.append(("vc", entry))
            recognized = True
        elif rum:
            short, declared, type_id = rum.group(1), rum.group(2), rum.group(3)
            eid = _unescape(short) if short else declared
            aliases[declared] = eid
            if in_vc_section:
                entry = {"id": eid, "name": eid, "cascade_from": type_id, "verified_requirements": []}
                verification_cases.append(entry)
                stack.append(("vc", entry))
            else:
                entry = {"id": eid, "name": eid, "cascade_from": type_id, "attributes": [],
                         "relations": [], "verification_cases": [], "parameters": [], "constraints": []}
                parent = nearest("requirement")
                if parent:
                    entry["parent"] = parent
                requirements.append(entry)
                stack.append(("requirement", entry))
            recognized = True
        elif rm:
            short, declared = rm.group(1), rm.group(2)
            eid = _unescape(short) if short else declared
            aliases[declared] = eid
            if in_vc_section:
                entry = {"id": eid, "name": eid, "verified_requirements": []}
                verification_cases.append(entry)
                stack.append(("vc", entry))
            else:
                entry = {"id": eid, "name": eid, "attributes": [], "relations": [],
                         "verification_cases": [], "parameters": [], "constraints": []}
                parent = nearest("requirement")
                if parent:
                    entry["parent"] = parent
                requirements.append(entry)
                stack.append(("requirement", entry))
            recognized = True
        elif pm:
            short, declared = pm.group(1), pm.group(2)
            eid = _unescape(short) if short else declared
            aliases[declared] = eid
            entry = {"id": eid, "name": eid, "parameters": [], "satisfies": []}
            parent = nearest("component")
            if parent:
                entry["parent"] = parent
            components.append(entry)
            stack.append(("component", entry))
            recognized = True
        elif pum:
            short, declared = pum.group(1), pum.group(2)
            eid = _unescape(short) if short else declared
            aliases[declared] = eid
            if pum.group(3):
                ignored_constructs["part_typing"] = ignored_constructs.get("part_typing", 0) + 1
            entry = {"id": eid, "name": eid, "parameters": [], "satisfies": []}
            parent = nearest("component")
            if parent:
                entry["parent"] = parent
            components.append(entry)
            stack.append(("component", entry))
            recognized = True
        elif pkgm:
            # Transparent wrapper — recognised so it isn't counted as ignored,
            # but no entity is created.  Pushing a sentinel keeps brace-matching
            # correct for nested blocks.
            stack.append(("package", {}))
            recognized = True

        if not stack:
            # Ignored-keyword lines at top level (outside any block).
            if not recognized and not line.startswith("//") and not line.startswith("}"):
                _check_ignored(line, ignored_constructs)
            continue
        kind, current = stack[-1]

        doc = _DOC_RE.search(line)
        if doc and doc.group(1).strip():
            recognized = True
            if kind in ("definition", "analysis_case"):
                current["doc"] = doc.group(1).strip()
            else:
                current["name"] = doc.group(1).strip()

        text = _TEXT_RE.search(line)
        if text and not in_vc_section:
            recognized = True
            desc = _unquote(text.group(1))
            if desc:
                current["description"] = desc

        assign = _ASSIGN_RE.search(line)
        if assign:
            recognized = True
            key, value = assign.group(1), _unquote(assign.group(2))
            if key == "verificationMethod":
                current["verification_method"] = value
            elif key in ("status", "priority", "rationale", "source", "method"):
                current[key] = value

        sm = _SUBJECT_RE.match(line)
        if sm and kind == "requirement":
            recognized = True
            current["subject"] = sm.group(1)

        if line.startswith("attribute"):
            attr = _parse_attribute(line)
            if attr:
                recognized = True
                if kind == "component" and attr["name"] == "quantity" and "value" in attr:
                    current["quantity"] = int(attr["value"])
                else:
                    current.setdefault("parameters", []).append(attr)

        cm = _CONSTRAINT_RE.match(line)
        if cm:
            recognized = True
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
                dm = _DEF_USE_RE.search(line)
                if dm:
                    constraint["constraint_def"] = dm.group(1)
                bm = _BIND_RE.search(line)
                if bm:
                    bindings = _parse_bindings(bm.group(1))
                    if bindings:
                        constraint["bindings"] = bindings
                current.setdefault("constraints", []).append(constraint)

        rel = _REL_RE.match(line)
        if rel:
            recognized = True
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

        rel_annot = _REL_ANNOT_RE.search(line)
        if rel_annot and kind == "requirement":
            recognized = True
            rtype = rel_annot.group(1)
            target = rel_annot.group(2)
            current.setdefault("relations", []).append({"type": rtype, "target": target})
            traces.append({"source": current["id"], "target": target, "type": rtype})

        # --- definition block internals ---
        if kind == "definition":
            inm = _IN_PARAM_RE.match(line)
            if inm:
                recognized = True
                current.setdefault("parameters", []).append(inm.group(1))
                continue
            rtm = _RETURN_RE.match(line)
            if rtm:
                recognized = True
                current["unit"] = (rtm.group(1) or "").strip()
                current["expr"] = rtm.group(2).strip()
                continue
            # Constraint def expression line (not in/return/doc/comment/close-brace)
            if (current.get("type") == "constraint"
                    and not opened_here
                    and not line.startswith("//")
                    and not line.startswith("in ")
                    and not line.startswith("doc ")
                    and not line.startswith("return ")
                    and not line.startswith("}")):
                recognized = True
                current["expr"] = line.strip()

        # --- analysis case block internals ---
        if kind == "analysis_case":
            scm = _SCOPE_RE.match(line)
            if scm:
                recognized = True
                current["scope"] = scm.group(1).split(",")
            sccm = _SCOPE_COMP_RE.match(line)
            if sccm:
                recognized = True
                current["scope_components"] = sccm.group(1).split(",")
            ovm = _OVERRIDE_RE.match(line)
            if ovm:
                recognized = True
                ref = ovm.group(1)
                try:
                    current["overrides"][ref] = float(ovm.group(2))
                except ValueError:
                    pass

        if line.startswith("}") and stack:
            recognized = True
            stack.pop()

        if not recognized and not line.startswith("//") and not line.startswith("}"):
            _check_ignored(line, ignored_constructs)

    if not (requirements or components or verification_cases or definitions or analysis_cases):
        raise SysMLParseError("No SysML v2 entities found — is this a SysML v2 model?")

    for entry in requirements:
        entry.pop("_pending_assume", None)

    # --- alias resolution (post-pass) ---
    def _remap(value: str) -> str:
        return aliases.get(value, value)

    # Resolve in-entity references.  A name absent from the alias map is left
    # as-is — it names an entity outside this file.
    for req in requirements:
        for rel in req.get("relations", []):
            rel["target"] = _remap(rel["target"])
        if req.get("parent"):
            req["parent"] = _remap(req["parent"])
        if req.get("cascade_from"):
            req["cascade_from"] = _remap(req["cascade_from"])
        if req.get("subject"):
            req["subject"] = _remap(req["subject"])
        for i, vid in enumerate(list(req.get("verification_cases", []))):
            req["verification_cases"][i] = _remap(vid)

    for comp in components:
        for i, rid in enumerate(list(comp.get("satisfies", []))):
            comp["satisfies"][i] = _remap(rid)
        if comp.get("parent"):
            comp["parent"] = _remap(comp["parent"])

    for vc in verification_cases:
        for i, rid in enumerate(list(vc.get("verified_requirements", []))):
            vc["verified_requirements"][i] = _remap(rid)
        if vc.get("cascade_from"):
            vc["cascade_from"] = _remap(vc["cascade_from"])

    for trace in traces:
        if trace.get("source"):
            trace["source"] = _remap(trace["source"])
        if trace.get("target"):
            trace["target"] = _remap(trace["target"])

    # Clear cascade_from when the type reference does not resolve to a
    # requirement in this file — a dangling link is worse than a lost one.
    all_imported_ids = {r["id"] for r in requirements}
    for entry in requirements:
        cfrom = entry.get("cascade_from")
        if cfrom and cfrom not in all_imported_ids:
            entry.pop("cascade_from", None)

    return {
        "requirements": requirements,
        "components": components,
        "verification_cases": verification_cases,
        "traces": traces,
        "definitions": definitions,
        "analysis_cases": analysis_cases,
        "ignored": {
            "lines": sum(ignored_constructs.values()),
            "constructs": ignored_constructs,
        },
    }
