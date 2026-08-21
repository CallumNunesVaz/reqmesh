r"""Parameter-mention resolution for exports.

The in-app read mode resolves ``[[ID.param]]`` mentions (task 125); this is the
export-side half. ``resolve_parameter_mentions`` is pure — a caller supplies the
lookup — so the token-level behaviour is unit-tested directly, and the
publisher is tested end-to-end to prove HTML, LaTeX and Markdown all resolve the
same value.

Bare ``ID.param`` (the plain-text form) is deliberately left alone: rewriting it
would corrupt ordinary prose. Only the rich-text bracket token ``[[ID.param]]``
is rewritten.
"""

from __future__ import annotations

from app.services.mention_resolve import ParamValue, resolve_parameter_mentions
from app.services.publisher import Publisher
from app.services.publishers.latex_helpers import latex_escape
from app.services.yaml_store import YamlStore


# ── helpers ────────────────────────────────────────────────────────────────────


def _lookup(values: dict[str, ParamValue]):
    """Build a lookup from a ``{"ID.param": ParamValue}`` mapping."""

    def lookup(entity_id: str, name: str) -> ParamValue | None:
        return values.get(f"{entity_id}.{name}")

    return lookup


def _requirement(**overrides) -> dict:
    data: dict = {
        "id": "REQ-0001",
        "name": "Temperature",
        "type": "functional",
        "status": "proposed",
        "priority": "medium",
        "description": "",
        "rationale": "",
        "source": "",
    }
    data.update(overrides)
    return data


# ── the pure resolver ──────────────────────────────────────────────────────────


class TestResolveParameterMentions:
    def test_resolves_value_and_unit(self):
        lookup = _lookup({"REQ-0001.temp_max": ParamValue(30, "°C")})
        assert resolve_parameter_mentions("[[REQ-0001.temp_max]]", lookup) == "30 °C"

    def test_unit_omitted_when_empty(self):
        lookup = _lookup({"REQ-0001.temp_max": ParamValue(30, "")})
        out = resolve_parameter_mentions("[[REQ-0001.temp_max]]", lookup)
        assert out == "30"
        assert not out.endswith(" ")

    def test_whole_number_has_no_trailing_dot_zero(self):
        lookup = _lookup({"REQ-0001.temp_max": ParamValue(30.0, "°C")})
        assert resolve_parameter_mentions("[[REQ-0001.temp_max]]", lookup) == "30 °C"

    def test_unknown_requirement_id_is_unresolved(self):
        lookup = _lookup({})
        out = resolve_parameter_mentions("[[NOPE.temp_max]]", lookup)
        assert out == "NOPE.temp_max (unresolved reference)"

    def test_known_requirement_unknown_parameter_is_unresolved(self):
        lookup = _lookup({"REQ-0001.temp_max": ParamValue(30, "°C")})
        out = resolve_parameter_mentions("[[REQ-0001.pressure]]", lookup)
        assert out == "REQ-0001.pressure (unresolved reference)"

    def test_multiple_mentions_all_resolve(self):
        lookup = _lookup({
            "REQ-0001.a": ParamValue(1, "s"),
            "REQ-0002.b": ParamValue(2, ""),
        })
        out = resolve_parameter_mentions("[[REQ-0001.a]] then [[REQ-0002.b]]", lookup)
        assert out == "1 s then 2"

    def test_entity_bracket_token_is_left_alone(self):
        lookup = _lookup({})
        assert resolve_parameter_mentions("[[REQ-0001]]", lookup) == "[[REQ-0001]]"

    def test_bare_plain_text_form_is_not_rewritten(self):
        lookup = _lookup({"REQ-0001.temp_max": ParamValue(30, "°C")})
        assert resolve_parameter_mentions("REQ-0001.temp_max", lookup) == "REQ-0001.temp_max"


# ── the publisher ──────────────────────────────────────────────────────────────


class TestPublisherResolution:
    def _publish(self, tmp_path, **fields):
        store = YamlStore(tmp_path / "proj")
        store.create_requirement(_requirement(**fields))
        pub = Publisher(store)
        return pub.build_html(), pub.build_latex(), pub.build_markdown()

    def test_resolves_in_all_three_builders(self, tmp_path):
        html, latex, md = self._publish(
            tmp_path,
            description="The maximum is [[REQ-0001.temp_max]].",
            parameters=[{"name": "temp_max", "value": 30, "unit": "°C"}],
        )
        assert "30 °C" in html
        assert "30 °C" in md
        assert "[[REQ-0001.temp_max]]" not in html
        assert "[[REQ-0001.temp_max]]" not in md
        assert "[[REQ-0001.temp_max]]" not in latex
        # LaTeX renders the degree sign as its macro, not as raw unicode.
        assert latex_escape("30 °C") in latex

    def test_computed_parameter_resolves_to_value(self, tmp_path):
        html, _latex, md = self._publish(
            tmp_path,
            description="The maximum is [[REQ-0001.temp_max]].",
            parameters=[{"name": "temp_max", "expr": "15 * 2", "unit": "°C"}],
        )
        assert "30 °C" in html
        assert "30 °C" in md

    def test_unresolved_mention_renders_broken(self, tmp_path):
        html, latex, md = self._publish(
            tmp_path,
            description="The maximum is [[REQ-0001.missing]].",
            parameters=[{"name": "temp_max", "value": 30, "unit": "°C"}],
        )
        for out in (html, latex, md):
            assert "REQ-0001.missing (unresolved reference)" in out

    def test_latex_escapes_percent_and_underscore_in_unit(self, tmp_path):
        html, latex, _md = self._publish(
            tmp_path,
            description="Gain is [[REQ-0001.gain]].",
            parameters=[{"name": "gain", "value": 30, "unit": "50%_span"}],
        )
        assert "[[REQ-0001.gain]]" not in latex
        # % and _ are escaped rather than acting as a comment / subscript.
        assert r"50\%\_" in latex
        assert "50%_span" not in latex
        # HTML keeps the literal unit.
        assert "30 50%_span" in html
