"""Tests for ReqIF / SysML import (Phase 3) and the /import endpoint."""

from __future__ import annotations

import io

from app.services.reqif_import import ReqIFParseError, parse_reqif
from app.services.sysml_import import SysMLParseError, parse_sysml

from .conftest import make_req


# ── Unit: parsers ─────────────────────────────────────────────────────────────

def test_parse_reqif_roundtrip():
    from app.services.reqif_export import export_reqif
    from app.services.yaml_store import YamlStore
    import tempfile
    from pathlib import Path

    root = Path(tempfile.mkdtemp())
    store = YamlStore(root)
    store.ensure_dirs()
    store.write_meta({"name": "Src"})
    store.create_requirement({
        "id": "SYST0001", "name": "Auth", "description": "<p>Shall authenticate.</p>",
        "status": "approved", "priority": "high", "type": "functional",
    })
    store.create_requirement({"id": "SYST0002", "name": "Logging"})
    store.write_traces({"links": [{"source": "SYST0001", "target": "SYST0002", "type": "derives"}]})

    parsed = parse_reqif(export_reqif(store))
    by_id = {r["id"]: r for r in parsed["requirements"]}
    assert set(by_id) == {"SYST0001", "SYST0002"}
    assert by_id["SYST0001"]["name"] == "Auth"
    assert by_id["SYST0001"]["status"] == "approved"
    assert by_id["SYST0001"]["priority"] == "high"
    assert "authenticate" in by_id["SYST0001"]["description"]
    assert any(t["source"] == "SYST0001" and t["target"] == "SYST0002" for t in parsed["traces"])


def test_parse_reqif_rejects_garbage():
    try:
        parse_reqif("this is not xml at all <<<")
        assert False, "expected ReqIFParseError"
    except ReqIFParseError:
        pass


def test_parse_sysml_basic():
    text = """
    package Demo {
      requirement def SYST0001 {
        doc /* Top requirement */
        :>> status = approved;
        :>> priority = high;
        text /* "The system shall work" */
        requirement def SYST0002 {
          doc /* Child requirement */
          derive requirement SYST0001;
        }
      }

      // Verification Cases
      requirement def VC0001 {
        doc /* Smoke test */
        :>> status = pending;
        :>> method = test;
        verify requirement SYST0001;
      }
    }
    """
    parsed = parse_sysml(text)
    by_id = {r["id"]: r for r in parsed["requirements"]}
    assert set(by_id) == {"SYST0001", "SYST0002"}
    assert by_id["SYST0001"]["name"] == "Top requirement"
    assert by_id["SYST0001"]["status"] == "approved"
    assert "work" in by_id["SYST0001"].get("description", "")
    # Child parent relationship reconstructed from nesting.
    assert by_id["SYST0002"]["parent"] == "SYST0001"
    assert any(r["type"] == "derives" and r["target"] == "SYST0001" for r in by_id["SYST0002"]["relations"])
    # Verification case captured separately.
    vcs = {v["id"]: v for v in parsed["verification_cases"]}
    assert "VC0001" in vcs
    assert vcs["VC0001"]["verified_requirements"] == ["SYST0001"]


def test_parse_sysml_rejects_garbage():
    try:
        parse_sysml("just some prose without any requirement blocks")
        assert False, "expected SysMLParseError"
    except SysMLParseError:
        pass


# ── Integration: /import endpoint ─────────────────────────────────────────────

def test_import_endpoint_sysml(client, project):
    sysml = (
        "package P {\n"
        "  requirement def SYST0001 {\n"
        "    doc /* Imported req */\n"
        "    :>> status = approved;\n"
        "  }\n"
        "}\n"
    )
    files = {"file": ("model.sysml", io.BytesIO(sysml.encode()), "text/plain")}
    res = client.post(f"/api/projects/{project}/import", files=files, data={"format": "auto", "mode": "merge"})
    assert res.status_code == 200, res.text
    summary = res.json()
    assert summary["format"] == "sysml"
    assert summary["created"] == 1

    got = client.get(f"/api/projects/{project}/requirements/SYST0001").json()
    assert got["name"] == "Imported req"
    assert got["status"] == "approved"


def test_import_endpoint_reqif_and_replace(client, project):
    # Seed one requirement, then export it and re-import elsewhere via replace.
    make_req(client, project, "SYST0001", name="Original")
    from app.services.yaml_store import YamlStore
    store = YamlStore(Path_data_root(project))
    from app.services.reqif_export import export_reqif
    reqif = export_reqif(store)

    # A second requirement that 'replace' should wipe.
    make_req(client, project, "SYST0002", name="ToBeRemoved")

    files = {"file": ("out.xml", io.BytesIO(reqif.encode()), "application/xml")}
    res = client.post(f"/api/projects/{project}/import", files=files, data={"format": "reqif", "mode": "replace"})
    assert res.status_code == 200, res.text
    ids = {r["id"] for r in client.get(f"/api/projects/{project}/requirements").json()}
    assert ids == {"SYST0001"}


def test_import_endpoint_rejects_bad_file(client, project):
    files = {"file": ("bad.xml", io.BytesIO(b"<not-reqif/>"), "application/xml")}
    res = client.post(f"/api/projects/{project}/import", files=files, data={"format": "reqif", "mode": "merge"})
    assert res.status_code == 400


def Path_data_root(project_id: str):
    from pathlib import Path
    from app.core.config import settings
    return Path(settings.data_root) / project_id
