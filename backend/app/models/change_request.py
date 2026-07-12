from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class CRStatus(str, Enum):
    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    IMPLEMENTED = "implemented"
    CLOSED = "closed"


class ChangeRequest(BaseModel):
    id: str
    title: str = ""
    description: str = ""
    affected_requirements: list[str] = Field(default_factory=list)
    status: CRStatus = CRStatus.SUBMITTED
    submitted_by: str = ""
    reviewed_by: str = ""
    approved_by: str = ""
    created: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    modified: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ChangeRequestCreate(BaseModel):
    id: str
    title: str = ""
    description: str = ""
    affected_requirements: list[str] = Field(default_factory=list)


class ChangeRequestUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[CRStatus] = None
    affected_requirements: Optional[list[str]] = None
    submitted_by: Optional[str] = None
    reviewed_by: Optional[str] = None
    approved_by: Optional[str] = None
