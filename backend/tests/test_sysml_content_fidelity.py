"""SysML v2 content fidelity: descriptions, relations, and verification cases.

Three silent losses in the SysML v2 interchange fixed here:
- Descriptions truncated at 500 chars with raw HTML leaking in
- Relation types outside {refines, satisfies, derives} vanishing
- Verification cases exported as ``requirement def``
"""

from __future__ import annotations

from pathlib import Path

from app.services.sysml_export import export_sysml_v2
from app.services.sysml_import import parse_sysml
from app.services.yaml_store import YamlStore


def _store(tmp_path: Path) -> YamlStore:
    root = tmp_path / "project"
    root.mkdir(parents=True, exist_ok=True)
    store = YamlStore(root)
    store.ensure_dirs()
    store.write_meta({"name": "Fidelity"})
    return store


# ── 1. Long description round-trips in full ────────────────────────────────────

def test_long_description_round_trips_in_full(tmp_path):
    store = _store(tmp_path)
    long_desc = "The system shall " + " ".join(f"perform_{i}" for i in range(150))
    assert len(long_desc) >= 900, f"precondition: {len(long_desc)}"

    store.create_requirement({
        "id": "REQ-001",
        "name": "Long Desc",
        "description": long_desc,
    })

    text = export_sysml_v2(store)
    parsed = parse_sysml(text)
    reqs = parsed["requirements"]
    assert len(reqs) == 1
    assert reqs[0]["description"] == long_desc


# ── 2. HTML is stripped ────────────────────────────────────────────────────────

def test_html_description_stripped_on_export_and_import(tmp_path):
    store = _store(tmp_path)
    store.create_requirement({
        "id": "REQ-002",
        "name": "HTML Desc",
        "description": "<p>Load is <b>1200</b> kg</p>",
    })

    text = export_sysml_v2(store)
    # No raw HTML should appear in the emitted text
    assert "<" not in text or "Load is" not in _lines_containing(text, "<")
    # Specifically no tag open/close brackets in the description text area
    assert "<p>" not in text
    assert "<b>" not in text

    parsed = parse_sysml(text)
    reqs = parsed["requirements"]
    assert len(reqs) == 1
    assert reqs[0]["description"] == "Load is 1200 kg"


def _lines_containing(text: str, needle: str) -> list[str]:
    return [line for line in text.splitlines() if needle in line]


# ── 3. */ in description doesn't break the block comment ───────────────────────

def test_description_with_star_slash_does_not_break_block(tmp_path):
    store = _store(tmp_path)
    store.create_requirement({
        "id": "REQ-003",
        "name": "StarSlash",
        "description": "Regex pattern is /* comment */ important",
    })

    text = export_sysml_v2(store)
    parsed = parse_sysml(text)
    reqs = parsed["requirements"]
    assert len(reqs) == 1
    # The crucial thing: the status line still parses after the text comment.
    req = reqs[0]
    assert req["status"] == "proposed", (
        f"status not parsed — */ likely broke the block comment: {req.get('status')!r}"
    )


# ── 4. Long rationale and source are not truncated ─────────────────────────────

def test_long_rationale_not_truncated(tmp_path):
    store = _store(tmp_path)
    rationale = "Reason: " + " ".join(f"point_{i}" for i in range(120))
    assert len(rationale) >= 700, f"precondition: {len(rationale)}"

    store.create_requirement({
        "id": "REQ-004",
        "name": "Rationale",
        "rationale": rationale,
    })

    text = export_sysml_v2(store)
    parsed = parse_sysml(text)
    reqs = parsed["requirements"]
    assert len(reqs) == 1
    assert reqs[0]["rationale"] == rationale


def test_long_source_not_truncated(tmp_path):
    store = _store(tmp_path)
    source = "Source: " + " ".join(f"ref_{i}" for i in range(70))
    assert len(source) >= 400, f"precondition: {len(source)}"

    store.create_requirement({
        "id": "REQ-005",
        "name": "Source",
        "source": source,
    })

    text = export_sysml_v2(store)
    parsed = parse_sysml(text)
    reqs = parsed["requirements"]
    assert len(reqs) == 1
    assert reqs[0]["source"] == source


