"""SysML v2-style analysis cases: named, scoped, parameterised evaluations.

An analysis case runs reqmesh's parametric evaluation over a subset of
requirements (``scope``) with hypothetical input values (``overrides`` mapping
``ENTITY.param`` refs to numbers) — e.g. "worst-case fuel load" — reusing the
same solver that produces the live design verdicts.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AnalysisCase(BaseModel):
    id: str
    name: str = ""
    doc: str = ""
    # Requirement ids to evaluate; empty means the whole project.
    scope: list[str] = Field(default_factory=list)
    # Hypothetical parameter values, keyed by fully-qualified ref "ENTITY.param".
    overrides: dict[str, float] = Field(default_factory=dict)


class AnalysisCaseCreate(BaseModel):
    id: str
    name: str = ""
    doc: str = ""
    scope: list[str] = Field(default_factory=list)
    overrides: dict[str, float] = Field(default_factory=dict)


class AnalysisCaseUpdate(BaseModel):
    name: Optional[str] = None
    doc: Optional[str] = None
    scope: Optional[list[str]] = None
    overrides: Optional[dict[str, float]] = None
