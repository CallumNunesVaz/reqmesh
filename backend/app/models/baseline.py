from __future__ import annotations

import re

from pydantic import BaseModel, Field

#: A baseline's due date, or "" when it has none. Date only — a baseline is a
#: project milestone, not an appointment, and a time zone on it would be a
#: field nobody can answer correctly.
DUE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Baseline(BaseModel):
    name: str
    frozen_at: str = ""
    frozen: bool = True
    snapshot: dict[str, dict] = Field(default_factory=dict)


class BaselineCreate(BaseModel):
    name: str
    frozen_at: str = ""
    snapshot: dict[str, dict] = Field(default_factory=dict)


class BaselineDef(BaseModel):
    """A baseline *definition*, as stored in ``_meta.yaml`` under ``baselines``.

    Distinct from ``Baseline`` above, which is the frozen snapshot written into
    the ``baselines`` collection when a baseline is frozen. The definition is
    the plan; the snapshot is the record of what the plan contained when it was
    frozen.

    ``order`` is **not stored**. A baseline's position in the sequence is its
    index in the ``_meta.yaml`` list — one source of truth, which a stored
    integer would immediately start disagreeing with (two baselines claiming
    order 3, a gap after a delete, a reorder that updates the list but not the
    field). The API reports a computed 1-based ``order`` for display, and
    reordering rewrites the list.
    """

    name: str
    symbol: str = ""
    description: str = ""
    #: ``YYYY-MM-DD``, or "" when the baseline has no deadline yet. Validated
    #: by ``normalize_baseline_defs``; a malformed value read from hand-edited
    #: YAML degrades to "" rather than taking the whole project listing down.
    due_date: str = ""
