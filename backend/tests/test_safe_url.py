"""The guard between stored data and an href — belt-and-braces with the
frontend copy, tested with identical cases so the two implementations cannot
drift apart."""

import pytest

from app.services.sanitize import is_safe_external_url
from app.services.load_guard import validate_on_load


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://example.com/spec.pdf", True),
        ("http://intranet/doc", True),
        ("mailto:eng@example.com", True),
        ("docs/spec.pdf", True),                   # relative
        ("javascript:alert(1)", False),
        ("JaVaScRiPt:alert(1)", False),
        ("java\tscript:alert(1)", False),           # tab inside the scheme
        ("  javascript:alert(1)", False),           # leading space
        ("data:text/html,<script>", False),
        ("file:///etc/passwd", False),
        ("//evil.com", False),                     # protocol-relative
        ("", False),
        (None, False),
    ],
)
def test_is_safe_external_url(url, expected):
    assert is_safe_external_url(url) is expected


def test_spec_with_unsafe_url_is_blanked_not_withheld():
    """An unsafe url is blanked but the specification is still served — losing
    it would break every requirement that traces to it."""
    item = validate_on_load("specifications", {
        "id": "SRS-001",
        "name": "Safety Spec",
        "description": "The safety specification",
        "url": "javascript:alert(1)",
        "requirements": ["REQ-001"],
    })
    assert item is not None, "specification was withheld when it should have been served"
    assert item["url"] == "", "unsafe url was not blanked"
    assert item["id"] == "SRS-001"
    assert item["name"] == "Safety Spec"
    assert item["description"] == "The safety specification"
    assert item["requirements"] == ["REQ-001"]


def test_spec_with_safe_url_is_untouched():
    item = validate_on_load("specifications", {
        "id": "SRS-002",
        "name": "Standards",
        "url": "https://standards.example.com/spec.pdf",
    })
    assert item is not None
    assert item["url"] == "https://standards.example.com/spec.pdf"
