from app.services.tracing import trace_all, shallow_status, _build_coverage_graph


def test_shallow_covered_with_needs_met(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "REQ-PARENT", "name": "P", "description": "Parent"})
    store.create_requirement({
        "id": "REQ-CHILD", "name": "C", "description": "Child",
        "type": "design",
        "relations": [{"type": "refines", "target": "REQ-PARENT"}],
        "needs": ["design"],
    })

    items = trace_all(store)
    parent = next(i for i in items if i["id"] == "REQ-PARENT")
    assert parent["shallow"] is True
    child = next(i for i in items if i["id"] == "REQ-CHILD")
    assert child["shallow"] is False
    assert "design" in child["uncovered_types"]


def test_deep_coverage_chain(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "SYS", "name": "System", "description": "S", "needs": ["design"]})
    store.create_requirement({
        "id": "ARCH", "name": "Architecture", "description": "A",
        "type": "design",
        "needs": ["design"],
        "relations": [{"type": "refines", "target": "SYS"}],
    })
    store.create_requirement({
        "id": "IMPL", "name": "Implementation", "description": "I",
        "type": "design",
        "needs": [],
        "relations": [{"type": "refines", "target": "ARCH"}],
    })

    items = trace_all(store)
    sys_item = next(i for i in items if i["id"] == "SYS")
    assert sys_item["shallow"] is True
    assert sys_item["deep"] is True
    impl_item = next(i for i in items if i["id"] == "IMPL")
    assert impl_item["deep"] is True


def test_shallow_but_not_deep(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "SYS2", "name": "S2", "description": "S", "needs": ["design"]})
    store.create_requirement({
        "id": "ARCH2", "name": "A2", "description": "A",
        "type": "design",
        "needs": ["design"],
        "relations": [{"type": "refines", "target": "SYS2"}],
    })

    items = trace_all(store)
    sys_item = next(i for i in items if i["id"] == "SYS2")
    assert sys_item["shallow"] is True
    assert sys_item["deep"] is False
    assert sys_item["broken_chain"] is True


def test_terminating_item(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "LEAF", "name": "Leaf", "description": "No further needs", "needs": []})

    items = trace_all(store)
    leaf = next(i for i in items if i["id"] == "LEAF")
    assert leaf["shallow"] is True
    assert leaf["deep"] is True


def test_cycle_detection_does_not_crash(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({
        "id": "CYCLE-A", "name": "A", "description": "Cycle",
        "needs": ["design"],
        "relations": [{"type": "refines", "target": "CYCLE-B"}],
    })
    store.create_requirement({
        "id": "CYCLE-B", "name": "B", "description": "Cycle",
        "needs": ["design"],
        "relations": [{"type": "refines", "target": "CYCLE-A"}],
    })

    items = trace_all(store)
    a = next(i for i in items if i["id"] == "CYCLE-A")
    assert a["deep"] is False


def test_coverage_api_endpoint(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "COVER1", "name": "C1", "description": "X", "needs": []})

    res = client.get(f"/api/projects/{project}/coverage")
    assert res.status_code == 200
    data = res.json()
    assert "shallow_covered" in data
    assert "deep_covered" in data
    assert "items" in data


def test_trace_api_endpoint(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "TR1", "name": "T1", "description": "X", "needs": []})

    res = client.get(f"/api/projects/{project}/coverage")
    assert res.status_code == 200
    data = res.json()
    items = data.get("items", [])
    assert len(items) >= 1
    assert "shallow" in items[0]
    assert "deep" in items[0]


def test_relation_cycle_detected(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({
        "id": "RC-A", "name": "A", "description": "Cycle",
        "relations": [{"type": "refines", "target": "RC-B"}],
    })
    store.create_requirement({
        "id": "RC-B", "name": "B", "description": "Cycle",
        "relations": [{"type": "refines", "target": "RC-C"}],
    })
    store.create_requirement({
        "id": "RC-C", "name": "C", "description": "Cycle",
        "relations": [{"type": "refines", "target": "RC-A"}],
    })

    res = client.get(f"/api/projects/{project}/validate")
    data = res.json()
    assert any(i["type"] == "circular_relation" for i in data["issues"])
