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
    """A chain of decomposition is deep-covered only if every link is.

    Was written against the previous model, where a ``needs`` entry matched the
    ``type`` of a covering child requirement — so this declared
    ``needs: ["design"]`` and satisfied it with a child of ``type: design``.
    That model could not be satisfied at all for the two values the demo ships
    (``design`` is not a RequirementType, so the API will not create one), which
    is why ``needs`` now names artifact kinds instead. Decomposition is
    ``child_requirement``.
    """
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "SYS", "name": "System", "description": "S",
                              "needs": ["child_requirement"]})
    store.create_requirement({
        "id": "ARCH", "name": "Architecture", "description": "A",
        "needs": ["child_requirement"],
        "relations": [{"type": "refines", "target": "SYS"}],
    })
    store.create_requirement({
        "id": "IMPL", "name": "Implementation", "description": "I",
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
    """SYS2 has a child, so it is shallow-covered; that child has an unmet
    obligation of its own, so the chain below it is broken."""
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "SYS2", "name": "S2", "description": "S",
                              "needs": ["child_requirement"]})
    store.create_requirement({
        "id": "ARCH2", "name": "A2", "description": "A",
        "needs": ["child_requirement"],
        "relations": [{"type": "refines", "target": "SYS2"}],
    })

    items = trace_all(store)
    sys_item = next(i for i in items if i["id"] == "SYS2")
    assert sys_item["shallow"] is True
    assert sys_item["deep"] is False
    assert sys_item["broken_chain"] is True


# ── The obligation kinds, one test each ──────────────────────────────────────
# Each of these was unsatisfiable under the old model: `needs` was compared
# against the *type* of a covering child requirement, so no component,
# verification case or analysis could ever discharge an obligation.

def test_design_need_satisfied_by_a_component(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "D1", "name": "D1", "description": "X", "needs": ["design"]})

    items = trace_all(store)
    assert next(i for i in items if i["id"] == "D1")["shallow"] is False

    store.create_component({"id": "COMP1", "name": "Comp", "satisfies": ["D1"]})
    items = trace_all(store)
    d1 = next(i for i in items if i["id"] == "D1")
    assert d1["shallow"] is True
    assert "design" in d1["covered_types"]


def test_verification_need_satisfied_by_a_case(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "V1", "name": "V1", "description": "X",
                              "needs": ["verification_case"]})
    assert next(i for i in trace_all(store) if i["id"] == "V1")["shallow"] is False

    store.create_verification_case({"id": "VC1", "name": "VC", "verified_requirements": ["V1"]})
    v1 = next(i for i in trace_all(store) if i["id"] == "V1")
    assert v1["shallow"] is True
    assert "verification_case" in v1["covered_types"]


def test_verification_need_satisfied_from_the_requirement_side(client, project):
    """The VC owns the link.  Writing on the requirement side still counts
    because the VC records it on the owning side (verified_requirements)."""
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_verification_case({"id": "VC2", "name": "VC2", "verified_requirements": ["V2"]})
    store.create_requirement({"id": "V2", "name": "V2", "description": "X",
                              "needs": ["verification_case"],
                              "verification_cases": ["VC2"]})

    assert next(i for i in trace_all(store) if i["id"] == "V2")["shallow"] is True


def test_reference_need_satisfied_by_an_attached_reference(client, project):
    """References were keyed by ``ref["path"]`` — a filesystem path, never a
    requirement id — so they counted towards nothing at all."""
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "R1", "name": "R1", "description": "X", "needs": ["reference"]})
    assert next(i for i in trace_all(store) if i["id"] == "R1")["shallow"] is False

    store.update_requirement("R1", {"references": [{"path": "src/wing.py", "kind": "impl"}]})
    r1 = next(i for i in trace_all(store) if i["id"] == "R1")
    assert r1["shallow"] is True
    assert "reference" in r1["covered_types"]


def test_coverage_needs_vocabulary_endpoint(client):
    """The picker is served from the same constant tracing.py satisfies, so the
    two cannot drift the way `design`/`verification_case` did."""
    from app.services.tracing import NEEDS_VOCABULARY

    res = client.get("/api/coverage-needs")
    assert res.status_code == 200
    values = {i["value"] for i in res.json()["items"]}
    assert values == set(NEEDS_VOCABULARY)
    assert "design" in values and "verification_case" in values


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
