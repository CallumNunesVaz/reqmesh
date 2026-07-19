from __future__ import annotations

import html
import re
from html.parser import HTMLParser

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


WEAK_WORDS = {
    "should", "may", "might", "could", "would",
    "appropriate", "adequate", "sufficient",
    "as needed", "if needed", "if required",
    "and/or", "user-friendly", "user friendly",
    "fast", "robust", "flexible", "scalable",
    "easy", "simple", "simply", "easily",
    "normally", "typically", "generally", "usually",
    "reasonable", "reasonably",
}

VAGUE_QUANTIFIERS = re.compile(
    r"\b(some|several|many|few|minimal|maximal|enough|sufficient|"
    r"a lot of|a number of|a few|a couple of)\b",
    re.IGNORECASE,
)

PASSIVE_RE = re.compile(
    r"\b(am|is|are|was|were|be|been|being)\s+(\w+(?:ed|en|t)|"
    r"given|taken|made|set|built|known|shown|found|seen|done|sent|held|left)\b",
    re.IGNORECASE,
)

PLACEHOLDER_RE = re.compile(r"\b(TODO|FIXME|TBD|XXX|HACK)\b|\?\?\?|\?\?")

MULTI_AND_OR_RE = re.compile(r"\band\s+.*?\band\b|\bor\s+.*?\bor\b", re.IGNORECASE)

MEASURABLE_TERMS = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:%|percent|ms|s|sec|seconds?|minutes?|hours?|"
    r"days?|weeks?|months?|years?|bytes?|KB|MB|GB|TB|"
    r"Hz|kHz|MHz|GHz|bps|fps|px|mm|cm|m|km|g|kg|lb|°C|°F)\b",
    re.IGNORECASE,
)

_WEAK_WORD_PATTERNS: dict[str, re.Pattern] = {
    word: re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
    for word in WEAK_WORDS
}

DEFAULT_CONFIG = {
    "min_words": 5,
    "max_words": 200,
    "rules": {
        "weak_words": True,
        "vague_quantifiers": True,
        "passive_voice": True,
        "placeholders": True,
        "non_atomic": True,
        "untestable": True,
        "word_count": True,
    },
    "weights": {
        "weak_words": 5,
        "vague_quantifiers": 3,
        "passive_voice": 2,
        "placeholders": 10,
        "non_atomic": 5,
        "untestable": 5,
        "word_count": 10,
    },
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
    name = req.get("name", "")
    combined = f"{name}\n{text}"
    plain = combined.strip()
    findings: list[dict] = []
    penalty = 0
    weights = config.get("weights", DEFAULT_CONFIG["weights"])
    rules = config.get("rules", DEFAULT_CONFIG["rules"])
    max_penalty = sum(weights.values())

    if rules.get("weak_words", True):
        lower = plain.lower()
        for word, pattern in _WEAK_WORD_PATTERNS.items():
            for m in pattern.finditer(lower):
                findings.append({
                    "rule": "weak_words",
                    "severity": "warning",
                    "message": f'Weak/ambiguous word: "{word}"',
                    "start": m.start(),
                    "end": m.end(),
                })
                penalty += weights.get("weak_words", 5)

    if rules.get("vague_quantifiers", True):
        for m in VAGUE_QUANTIFIERS.finditer(plain):
            findings.append({
                "rule": "vague_quantifier",
                "severity": "warning",
                "message": f'Vague quantifier: "{m.group()}"',
                "start": m.start(),
                "end": m.end(),
            })
            penalty += weights.get("vague_quantifiers", 3)

    if rules.get("passive_voice", True):
        for m in PASSIVE_RE.finditer(plain):
            findings.append({
                "rule": "passive_voice",
                "severity": "info",
                "message": f'Possible passive voice: "{m.group()}"',
                "start": m.start(),
                "end": m.end(),
            })
            penalty += weights.get("passive_voice", 2)

    if rules.get("placeholders", True):
        for m in PLACEHOLDER_RE.finditer(plain):
            findings.append({
                "rule": "placeholder",
                "severity": "error",
                "message": f'Placeholder found: "{m.group()}"',
                "start": m.start(),
                "end": m.end(),
            })
            penalty += weights.get("placeholders", 10)

    if rules.get("non_atomic", True):
        match = re.search(r"\band\b.*\band\b", plain, re.IGNORECASE)
        if match:
            findings.append({
                "rule": "non_atomic",
                "severity": "info",
                "message": "Multiple conjunctions — consider splitting into separate requirements",
                "start": 0,
                "end": len(plain),
            })
            penalty += weights.get("non_atomic", 5)

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
