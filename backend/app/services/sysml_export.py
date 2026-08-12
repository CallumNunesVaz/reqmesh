"""SysML v2 textual notation export.

SysML v2 uses a human-readable textual syntax (KerML-based) rather than
the XMI-based v1.x. This generates valid .sysml files that can be imported
into tools like the SysML v2 Pilot Implementation.
"""

from __future__ import annotations

import re

from app.services.verification_links import attach as attach_verification_cases


# Block-level boundaries carry meaning. Descriptions are TipTap rich text, so
# multi-paragraph and bulleted content is normal, and stripping the tags without
# putting a separator back welds the last word of one block onto the first word
# of the next ("Para onePara two").
_BLOCK_BREAK = re.compile(r"(?i)</(?:p|div|li|h[1-6]|tr)\s*>|<br\s*/?>")
_TAG = re.compile(r"<[^>]*>")


def _plain_text(html: str) -> str:
    """Rich text as plain text, keeping block boundaries as newlines.

    Block boundaries become newlines first; the remaining (inline and opening)
    tags are then dropped without a separator, since the block pass has already
    put a separator where one is needed.
    """
    return _TAG.sub("", _BLOCK_BREAK.sub("\n", html or "")).strip()


def _safe_name(entity_id: str) -> str:
    """The SysML declared name for a reqmesh id (dots and hyphens are illegal)."""
    return entity_id.replace("-", "_").replace(".", "_")


def _decl(keyword: str, entity_id: str, suffix: str = "") -> str:
    """A block opener carrying a short name when the id was mangled.

    _decl("requirement def", "REQ-001")        -> "requirement def <'REQ-001'> REQ_001"
    _decl("requirement", "R-2", " : R_1")      -> "requirement <'R-2'> R_2 : R_1"
    _decl("part def", "WING")                  -> "part def WING"
    """
    safe = _safe_name(entity_id)
    if safe != entity_id:
        escaped = entity_id.replace("'", "\\'")
        return f"{keyword} <'{escaped}'> {safe}{suffix}"
    else:
        return f"{keyword} {safe}{suffix}"


def _subst_bindings(expr: str, bindings: dict) -> str:
    """Substitute a definition's formal names with their bound actual refs, so a
    reusable constraint/calc usage exports as a concrete (round-trippable) expr."""
    return re.sub(r"[A-Za-z_]\w*", lambda m: bindings.get(m.group(0), m.group(0)), expr)


def _effective(item: dict, def_key: str, defs: dict) -> dict:
    """Resolve a def-based usage to an inline ``expr`` for export."""
    def_id = item.get(def_key)
    if def_id and def_id in defs:
        expr = _subst_bindings(defs[def_id].get("expr", ""), item.get("bindings") or {})
        return {**item, "expr": expr}
    return item


