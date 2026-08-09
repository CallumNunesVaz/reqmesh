"""SysML v2 native entities: definition blocks, analysis case blocks, and
``@def=`` / ``@bind=`` annotations survive export → import.

These are genuine SysML v2 concepts that reqmesh already models (``Definition``,
``AnalysisCase``).  The exporter used to erase both — definitions were inlined
via ``_effective`` and analysis cases were never read.  Now both are emitted as
real blocks and restored on import.
"""

from __future__ import annotations

from pathlib import Path

from app.services.importer import import_into_store
from app.services.sysml_export import export_sysml_v2
from app.services.sysml_import import parse_sysml
from app.services.yaml_store import YamlStore


def _store(tmp_path: Path, name: str = "Test") -> YamlStore:
    root = tmp_path / "project"
    root.mkdir(parents=True, exist_ok=True)
    store = YamlStore(root)
    store.ensure_dirs()
    store.write_meta({"name": name})
    return store


def _fresh(tmp_path: Path, name: str = "Target") -> YamlStore:
    root = tmp_path / name
    root.mkdir()
    store = YamlStore(root)
    store.ensure_dirs()
    store.write_meta({"name": name})
    return store


# ── 1. constraint def with two formals ───────────────────────────────────────

def test_constraint_def_round_trips_parameters_expr_and_doc(tmp_path):
    store = _store(tmp_path)
    store.write_item("definitions", "DERATE-1", {
        "id": "DERATE-1", "type": "constraint",
        "name": "Derate", "parameters": ["p1", "p2"],
        "expr": "p1 <= p2 * 0.8", "unit": "",
        "doc": "Structural derating rule",
    })

    text = export_sysml_v2(store)

    # Export emits a real constraint def block.
    assert "// Definitions" in text
    assert "constraint def <'DERATE-1'> DERATE_1 {" in text
    assert "Structural derating rule" in text
    assert "in p1;" in text
    assert "in p2;" in text
    assert "p1 <= p2 * 0.8" in text

    # Re-import restores id, parameters, expr, and doc.
    parsed = parse_sysml(text)
    defs = parsed["definitions"]
    assert len(defs) == 1
    d = defs[0]
    assert d["id"] == "DERATE-1"
    assert d["type"] == "constraint"
    assert d["parameters"] == ["p1", "p2"]
    assert d["expr"] == "p1 <= p2 * 0.8"
    assert d["doc"] == "Structural derating rule"


# ── 2. calc def with unit ────────────────────────────────────────────────────

def test_calc_def_round_trips_unit(tmp_path):
    store = _store(tmp_path)
    store.write_item("definitions", "MARGIN", {
        "id": "MARGIN", "type": "calc",
        "name": "Margin", "parameters": ["actual", "limit"],
        "expr": "(limit - actual) / limit * 100", "unit": "%",
        "doc": "Percentage margin",
    })

    text = export_sysml_v2(store)
    assert "calc def MARGIN {" in text
    assert "return [%] (limit - actual) / limit * 100" in text

    parsed = parse_sysml(text)
    d = parsed["definitions"][0]
    assert d["type"] == "calc"
    assert d["unit"] == "%"
    assert d["expr"] == "(limit - actual) / limit * 100"


# ── 3. constraint bound to a def ──────────────────────────────────────────────

def test_constraint_bound_to_def_round_trips_constraint_def_and_bindings(tmp_path):
    store = _store(tmp_path)
    store.write_item("definitions", "DERATE-1", {
        "id": "DERATE-1", "type": "constraint",
        "name": "Derate", "parameters": ["p1", "p2"],
        "expr": "p1 <= p2 * 0.8", "unit": "",
        "doc": "",
    })
    store.create_requirement({
        "id": "REQ-001", "name": "Test",
        "constraints": [{
            "expr": "p1 <= p2 * 0.8",
            "constraint_def": "DERATE-1",
            "bindings": {"p1": "mtow", "p2": "struct_limit"},
        }],
    })

    text = export_sysml_v2(store)

    # The expanded expression is still emitted (backward-compatibility guarantee).
    assert "mtow <= struct_limit * 0.8" in text

    # The binding annotations ride alongside.
    def_line = [ln for ln in text.splitlines() if "require constraint" in ln][0]
    assert "@def=DERATE-1" in def_line
    assert "@bind=p1:mtow,p2:struct_limit" in def_line

    # Re-import restores constraint_def and bindings.
    parsed = parse_sysml(text)
    reqs = parsed["requirements"]
    assert len(reqs) == 1
    cons = reqs[0].get("constraints", [])
    assert len(cons) == 1
    assert cons[0]["constraint_def"] == "DERATE-1"
    assert cons[0]["bindings"] == {"p1": "mtow", "p2": "struct_limit"}
    # The expanded expression is also preserved.
    assert cons[0]["expr"] == "mtow <= struct_limit * 0.8"


