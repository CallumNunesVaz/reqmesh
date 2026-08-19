"""Tests for the rule definitions in app.services.quality_rules."""

from __future__ import annotations

import re

import pytest

from app.services.quality_rules import PATTERN_RULES, Rule, assert_portable, as_dicts


# ── Structural invariants ────────────────────────────────────────────────────


def test_unique_ids():
    """Every rule has a unique id."""
    ids = [r.id for r in PATTERN_RULES]
    assert len(ids) == len(set(ids)), f"Duplicate ids: {ids}"


def test_unique_configs():
    """Every rule has a unique config key."""
    configs = [r.config for r in PATTERN_RULES]
    assert len(configs) == len(set(configs)), f"Duplicate configs: {configs}"


# ── Pattern validity & portability ───────────────────────────────────────────


def test_all_patterns_compile():
    """Every rule's pattern is a valid regex."""
    for rule in PATTERN_RULES:
        try:
            re.compile(rule.pattern)
        except re.error as exc:
            pytest.fail(f"{rule.id}: pattern does not compile: {exc}")


def test_all_patterns_portable():
    """Every rule's pattern passes the portability check."""
    for rule in PATTERN_RULES:
        try:
            assert_portable(rule.id, rule.pattern)
        except ValueError as exc:
            pytest.fail(f"{rule.id}: {exc}")


# ── Positive / negative fixtures per rule ────────────────────────────────────
#
# Each entry: (rule_id, should_match, should_not_match)
#
# should_match is a sentence that *contains* at least one match.
# should_not_match is a sentence that must produce *no* match — it guards
# against patterns so broad they fire on everything.

FIXTURES: list[tuple[str, str, str]] = [
    ("weak_words", "The system should authenticate users", "The system shall authenticate users"),
    ("negation", "The system shall not crash", "The system shall be stable"),
    (
        "superfluous_infinitive",
        "The system shall be able to authenticate users",
        "The system shall authenticate users",
    ),
    (
        "escape_clauses",
        "The system shall retry where possible",
        "The system shall retry three times",
    ),
    ("oblique", "The system shall support input/output devices", "The system shall support input and output devices"),
    (
        "purpose_clause",
        "The system shall cache results in order to reduce latency",
        "The system shall respond within 500 ms",
    ),
    ("passive_voice", "Data is processed by the system", "The system processes data"),
    ("vague_quantifier", "The system shall support several users", "The system shall support 500 users"),
    ("pronoun", "The system shall authenticate it", "The system shall authenticate the user"),
    ("absolute", "The system shall always log errors", "The alloy shall withstand 500 degrees"),
    ("combinator", "The system shall do X unless Y occurs", "The system shall do X and Y"),
    (
        "temporal_indefinite",
        "The system shall eventually log out",
        "The system shall log out after 30 minutes",
    ),
    ("open_ended", "The system shall support protocols such as TCP", "The system shall support TCP and UDP"),
    ("placeholder", "TODO: implement authentication", "The system shall implement authentication"),
    ("abbreviation", "The system shall support e.g. OAuth", "The system shall support for example OAuth"),
    ("non_atomic", "The system shall do X and the system shall do Y and also Z", "The system shall perform authentication"),
    (
        "parentheses",
        "The system shall be fast (under 500 ms)",
        "The system shall respond within 500 ms",
    ),
    # no_obligation's pattern matches *obligation verbs* (the bespoke check
    # in quality.py inverts it).  Test the pattern as-is.
    ("no_obligation", "The system shall authenticate users", "The system description"),
]


@pytest.mark.parametrize("rule_id,should_match,should_not_match", FIXTURES)
def test_positive_match(rule_id: str, should_match: str, should_not_match: str):
    """Each rule's pattern matches its positive fixture."""
    rule = _get_rule(rule_id)
    matches = list(re.finditer(rule.pattern, should_match, re.IGNORECASE))
    assert len(matches) > 0, (
        f"{rule_id}: pattern {rule.pattern!r} did not match {should_match!r}"
    )


@pytest.mark.parametrize("rule_id,should_match,should_not_match", FIXTURES)
def test_negative_no_match(rule_id: str, should_match: str, should_not_match: str):
    """Each rule's pattern does NOT match its negative fixture."""
    rule = _get_rule(rule_id)
    matches = list(re.finditer(rule.pattern, should_not_match, re.IGNORECASE))
    assert len(matches) == 0, (
        f"{rule_id}: pattern {rule.pattern!r} unexpectedly matched {should_not_match!r}: "
        f"{[m.group(0) for m in matches]}"
    )


def _get_rule(rule_id: str) -> Rule:
    for r in PATTERN_RULES:
        if r.id == rule_id:
            return r
    pytest.fail(f"Rule not found: {rule_id}")


# ── as_dicts / gen_quality_rules integration ─────────────────────────────────


def test_as_dicts_matches_rules():
    """as_dicts() returns one dict per PATTERN_RULES entry."""
    dicts = as_dicts()
    assert len(dicts) == len(PATTERN_RULES)
    for rule, d in zip(PATTERN_RULES, dicts, strict=True):
        assert d["id"] == rule.id
        assert d["config"] == rule.config
        assert d["severity"] == rule.severity
        assert d["pattern"] == rule.pattern
        assert d["weight"] == rule.weight
        assert d["enabled"] == rule.enabled
