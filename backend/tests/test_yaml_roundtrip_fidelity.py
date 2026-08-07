"""The YAML store must preserve string content exactly across a write-then-read
cycle — through both the round-trip and fast-reader paths.

A width of 120 made ruamel.yaml 0.19.1 emit a line break inside a run of two
spaces, turning the second space into end-of-line whitespace that YAML folding
stripped on re-read. The fix is y.width = 4096 in _round_trip_yaml(). These
tests prove no regression returns, and that the fast reader (used for
collection lists) agrees with what was written.
"""

from pathlib import Path

from app.services.yaml_store import YamlStore


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _write_and_read(tmp_path: Path, name: str, value: str):
    """Write `{"text": value}` to a temp YAML, read back with both parsers.

    Returns (round_trip_value, fast_reader_value).
    """
    store = YamlStore(tmp_path / "proj")
    store.ensure_dirs()
    p = tmp_path / "proj" / f"{name}.yaml"
    store._write_yaml(p, {"text": value})
    rt = store._parse_yaml(p)
    fast = store._parse_fast(p)
    return rt["text"], fast["text"]


def _assert_both(rt: str, fast: str, original: str, label: str):
    """Fail with a clear message naming which parser misread and how."""
    assert rt == original, (
        f"{label}: round-trip parser changed the value.\n"
        f"  original: {original!r}\n"
        f"  got:      {rt!r}"
    )
    assert fast == original, (
        f"{label}: fast reader changed the value.\n"
        f"  original: {original!r}\n"
        f"  got:      {fast!r}"
    )


# ---------------------------------------------------------------------------
# 1. The real regression
# ---------------------------------------------------------------------------

def test_real_regression(tmp_path):
    """The exact string from FLTC0000 that lost a character on every save."""
    value = (
        "Mechanical controls provide direct tactile feedback to the pilot — there is "
        "no lag or artificial feel system.  This is essential for a training aircraft "
        "where the student must learn to interpret control forces."
    )
    rt, fast = _write_and_read(tmp_path, "real_regression", value)
    _assert_both(rt, fast, value, "real regression")


# ---------------------------------------------------------------------------
# 2. Multi-space runs at many offsets
# ---------------------------------------------------------------------------

def _build_two_space_at_offset(offset: int) -> str:
    """Return a string where two consecutive spaces start at 1-indexed *offset*."""
    before = "A" * (offset - 1)
    after = "B" * 50
    return before + "  " + after


def test_two_space_runs_at_every_offset(tmp_path):
    """A two-space run at every offset from 90–200 must survive the round-trip.

    The original bug only triggered when the wrap column fell *inside* a
    multi-space run.  A single fixed offset only proves one column; this
    exercises the range that would be hit at typical width values (80–200).
    """
    store = YamlStore(tmp_path / "proj")
    store.ensure_dirs()

    for offset in range(90, 201):
        value = _build_two_space_at_offset(offset)
        p = tmp_path / "proj" / f"offset_{offset}.yaml"
        store._write_yaml(p, {"text": value})
        rt = store._parse_yaml(p)
        fast = store._parse_fast(p)
        label = f"two-space run at offset {offset}"
        _assert_both(rt["text"], fast["text"], value, label)


# ---------------------------------------------------------------------------
# 3. Three or more consecutive spaces
# ---------------------------------------------------------------------------

def test_three_consecutive_spaces(tmp_path):
    value = "alpha   beta"
    rt, fast = _write_and_read(tmp_path, "three_spaces", value)
    _assert_both(rt, fast, value, "three consecutive spaces")


def test_four_consecutive_spaces(tmp_path):
    value = "gamma    delta"
    rt, fast = _write_and_read(tmp_path, "four_spaces", value)
    _assert_both(rt, fast, value, "four consecutive spaces")


def test_many_consecutive_spaces(tmp_path):
    value = "start" + (" " * 10) + "end"
    rt, fast = _write_and_read(tmp_path, "many_spaces", value)
    _assert_both(rt, fast, value, "10 consecutive spaces")


# ---------------------------------------------------------------------------
# 4. Long string with no multi-space run (control — must still pass)
# ---------------------------------------------------------------------------

