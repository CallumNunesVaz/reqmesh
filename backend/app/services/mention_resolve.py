"""Resolve ``[[ID.param]]`` parameter mentions to their rendered value.

Task 125 taught the app to render ``@parameter`` mentions live: a description
can reference ``[[ID.param]]`` and the in-app read mode swaps it for the
parameter's value. This module is the export-side half — the same resolution
applied to the text the publisher writes into PDF/HTML/Markdown.

The resolver is deliberately pure: no store access, no I/O. The caller supplies
a ``lookup`` that maps an ``(entity id, parameter name)`` pair to a
:class:`ParamValue` (or ``None`` when the reference cannot be resolved), so the
function itself is unit-testable without a project.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from app.services.sysml_export import _fmt_num

#: The suffix the publisher already appends to dangling entity ids — reused here
#: so an unresolvable parameter mention reads the same way as a dangling link.
UNRESOLVED_SUFFIX = " (unresolved reference)"

#: A bracket parameter token: ``[[ID.param]]``. The owner id is word/hyphen
#: characters and the name is word/hyphen/dot, mirroring the frontend's
#: ``PARAM_BRACKET_RE`` in ``frontend/src/components/autoLink.tsx``.
_PARAM_BRACKET_RE = re.compile(r"\[\[([\w-]+\.[\w.-]+)\]\]")


@dataclass(frozen=True)
class ParamValue:
    """A resolvable parameter: its value and unit."""

    value: float
    unit: str = ""


def resolve_parameter_mentions(
    text: str,
    lookup: Callable[[str, str], ParamValue | None],
) -> str:
    """Rewrite every ``[[ID.param]]`` bracket token in *text*.

    A resolvable token becomes ``value unit`` (the unit omitted when empty); an
    unresolvable one becomes the bare reference plus ``(unresolved reference)``.
    Any other ``[[…]]`` — an entity link, for instance — is left completely
    alone.
    """
    if not text or "[[" not in text:
        return text

    def _replace(match: re.Match[str]) -> str:
        ref = match.group(1)
        entity_id, _, name = ref.partition(".")
        param = lookup(entity_id, name)
        if param is None:
            return f"{ref}{UNRESOLVED_SUFFIX}"
        rendered = _fmt_num(param.value)
        if param.unit:
            return f"{rendered} {param.unit}"
        return rendered

    return _PARAM_BRACKET_RE.sub(_replace, text)
