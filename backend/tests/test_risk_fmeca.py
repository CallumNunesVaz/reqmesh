"""FMECA split: risks carry failure_mode / effect / cause instead of one
free-text description, with a schema migration moving old descriptions.

Migration 2 → 3 rewrites each risk's ``description`` into ``failure_mode``,
leaving ``effect`` and ``cause`` empty and keeping ``description`` on disk.
"""
from __future__ import annotations

import json
from pathlib import Path

from ruamel.yaml import YAML

from app.services.migrations import (
    CURRENT_SCHEMA_VERSION,
    MIGRATIONS,
    _migrate_3_to_4,
    read_schema_version,
    run_migrations,
)


def _yaml():
    return YAML()


def _project(root, name="p1"):
    proj = root / name
    (proj / "risks").mkdir(parents=True)
    (proj / "_meta.yaml").write_text("name: P1\n")
    return proj


def _write(path, data):
    with open(path, "w") as f:
        _yaml().dump(data, f)


def _read(path):
    with open(path) as f:
        return _yaml().load(f)


# ── Migration ─────────────────────────────────────────────────────────────────


def test_registry_is_wired(tmp_path):
    """A migration that is written but not registered silently never runs."""
    assert MIGRATIONS.get(4) is _migrate_3_to_4
    assert CURRENT_SCHEMA_VERSION >= 3


def test_description_moves_to_failure_mode_and_stays_on_disk(tmp_path):
    proj = _project(tmp_path)
    _write(proj / "risks" / "R1.yaml",
           {"id": "R1", "title": "T", "description": "engine quits"})

    _migrate_3_to_4(tmp_path)

    got = _read(proj / "risks" / "R1.yaml")
    assert got["failure_mode"] == "engine quits"
    assert got.get("effect", "") == "", "effect has nothing to derive from"
    assert got.get("cause", "") == "", "cause has nothing to derive from"
    assert got["description"] == "engine quits", "description must stay on disk"


def test_migration_is_idempotent(tmp_path):
    """A second run must change nothing — a non-idempotent migration corrupts
    data the second time a container restarts before the marker is written."""
    proj = _project(tmp_path)
    _write(proj / "risks" / "R1.yaml", {"id": "R1", "description": "engine quits"})

    _migrate_3_to_4(tmp_path)
    first = _read(proj / "risks" / "R1.yaml")
    _migrate_3_to_4(tmp_path)
    second = _read(proj / "risks" / "R1.yaml")

    assert dict(first) == dict(second)


def test_risk_with_failure_mode_is_left_alone(tmp_path):
    proj = _project(tmp_path)
    _write(proj / "risks" / "R1.yaml",
           {"id": "R1", "description": "old", "failure_mode": "new"})

    _migrate_3_to_4(tmp_path)

    got = _read(proj / "risks" / "R1.yaml")
    assert got["failure_mode"] == "new", "must not overwrite a real failure_mode"


def test_one_unreadable_risk_does_not_abort_the_rest(tmp_path):
    """Startup runs migrations, so an unparseable file must not take it down."""
    proj = _project(tmp_path)
    (proj / "risks" / "broken.yaml").write_text("{{{ not yaml")
    _write(proj / "risks" / "R2.yaml", {"id": "R2", "description": "fuel leak"})

    _migrate_3_to_4(tmp_path)

    assert _read(proj / "risks" / "R2.yaml")["failure_mode"] == "fuel leak"


def test_a_directory_that_is_not_a_project_is_skipped(tmp_path):
    stray = tmp_path / "not-a-project" / "risks"
    stray.mkdir(parents=True)
    _write(stray / "R1.yaml", {"id": "R1", "description": "engine quits"})

    _migrate_3_to_4(tmp_path)

    assert "failure_mode" not in _read(stray / "R1.yaml")


def test_run_migrations_advances_a_recorded_version_2(tmp_path):
    """The path every existing deployment takes: marker at 2, migrate to 3."""
    proj = _project(tmp_path)
    _write(proj / "risks" / "R1.yaml", {"id": "R1", "description": "engine quits"})
    (tmp_path / ".reqmesh-schema.json").write_text(json.dumps({"schema_version": 2}))

    result = run_migrations(tmp_path)

    assert 3 in result["ran"]
    assert read_schema_version(tmp_path) == CURRENT_SCHEMA_VERSION
    assert _read(proj / "risks" / "R1.yaml")["failure_mode"] == "engine quits"


