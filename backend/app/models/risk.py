from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


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
    linked_requirements: list[str] = Field(default_factory=list)
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
    status: Optional[str] = None
    linked_requirements: Optional[list[str]] = None


class Comment(BaseModel):
    id: str
    requirement_id: str
    author: str = ""
    text: str = ""
    resolved: bool = False
    created: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CommentCreate(BaseModel):
    requirement_id: str
    author: str = ""
    text: str = ""


class DecisionRecord(BaseModel):
    id: str
    title: str = ""
    context: str = ""
    decision: str = ""
    rationale: str = ""
    consequences: str = ""
    linked_requirements: list[str] = Field(default_factory=list)
    status: str = "accepted"
    decided_by: str = ""
    created: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    modified: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class DecisionRecordCreate(BaseModel):
    id: str
    title: str = ""
    context: str = ""
    decision: str = ""


class DecisionRecordUpdate(BaseModel):
    title: Optional[str] = None
    context: Optional[str] = None
    decision: Optional[str] = None
    rationale: Optional[str] = None
    consequences: Optional[str] = None
    status: Optional[str] = None
    decided_by: Optional[str] = None
    linked_requirements: Optional[list[str]] = None
