from __future__ import annotations

from pydantic import BaseModel, Field


class Baseline(BaseModel):
    name: str
    frozen_at: str = ""
    frozen: bool = True
    snapshot: dict[str, dict] = Field(default_factory=dict)


class BaselineCreate(BaseModel):
    name: str
    frozen_at: str = ""
    snapshot: dict[str, dict] = Field(default_factory=dict)
