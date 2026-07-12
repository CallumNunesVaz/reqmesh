from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class TestStep(BaseModel):
    action: str = ""
    expected_result: str = ""
    actual_result: Optional[str] = None


class ExecutionRecord(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "pending"
    notes: str = ""
    executed_by: str = ""


class VerificationCase(BaseModel):
    id: str
    name: str = ""
    description: str = ""
    method: str = "test"
    status: str = "pending"
    result: Optional[str] = None
    verified_requirements: list[str] = Field(default_factory=list)
    test_procedure: str = ""
    steps: list[TestStep] = Field(default_factory=list)
    execution_history: list[ExecutionRecord] = Field(default_factory=list)
    created: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    modified: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class VerificationCaseCreate(BaseModel):
    id: str
    name: str = ""
    description: str = ""
    method: str = "test"


class VerificationCaseUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    method: Optional[str] = None
    status: Optional[str] = None
    result: Optional[str] = None
    verified_requirements: Optional[list[str]] = None
    test_procedure: Optional[str] = None
    steps: Optional[list[TestStep]] = None
    execution_history: Optional[list[ExecutionRecord]] = None
