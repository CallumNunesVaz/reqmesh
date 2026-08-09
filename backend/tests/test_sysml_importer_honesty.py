"""SysML v2 importer honesty: accept more, refuse less, report what was dropped.

Covers part usages, structural-model acceptance, and ignored-construct reporting.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.demo_seed import PROJECT_ID, seed_demo_project
from app.services.importer import import_into_store
from app.services.reqif_import import parse_reqif
from app.services.sysml_export import export_sysml_v2
from app.services.sysml_import import SysMLParseError, parse_sysml
from app.services.yaml_store import YamlStore


def _store(tmp_path: Path) -> YamlStore:
    root = tmp_path / "project"
    root.mkdir()
    store = YamlStore(root)
    store.ensure_dirs()
    store.write_meta({"name": "Test"})
    return store


@pytest.fixture
def seeded(tmp_path):
    """The bundled demo project."""
    seed_demo_project(tmp_path, force=True)
    return YamlStore(tmp_path / PROJECT_ID)


# ── 1. part usage imports a component ───────────────────────────────────────

def test_part_usage_imports_component():
    text = """\
part WING {
    attribute mass = 120 [kg];
}"""
    parsed = parse_sysml(text)
    comps = parsed["components"]
    assert len(comps) == 1
    assert comps[0]["id"] == "WING"
    assert any(p["name"] == "mass" and p.get("value") == 120 and p.get("unit") == "kg"
               for p in comps[0]["parameters"])


# ── 2. part usage with type reference counts part_typing ────────────────────

def test_part_usage_with_type_counts_part_typing():
    text = """\
part WING : Airframe {
}"""
    parsed = parse_sysml(text)
    assert len(parsed["components"]) == 1
    assert parsed["components"][0]["id"] == "WING"
    ignored = parsed["ignored"]
    assert ignored["constructs"].get("part_typing") == 1
    assert ignored["lines"] == 1


# ── 3. nested part usage inherits parent ─────────────────────────────────────

def test_nested_part_usage_inside_part_def():
    text = """\
part def FUSELAGE {
    part WING {
    }
}"""
    parsed = parse_sysml(text)
    assert len(parsed["components"]) == 2
    fuselage = next(c for c in parsed["components"] if c["id"] == "FUSELAGE")
    wing = next(c for c in parsed["components"] if c["id"] == "WING")
    assert wing.get("parent") == fuselage["id"]


# ── 4. part def behaviour is unchanged ──────────────────────────────────────

def test_part_def_still_imports():
    text = """\
part def FUSELAGE {
    attribute length = 30 [m];
}"""
    parsed = parse_sysml(text)
    assert len(parsed["components"]) == 1
    c = parsed["components"][0]
    assert c["id"] == "FUSELAGE"
    assert any(p["name"] == "length" for p in c["parameters"])
    assert parsed["ignored"]["lines"] == 0


# ── 5. model with components but no requirement def imports successfully ─────

def test_components_without_requirements_imports():
    text = """\
part def WING {
    attribute span = 15 [m];
}
part FUSELAGE {
    attribute length = 30 [m];
}"""
    parsed = parse_sysml(text)
    assert len(parsed["components"]) == 2
    assert len(parsed.get("requirements", [])) == 0


# ── 6. model with only definitions imports successfully ──────────────────────

def test_only_definitions_imports():
    text = """\
constraint def MARGIN {
    in actual;
    in limit;
    return (limit - actual) / limit * 100;
}"""
    parsed = parse_sysml(text)
    assert len(parsed.get("requirements", [])) == 0
    assert len(parsed["definitions"]) == 1
    assert parsed["definitions"][0]["id"] == "MARGIN"


# ── 7. genuinely empty / irrelevant file still raises ────────────────────────

def test_empty_text_raises():
    with pytest.raises(SysMLParseError, match="No SysML v2 entities found"):
        parse_sysml("")


def test_irrelevant_text_raises():
    with pytest.raises(SysMLParseError, match="No SysML v2 entities found"):
        parse_sysml("This is not SysML.\nJust some random text.\n")


# ── 8. ports, connects and states are reported in ignored.constructs ─────────

def test_ignored_constructs_reported():
    text = """\
part def WING {
    port p1;
    port p2;
    port p3;
    connect c1;
    connect c2;
    state idle {
        entry / reset_timer;
    }
}"""
    parsed = parse_sysml(text)
    assert len(parsed["components"]) == 1
    constructs = parsed["ignored"]["constructs"]
    # 3 port lines, 2 connect lines, 1 state, 1 entry
    assert constructs.get("port") == 3
    assert constructs.get("connect") == 2
    assert constructs.get("state") == 1
    assert constructs.get("entry") == 1
    # lines = sum of all construct values
    assert parsed["ignored"]["lines"] == sum(constructs.values())


# ── 9. word-boundary: portName / state_of_charge are NOT counted ─────────────

def test_word_boundary_not_counted():
    text = """\
