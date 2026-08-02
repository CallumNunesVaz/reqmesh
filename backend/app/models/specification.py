from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class Specification(BaseModel):
    id: str
    name: str = ""
    description: str = ""
    # A link to the authoritative document this specification comes from — an
    # intranet page, a PDF in a document system, a standard. Stored as typed by
    # the operator and rendered as a link; validated only to the extent that it
    # cannot smuggle script (see `is_safe_external_url`), because the set of
    # schemes a real deployment needs is wider than http/https alone.
    url: str = ""
    requirements: list[str] = Field(default_factory=list)
    children: list[str] = Field(default_factory=list)
    created: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    modified: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SpecificationCreate(BaseModel):
    id: str
    name: str = ""
    description: str = ""
    url: str = ""


class SpecificationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    requirements: Optional[list[str]] = None
    children: Optional[list[str]] = None
