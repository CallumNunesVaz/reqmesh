"""Search reuses stripped HTML across queries.

`strip_html` parses the description and dominated a search over a large project;
a keystroke-by-keystroke search used to re-strip every entity's description each
time. The cache is keyed by the raw HTML, so an unchanged description is parsed
once.
"""
from app.services import search as search_mod
from app.services.yaml_store import YamlStore


def _store(tmp_path) -> YamlStore:
    s = YamlStore(tmp_path / "p")
    s.ensure_dirs()
    s.create_requirement({"id": "R-1", "name": "Widget", "description": "<p>needle in html</p>"})
    s.create_requirement({"id": "R-2", "name": "Gadget", "description": "<p>nothing here</p>"})
    return s


def test_search_reuses_stripped_html(tmp_path, monkeypatch):
    store = _store(tmp_path)
    search_mod._strip_cache.clear()
    calls = {"n": 0}
    orig = search_mod.strip_html

    def counting(text: str) -> str:
        calls["n"] += 1
        return orig(text)

    monkeypatch.setattr(search_mod, "strip_html", counting)

    results = search_mod.search_project(store, "needle")
    assert [r["id"] for r in results] == ["R-1"]
    first = calls["n"]
    assert first > 0

    search_mod.search_project(store, "needle")
    assert calls["n"] == first, "second search re-stripped cached HTML"
