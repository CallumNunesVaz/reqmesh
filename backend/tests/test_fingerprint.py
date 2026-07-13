from app.services.fingerprint import (
    compute_fingerprint,
    check_unreviewed,
    check_suspect_links,
    review_item,
    review_all,
)


def test_identical_reqs_have_same_fingerprint():
    r1 = {"type": "functional", "name": "Login", "description": "Auth users <p>quickly</p>", "rationale": "", "priority": "medium", "verification_method": "test", "verification_cases": [], "parent": None, "source": ""}
    r2 = {"type": "functional", "name": "Login", "description": "Auth users <p>quickly</p>", "rationale": "", "priority": "medium", "verification_method": "test", "verification_cases": [], "parent": None, "source": ""}
    assert compute_fingerprint(r1) == compute_fingerprint(r2)


def test_different_descriptions_yield_different_fingerprints():
    r1 = {"type": "functional", "name": "Login", "description": "Auth users", "rationale": "", "priority": "medium", "verification_method": "test", "verification_cases": [], "parent": None, "source": ""}
    r2 = {"type": "functional", "name": "Login", "description": "Auth users differently", "rationale": "", "priority": "medium", "verification_method": "test", "verification_cases": [], "parent": None, "source": ""}
    assert compute_fingerprint(r1) != compute_fingerprint(r2)


def test_non_normative_fields_do_not_affect_fingerprint():
    r1 = {"type": "functional", "name": "Login", "description": "Auth", "rationale": "", "priority": "medium", "verification_method": "test", "verification_cases": [], "parent": None, "source": "", "allocated_to": "team-a", "baseline": "v1", "modified": "2023-01-01"}
    r2 = {"type": "functional", "name": "Login", "description": "Auth", "rationale": "", "priority": "medium", "verification_method": "test", "verification_cases": [], "parent": None, "source": "", "allocated_to": "team-b", "baseline": "v2", "modified": "2024-06-15"}
    assert compute_fingerprint(r1) == compute_fingerprint(r2)


def test_unreviewed_detected(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "REQ-F1", "name": "F1", "description": "Do X"})

    unreviewed = check_unreviewed(store)
    assert len(unreviewed) == 0

    review_item(store, "REQ-F1")
    store.update_requirement("REQ-F1", {"description": "Changed"})
    unreviewed = check_unreviewed(store)
    assert len(unreviewed) == 1
    assert unreviewed[0]["id"] == "REQ-F1"


def test_review_clears_unreviewed(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "REQ-F2", "name": "F2", "description": "Do Y"})

    result = review_item(store, "REQ-F2")
    assert result is not None
    assert result.get("reviewed") is not None

    unreviewed = check_unreviewed(store)
    assert len(unreviewed) == 0


def test_edit_flips_unreviewed(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "REQ-F3", "name": "F3", "description": "Do Z"})

    review_item(store, "REQ-F3")
    assert len(check_unreviewed(store)) == 0

    store.update_requirement("REQ-F3", {"description": "Changed description"})
    assert len(check_unreviewed(store)) == 1


def test_suspect_link_from_fingerprint(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "REQ-PARENT", "name": "Parent", "description": "Parent req"})
    store.create_requirement({
        "id": "REQ-CHILD", "name": "Child",
        "description": "Child links to parent",
        "relations": [{"type": "refines", "target": "REQ-PARENT"}],
    })

    review_all(store)
    suspects = check_suspect_links(store)
    assert len(suspects) == 0

    store.update_requirement("REQ-PARENT", {"description": "Parent changed"})
    suspects = check_suspect_links(store)
    assert len(suspects) >= 1
    assert suspects[0]["target"] == "REQ-PARENT"


def test_review_api_endpoint(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "REQ-R1", "name": "R1", "description": "Review me"})

    res = client.post(f"/api/projects/{project}/requirements/REQ-R1/review", json={"comment": "LGTM"})
    assert res.status_code == 200
    data = res.json()
    assert data.get("reviewed") is not None


def test_review_all_api_endpoint(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "REQ-RA1", "name": "RA1", "description": "First"})
    store.create_requirement({"id": "REQ-RA2", "name": "RA2", "description": "Second"})

    res = client.post(f"/api/projects/{project}/review-all")
    assert res.status_code == 200
    data = res.json()
    assert data["reviewed"] == 2
    assert data["total"] == 2


def test_unreviewed_api_endpoint(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "REQ-UR1", "name": "UR1", "description": "Will be reviewed then changed"})

    review_item(store, "REQ-UR1")
    store.update_requirement("REQ-UR1", {"description": "Now different"})

    res = client.get(f"/api/projects/{project}/unreviewed")
    assert res.status_code == 200
    data = res.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == "REQ-UR1"


def test_derived_skips_orphan_check(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "REQ-DERIVED", "name": "Derived", "description": "No parent needed", "derived": True, "parent": "NONEXISTENT"})

    from app.services.integrity import IntegrityChecker
    checker = IntegrityChecker(store)
    result = checker.check_all()
    assert not any(i["type"] == "orphan_parent" and i["id"] == "REQ-DERIVED" for i in result["issues"])


def test_non_normative_skips_verification_check(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "REQ-HEADING", "name": "Heading", "description": "Section heading", "normative": False, "status": "approved"})

    from app.services.integrity import IntegrityChecker
    checker = IntegrityChecker(store)
    result = checker.check_all()
    assert not any(i["type"] == "no_verification" and i["id"] == "REQ-HEADING" for i in result["issues"])
