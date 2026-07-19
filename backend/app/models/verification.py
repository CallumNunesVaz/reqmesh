from __future__ import annotations

"""Verification model — aligned with ISO/IEC 15288:2023 §6.4.9 (Verification Process).

A VerificationCase confirms through objective evidence that a requirement is met.
Methods align with ISO 15288 verification approaches: Test (physical testing),
Analysis (modelling/simulation), Demonstration (showing it works), Inspection
(review/examination). Measurements feed the parametric engine to produce
measured verdicts (§6.4.11 Validation).
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class CaseType(str, Enum):
    """OOSEM Activity 6: verification (did we build it right?) vs validation (did we build the right thing?)."""
    VERIFICATION = "verification"
    VALIDATION = "validation"


class TestStep(BaseModel):
    action: str = ""
    expected_result: str = ""
    actual_result: Optional[str] = None


class ExecutionRecord(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "pending"
    notes: str = ""
    executed_by: str = ""


class Measurement(BaseModel):
    """A measured value recorded against a requirement parameter.

    `parameter` is a fully-qualified reference (`"AFRM0005.max_load"`). The
    evaluation engine substitutes these into the owning requirement's
    constraints to compute a verification verdict from evidence rather than a
    hand-set status.
    """

    parameter: str
    value: float
    unit: str = ""


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
    measurements: list[Measurement] = Field(default_factory=list)
    case_type: CaseType = CaseType.VERIFICATION
    environment: str = ""
    decision_gate: Optional[str] = None
    created: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    modified: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class VerificationCaseCreate(BaseModel):
    id: str
    name: str = ""
    description: str = ""
    method: str = "test"
    case_type: CaseType = CaseType.VERIFICATION
    environment: str = ""
    decision_gate: Optional[str] = None


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
    measurements: Optional[list[Measurement]] = None
    case_type: Optional[CaseType] = None
    environment: Optional[str] = None
    decision_gate: Optional[str] = None