# ── 4. parameter bound to a calc_def ─────────────────────────────────────────

def test_param_bound_to_calc_def_round_trips_calc_def_and_bindings(tmp_path):
    store = _store(tmp_path)
    store.write_item("definitions", "MARGIN", {
        "id": "MARGIN", "type": "calc",
        "name": "Margin", "parameters": ["actual", "limit"],
        "expr": "(limit - actual) / limit * 100", "unit": "%",
        "doc": "",
    })
    store.create_requirement({
        "id": "REQ-002", "name": "Derived",
        "parameters": [{
            "name": "margin", "expr": "(limit - actual) / limit * 100",
            "calc_def": "MARGIN",
            "bindings": {"actual": "mtow", "limit": "struct_limit"},
        }],
    })

    text = export_sysml_v2(store)

    # The expanded expression is still emitted.
    assert "(struct_limit - mtow) / struct_limit * 100" in text

    # The binding annotations ride alongside.
    attr_line = [ln for ln in text.splitlines() if "attribute margin" in ln][0]
    assert "@def=MARGIN" in attr_line
    assert "@bind=actual:mtow,limit:struct_limit" in attr_line

    # Re-import restores calc_def and bindings.
    parsed = parse_sysml(text)
    req = parsed["requirements"][0]
    params = req.get("parameters", [])
    assert len(params) == 1
    assert params[0]["calc_def"] == "MARGIN"
    assert params[0]["bindings"] == {"actual": "mtow", "limit": "struct_limit"}
    assert params[0]["expr"] == "(struct_limit - mtow) / struct_limit * 100"


# ── 5. @kind= and @def= coexist on the same line ─────────────────────────────

def test_kind_and_def_annotations_coexist_on_same_line(tmp_path):
    store = _store(tmp_path)
    store.write_item("definitions", "DERATE-1", {
        "id": "DERATE-1", "type": "constraint",
        "name": "Derate", "parameters": ["p1", "p2"],
        "expr": "p1 <= p2 * 0.8", "unit": "",
        "doc": "",
    })
    store.create_requirement({
        "id": "REQ-003", "name": "Test",
        "constraints": [{
            "expr": "p1 <= p2 * 0.8",
            "constraint_def": "DERATE-1",
            "bindings": {"p1": "mtow", "p2": "struct_limit"},
            "kind": "TPM",
        }],
    })

    text = export_sysml_v2(store)
    req_line = [ln for ln in text.splitlines() if "require constraint" in ln][0]
    assert "@kind=TPM" in req_line
    assert "@def=DERATE-1" in req_line

    # Both survive re-import.
    parsed = parse_sysml(text)
    req = parsed["requirements"][0]
    cons = req["constraints"]
    assert len(cons) == 1
    assert cons[0]["kind"] == "TPM"
    assert cons[0]["constraint_def"] == "DERATE-1"


# ── 6. analysis case round-trips with scope, scope_components, overrides ────

def test_analysis_case_round_trips(tmp_path):
    store = _store(tmp_path)
    store.write_item("analysis_cases", "AC-1", {
        "id": "AC-1", "name": "Worst case",
        "doc": "Worst-case fuel load",
        "scope": ["REQ-001", "REQ-002"],
        "scope_components": ["WING", "TAIL"],
        "overrides": {"AFRM0001.mass": 1200.0, "AFRM0001.fuel": 210.0},
    })

    text = export_sysml_v2(store)

    assert "// Analysis Cases" in text
    assert "analysis case def <'AC-1'> AC_1 {" in text
    assert "Worst-case fuel load" in text
    assert "// @scope=REQ-001,REQ-002" in text
    assert "// @scope_components=WING,TAIL" in text
    assert "// @override=AFRM0001.mass=1200" in text
    assert "// @override=AFRM0001.fuel=210" in text

    # Re-import restores everything.
    parsed = parse_sysml(text)
    cases = parsed["analysis_cases"]
    assert len(cases) == 1
    c = cases[0]
    assert c["id"] == "AC-1"
    assert c["doc"] == "Worst-case fuel load"
    assert c["scope"] == ["REQ-001", "REQ-002"]
    assert c["scope_components"] == ["WING", "TAIL"]
    assert c["overrides"] == {"AFRM0001.mass": 1200.0, "AFRM0001.fuel": 210.0}


# ── 7. analysis case with empty scope emits no @scope= line ──────────────────

def test_analysis_case_empty_scope_emits_no_scope_line(tmp_path):
    store = _store(tmp_path)
    store.write_item("analysis_cases", "EMPTY-SCOPE", {
        "id": "EMPTY-SCOPE", "name": "Empty",
        "doc": "",
        "scope": [],
        "scope_components": [],
        "overrides": {},
    })

    text = export_sysml_v2(store)
    assert "// Analysis Cases" in text
    assert "@scope=" not in text
    assert "@scope_components=" not in text

    parsed = parse_sysml(text)
    c = parsed["analysis_cases"][0]
    assert c["scope"] == []
    assert c["scope_components"] == []