# ── Read-side fallback (old shape, no migration run) ─────────────────────────


def test_old_shape_risk_loads_without_migration(tmp_path):
    """A risk written before the split arrives by git pull, so it must read
    its failure mode from ``description`` even when no migration has run."""
    from app.services.yaml_store import YamlStore

    proj = _project(tmp_path)
    _write(proj / "risks" / "R1.yaml", {"id": "R1", "description": "engine quits"})

    store = YamlStore(proj)
    risk = store.list_items("risks")[0]
    assert risk["failure_mode"] == "engine quits"
    assert risk["description"] == "engine quits"


# ── Fingerprint ───────────────────────────────────────────────────────────────


def test_reviewed_fingerprints_survive_the_migration(tmp_path):
    """Risks are not fingerprinted (fingerprint.py fingerprints requirements
    only), so the migration cannot flag the register as needing re-review."""
    from app.services.fingerprint import compute_fingerprint
    from app.services.yaml_store import YamlStore

    proj = _project(tmp_path)
    (proj / "requirements").mkdir(parents=True)
    req = {"id": "REQ-1", "name": "N", "description": "d",
           "type": "functional", "status": "proposed", "priority": "high"}
    req["reviewed"] = compute_fingerprint(req)
    _write(proj / "requirements" / "REQ-1.yaml", req)
    _write(proj / "risks" / "R1.yaml",
           {"id": "R1", "description": "engine quits", "linked_requirements": ["REQ-1"]})

    _migrate_3_to_4(tmp_path)

    store = YamlStore(proj)
    loaded = store.get_requirement("REQ-1")
    assert loaded["reviewed"] == compute_fingerprint(loaded)


# ── Create / update round-trip ────────────────────────────────────────────────


def test_create_accepts_and_roundtrips_fmeca_fields(client, project):
    res = client.post(f"/api/projects/{project}/risks", json={
        "id": "RSK-FM", "title": "FMECA risk",
        "failure_mode": "engine fails",
        "effect": "loss of thrust",
        "cause": "fuel starvation",
        "severity": "high", "likelihood": "rare"})
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["failure_mode"] == "engine fails"
    assert body["effect"] == "loss of thrust"
    assert body["cause"] == "fuel starvation"

    got = client.get(f"/api/projects/{project}/risks/RSK-FM").json()
    assert got["failure_mode"] == "engine fails"
    assert got["effect"] == "loss of thrust"
    assert got["cause"] == "fuel starvation"


def test_update_roundtrips_fmeca_fields(client, project):
    client.post(f"/api/projects/{project}/risks", json={
        "id": "RSK-FU", "title": "T",
        "failure_mode": "a", "effect": "b", "cause": "c"})

    res = client.put(f"/api/projects/{project}/risks/RSK-FU", json={
        "effect": "new effect", "cause": "new cause"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["failure_mode"] == "a", "untouched field must survive a partial update"
    assert body["effect"] == "new effect"
    assert body["cause"] == "new cause"


# ── Search ────────────────────────────────────────────────────────────────────


def test_search_matches_each_fmeca_field_independently(client, project):
    client.post(f"/api/projects/{project}/risks", json={
        "id": "RSK-S", "title": "Searchable",
        "failure_mode": "wing spar cracks",
        "effect": "airframe breaks apart",
        "cause": "fatigue cycling"})

    for q in ("spar", "breaks", "fatigue"):
        res = client.get(f"/api/projects/{project}/search",
                         params={"q": q, "kind": "risk"})
        ids = [r["id"] for r in res.json()["results"]]
        assert "RSK-S" in ids, f"{q!r} did not match the risk"


# ── Publish ───────────────────────────────────────────────────────────────────


def test_publish_carries_all_three_fields(client, project):
    from app.core.config import settings
    from app.services.publisher import Publisher
    from app.services.yaml_store import YamlStore

    client.post(f"/api/projects/{project}/risks", json={
        "id": "RSK-P", "title": "Published",
        "failure_mode": "mode text",
        "effect": "effect text",
        "cause": "cause text"})

    store = YamlStore(Path(settings.data_root) / project)
    pub = Publisher(store)
    html = pub.build_html()
    latex = pub.build_latex()

    for field in ("mode text", "effect text", "cause text"):
        assert field in html, f"{field!r} missing from the HTML report"
        assert field in latex, f"{field!r} missing from the LaTeX report"