def test_long_string_no_multi_space_run(tmp_path):
    """A string long enough to wrap, with NO consecutive spaces."""
    # 300 characters of alternating single-letter words — no two spaces.
    parts = [chr(97 + i % 26) for i in range(300)]
    value = " ".join(parts)
    rt, fast = _write_and_read(tmp_path, "long_no_multi", value)
    _assert_both(rt, fast, value, "long string, no multi-space runs")


# ---------------------------------------------------------------------------
# 5. Embedded newlines
# ---------------------------------------------------------------------------

def test_embedded_newlines(tmp_path):
    value = "line1\nline2\n\nline4 after blank"
    rt, fast = _write_and_read(tmp_path, "embedded_nl", value)
    _assert_both(rt, fast, value, "embedded newlines")


def test_windows_newlines(tmp_path):
    value = "first line\r\nsecond line\r\nthird line"
    rt, fast = _write_and_read(tmp_path, "windows_nl", value)
    _assert_both(rt, fast, value, "Windows newlines")


def test_trailing_newline(tmp_path):
    value = "ends with newline\n"
    rt, fast = _write_and_read(tmp_path, "trailing_nl", value)
    _assert_both(rt, fast, value, "trailing newline")


# ---------------------------------------------------------------------------
# 6. Leading and trailing whitespace
# ---------------------------------------------------------------------------

def test_leading_whitespace(tmp_path):
    value = "  leading spaces"
    rt, fast = _write_and_read(tmp_path, "leading_ws", value)
    _assert_both(rt, fast, value, "leading whitespace")


def test_trailing_whitespace(tmp_path):
    value = "trailing spaces  "
    rt, fast = _write_and_read(tmp_path, "trailing_ws", value)
    _assert_both(rt, fast, value, "trailing whitespace")


def test_both_ends_whitespace(tmp_path):
    value = "  both ends  "
    rt, fast = _write_and_read(tmp_path, "both_ws", value)
    _assert_both(rt, fast, value, "whitespace at both ends")


def test_tab_characters(tmp_path):
    value = "column1\tcolumn2\tcolumn3"
    rt, fast = _write_and_read(tmp_path, "tabs", value)
    _assert_both(rt, fast, value, "tab characters")


# ---------------------------------------------------------------------------
# 7. Non-ASCII
# ---------------------------------------------------------------------------

def test_em_dash(tmp_path):
    value = "Pilot awareness — the single most important factor — cannot be automated."
    rt, fast = _write_and_read(tmp_path, "em_dash", value)
    _assert_both(rt, fast, value, "em dash")


def test_multibyte_characters(tmp_path):
    value = "café résumé naïve — touché"
    rt, fast = _write_and_read(tmp_path, "multibyte", value)
    _assert_both(rt, fast, value, "multi-byte characters")


def test_multibyte_at_wrap_boundaries(tmp_path):
    """Multi-byte chars placed near typical wrap columns — char count vs byte
    count confusion would be caught here."""
    # Build a string where multi-byte chars straddle position 120.
    prefix = "X" * 115
    value = prefix + "—café—résumé" + ("Y" * 60)
    rt, fast = _write_and_read(tmp_path, "multibyte_boundary", value)
    _assert_both(rt, fast, value, "multi-byte near wrap boundary")


# ---------------------------------------------------------------------------
# 8. HTML content
# ---------------------------------------------------------------------------

def test_html_paragraph(tmp_path):
    value = (
        "<p>Mechanical controls provide direct tactile feedback to the pilot — "
        "there is no lag or artificial feel system.  This is essential for a "
        "training aircraft where the student must learn to interpret control "
        "forces.</p>"
    )
    rt, fast = _write_and_read(tmp_path, "html_para", value)
    _assert_both(rt, fast, value, "HTML paragraph")


def test_html_nested_tags(tmp_path):
    value = "<div><p>Nested <strong>bold</strong> and <em>italic</em> text.</p></div>"
    rt, fast = _write_and_read(tmp_path, "html_nested", value)
    _assert_both(rt, fast, value, "HTML nested tags")


def test_html_with_attributes(tmp_path):
    value = '<a href="https://example.com" target="_blank" class="link">click here</a>'
    rt, fast = _write_and_read(tmp_path, "html_attrs", value)
    _assert_both(rt, fast, value, "HTML with attributes")
