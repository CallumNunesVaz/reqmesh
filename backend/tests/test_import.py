"""Tests for ReqIF / SysML import (Phase 3) and the /import endpoint."""

from __future__ import annotations

import io

import pytest

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


def test_import_endpoint_rejects_oversized_upload(client, project, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    oversized = io.BytesIO(b"x" * (2 * 1024 * 1024))  # 2 MB > 1 MB cap
    files = {"file": ("big.sysml", oversized, "text/plain")}
    res = client.post(f"/api/projects/{project}/import", files=files, data={"format": "auto", "mode": "merge"})
    assert res.status_code == 413, res.text
    assert "exceeds" in res.json()["detail"].lower()


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
    ids = {r["id"] for r in client.get(f"/api/projects/{project}/requirements").json()["items"]}
    assert ids == {"SYST0001"}


def test_import_endpoint_rejects_bad_file(client, project):
    files = {"file": ("bad.xml", io.BytesIO(b"<not-reqif/>"), "application/xml")}
    res = client.post(f"/api/projects/{project}/import", files=files, data={"format": "reqif", "mode": "merge"})
    assert res.status_code == 400


def Path_data_root(project_id: str):
    from pathlib import Path
    from app.core.config import settings
    return Path(settings.data_root) / project_id


# ── Dry-run over the HTTP route ──────────────────────────────────────────────

_CSV_HEADER = ('"id","type","name","description","status","priority",'
               '"verification_method","parent","relations","verification_cases",'
               '"rationale","source","allocated_to","baselines"')


def _csv_bytes(*ids: str) -> bytes:
    rows = [f'"{rid}","functional","Name {rid}","Desc","proposed","medium","test","","","","","","",""'
            for rid in ids]
    return "\n".join([_CSV_HEADER, *rows]).encode("utf-8")


def _xlsx_bytes(*ids: str) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["id", "type", "name", "description"])
    for rid in ids:
        ws.append([rid, "functional", f"Name {rid}", "Desc"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _count(client, project) -> int:
    return client.get(f"/api/projects/{project}/requirements").json()["total"]


def test_import_dry_run_csv_changes_nothing(client, project):
    make_req(client, project, "REQ-EX", name="Existing")
    before = _count(client, project)

    res = client.post(
        f"/api/projects/{project}/import",
        data={"format": "csv", "mode": "merge", "dry_run": "true"},
        files={"file": ("t.csv", io.BytesIO(_csv_bytes("REQ-EX", "REQ-NEW")), "text/csv")},
    )

    assert res.status_code == 200, res.text
    data = res.json()
    assert data["dry_run"] is True
    assert data["would_create"] == 1
    assert data["would_update"] == 1
    assert data["created"] == 0 and data["updated"] == 0
    assert _count(client, project) == before


def test_import_dry_run_xlsx_changes_nothing(client, project):
    make_req(client, project, "REQ-EX", name="Existing")
    before = _count(client, project)

    res = client.post(
        f"/api/projects/{project}/import",
        data={"format": "xlsx", "mode": "merge", "dry_run": "true"},
        files={"file": ("t.xlsx", io.BytesIO(_xlsx_bytes("REQ-EX", "REQ-NEW")),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert res.status_code == 200, res.text
    data = res.json()
    assert data["dry_run"] is True
    assert data["would_create"] == 1
    assert data["would_update"] == 1
    assert _count(client, project) == before


@pytest.mark.parametrize("fmt", ["reqif", "sysml", "auto"])
def test_import_dry_run_rejected_for_non_table_formats(client, project, fmt):
    """parse_and_import has no dry-run path, so honouring the flag would mean a
    real import behind a button labelled "Preview"."""
    res = client.post(
        f"/api/projects/{project}/import",
        data={"format": fmt, "mode": "merge", "dry_run": "true"},
        files={"file": ("t.csv", io.BytesIO(_csv_bytes("REQ-X")), "text/csv")},
    )

    assert res.status_code == 400
    assert res.json()["detail"] == "Dry run is only available for csv, tsv and xlsx"


def test_real_csv_import_reports_dry_run_false_and_zeroed_would_keys(client, project):
    res = client.post(
        f"/api/projects/{project}/import",
        data={"format": "csv", "mode": "merge"},
        files={"file": ("t.csv", io.BytesIO(_csv_bytes("REQ-REAL")), "text/csv")},
    )

    assert res.status_code == 200, res.text
    data = res.json()
    assert data["created"] == 1
    assert data["dry_run"] is False
    assert data["would_create"] == 0
    assert data["would_update"] == 0
    assert data["would_delete"] == 0
    assert data["rows"] == 0


def test_sysml_import_still_carries_the_preview_defaults(client, project):
    """Every format returns the same key set, so the TypeScript type can declare
    the preview fields required and no caller branches on format."""
    res = client.post(
        f"/api/projects/{project}/import",
        data={"format": "sysml", "mode": "merge"},
        files={"file": ("t.sysml", io.BytesIO(
            "package P {\n"
            "  requirement def SYST0009 {\n"
            "    doc /* Preview defaults */\n"
            "  }\n"
            "}\n".encode("utf-8")), "text/plain")},
    )

    assert res.status_code == 200, res.text
    data = res.json()
    for key in ("dry_run", "would_create", "would_update", "would_delete", "rows", "ignored"):
        assert key in data, f"missing {key}"
    assert data["dry_run"] is False


# ── Paste import ──────────────────────────────────────────────────────────────

def test_paste_csv_creates_requirements(client, project):
    csv_text = '"id","type","name","description","status","priority","verification_method","parent","relations","verification_cases","rationale","source","allocated_to","baselines"\n"REQ-PASTE","functional","Paste Test","Desc","proposed","medium","test","","","","","","",""'
    res = client.post(
        f"/api/projects/{project}/import",
        data={"text": csv_text, "format": "csv", "mode": "merge"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["created"] == 1
    req = client.get(f"/api/projects/{project}/requirements/REQ-PASTE").json()
    assert req["name"] == "Paste Test"


def test_paste_csv_dry_run_writes_no_history(client, project):
    from app.services.yaml_store import YamlStore
    from pathlib import Path
    store = YamlStore(Path_data_root(project))
    csv_text = _csv_bytes("REQ-DRY-P").decode()
    history_dir = store.root / "history"
    store.ensure_dirs()
    before = sorted([f.name for f in history_dir.iterdir()]) if history_dir.exists() else []

    res = client.post(
        f"/api/projects/{project}/import",
        data={"text": csv_text, "format": "csv", "mode": "merge", "dry_run": "true"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["dry_run"] is True

    after = sorted([f.name for f in history_dir.iterdir()]) if history_dir.exists() else []
    assert after == before


def test_paste_tsv_creates_requirements(client, project):
    tsv_text = '"id"\t"type"\t"name"\t"description"\t"status"\t"priority"\t"verification_method"\t"parent"\t"relations"\t"verification_cases"\t"rationale"\t"source"\t"allocated_to"\t"baselines"\n"REQ-TSV"\t"functional"\t"TSV Test"\t"Desc"\t"proposed"\t"medium"\t"test"\t""\t""\t""\t""\t""\t""\t""'
    res = client.post(
        f"/api/projects/{project}/import",
        data={"text": tsv_text, "format": "tsv", "mode": "merge"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["created"] == 1


def test_paste_auto_sniffs_tab_as_tsv(client, project):
    tsv_text = 'id\tname\tdescription\nREQ-SNIFF\tSniff Test\tDesc'
    res = client.post(
        f"/api/projects/{project}/import",
        data={"text": tsv_text, "format": "auto", "mode": "merge"},
    )
    assert res.status_code == 200, res.text
    req = client.get(f"/api/projects/{project}/requirements/REQ-SNIFF").json()
    assert req["name"] == "Sniff Test"


def test_paste_both_file_and_text_is_400(client, project):
    csv_text = '"id","name"\n"R1","One"'
    res = client.post(
        f"/api/projects/{project}/import",
        data={"text": csv_text, "format": "csv", "mode": "merge"},
        files={"file": ("t.csv", io.BytesIO(_csv_bytes("R2")), "text/csv")},
    )
    assert res.status_code == 400, res.text
    assert "either" in res.json()["detail"].lower()


def test_paste_neither_file_nor_text_is_400(client, project):
    res = client.post(
        f"/api/projects/{project}/import",
        data={"format": "csv", "mode": "merge"},
    )
    assert res.status_code == 400, res.text
    assert "either" in res.json()["detail"].lower()


def test_paste_xlsx_is_400(client, project):
    res = client.post(
        f"/api/projects/{project}/import",
        data={"text": "some,text", "format": "xlsx", "mode": "merge"},
    )
    assert res.status_code == 400, res.text
    assert "pasted" in res.json()["detail"].lower()


def test_paste_oversized_text_is_rejected(client, project, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    res = client.post(
        f"/api/projects/{project}/import",
        data={"text": "x" * (2 * 1024 * 1024), "format": "csv", "mode": "merge"},
    )
    assert res.status_code in (400, 413), res.text
