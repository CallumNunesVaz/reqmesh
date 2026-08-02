from __future__ import annotations

import html
import re
from html.parser import HTMLParser

from app.services.quality_rules import PATTERN_RULES

_BLOCK_TAGS = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th", "tr", "section", "article", "header", "footer", "blockquote"}


class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._text: list[str] = []
        self._last_data = False

    def handle_starttag(self, tag, attrs):
        if tag in _BLOCK_TAGS and self._last_data:
            self._text.append(" ")
            self._last_data = False

    def handle_endtag(self, tag):
        if tag in _BLOCK_TAGS:
            self._text.append(" ")
            self._last_data = False

    def handle_data(self, data: str):
        self._text.append(data)
        self._last_data = True

    def get_text(self) -> str:
        raw = "".join(self._text)
        return html.unescape(raw)


def strip_html(text: str) -> str:
    s = _HTMLStripper()
    s.feed(text)
    return s.get_text()


MEASURABLE_TERMS = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:%|percent|ms|s|sec|seconds?|minutes?|hours?|"
    r"days?|weeks?|months?|years?|bytes?|KB|MB|GB|TB|"
    r"Hz|kHz|MHz|GHz|bps|fps|px|mm|cm|m|km|g|kg|lb|°C|°F)\b",
    re.IGNORECASE,
)

# Bespoke (non-pattern) rule config entries, added to the defaults derived
# from PATTERN_RULES.
_BESPOKE_RULES: dict[str, bool] = {
    "untestable": True,
    "word_count": True,
    "no_obligation": True,
}
_BESPOKE_WEIGHTS: dict[str, int] = {
    "untestable": 5,
    "word_count": 10,
    "no_obligation": 6,
}

# Derive the default config from PATTERN_RULES plus bespoke entries, so a
# rule added to the table does not need a second edit here.
_DERIVED_RULES: dict[str, bool] = {}
_DERIVED_WEIGHTS: dict[str, int] = {}
for _rule in PATTERN_RULES:
    _DERIVED_RULES[_rule.config] = _rule.enabled
    _DERIVED_WEIGHTS[_rule.config] = _rule.weight
_DERIVED_RULES.update(_BESPOKE_RULES)
_DERIVED_WEIGHTS.update(_BESPOKE_WEIGHTS)

DEFAULT_CONFIG: dict = {
    "min_words": 5,
    "max_words": 200,
    "rules": _DERIVED_RULES,
    "weights": _DERIVED_WEIGHTS,
}


def _load_config(store) -> dict:
    meta = store.read_meta()
    raw = meta.get("quality", {})
    cfg = dict(DEFAULT_CONFIG)
    if "min_words" in raw:
        cfg["min_words"] = raw["min_words"]
    if "max_words" in raw:
        cfg["max_words"] = raw["max_words"]
    if "rules" in raw:
        cfg["rules"] = {**cfg["rules"], **raw["rules"]}
    if "weights" in raw:
        cfg["weights"] = {**cfg["weights"], **raw["weights"]}
    return cfg


def score_requirement(req: dict, config: dict | None = None) -> dict:
    if config is None:
        config = DEFAULT_CONFIG

    text = strip_html(req.get("description", ""))
    name = html.unescape(req.get("name", ""))
    combined = f"{name}\n{text}"
    plain = combined.strip()
    findings: list[dict] = []
    penalty = 0
    weights = config.get("weights", DEFAULT_CONFIG["weights"])
    rules = config.get("rules", DEFAULT_CONFIG["rules"])
    max_penalty = sum(weights.values())

    # --- Pattern rules (one loop over the single source of truth) ---
    for rule in PATTERN_RULES:
        if not rule.enabled or not rules.get(rule.config, True):
            continue
        for m in re.finditer(rule.pattern, plain, re.IGNORECASE):
            findings.append({
                "rule": rule.id,
                "severity": rule.severity,
                "message": rule.message.format(match=m.group(0)),
                "start": m.start(),
                "end": m.end(),
            })
            penalty += weights.get(rule.config, rule.weight)

    # --- Bespoke checks ---

    # no_obligation: a statement with none of the standard obligation verbs.
    # The Rule entry (enabled=False) lives in PATTERN_RULES so the pattern,
    # weight and INCOSE citation are defined in one place — this check
    # inverts it.
    if rules.get("no_obligation", True):
        for rule in PATTERN_RULES:
            if rule.id == "no_obligation":
                if not re.search(rule.pattern, plain, re.IGNORECASE):
                    findings.append({
                        "rule": rule.id,
                        "severity": rule.severity,
                        "message": rule.message.format(match=""),
                        "start": 0,
                        "end": len(plain),
                    })
                    penalty += weights.get(rule.config, rule.weight)
                break

    if rules.get("untestable", True):
        vm = req.get("verification_method", "")
        if vm == "test":
            has_measure = bool(MEASURABLE_TERMS.search(plain))
            if not has_measure:
                findings.append({
                    "rule": "untestable",
                    "severity": "warning",
                    "message": "Marked for test verification but contains no measurable criteria (numbers with units)",
                    "start": 0,
                    "end": len(plain),
                })
                penalty += weights.get("untestable", 5)

    if rules.get("word_count", True):
        word_count = len(plain.split())
        min_w = config.get("min_words", 5)
        max_w = config.get("max_words", 200)
        if word_count < min_w:
            findings.append({
                "rule": "word_count",
                "severity": "warning",
                "message": f"Too short: {word_count} words (minimum {min_w})",
                "start": 0,
                "end": len(plain),
            })
            penalty += weights.get("word_count", 10)
        elif word_count > max_w:
            findings.append({
                "rule": "word_count",
                "severity": "info",
                "message": f"Too long: {word_count} words (maximum {max_w})",
                "start": 0,
                "end": len(plain),
            })
            penalty += weights.get("word_count", 10) // 2

    clamped = max(0, max_penalty - min(penalty, max_penalty))
    score = int(clamped * 100 // max_penalty)
    return {"score": score, "findings": findings, "penalty": penalty}


def project_quality(store) -> dict:
    config = _load_config(store)
    reqs = store.list_requirements()
    results = []
    for r in reqs:
        result = score_requirement(r, config)
        results.append({
            "id": r["id"],
            "name": r.get("name", ""),
            "score": result["score"],
            "findings": result["findings"],
        })
    avg = sum(r["score"] for r in results) // len(results) if results else 100
    return {
        "average": avg,
        "per_requirement": sorted(results, key=lambda x: x["score"]),
        "total": len(results),
        "config": {
            "min_words": config["min_words"],
            "max_words": config["max_words"],
        },
    }
