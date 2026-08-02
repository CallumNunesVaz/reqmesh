"""The requirement-lint rule set — one definition, two consumers.

The pattern-based rules live here as *data* rather than as code, because they
are needed in two places: :mod:`app.services.quality` scores requirements
server-side, and ``frontend/src/components/DescriptionHelper.tsx`` gives live
feedback while someone types. Those two had independently hand-written copies of
the same regexes and had already drifted — the frontend was missing
``passive_voice`` entirely and worded several messages differently.

So the rules are declared once and the frontend's copy is *generated*:

    cd backend && .venv/bin/python gen_quality_rules.py

which writes ``frontend/src/lib/qualityRules.json``. That file is generated —
never hand-edit it — exactly as ``schemas/*.json`` is generated from the
Pydantic models.

**Patterns must be portable between Python ``re`` and JavaScript ``RegExp``.**
Both are applied case-insensitively by their respective consumers. Stick to
character classes, ``\\b``, alternation and simple quantifiers; do not use named
groups, possessive quantifiers, or ``\\A``/``\\Z``, none of which mean the same
thing on both sides. :func:`assert_portable` enforces the parts of that which
can be checked mechanically.

Rules that are not a regex over the text — word count, and the
measurable-criteria check that depends on ``verification_method`` — stay as code
in :mod:`app.services.quality`. Forcing them into this table would mean encoding
their logic in a second language anyway, which is the thing this module exists
to prevent.

Rule ids are a public contract: they appear in ``_meta.yaml`` under
``quality.rules`` / ``quality.weights`` so a project can disable or reweight
one, and they are what ``QualityFinding.rule`` carries to the UI. Renaming an id
silently re-enables a rule somebody turned off.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict

# Severities, in the order the UI sorts them. `error` means the statement is
# not fit to review; `warning` means it is probably wrong; `info` is a matter
# of house style.
SEVERITIES = ("error", "warning", "info")


@dataclass(frozen=True)
class Rule:
    """One pattern-based lint rule.

    ``message`` is a template with a single ``{match}`` placeholder, filled with
    the matched text. It is written for the person editing the requirement, so
    it says what to do instead — not merely what is wrong.

    ``incose`` cites the rule in the INCOSE *Guide to Writing Requirements*
    (v4 summary sheet) that this implements, or "" where reqmesh checks
    something the guide does not cover. Rule numbering shifted between guide
    versions, so the citation carries the rule *name* too and the name is the
    authoritative half.
    """

    id: str
    title: str
    severity: str
    pattern: str
    message: str
    weight: int
    incose: str = ""
    enabled: bool = True
    # The key under `_meta.yaml` -> quality.rules / quality.weights, when it is
    # not the id. Three of the original rules report a singular finding name
    # but are configured under a plural key (`vague_quantifier` vs
    # `vague_quantifiers`). That is not worth a migration of every project's
    # meta file, so the discrepancy is recorded rather than corrected.
    config_key: str = ""

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(f"{self.id}: severity must be one of {SEVERITIES}")
        if "{match}" not in self.message:
            raise ValueError(f"{self.id}: message must contain the {{match}} placeholder")
        assert_portable(self.id, self.pattern)

    @property
    def config(self) -> str:
        """The `_meta.yaml` key that enables/weights this rule."""
        return self.config_key or self.id


# Constructs that mean different things — or nothing — in JavaScript RegExp.
_NON_PORTABLE = (
    (r"\(\?P<", "Python named group; JS uses (?<name>...)"),
    (r"\(\?P=", "Python named backreference"),
    (r"\\A", r"use ^ instead of \A"),
    (r"\\Z", r"use $ instead of \Z"),
    (r"\(\?#", "Python inline comment group"),
    (r"\(\?[aiLmsux)]*\)", "Python inline flags; flags are set by the consumer"),
)


def assert_portable(rule_id: str, pattern: str) -> None:
    """Raise if *pattern* uses syntax that does not port to JavaScript.

    Catches the mechanical differences only — it cannot prove semantic
    equivalence, which is what ``tests/test_quality_rules.py`` is for by running
    every pattern against the same fixtures on both sides.
    """
    for probe, why in _NON_PORTABLE:
        if re.search(probe, pattern):
            raise ValueError(f"{rule_id}: non-portable regex ({why}): {pattern!r}")
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"{rule_id}: invalid regex: {exc}") from exc


# ── The rule set ─────────────────────────────────────────────────────────────
#
# Weights are the penalty per *occurrence*, and the score is
# 100 - min(total_penalty, max_penalty) / max_penalty. Stylistic rules are
# deliberately cheap: a requirement that is precise and testable should not
# score badly for containing a bracket.

PATTERN_RULES: tuple[Rule, ...] = (
    # ── Obligation & phrasing ──
    Rule(
        id="weak_words",
        title="Weak or ambiguous wording",
        severity="warning",
        incose="R07 Avoid Vague Terms",
        pattern=(
            r"\b(should|may|might|could|would|appropriate|adequate|sufficient|"
            r"user-friendly|user friendly|fast|robust|flexible|scalable|"
            r"easy|simple|simply|easily|normally|typically|generally|usually|"
            r"reasonable|reasonably)\b"
        ),
        message='"{match}" is imprecise — use "shall" for an obligation, or state the measurable property',
        weight=5,
    ),
    Rule(
        id="negation",
        title="Negation",
        severity="warning",
        incose="R16 Avoid Not",
        pattern=r"\b(shall not|must not|will not|never|not)\b",
        message='"{match}" is a negative — state what the system shall do, not what it shall not do',
        weight=4,
    ),
    Rule(
        id="superfluous_infinitive",
        title="Superfluous infinitive",
        severity="warning",
        incose="R11 Superfluous Infinitives",
        pattern=r"\b(have the ability to|be capable of|be designed to|be able to|be used to)\b",
        message='"{match}" is unnecessary — state the requirement directly with "shall"',
        weight=4,
    ),
    Rule(
        id="escape_clauses",
        title="Escape clause",
        severity="warning",
        incose="R08 No Escape Clauses",
        pattern=(
            r"\b(as far as (?:is )?possible|as little as possible|as much as possible|"
            r"where possible|if possible|if necessary|if required|if needed|as needed|"
            r"to the extent (?:necessary|practical|practicable)|as appropriate|"
            r"as required|if it should prove necessary|if practicable|"
            r"wherever practical|to the greatest extent)\b"
        ),
        message='"{match}" lets the supplier decide whether to comply — state the condition explicitly or drop it',
        weight=6,
    ),
    Rule(
        id="oblique",
        title="Oblique requirement",
        severity="warning",
        incose="R17 Oblique",
        # Both sides must be 3+ letters. `\w/\w` also matched every unit an
        # engineering requirement contains — km/h, m/s, kg/m3, L/min — which
        # made the rule fire constantly on exactly the well-formed, quantified
        # statements it should have left alone.
        pattern=r"\band/or\b|[A-Za-z]{3,}/[A-Za-z]{3,}",
        message='"{match}" is oblique — use "and" or "or", not both; spell out alternatives separated by "and" or "or"',
        weight=3,
    ),
    Rule(
        id="purpose_clause",
        title="Purpose clause",
        severity="info",
        incose="R20 Avoid Purpose",
        pattern=r"\b(with the intent of|in order to|so as to|so that)\b",
        message='"{match}" states why — state what behaviour shall be satisfied instead',
        weight=2,
    ),
    Rule(
        id="passive_voice",
        title="Passive voice",
        severity="info",
        incose="",
        pattern=(
            r"\b(am|is|are|was|were|be|been|being)\s+(\w+(?:ed|en|t)|"
            r"given|taken|made|set|built|known|shown|found|seen|done|sent|held|left)\b"
        ),
        message='Possible passive voice "{match}" — use active voice (e.g. "The system shall…")',
        weight=2,
    ),
    # ── Precision & specificity ──
    Rule(
        id="vague_quantifier",
        title="Vague quantifier",
        severity="warning",
        incose="",
        pattern=(
            r"\b(some|several|many|few|minimal|maximal|enough|sufficient|"
            r"a lot of|a number of|a few|a couple of)\b"
        ),
        message='Vague quantifier "{match}" — use a specific number or value',
        weight=3,
        config_key="vague_quantifiers",
    ),
    Rule(
        id="pronoun",
        title="Pronoun",
        severity="warning",
        incose="R24 Avoid Pronouns",
        pattern=r"\b(these|those|their|them|they|this|its|she|he|it)\b",
        message='Pronoun "{match}" — name the specific entity (e.g. "the system" rather than "it")',
        weight=4,
    ),
    Rule(
        id="absolute",
        title="Absolute term",
        severity="warning",
        incose="R26 Avoid Absolutes",
        pattern=r"\b(completely|totally|always|every|never|none|any|all)\b|\b100%",
        message='Absolute term "{match}" — qualify with conditions or tolerances (e.g. "under normal load" rather than "always")',
        weight=4,
    ),
    # ── Structure & cohesion ──
    Rule(
        id="combinator",
        title="Combinator",
        severity="info",
        incose="R19 Avoid Combinators",
        pattern=r"\b(in addition to|as well as|otherwise|meanwhile|however|whether|unless|but)\b",
        message='Combinator "{match}" — split into separate, independently verifiable requirements',
        weight=3,
    ),
    Rule(
        id="temporal_indefinite",
        title="Temporal indefinite",
        severity="warning",
        incose="R35 Temporal Indefinite",
        pattern=r"\b(in a timely manner|in due course|when convenient|as soon as|eventually|promptly|at last)\b",
        message='Temporal indefinite "{match}" — specify a concrete deadline or interval (e.g. "within 500 ms")',
        weight=4,
    ),
    Rule(
        id="open_ended",
        title="Open-ended clause",
        severity="warning",
        incose="R10 Avoid Open-Ended Clauses",
        pattern=r"(\b(including but not limited to|such as|and so on|and so forth|among others)\b|\betc\.?)",
        message='"{match}" leaves the set undefined — enumerate every item that must be satisfied',
        weight=6,
    ),
    # ── Format & presentation ──
    Rule(
        id="placeholder",
        title="Placeholder",
        severity="error",
        incose="",
        pattern=r"\b(TODO|FIXME|TBD|XXX|HACK)\b|\?\?\?|\?\?",
        message='Placeholder "{match}" — replace with concrete content before review',
        weight=10,
        config_key="placeholders",
    ),
    Rule(
        id="abbreviation",
        title="Abbreviation",
        severity="info",
        incose="R38 Avoid Abbreviations",
        pattern=r"\b(e\.g\.|i\.e\.|vs\.|approx\.|misc\.|min\.|max\.)",
        message='Abbreviation "{match}" — spell out in full (e.g. "for example" rather than "e.g.")',
        weight=2,
    ),
    Rule(
        id="non_atomic",
        title="Non-atomic requirement",
        severity="info",
        incose="",
        pattern=r"\band\b.*\band\b",
        message='Multiple conjunctions around "{match}" — consider splitting into separate requirements',
        weight=5,
    ),
    Rule(
        id="parentheses",
        title="Parentheses",
        severity="info",
        incose="R21 Avoid Parentheses",
        pattern=r"\([^)]+\)|\[[^\]]+\]",
        message='Parenthetical "{match}" — integrate the content into the main sentence or create a separate requirement',
        weight=2,
    ),
    # ── Disabled — checked by bespoke code ──
    Rule(
        id="no_obligation",
        title="No obligation verb",
        severity="warning",
        incose="R01 Structured Statements",
        pattern=r"\b(is required to|shall|must|will)\b",
        message='No obligation verb found — add "shall", "must", "will", or "is required to"{match}',
        weight=6,
        enabled=False,
    ),
)
"""The pattern rules, in the order findings are reported."""


def rule_ids() -> tuple[str, ...]:
    return tuple(r.id for r in PATTERN_RULES)


def as_dicts() -> list[dict]:
    """The rule set as plain dicts — the payload the frontend pack carries."""
    return [asdict(r) for r in PATTERN_RULES]
