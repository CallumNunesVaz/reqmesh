from pathlib import Path

from app.services.code_scan import scan_tree, merge_references, compute_sha


def test_compute_sha(tmp_path):
    f = tmp_path / "test.py"
    f.write_text("print('hello')")
    sha = compute_sha(f)
    assert sha is not None
    assert len(sha) == 64


def test_compute_sha_missing():
    assert compute_sha(Path("/nonexistent/path")) is None


def test_scan_tree_finds_python_tags(tmp_path):
    src = tmp_path / "src"
    src.mkdir(parents=True)
    (src / "auth.py").write_text("# [impl->REQ-AUTH-001]\ndef login(): pass\n")

    hits = scan_tree(src)
    assert len(hits) == 1
    assert hits[0]["req_id"] == "REQ-AUTH-001"
    assert hits[0]["kind"] == "impl"
    assert hits[0]["sha256"] is not None


def test_scan_tree_finds_java_tags(tmp_path):
    src = tmp_path / "src"
    src.mkdir(parents=True)
    (src / "Login.java").write_text("// [test->REQ-LOGIN]\npublic class Login {}")

    hits = scan_tree(src)
    assert len(hits) >= 1
    assert any(h["req_id"] == "REQ-LOGIN" for h in hits)


def test_scan_tree_finds_loose_covers_tags(tmp_path):
    src = tmp_path / "src"
    src.mkdir(parents=True)
    (src / "test_auth.py").write_text("# @covers REQ-AUTH-001\ndef test(): pass")

    hits = scan_tree(src)
    assert len(hits) >= 1
    assert any(h["req_id"] == "REQ-AUTH-001" and h["kind"] == "covers" for h in hits)


def test_scan_tree_skips_git_dir(tmp_path):
    src = tmp_path / "src"
    src.mkdir(parents=True)
    git_dir = src / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "secret.py").write_text("# [impl->REQ-SECRET]\npass")

    hits = scan_tree(src)
    assert not any("secret" in str(h.get("path", "")) for h in hits)


def test_merge_references_creates_new_links(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "REQ-CODE", "name": "Code", "description": "X"})

    hits = [{"req_id": "REQ-CODE", "kind": "impl", "path": "src/auth.py", "line": 42, "sha256": "abc123"}]
    summary = merge_references(store, hits)
    assert summary["created"] == 1
    assert summary["requirements_touched"] == 1

    req = store.get_requirement("REQ-CODE")
    assert len(req["references"]) == 1
    assert req["references"][0]["path"] == "src/auth.py"
    assert req["references"][0]["kind"] == "impl"


def test_scan_api_endpoint(client, project, tmp_path):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "REQ-API-SCAN", "name": "API Scan Test"})

    src = store.root / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "main.py").write_text("# [impl->REQ-API-SCAN]\ndef go(): pass")

    res = client.post(
        f"/api/projects/{project}/scan",
        data={"code_root": str(src)},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["created"] >= 1
    assert data["requirements_touched"] >= 1