# ── 5. All six relation types round-trip ───────────────────────────────────────

def test_all_six_relation_types_round_trip(tmp_path):
    store = _store(tmp_path)
    store.create_requirement({
        "id": "REQ-010",
        "name": "Source",
        "relations": [
            {"type": "refines",   "target": "REQ-T1"},
            {"type": "satisfies", "target": "REQ-T2"},
            {"type": "verified_by", "target": "REQ-T3"},
            {"type": "derives",   "target": "REQ-T4"},
            {"type": "conflicts", "target": "REQ-T5"},
            {"type": "duplicates","target": "REQ-T6"},
        ],
    })

    text = export_sysml_v2(store)
    parsed = parse_sysml(text)
    reqs = parsed["requirements"]
    assert len(reqs) == 1
    rels = {r["type"]: r["target"] for r in reqs[0].get("relations", [])}
    assert rels == {
        "refines": "REQ_T1",
        "satisfies": "REQ_T2",
        "verified_by": "REQ_T3",
        "derives": "REQ_T4",
        "conflicts": "REQ_T5",
        "duplicates": "REQ_T6",
    }


# ── 6. verified_by is not satisfy ──────────────────────────────────────────────

def test_verified_by_not_satisfy(tmp_path):
    store = _store(tmp_path)
    store.create_requirement({
        "id": "REQ-020",
        "name": "Verification Owner",
        "relations": [{"type": "verified_by", "target": "VC-01"}],
    })

    text = export_sysml_v2(store)
    # The substring "satisfy" must not appear in a line about this relation.
    # Find the relevant lines.
    rel_lines = [ln for ln in text.splitlines() if "VC_01" in ln]
    for line in rel_lines:
        assert "satisfy" not in line.lower(), (
            f"verified_by emitted as satisfy: {line!r}"
        )

    parsed = parse_sysml(text)
    reqs = parsed["requirements"]
    assert len(reqs) == 1
    rels = reqs[0].get("relations", [])
    assert len(rels) == 1
    assert rels[0]["type"] == "verified_by"


# ── 7. Unknown relation type round-trips unchanged ─────────────────────────────

def test_unknown_relation_type_round_trips(tmp_path):
    store = _store(tmp_path)
    store.create_requirement({
        "id": "REQ-030",
        "name": "Unknown Rel",
        "relations": [{"type": "traces_to", "target": "REQ-031"}],
    })

    text = export_sysml_v2(store)
    assert "@rel=traces_to" in text
    assert "requirement REQ_031" not in text  # no keyword emitted for unknown type

    parsed = parse_sysml(text)
    reqs = parsed["requirements"]
    assert len(reqs) == 1
    rels = reqs[0].get("relations", [])
    assert len(rels) == 1
    assert rels[0]["type"] == "traces_to"
    assert rels[0]["target"] == "REQ_031"


# ── 8. Verification case emits verification case def ───────────────────────────

def test_verification_case_emits_verification_case_def(tmp_path):
    store = _store(tmp_path)
    store.create_verification_case({
        "id": "VC-01",
        "name": "Static load test",
        "status": "pending",
        "method": "test",
    })

    text = export_sysml_v2(store)
    assert "verification case def" in text, (
        "verification case must emit `verification case def`, not `requirement def`"
    )
    # The exported text must not contain `requirement def` for this VC id.
    vc_safe = "VC_01"
    lines_with_vc = [
        ln for ln in text.splitlines()
        if vc_safe in ln and "requirement def" in ln
    ]
    assert len(lines_with_vc) == 0, (
        f"VC {vc_safe!r} should not appear in a `requirement def` line: {lines_with_vc}"
    )

    # And the short-name form should also work
    p2 = tmp_path / "p2"
    p2.mkdir()
    store2 = _store(p2)
    store2.create_verification_case({
        "id": "VC-02",
        "name": "Dynamic test",
    })
    text2 = export_sysml_v2(store2)
    assert "verification case def" in text2


# ── 9. VC round-trips with verified_requirements ───────────────────────────────

