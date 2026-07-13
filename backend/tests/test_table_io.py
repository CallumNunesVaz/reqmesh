import textwrap

from app.services.table_io import export_table, import_table, _req_to_row, _row_to_req


def test_row_to_req_roundtrip():
    req = {
        "id": "REQ-001", "type": "functional", "name": "Login",
        "description": "The system must authenticate users", "status": "approved",
        "priority": "high", "verification_method": "test", "parent": None,
        "relations": [{"type": "refines", "target": "FEAT-001"}],
        "verification_cases": ["VC-001"], "rationale": "Security requirement",
        "source": "ISO 27001", "allocated_to": "auth-module", "baseline": None,
    }
    row = _req_to_row(req)
    back = _row_to_req(row)
    assert back["id"] == "REQ-001"
    assert back["type"] == "functional"
    assert back["status"] == "approved"
    assert back["priority"] == "high"
    assert len(back["relations"]) == 1
    assert back["relations"][0]["type"] == "refines"
    assert back["relations"][0]["target"] == "FEAT-001"
    assert back["verification_cases"] == ["VC-001"]


def test_export_csv(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "REQ-A", "name": "Alpha", "description": "Do alpha"})
    store.create_requirement({"id": "REQ-B", "name": "Beta", "description": "Do beta"})

    csv_content = export_table(store, "csv")
    lines = csv_content.strip().split("\n")
    assert len(lines) >= 3
    assert lines[0].startswith('"id"')
    assert "Alpha" in csv_content
    assert "Beta" in csv_content


def test_export_tsv(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "REQ-T1", "name": "TSV Test"})

    content = export_table(store, "tsv")
    assert "\t" in content
    assert "REQ-T1" in content


def test_import_csv_merge(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    csv_data = '"id","type","name","description","status","priority","verification_method","parent","relations","verification_cases","rationale","source","allocated_to","baseline"\n"REQ-IMP","functional","Import Test","Do import stuff","proposed","medium","test","","","","","","",""'
    summary = import_table(store, csv_data, fmt="csv", mode="merge")
    assert summary["created"] == 1
    req = store.get_requirement("REQ-IMP")
    assert req is not None
    assert req["name"] == "Import Test"


def test_import_csv_update_existing(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "REQ-EX", "name": "Old Name"})

    csv_data = '"id","type","name","description","status","priority","verification_method","parent","relations","verification_cases","rationale","source","allocated_to","baseline"\n"REQ-EX","functional","New Name","Updated","approved","high","test","","","","","","",""'
    summary = import_table(store, csv_data, fmt="csv", mode="merge")
    assert summary["updated"] == 1
    req = store.get_requirement("REQ-EX")
    assert req["name"] == "New Name"


def test_import_csv_replace(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "REQ-OLD", "name": "Old"})
    assert len(store.list_requirements()) == 1

    csv_data = '"id","type","name","description","status","priority","verification_method","parent","relations","verification_cases","rationale","source","allocated_to","baseline"\n"REQ-NEW","functional","New Only","New desc","proposed","medium","test","","","","","","",""'
    summary = import_table(store, csv_data, fmt="csv", mode="replace")
    reqs = store.list_requirements()
    assert len(reqs) == 1
    assert reqs[0]["id"] == "REQ-NEW"


def test_import_skips_empty_id(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    csv_data = '"id","type","name","description"\n"","functional","No ID","Missing ID"'
    summary = import_table(store, csv_data, fmt="csv", mode="merge")
    assert summary["skipped"] == 1


def test_api_import_csv_endpoint(client, project):
    import io
    csv_content = '"id","type","name","description","status","priority","verification_method","parent","relations","verification_cases","rationale","source","allocated_to","baseline"\n"REQ-API","functional","API Import","Imported via API","proposed","medium","test","","","","","","",""'
    res = client.post(
        f"/api/projects/{project}/import",
        data={"format": "csv", "mode": "merge"},
        files={"file": ("test.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["created"] == 1


def test_api_download_csv(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "REQ-DL", "name": "Download Test"})

    res = client.get(f"/api/projects/{project}/publish/download?format=csv")
    assert res.status_code == 200
    content = res.content.decode("utf-8")
    assert "REQ-DL" in content
    assert content.startswith('"id"')
