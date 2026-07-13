import textwrap

from app.services.quality import score_requirement, project_quality, strip_html


def test_strip_html():
    assert strip_html("<p>Hello <b>world</b></p>") == "Hello world"
    assert strip_html("Plain text") == "Plain text"
    assert strip_html("") == ""


def test_clean_sentence_scores_100():
    result = score_requirement({
        "name": "Login",
        "description": "The system must authenticate users within 500 ms using OAuth 2.0",
        "verification_method": "test",
    })
    assert result["score"] == 100


def test_weak_words_flagged():
    result = score_requirement({
        "name": "Login",
        "description": "The system should authenticate users quickly",
        "verification_method": "test",
    })
    assert result["score"] < 100
    rules = {f["rule"] for f in result["findings"]}
    assert "weak_words" in rules
    assert "should" in result["findings"][0]["message"]


def test_placeholders_detected():
    result = score_requirement({
        "name": "Login",
        "description": "TODO: implement authentication",
        "verification_method": "analysis",
    })
    assert any(f["rule"] == "placeholder" for f in result["findings"])


def test_passive_voice_flag():
    result = score_requirement({
        "name": "Login",
        "description": "Data is processed by the system.",
        "verification_method": "analysis",
    })
    assert any(f["rule"] == "passive_voice" for f in result["findings"])


def test_vague_quantifiers_detected():
    result = score_requirement({
        "name": "Login",
        "description": "The system should support several concurrent users",
        "verification_method": "analysis",
    })
    rules = {f["rule"] for f in result["findings"]}
    assert "vague_quantifier" in rules


def test_untestable_with_no_measurement():
    result = score_requirement({
        "name": "Login",
        "description": "Authentication should be fast",
        "verification_method": "test",
    })
    assert any(f["rule"] == "untestable" for f in result["findings"])


def test_testable_with_measurement():
    result = score_requirement({
        "name": "Login",
        "description": "Authentication must complete within 200 ms",
        "verification_method": "test",
    })
    assert not any(f["rule"] == "untestable" for f in result["findings"])


def test_too_short():
    result = score_requirement({
        "name": "X",
        "description": "Do it",
        "verification_method": "analysis",
    })
    assert any(f["rule"] == "word_count" and "short" in f["message"].lower() for f in result["findings"])


def test_too_long():
    long_text = "The system must " + "and ".join(["do thing " + str(i) for i in range(100)])
    result = score_requirement({
        "name": "Long",
        "description": long_text,
        "verification_method": "analysis",
    })
    assert any(f["rule"] == "word_count" and "long" in f["message"].lower() for f in result["findings"])


def test_non_atomic():
    result = score_requirement({
        "name": "Login",
        "description": "The system must do X and the system must do Y and also Z",
        "verification_method": "analysis",
    })
    assert any(f["rule"] == "non_atomic" for f in result["findings"])


def test_html_stripped_in_analysis():
    result = score_requirement({
        "name": "Login",
        "description": '<p>The system <em>must</em> authenticate users within <strong>500 ms</strong>.</p>',
        "verification_method": "test",
    })
    assert result["score"] == 100
    assert not any(f["rule"] == "weak_words" for f in result["findings"])


def test_project_quality_integration(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "REQ-001", "name": "Good", "description": "The system must authenticate users within 500 ms.", "verification_method": "test"})
    store.create_requirement({"id": "REQ-002", "name": "Bad", "description": "The system should maybe do stuff TBD.", "verification_method": "test"})

    result = project_quality(store)
    assert result["total"] == 2
    assert 0 <= result["average"] <= 100
    scores = {r["id"]: r["score"] for r in result["per_requirement"]}
    assert scores["REQ-001"] > scores["REQ-002"]


def test_quality_api_endpoint(client, project):
    from app.services.yaml_store import YamlStore
    from app.core.config import settings
    from pathlib import Path

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "REQ-Q", "name": "Q", "description": "The system must do X.", "verification_method": "test"})

    res = client.get(f"/api/projects/{project}/quality")
    assert res.status_code == 200
    data = res.json()
    assert "average" in data
    assert "per_requirement" in data
    assert data["total"] == 1
