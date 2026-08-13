"""Decision record model — architecture/design decision logs."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class DecisionRecord(BaseModel):
    id: str
    title: str = ""
    context: str = ""
    decision: str = ""
    rationale: str = ""
    consequences: str = ""
    linked_requirements: list[str] = Field(default_factory=list)
    #: Decisions are as often about the design as about the specification —
    #: "we chose this supplier's actuator" is a decision about a component.
    linked_components: list[str] = Field(default_factory=list)
    status: str = "accepted"
    decided_by: str = ""
    created: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    modified: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class DecisionRecordCreate(BaseModel):
    id: str
    title: str = ""
    context: str = ""
    decision: str = ""
    rationale: str = ""
    consequences: str = ""
    linked_requirements: list[str] = Field(default_factory=list)
    #: Decisions are as often about the design as about the specification.
    linked_components: list[str] = Field(default_factory=list)
    status: str = "accepted"


class DecisionRecordUpdate(BaseModel):
    title: Optional[str] = None
    context: Optional[str] = None
    decision: Optional[str] = None
    rationale: Optional[str] = None
    consequences: Optional[str] = None
    status: Optional[str] = None
    decided_by: Optional[str] = None
    linked_requirements: Optional[list[str]] = None
    linked_components: Optional[list[str]] = None
