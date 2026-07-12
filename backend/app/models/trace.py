from __future__ import annotations

from pydantic import BaseModel


class TraceLink(BaseModel):
    source: str
    target: str
    type: str


class TraceMatrix(BaseModel):
    links: list[TraceLink]
