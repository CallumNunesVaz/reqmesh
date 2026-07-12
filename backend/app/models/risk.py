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


class Risk(BaseModel):
    id: str
    title: str = ""
    description: str = ""
    severity: RiskSeverity = RiskSeverity.MEDIUM
    probability: str = "medium"
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
    severity: RiskSeverity = RiskSeverity.MEDIUM
    probability: str = "medium"


class RiskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[RiskSeverity] = None
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