# ── 8. project without defs or analysis cases ────────────────────────────────

def test_project_without_defs_or_analysis_cases_exports_and_imports(tmp_path):
    store = _store(tmp_path)
    store.create_requirement({"id": "REQ-001", "name": "Plain"})

    text = export_sysml_v2(store)
    assert "// Definitions" not in text
    assert "// Analysis Cases" not in text

    parsed = parse_sysml(text)
    assert parsed["definitions"] == []
    assert parsed["analysis_cases"] == []
    assert len(parsed["requirements"]) == 1


# ── 9. replace mode removes pre-existing definition ──────────────────────────

def test_replace_mode_removes_pre_existing_definition(tmp_path):
    """A definition in the target store that is not in the incoming file
    must be removed by the replace-mode deletion."""
    src = _store(tmp_path)
    src.write_item("definitions", "KEEP-ME", {
        "id": "KEEP-ME", "type": "constraint",
        "name": "Keep", "parameters": ["x"],
        "expr": "x > 0", "unit": "", "doc": "",
    })

    text = export_sysml_v2(src)
    parsed = parse_sysml(text)

    tgt = _fresh(tmp_path)
    # Pre-populate with a definition that is NOT in the incoming file.
    tgt.write_item("definitions", "PRE-EXISTING", {
        "id": "PRE-EXISTING", "type": "calc",
        "name": "Old", "parameters": ["a", "b"],
        "expr": "a + b", "unit": "m", "doc": "",
    })
    assert tgt.list_items("definitions")  # precondition

    import_into_store(tgt, parsed, mode="replace")

    defs = tgt.list_items("definitions")
    ids = {d["id"] for d in defs}
    assert "KEEP-ME" in ids, "incoming definition should survive"
    assert "PRE-EXISTING" not in ids, (
        "pre-existing definition not in the incoming file must be removed"
    )


# ── 10. malformed definition id is skipped and counted ───────────────────────

def test_definition_with_malformed_id_is_skipped(tmp_path):
    """A definition id that fails _clean_id is skipped (counted), and the
    rest of the import still lands."""
    tgt = _fresh(tmp_path)
    parsed = {
        "requirements": [
            {"id": "REQ-K", "name": "Good Req", "description": "",
             "type": "functional", "status": "proposed", "priority": "medium",
             "verification_method": "test"},
        ],
        "components": [],
        "verification_cases": [],
        "traces": [],
        "definitions": [
            {"id": "..", "type": "constraint", "name": "Bad",
             "parameters": ["x"], "expr": "x > 0", "unit": "", "doc": ""},
            {"id": "OK-ONE", "type": "calc", "name": "Good",
             "parameters": ["a"], "expr": "a + 1", "unit": "", "doc": ""},
        ],
        "analysis_cases": [],
    }

    summary = import_into_store(tgt, parsed, mode="replace")
    assert summary["skipped"] >= 1, "malformed definition should be skipped"
    assert summary.get("definitions", 0) == 1, "the valid definition should be written"
    assert tgt.get_requirement("REQ-K") is not None, "rest of import must still land"


# ── A def with no expression must not adopt its own opener ────────────────────

def test_definition_without_an_expression_is_not_given_the_opener_line(tmp_path):
    """The expression is recognised by elimination — the body line that is not
    `in`, `doc` or `return`. The opener passes that test too, so a def with no
    expression line would otherwise store `constraint def X {` as its rule, and
    importer.py's empty-expr guard could not catch it because it isn't empty."""
    text = """package P {
  constraint def EMPTY_DEF {
    doc /* nothing here */
    in p1;
  }
  constraint def GOOD_DEF {
    in p1;
    in p2;
    p1 <= p2 * 0.8
  }
}"""
    by_id = {d["id"]: d for d in parse_sysml(text)["definitions"]}

    assert by_id["EMPTY_DEF"]["expr"] == ""
    assert by_id["GOOD_DEF"]["expr"] == "p1 <= p2 * 0.8"


def test_expressionless_definition_is_skipped_not_written(tmp_path):
    """The parse-level guard above only matters if the write path honours it."""
    store = _store(tmp_path)
    parsed = {"definitions": [
        {"id": "NO-EXPR", "type": "constraint", "name": "No expr",
         "parameters": ["p1"], "expr": "", "unit": "", "doc": ""},
        {"id": "HAS-EXPR", "type": "constraint", "name": "Has expr",
         "parameters": ["p1"], "expr": "p1 > 0", "unit": "", "doc": ""},
    ]}
    summary = import_into_store(store, parsed, mode="merge")

    stored = {d["id"] for d in store.list_items("definitions")}
    assert stored == {"HAS-EXPR"}
    assert summary["definitions"] == 1
    assert summary["skipped"] == 1
