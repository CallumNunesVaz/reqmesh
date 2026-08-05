"""Risk model — project risks with severity, likelihood, and mitigation.

Comment and DecisionRecord were extracted to their own modules; they are
re-exported here for backward compatibility.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

# Backward-compat re-exports — callers that imported from risk.py keep working.
from app.models.comment import Comment, CommentCreate          # noqa: F401
from app.models.decision import (                              # noqa: F401
    DecisionRecord, DecisionRecordCreate, DecisionRecordUpdate,
)


class RiskSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# severity and likelihood are the two *inputs* a risk carries; the rating is
# derived from the project's matrix on read (services/risk_matrix.py) and is
# deliberately not a stored field. They are plain strings rather than enums
# because a project can rename its matrix axes, and a renamed level must not
# make every existing risk fail validation.
class Risk(BaseModel):
    id: str
    title: str = ""
    description: str = ""
    severity: str = "medium"
    likelihood: str = "possible"
    # Superseded by `likelihood`. Kept so risks written before the matrix load
    # unchanged; resolve_likelihood() reads it as a fallback.
    probability: str = ""
    impact: str = ""
    mitigation: str = ""
    #: How likely the risk is to be *noticed* before it bites — the third FMEA
    #: axis. Deliberately does **not** feed the rating: the project's matrix is
    #: two-dimensional and user-configured, so folding detection into the band
    #: would silently re-rate every existing risk and leave the configured
    #: matrix no longer describing its own output. A plain string, for the same
    #: reason severity and likelihood are: a project may rename its levels, and
    #: a rename must not make every stored risk fail validation.
    detection: str = ""
    #: Requirements this risk endangers — "threatens".
    linked_requirements: list[str] = Field(default_factory=list)
    #: Requirements that exist to control this risk — "mitigated by". The
    #: opposite direction to `linked_requirements`: those are what the risk puts
    #: at stake, these are what reduces it. Kept as a separate list rather than a
    #: typed relation because the two are asked and answered independently, and
    #: a requirement can legitimately appear in both.
    mitigating_requirements: list[str] = Field(default_factory=list)
    #: The same two relationships, against the design rather than the
    #: specification. A risk usually lives in a *part* — "this actuator is a
    #: single point of failure" was unsayable while risks could only point at
    #: requirements, which is a statement about the thing, not about the text
    #: describing it.
    #:
    #: Separate fields rather than one polymorphic list: these are lists, so a
    #: single discriminator could not say which collection each entry belongs
    #: to, and `link_registry` needs a concrete target per row.
    linked_components: list[str] = Field(default_factory=list)
    mitigating_components: list[str] = Field(default_factory=list)
    status: str = "open"
    created: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    modified: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class RiskCreate(BaseModel):
    id: str
    title: str = ""
    description: str = ""
    severity: str = "medium"
    likelihood: str = "possible"


class RiskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[str] = None
    likelihood: Optional[str] = None
    probability: Optional[str] = None
    impact: Optional[str] = None
    mitigation: Optional[str] = None
    detection: Optional[str] = None
    status: Optional[str] = None
    linked_requirements: Optional[list[str]] = None
    mitigating_requirements: Optional[list[str]] = None
    linked_components: Optional[list[str]] = None
    mitigating_components: Optional[list[str]] = None
