"""The generated quality-rule module must be checked in up to date, and the
client scorer must agree with the server scorer on the same text.

`gen_quality_rules.py` derives `frontend/src/lib/generated/qualityRules.ts` from
`PATTERN_RULES` (and the default config from `quality.py`), the same way
`gen_schemas.py` derives `schemas/`. CI regenerates and diffs the file; the
currency test below is the fast, local version of that check.

The cross-check is the important one: it scores the same inputs through the
Python `score_requirement` and the TypeScript `scoreRequirement` and asserts the
scores and finding ids are identical. It runs the real frontend scorer (via
`vite-node`), not a hand-typed copy, so a drift in the port is caught rather
than reproduced.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

import gen_quality_rules
from app.services.quality import score_requirement
from app.services.quality_rules import PATTERN_RULES
from tests.test_quality_rules import FIXTURES

_FRONTEND = Path(__file__).resolve().parent.parent.parent / "frontend"
_QUALITY_MODULE = _FRONTEND / "src" / "lib" / "quality.ts"
_VITE_NODE = _FRONTEND / "node_modules" / ".bin" / "vite-node"


# ── Freshness / idempotency ──────────────────────────────────────────────────


def test_generated_quality_rules_are_current():
    """The committed TS module is what the generator would write today."""
    assert gen_quality_rules.OUT.read_text(encoding="utf-8") == gen_quality_rules.render(), (
        f"{gen_quality_rules.OUT} is out of date — run `python gen_quality_rules.py` "
        "from backend/ and commit the result."
    )


def test_generated_quality_rules_are_not_empty():
    """Guards the CI gate against a generator that goes silently empty."""
    rendered = gen_quality_rules.render()
    assert "export const QUALITY_RULES: QualityRule[] = [" in rendered
    assert len(gen_quality_rules.rule_table()) == len(PATTERN_RULES)


def test_generator_is_idempotent():
    """render() is deterministic — the CI diff gate must not flap."""
    assert gen_quality_rules.render() == gen_quality_rules.render()


def test_generator_raises_on_python_only_construct():
    """A pattern that cannot port to JavaScript RegExp is rejected, not emitted."""
    from app.services.quality_rules import Rule

    with pytest.raises(ValueError):
        Rule(id="bad", title="bad", severity="warning", pattern=r"ends\Z", message="{match}", weight=1)
    with pytest.raises(ValueError):
        Rule(id="bad", title="bad", severity="warning", pattern=r"(?P<name>foo)", message="{match}", weight=1)


# ── Cross-check: Python score_requirement vs TS scoreRequirement ──────────────


def _inputs() -> list[str]:
    """Texts that exercise every rule, plus the bespoke checks and HTML.

    Driven from `FIXTURES` (which is itself derived from `PATTERN_RULES`), so a
    rule added later is automatically covered by its own positive and negative
    fixture. The extras exercise the bespoke rules (`word_count`, `no_obligation`)
    and the HTML/entity stripping path.
    """
    texts = []
    for _rule_id, should_match, should_not_match in FIXTURES:
        texts.append(should_match)
        texts.append(should_not_match)
    texts += [
        # word_count: too short / too long
        "Do it",
        "The system must " + "and ".join("do thing " + str(i) for i in range(100)),
        # no_obligation: no obligation verb present
        "This describes the authentication module",
        # HTML with block tags and entities, as the editor produces
        "<p>The system <strong>must</strong> authenticate users within <em>500 ms</em>.</p>",
        "<p>Hello &amp; welcome</p><div>second block</div>",
        # A clean sentence that should score 100 (no findings at all).
        "The system must authenticate users within 500 ms using OAuth 2.0",
    ]
    return texts


def _python_scores(texts: list[str], config: dict | None) -> list[dict]:
    out = []
    for text in texts:
        result = score_requirement(
            {"name": "", "description": text, "verification_method": ""},
            config=config,
        )
        out.append({"score": result["score"], "findings": sorted(f["rule"] for f in result["findings"])})
    return out


def _node_available() -> bool:
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False
    return _VITE_NODE.exists()


def _ts_scores(texts: list[str], config: dict | None) -> list[dict]:
    """Run the real `scoreRequirement` through vite-node and return its output."""
    runner = """\
import { readFileSync } from 'node:fs';
import { scoreRequirement } from '%s';
const payload = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const out = payload.inputs.map((t) => {
  const r = scoreRequirement(t, payload.config);
  return { score: r.score, findings: r.findings.map((f) => f.rule).sort() };
});
console.log(JSON.stringify(out));
""" % str(_QUALITY_MODULE)

    with tempfile.TemporaryDirectory() as tmp:
        runner_path = Path(tmp) / "runner.ts"
        payload_path = Path(tmp) / "payload.json"
        runner_path.write_text(runner, encoding="utf-8")
        payload_path.write_text(
            json.dumps({"inputs": texts, "config": config}),
            encoding="utf-8",
        )
        result = subprocess.run(
            [str(_VITE_NODE), str(runner_path), str(payload_path)],
            cwd=str(_FRONTEND),
            capture_output=True,
            text=True,
            timeout=60,
        )
    assert result.returncode == 0, f"vite-node failed:\n{result.stderr}"
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"TS scorer output not valid JSON:\n{result.stdout}")


def test_cross_check_scores_and_finding_ids_match():
    """Python and TS produce identical scores and finding ids on the same text."""
    if not _node_available():
        pytest.skip("node/vite-node not available — cannot run the cross-check")

    texts = _inputs()
    py = _python_scores(texts, config=None)
    ts = _ts_scores(texts, config=None)

    assert len(ts) == len(py)
    for text, p, t in zip(texts, py, ts, strict=True):
        assert t["score"] == p["score"], (
            f"score mismatch for {text!r}:\n  python={p}\n  ts={t}"
        )
        assert t["findings"] == p["findings"], (
            f"finding ids mismatch for {text!r}:\n  python={p['findings']}\n  ts={t['findings']}"
        )


def test_cross_check_honours_project_config():
    """A per-project enable/disable and reweight is honoured identically."""
    if not _node_available():
        pytest.skip("node/vite-node not available — cannot run the cross-check")

    from app.services.quality import DEFAULT_CONFIG

    # Mirror `_load_config`: the project's overrides are merged over the defaults,
    # so the client always receives a *full* rules/weights dict.
    config = {
        "min_words": 8,
        "max_words": 120,
        "rules": {**DEFAULT_CONFIG["rules"], "weak_words": False, "passive_voice": False},
        "weights": {**DEFAULT_CONFIG["weights"], "placeholder": 20, "weak_words": 1},
    }
    texts = [
        "The system should authenticate users promptly",
        "TODO: implement the login flow",
        "Data is processed by the system",
        "The system must authenticate users within 500 ms",
    ]
    py = _python_scores(texts, config=config)
    ts = _ts_scores(texts, config=config)

    for text, p, t in zip(texts, py, ts, strict=True):
        assert t["score"] == p["score"], f"score mismatch for {text!r}: python={p} ts={t}"
        assert t["findings"] == p["findings"], f"finding ids mismatch for {text!r}"