def test_verification_case_round_trips_with_verified_requirements(tmp_path):
    store = _store(tmp_path)
    store.create_requirement({"id": "REQ-VC-1", "name": "Target Req"})
    store.create_verification_case({
        "id": "VC-10",
        "name": "Integration test",
        "verified_requirements": ["REQ-VC-1"],
    })

    text = export_sysml_v2(store)
    parsed = parse_sysml(text)

    vcs = parsed["verification_cases"]
    assert len(vcs) == 1
    assert vcs[0]["id"] == "VC-10"
    assert vcs[0]["verified_requirements"] == ["REQ-VC-1"]

    # Also check no requirements were created from the VC
    req_ids = {r["id"] for r in parsed["requirements"]}
    assert "VC-10" not in req_ids, "verification case leaked into requirements"


# ── 10. Backward compatibility ─────────────────────────────────────────────────

def test_backward_compatible_old_format_vc_imports_as_vc(tmp_path):
    """A file in the old format (verification cases as ``requirement def``
    under the ``// Verification Cases`` comment) still imports as verification
    cases, not requirements."""
    old_format = """// Test
package Legacy {
  requirement def REQ_A {
    doc /* Requirement A */
  }

  // Verification Cases
  requirement def VC_OLD {
    doc /* Old format VC */
    :>> status = passed;
    :>> method = test;
    verify requirement REQ_A;
  }
}
"""
    parsed = parse_sysml(old_format)
    vcs = parsed["verification_cases"]
    reqs = parsed["requirements"]

    assert len(vcs) == 1, f"expected 1 VC, got {len(vcs)}: {vcs}"
    assert vcs[0]["id"] == "VC_OLD"
    assert vcs[0]["name"] == "Old format VC"
    assert vcs[0]["verified_requirements"] == ["REQ_A"]

    assert "VC_OLD" not in {r["id"] for r in reqs}, (
        "old-format VC leaked into requirements"
    )


# ── Block boundaries survive the HTML strip ───────────────────────────────────

def test_block_boundaries_do_not_weld_words_together(tmp_path):
    """Stripping the tags without putting a separator back turns two paragraphs
    into one run-on word. Descriptions are TipTap rich text, so multi-paragraph
    and bulleted content is the normal case, not an edge case."""
    store = _store(tmp_path)
    store.create_requirement({
        "id": "REQ-BLOCKS",
        "name": "Blocks",
        "description": "<p>Para one</p><p>Para two</p><ul><li>alpha</li><li>beta</li></ul>",
    })

    text = export_sysml_v2(store)

    assert "Para onePara two" not in text, "paragraph boundary was dropped"
    assert "alphabeta" not in text, "list-item boundary was dropped"

    parsed = parse_sysml(text)
    desc = parsed["requirements"][0]["description"]
    assert desc.split("\n") == ["Para one", "Para two", "alpha", "beta"]


def test_line_break_becomes_a_newline_not_a_join(tmp_path):
    """`<br>` used to be converted to a newline explicitly; the plain-text pass
    must not regress that to a straight deletion."""
    store = _store(tmp_path)
    store.create_requirement({
        "id": "REQ-BR",
        "name": "Break",
        "description": "Line one<br>Line two",
    })

    parsed = parse_sysml(export_sysml_v2(store))
    assert parsed["requirements"][0]["description"] == "Line one\nLine two"


def test_multiline_rationale_stays_on_one_line(tmp_path):
    """rationale and source are single-line `:>> x = "…";` assignments, so an
    unescaped newline would split the statement for the line-oriented parser."""
    store = _store(tmp_path)
    store.create_requirement({
        "id": "REQ-RAT",
        "name": "Rationale",
        "rationale": "<p>First reason</p><p>Second reason</p>",
        "source": "<p>Doc A</p><p>Doc B</p>",
    })

    text = export_sysml_v2(store)
    rat_lines = [ln for ln in text.splitlines() if ":>> rationale" in ln]
    assert len(rat_lines) == 1 and rat_lines[0].rstrip().endswith('";')

    parsed = parse_sysml(text)
    req = parsed["requirements"][0]
    assert req["rationale"] == "First reason\nSecond reason"
    assert req["source"] == "Doc A\nDoc B"