part def WING {
    portName = 3;
    state_of_charge = 100;
    port p1;
}"""
    parsed = parse_sysml(text)
    constructs = parsed["ignored"]["constructs"]
    # Only the bare "port p1;" line should be counted.
    assert constructs.get("port") == 1
    assert "state" not in constructs


# ── 10. clean reqmesh export round-trips with ignored.lines == 0 ─────────────

def test_round_trip_has_zero_ignored(seeded):
    text = export_sysml_v2(seeded)
    parsed = parse_sysml(text)
    assert parsed["ignored"]["lines"] == 0, (
        f"reqmesh's own export produced {parsed['ignored']['lines']} ignored lines: "
        f"{parsed['ignored']['constructs']}"
    )


# ── 11. import_into_store carries ignored onto summary ───────────────────────

def test_import_into_store_carries_ignored(tmp_path):
    store = _store(tmp_path)
    text = """\
part WING : Airframe {
    port p1;
}"""
    parsed = parse_sysml(text)
    summary = import_into_store(store, parsed)
    assert summary.get("ignored") is not None
    assert summary["ignored"]["lines"] > 0
    assert summary["ignored"]["constructs"].get("part_typing") == 1
    assert summary["ignored"]["constructs"].get("port") == 1


def test_reqif_path_gets_zero_ignored_default(tmp_path):
    """The ReqIF parser produces no ``ignored`` key; the importer gives the
    zero default so the field is always present."""
    store = _store(tmp_path)
    # Minimal valid ReqIF XML the parser can handle.
    reqif_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<REQ-IF xmlns="http://www.omg.org/spec/ReqIF/20110401/reqif.xsd">'
        '<CORE-CONTENT><REQ-IF-CONTENT><SPEC-OBJECTS>'
        '<SPEC-OBJECT IDENTIFIER="r1" LAST-CHANGE="2024-01-01T00:00:00">'
        '<VALUES><ATTRIBUTE-VALUE-STRING THE-VALUE="Hello"/></VALUES>'
        '<TYPE><SPEC-OBJECT-TYPE REF="t1"/></TYPE>'
        '</SPEC-OBJECT>'
        '</SPEC-OBJECTS><SPEC-TYPES><SPEC-OBJECT-TYPE IDENTIFIER="t1" LAST-CHANGE="2024-01-01T00:00:00">'
        '<SPEC-ATTRIBUTES><ATTRIBUTE-DEFINITION-STRING IDENTIFIER="a1" LONG-NAME="Description" LAST-CHANGE="2024-01-01T00:00:00"/>'
        '</SPEC-ATTRIBUTES></SPEC-OBJECT-TYPE></SPEC-TYPES></REQ-IF-CONTENT></CORE-CONTENT></REQ-IF>'
    )
    parsed = parse_reqif(reqif_xml)
    summary = import_into_store(store, parsed)
    assert summary.get("ignored") == {"lines": 0, "constructs": {}}


# ── The `ignored` field is guaranteed on every format ─────────────────────────

def test_every_import_format_returns_an_ignored_report(client):
    """The client reads `ignored.lines` unconditionally. Only the SysML parser
    can populate it, so the spreadsheet paths — which never reach
    import_into_store — must still carry the zero default or the import dialog
    throws on an otherwise successful CSV import."""
    pid = "ignored-report-probe"
    r = client.post("/api/projects", json={"id": pid, "name": "Probe"})
    assert r.status_code in (200, 201, 409), r.text

    cases = {
        "csv": ("r.csv", b"id,name,description\nREQ-1,One,Hello\n"),
        "tsv": ("r.tsv", b"id\tname\tdescription\nREQ-2\tTwo\tHello\n"),
        "sysml": ("m.sysml", b"package P {\n  requirement def REQ_3 {\n    doc /* Three */\n  }\n}\n"),
    }
    for fmt, (filename, payload) in cases.items():
        resp = client.post(
            f"/api/projects/{pid}/import",
            files={"file": (filename, payload)},
            data={"format": fmt, "mode": "merge"},
        )
        assert resp.status_code == 200, f"{fmt}: {resp.text}"
        body = resp.json()
        assert "ignored" in body, f"{fmt} summary has no ignored report"
        assert isinstance(body["ignored"]["lines"], int)
        assert isinstance(body["ignored"]["constructs"], dict)
