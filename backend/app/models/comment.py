"""Comment model — threaded comments on requirements."""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


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
