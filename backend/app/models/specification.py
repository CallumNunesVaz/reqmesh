from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class Specification(BaseModel):
    id: str
    name: str = ""
    description: str = ""
    requirements: list[str] = Field(default_factory=list)
    children: list[str] = Field(default_factory=list)
    created: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    modified: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SpecificationCreate(BaseModel):
    id: str
    name: str = ""
    description: str = ""


class SpecificationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[list[str]] = None
    children: Optional[list[str]] = None
