"""Baseline descriptions are HTML-sanitised on both the read and the write path.

`_meta.yaml` does not pass through ``load_guard.validate_on_load`` — that runs
only on the per-collection read path — so meta-held HTML had no sanitiser at
all. The baselines page renders the description with
``dangerouslySetInnerHTML``, which made it stored XSS: a maintainer (or a
`git pull`, or a hand edit) could land a ``<script>`` that ran for every
subsequent viewer.

``normalize_baseline_defs`` is the chokepoint both directions go through, which
is why the guard lives there and why these tests exercise the API rather than
the function.
"""

PAYLOAD = '<img src=x onerror=alert(1)><script>alert(2)</script>'


def _mkproject(client, pid="xss"):
    client.post("/api/projects", json={"id": pid, "name": "XSS probe"})
    return pid


def test_baseline_description_is_sanitised_on_write(client):
    pid = _mkproject(client)
    assert client.post(f"/api/projects/{pid}/baselines",
                       json={"name": "B1", "description": PAYLOAD}).status_code == 200

    served = client.get(f"/api/projects/{pid}/baselines").json()
    desc = next(b["description"] for b in served if b["name"] == "B1")
    assert "<script" not in desc
    assert "onerror" not in desc


def test_baseline_description_is_sanitised_on_rename(client):
    """PATCH takes its own description, so it needs its own proof."""
    pid = _mkproject(client, "xss2")
    client.post(f"/api/projects/{pid}/baselines", json={"name": "B1", "description": "clean"})
    client.patch(f"/api/projects/{pid}/baselines/B1",
                 json={"name": "B2", "description": PAYLOAD})

    served = client.get(f"/api/projects/{pid}/baselines").json()
    desc = next(b["description"] for b in served if b["name"] == "B2")
    assert "<script" not in desc and "onerror" not in desc


def test_hand_edited_meta_is_sanitised_on_read(client):
    """The write path is not the only way in.

    A description can arrive by a direct edit of `_meta.yaml` or by `git pull`,
    neither of which touches the API. Sanitising on read is what makes those
    safe, and is the same reasoning as ``load_guard``'s "disk is not a trusted
    input".
    """
    from app.core.config import settings
    from app.services.yaml_store import YamlStore
    from pathlib import Path

    pid = _mkproject(client, "xss3")
    store = YamlStore(Path(settings.data_root) / pid)
    meta = store.read_meta()
    meta["baselines"] = [{"name": "B1", "description": PAYLOAD}]
    store.write_meta(meta)

    served = client.get(f"/api/projects/{pid}/baselines").json()
    desc = next(b["description"] for b in served if b["name"] == "B1")
    assert "<script" not in desc and "onerror" not in desc


def test_legitimate_rich_text_survives(client):
    """The guard must not be a blunt strip — descriptions are rich text."""
    pid = _mkproject(client, "xss4")
    client.post(f"/api/projects/{pid}/baselines",
                json={"name": "B1", "description": "<p>First <strong>gate</strong></p>"})

    served = client.get(f"/api/projects/{pid}/baselines").json()
    desc = next(b["description"] for b in served if b["name"] == "B1")
    assert "<strong>" in desc
    assert "gate" in desc
