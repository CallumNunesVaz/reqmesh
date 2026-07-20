"""SysML v2 round-trip of parametrics (Slice 1): parameters, constraints,
assume/require, measure kinds, subject, and the component tree survive
export → import, and evaluation verdicts are unchanged."""

from pathlib import Path

from app.services.yaml_store import YamlStore
from app.services.sysml_export import export_sysml_v2
from app.services.sysml_import import parse_sysml
from app.services.importer import import_into_store
from app.services.evaluation import evaluate_project


def _seed(root: Path) -> YamlStore:
    store = YamlStore(root)
    store.ensure_dirs()
    store.write_meta({"name": "RT"})
    store.create_requirement({
        "id": "GROS0001", "name": "Gross weight", "subject": "WING",
        "parameters": [{"name": "mass", "value": 767.0, "unit": "kg", "kind": "MOP"}],
        "constraints": [{"expr": "mass <= 1157", "assume": "config == 1", "kind": "TPM"}],
    })
    store.create_requirement({
        "id": "DERV0001", "name": "Derived",
        "parameters": [{"name": "empty", "expr": "GROS0001.mass - 200", "unit": "kg"}],
        "constraints": [{"expr": "empty <= 600"}],
    })
    store.create_component({"id": "WING", "name": "Wing", "quantity": 1,
                            "parameters": [{"name": "mass", "value": 120.0, "unit": "kg"}],
                            "satisfies": ["GROS0001"]})
    store.create_component({"id": "SPAR", "name": "Spar", "parent": "WING", "quantity": 2,
                            "parameters": [{"name": "mass", "value": 30.0, "unit": "kg"}]})
    return store


def test_sysml_parametrics_roundtrip(tmp_path):
    src = _seed(tmp_path / "src")
    text = export_sysml_v2(src)

    # Export emits the SysML v2 parametric constructs.
    assert "attribute mass = 767 [kg];" in text
    assert "assume constraint { config == 1 }" in text
    assert "require constraint { mass <= 1157 }" in text
    assert "@kind=MOP" in text and "@kind=TPM" in text
    assert "subject WING;" in text
    assert "part def WING {" in text
    assert "satisfy requirement GROS0001;" in text

    parsed = parse_sysml(text)
    dst = YamlStore(tmp_path / "dst")
    dst.ensure_dirs()
    dst.write_meta({"name": "RT2"})
    summary = import_into_store(dst, parsed, mode="replace")
    assert summary["components"] == 2

    r = dst.get_requirement("GROS0001")
    assert r["parameters"] == [{"name": "mass", "unit": "kg", "value": 767.0, "kind": "MOP"}]
    assert r["constraints"] == [{"expr": "mass <= 1157", "assume": "config == 1", "kind": "TPM"}]
    assert r["subject"] == "WING"

    d = dst.get_requirement("DERV0001")
    assert d["parameters"][0]["expr"] == "GROS0001.mass - 200"

    spar = dst.get_component("SPAR")
    assert spar["parent"] == "WING" and spar["quantity"] == 2
    assert spar["parameters"][0]["value"] == 30.0
    assert dst.get_component("WING")["satisfies"] == ["GROS0001"]

    # Verdicts identical across the round-trip.
    v_src = {i["id"]: i["verdict"] for i in evaluate_project(src)["requirements"]}
    v_dst = {i["id"]: i["verdict"] for i in evaluate_project(dst)["requirements"]}
    assert v_src == v_dst
