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


def test_merge_references_keeps_every_file_when_one_requirement_is_hit_twice(client, project):
    """Regression: each hit used to rebuild the list from the unchanged
    snapshot and write it, so only the last file survived."""
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "REQ-MULTI", "name": "Multi"})

    hits = [
        {"req_id": "REQ-MULTI", "kind": "impl", "path": "src/a.py", "line": 1, "sha256": "aaa"},
        {"req_id": "REQ-MULTI", "kind": "impl", "path": "src/b.py", "line": 2, "sha256": "bbb"},
    ]
    summary = merge_references(store, hits)
    assert summary["created"] == 2
    assert summary["requirements_touched"] == 1

    req = store.get_requirement("REQ-MULTI")
    assert sorted(r["path"] for r in req["references"]) == ["src/a.py", "src/b.py"]


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


def test_scan_tree_skips_a_committed_symlink(tmp_path):
    """`git ls-files` lists a tracked symlink, which would otherwise let the
    scanner read a file anywhere on the host, outside code_root."""
    import subprocess

    secret = tmp_path / "secret.py"
    secret.write_text("# [impl->REQ-SECRET]\npass\n")
    src = tmp_path / "src"
    src.mkdir()
    (src / "real.py").write_text("# [impl->REQ-REAL]\npass\n")
    (src / "link.py").symlink_to(secret)
    subprocess.run(["git", "init", "-q"], cwd=src, check=True)
    subprocess.run(["git", "add", "-A"], cwd=src, check=True)

    ids = {h["req_id"] for h in scan_tree(src)}
    assert "REQ-REAL" in ids
    assert "REQ-SECRET" not in ids
