"""Tests for LaTeX table geometry in the publisher output.

Verifies that table column specifications use textwidth-based widths
and that the requirements-by-type table has correct structure.
"""
from __future__ import annotations

import re

import pytest

from app.services.publisher import Publisher
from app.services.yaml_store import YamlStore
from app.services.demo_seed import seed_demo_project, PROJECT_ID


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def seeded(tmp_path):
    seed_demo_project(tmp_path, force=True)
    return YamlStore(tmp_path / PROJECT_ID)


# ── helpers ───────────────────────────────────────────────────────────────────


_COL_SPEC_ENV = re.compile(
    r"\\begin\{(longtable|tabular|tabularx)\}(?:\{[^}]*\})?\{"
)


def _extract_col_spec(text: str) -> tuple[str, str] | None:
    """Given a line starting with \\begin{env}..., extract (env_type, col_spec)
    by matching braces.  Returns None if no match found."""
    m = _COL_SPEC_ENV.match(text)
    if m is None:
        return None
    env_type = m.group(1)
    start = m.end()
    depth = 1
    i = start
    while i < len(text) and depth > 0:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    col_spec = text[start : i - 1]
    return env_type, col_spec


def _all_table_specs(latex: str):
    """Yield (env_type, col_spec, line) for every longtable/tabular/tabularx."""
    for full_line in latex.split("\n"):
        m = _COL_SPEC_ENV.match(full_line)
        if m is None:
            continue
        result = _extract_col_spec(full_line)
        if result is None:
            continue
        env_type, col_spec = result
        line_no = latex[: latex.find(full_line)].count("\n") + 1
        yield env_type, col_spec, line_no


def _parse_fractions(col_spec: str) -> list[float]:
    """Extract the fraction from each p{\\dimexpr f\\textwidth... construct."""
    fractions = re.findall(r"\\dimexpr\s*(0\.\d+)\s*\\textwidth", col_spec)
    return [float(f) for f in fractions]


def _has_bare_cm(col_spec: str) -> bool:
    """True when the spec contains a bare p{Xcm} without \\dimexpr."""
    return bool(re.search(r"p\{[0-9]+(?:\.[0-9]+)?cm\}", col_spec))


# ── tests ─────────────────────────────────────────────────────────────────────


class TestNoBareCmWidths:
    """Every longtable/tabular column spec uses \\textwidth, not bare cm."""

    def test_no_bare_cm_in_longtable_or_tabular(self, seeded):
        pub = Publisher(seeded)
        latex = pub.build_latex()
        for env_type, col_spec, line in _all_table_specs(latex):
            if env_type == "tabularx":
                continue
            assert not _has_bare_cm(col_spec), (
                f"line {line}: {env_type} column spec has bare cm: {col_spec!r}"
            )


class TestRowcolorFractionSum:
    """For each table that uses \\rowcolor{tabhead}, the declared
    p-column fractions sum to 1.0 of \\textwidth."""

    def test_rowcolor_fractions_sum_to_one(self, seeded):
        pub = Publisher(seeded)
        latex = pub.build_latex()
        lines = latex.split("\n")

        tested = 0
        for i, line in enumerate(lines, 1):
            if r"\rowcolor{tabhead}" not in line:
                continue
            col_spec: str | None = None
            env_type: str | None = None
            for j in range(i - 1, max(i - 40, 0), -1):
                result = _extract_col_spec(lines[j])
                if result is not None:
                    env_type, col_spec = result
                    break

            assert col_spec is not None, (
                f"line {i}: \\rowcolor{{tabhead}} without a parent table"
            )

            if env_type == "tabularx":
                continue

            fractions = _parse_fractions(col_spec)
            if not fractions:
                continue

            total = sum(fractions)
            tested += 1
            assert abs(total - 1.0) < 0.005, (
                f"line {i}: {env_type} fractions sum to {total:.3f}, "
                f"expected ~1.0.  Spec: {col_spec!r}"
            )

        assert tested >= 1, "No rowcolor tables with p-columns were tested"


class TestRequirementsTableHeaders:
    """The requirements-by-type table emits headers ID, Name, Status,
    Priority in that order."""

    def test_headers_in_order(self, seeded):
        pub = Publisher(seeded)
        latex = pub.build_latex()

        m = re.search(
            r"\\textbf\{ID\}.*?&.*?\\textbf\{Name\}.*?&"
            r".*?\\textbf\{Status\}.*?&.*?\\textbf\{Priority\}",
            latex,
        )
        assert m is not None, "Requirements table header row not found"

        header_row = m.group(0)
        id_pos = header_row.find(r"\textbf{ID}")
        name_pos = header_row.find(r"\textbf{Name}")
        status_pos = header_row.find(r"\textbf{Status}")
        priority_pos = header_row.find(r"\textbf{Priority}")

        assert -1 < id_pos < name_pos < status_pos < priority_pos, (
            f"Header order wrong in: {header_row!r}"
        )


class TestRequirementRowStructure:
    """Every requirement in the output has exactly one header row and,
    when it carries a description, exactly one detail row — no split rows."""

    def test_one_hypertarget_per_requirement(self, seeded):
        """Each requirement ID appears in exactly one \\hypertarget."""
        pub = Publisher(seeded)
        latex = pub.build_latex()

        for r in pub.reqs:
            rid = r["id"]
            count = len(re.findall(
                rf"\\hypertarget\{{req-{re.escape(rid)}\}}", latex
            ))
            assert count == 1, (
                f"Requirement {rid} appears {count} times, expected 1"
            )

    def test_detail_rows_not_split(self, seeded):
        """Requirements that have a detail row produce exactly one
        \\multicolumn per occurrence."""
        pub = Publisher(seeded)
        latex = pub.build_latex()
        lines = latex.split("\n")

        req_ids_with_detail: set[str] = set()
        for i, line in enumerate(lines):
            if r"\hypertarget" not in line:
                continue
            m = re.search(r"\\hypertarget\{req-([^}]+)\}", line)
            if not m:
                continue
            rid = m.group(1)

            for j in range(i + 1, min(i + 5, len(lines))):
                if r"\multicolumn" in lines[j]:
                    req_ids_with_detail.add(rid)
                    break

        desc_reqs = {
            r["id"] for r in pub.reqs if r.get("description", "").strip()
        }
        overlap = req_ids_with_detail & desc_reqs
        assert len(overlap) > 0, (
            "Expected some requirements with descriptions to have detail rows"
        )