def _fmt_num(v) -> str:
    """Render a parameter value without a trailing .0 for whole numbers."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "0"
    return str(int(f)) if f.is_integer() else f"{f:g}"


def _annotation_suffix(item: dict, def_key: str) -> str:
    """Build a comment suffix carrying kind, def binding, and formal→actual links.

    ``// @kind=TPM @def=DERATE-1 @bind=p1:mtow,p2:struct_limit``
    """
    parts: list[str] = []
    if item.get("kind"):
        parts.append(f"@kind={item['kind']}")
    def_id = item.get(def_key)
    if def_id:
        parts.append(f"@def={def_id}")
    bindings = item.get("bindings")
    if bindings:
        bind_str = ",".join(f"{k}:{v}" for k, v in bindings.items())
        parts.append(f"@bind={bind_str}")
    if parts:
        return "  // " + " ".join(parts)
    return ""


def _param_line(p: dict, prefix: str) -> str:
    """One SysML v2 ``attribute`` line for a reqmesh parameter.

    Derived params bind to their expression (``= expr``); literals bind to a
    value with an optional ``[unit]``. The measure kind rides along as a
    reqmesh annotation comment so it round-trips.
    """
    name = p.get("name", "")
    value_type = p.get("value_type")
    typ = f" : {value_type}" if value_type else ""
    if p.get("expr"):
        rhs = p["expr"]
    else:
        v = p.get("value")
        rhs = _fmt_num(v) if v is not None else "0"
    unit = p.get("unit")
    unit_s = f" [{unit}]" if unit else ""
    annot = _annotation_suffix(p, "calc_def")
    return f"{prefix}attribute {name}{typ} = {rhs}{unit_s};{annot}"


def _constraint_lines(c: dict, prefix: str) -> list[str]:
    """SysML v2 ``assume``/``require constraint`` lines for a reqmesh constraint."""
    out: list[str] = []
    if c.get("assume"):
        out.append(f"{prefix}assume constraint {{ {c['assume']} }}")
    annot = _annotation_suffix(c, "constraint_def")
    out.append(f"{prefix}require constraint {{ {c.get('expr', '')} }}{annot}")
    return out


def export_sysml_v2(store) -> str:
    """Return a SysML v2 textual notation string for the project."""
    meta = store.read_meta()
    reqs = store.list_requirements()
    vcs = store.list_verification_cases()
    components = store.list_components()

    # Build a requirement-id → list-of-component-ids map from component.satisfies,
    # so the subject clause can be derived from the allocating component(s) when
    # no explicit subject is stored.  One pass before the recursion, not per req.
    req_to_components: dict[str, list[str]] = {}
    for c in components:
        for req_id in c.get("satisfies") or []:
            req_to_components.setdefault(req_id, []).append(c["id"])
    attach_verification_cases(store, reqs, vcs)
    try:
        defs = {d["id"]: d for d in store.list_items("definitions")}
    except Exception:
        defs = {}
    try:
        cases = store.list_items("analysis_cases")
    except Exception:
        cases = []
    project_name = meta.get("name", store.root.name)
    safe_name = project_name.replace(" ", "_").replace("-", "_")

    lines: list[str] = []
    lines.append("// SysML v2 requirements model generated by reqmesh")
    lines.append(f"// Project: {project_name}")
    lines.append("")
    lines.append(f"package {safe_name} {{")
    lines.append("")

    # --- Part definitions (one per requirement type as a "part") ---
    req_by_parent: dict[str | None, list[dict]] = {}
    for r in reqs:
        pid = r.get("parent") if isinstance(r.get("parent"), str) and r["parent"] else None
        req_by_parent.setdefault(pid, []).append(r)

    all_exported_ids = {r["id"] for r in reqs}

    # Render requirements as SysML requirement definitions.
    def render_req(r: dict, indent_level: int = 2) -> list[str]:
        rid = _safe_name(r["id"])
        body: list[str] = []
        prefix = "  " * indent_level

        name = r.get("name", rid) or rid
        # Escape quotes in name and protect block comments
        name_escaped = name.replace('"', '\\"').replace("*/", "* /")

        # Cascaded requirements become usages typed by their master, so the
        # cascade link survives a round-trip through SysML v2 (definition/usage
        # is the SysML v2 idiom that maps onto cascade).
        cascade_from = r.get("cascade_from")
        if cascade_from and cascade_from in all_exported_ids:
            master_safe = _safe_name(cascade_from)
            body.append(f"{prefix}{_decl('requirement', r['id'], f' : {master_safe}')} {{")
        else:
            body.append(f"{prefix}{_decl('requirement def', r['id'])} {{")
        body.append(f"{prefix}  doc /* {name_escaped} */")
        body.append(f"{prefix}  :>> status = {r.get('status', 'proposed')};")
        body.append(f"{prefix}  :>> priority = {r.get('priority', 'medium')};")
        body.append(f"{prefix}  :>> verificationMethod = {r.get('verification_method', 'test')};")

        desc = _plain_text(r.get("description", ""))
        if desc.strip():
            desc_escaped = desc.replace('"', '\\"').replace("\n", "\\n").replace("*/", "* /")
            body.append(f"{prefix}  text /* \"{desc_escaped}\" */")
        # Newlines are escaped here too: these are single-line `:>> x = "…";`
        # assignments, and a literal newline would split them in two for the
        # line-oriented parser on the way back in.
        if r.get("rationale"):
            rat_escaped = _plain_text(r["rationale"]).replace('"', '\\"').replace("\n", "\\n")
            body.append(f"{prefix}  :>> rationale = \"{rat_escaped}\";")
        if r.get("source"):
            src_escaped = _plain_text(r["source"]).replace('"', '\\"').replace("\n", "\\n")
            body.append(f"{prefix}  :>> source = \"{src_escaped}\";")

        # Relations
        for rel in r.get("relations") or []:
            tgt = _safe_name(rel["target"])
            rel_type = rel["type"]
            if rel_type == "refines":
                body.append(f"{prefix}  refine requirement {tgt};")
            elif rel_type == "satisfies":
                body.append(f"{prefix}  satisfy requirement {tgt};")
            elif rel_type == "derives":
                body.append(f"{prefix}  derive requirement {tgt};")
            else:
                body.append(f"{prefix}  // @rel={rel_type} {tgt}")

        # The verify relationship is emitted from the verification case that
        # owns it (see the "Verification Cases" section below), not from here.
        #
        # This block used to emit `verify requirement <VC_ID>` inside the
        # requirement, which is backwards twice over: in SysML v2 a
        # verification case verifies a requirement, not the reverse, and the
        # id named as a requirement was actually a verification case. Every
        # relationship was therefore exported twice, once inverted — 68 verify
        # lines for 34 relationships. Consumers reading the export got an edge
        # pointing the wrong way to an entity of the wrong type.

        # Parametrics: typed attributes and assume/require constraints.
        # Subject — an explicit stored subject wins; otherwise derive from the
        # single allocating component when there is exactly one.
        explicit = r.get("subject")
        if explicit:
            subj = _safe_name(explicit)
            body.append(f"{prefix}  subject {subj};")
        else:
            allocs = req_to_components.get(r["id"], [])
            if len(allocs) == 1:
                subj = _safe_name(allocs[0])
                body.append(f"{prefix}  subject {subj};")
        for p in r.get("parameters") or []:
            body.append(_param_line(_effective(p, "calc_def", defs), f"{prefix}  "))
        for c in r.get("constraints") or []:
            body.extend(_constraint_lines(_effective(c, "constraint_def", defs), f"{prefix}  "))

        # Children
        children = req_by_parent.get(r["id"], [])
        for child in children:
            body.extend(render_req(child, indent_level + 1))

        body.append(f"{prefix}}}")
        if indent_level == 2:
            body.append("")
        return body

    top_level = req_by_parent.get(None, [])
    for r in top_level:
        lines.extend(render_req(r))

    # --- Components as part defs (so rollup targets round-trip) ---
    if components:
        comp_by_parent: dict[str | None, list[dict]] = {}
        for c in components:
            pid = c.get("parent") if isinstance(c.get("parent"), str) and c["parent"] else None
            comp_by_parent.setdefault(pid, []).append(c)

        def render_part(c: dict, indent_level: int = 1) -> list[str]:
            cid = _safe_name(c["id"])
            prefix = "  " * indent_level
            body = [f"{prefix}{_decl('part def', c['id'])} {{"]
            body.append(f"{prefix}  doc /* {(c.get('name') or cid)} */")
            if c.get("quantity", 1) not in (1, None):
                body.append(f"{prefix}  attribute quantity = {int(c['quantity'])};")
            for p in c.get("parameters") or []:
                body.append(_param_line(_effective(p, "calc_def", defs), f"{prefix}  "))
            for rid in c.get("satisfies") or []:
                body.append(f"{prefix}  satisfy requirement {_safe_name(rid)};")
            for child in comp_by_parent.get(c["id"], []):
                body.extend(render_part(child, indent_level + 1))
            body.append(f"{prefix}}}")
            if indent_level == 1:
                body.append("")
            return body

        lines.append("")
        lines.append("  // Components")
        for c in comp_by_parent.get(None, []):
            lines.extend(render_part(c))

    # --- Definitions (constraint def / calc def) ---
    if defs:
        lines.append("")
        lines.append("  // Definitions")
        for did in sorted(defs):
            d = defs[did]
            dtype = d.get("type", "constraint")
            keyword = "constraint def" if dtype == "constraint" else "calc def"
            lines.append(f"  {_decl(keyword, did)} {{")
            if d.get("doc"):
                doc_esc = d["doc"].replace("*/", "* /")
                lines.append(f"    doc /* {doc_esc} */")
            for param_name in d.get("parameters", []):
                lines.append(f"    in {param_name};")
            if dtype == "calc":
                unit = d.get("unit", "")
                if unit:
                    lines.append(f"    return [{unit}] {d['expr']}")
                else:
                    lines.append(f"    return {d['expr']}")
            else:
                lines.append(f"    {d['expr']}")
            lines.append("  }")
            lines.append("")

    # --- Analysis Cases ---
    if cases:
        lines.append("")
        lines.append("  // Analysis Cases")
        for case in cases:
            lines.append(f"  {_decl('analysis case def', case['id'])} {{")
            if case.get("doc"):
                doc_esc = case["doc"].replace("*/", "* /")
                lines.append(f"    doc /* {doc_esc} */")
            scope = case.get("scope") or []
            if scope:
                lines.append(f"    // @scope={','.join(scope)}")
            scope_comps = case.get("scope_components") or []
            if scope_comps:
                lines.append(f"    // @scope_components={','.join(scope_comps)}")
            overrides = case.get("overrides") or {}
            for ref, val in overrides.items():
                lines.append(f"    // @override={ref}={_fmt_num(val)}")
            lines.append("  }")
            lines.append("")

    # Verification cases as separate defs
    vcs = store.list_verification_cases()
    if vcs:
        lines.append("")
        lines.append("  // Verification Cases")
        for vc in vcs:
            vcid = _safe_name(vc["id"])
            lines.append(f"  {_decl('verification case def', vc['id'])} {{")
            lines.append(f"    doc /* {(vc.get('name', vcid)).replace('*/', '* /')} */")
            lines.append(f"    :>> status = {vc.get('status', 'pending')};")
            lines.append(f"    :>> method = {vc.get('method', 'test')};")
            for req_id in vc.get("verified_requirements", []):
                rid_safe = _safe_name(req_id)
                lines.append(f"    verify requirement {rid_safe};")
            lines.append("  }")
            lines.append("")

    lines.append("}")
    return "\n".join(lines)
