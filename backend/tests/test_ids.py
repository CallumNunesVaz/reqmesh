"""Unit tests for `safe_id` — the guard that stops project/requirement ids
from escaping the project tree via path traversal or suspicious characters.
"""

import pytest
from fastapi import HTTPException

from app.core.ids import safe_id


# ── Accepted ids ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value, expected", [
    ("AVNC0000",  "AVNC0000"),
    ("cessna-172", "cessna-172"),
    ("a",         "a"),
    ("a.b_c 1",   "a.b_c 1"),
    ("  ok  ",    "ok"),
])
def test_accepted_ids(value, expected):
    assert safe_id(value) == expected


# ── Rejected ids ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value", [
    "",
    "   ",
    "../etc",
    "a/b",
    "a\\b",
    "..hidden",
    "a..b",
    ".start",
    "-start",
    "_start",
])
def test_rejected_ids(value):
    with pytest.raises(HTTPException) as exc_info:
        safe_id(value)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail.startswith("Invalid id")


# ── Non-str is rejected ───────────────────────────────────────────────────────

@pytest.mark.parametrize("value", [None, 123])
def test_non_str_rejected(value):
    with pytest.raises(HTTPException) as exc_info:
        safe_id(value)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail.startswith("Invalid id")


# ── Kind argument appears in rejection detail ─────────────────────────────────

def test_custom_kind_in_detail():
    with pytest.raises(HTTPException) as exc_info:
        safe_id("", kind="requirement id")
    assert exc_info.value.status_code == 400
    assert "requirement id" in exc_info.value.detail
