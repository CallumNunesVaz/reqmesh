"""Reusable SysML v2-style parametric definitions.

A ``ConstraintDef``/``CalcDef`` is a named template with formal ``parameters``
and an ``expr`` written over those formals. Requirements reference a definition
and *bind* each formal to an actual parameter reference (``ENTITY.param``),
mirroring SysML v2 constraint/calc usages with binding connectors — while still
evaluating through reqmesh's existing engine.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class Definition(BaseModel):
    id: str
    type: Literal["constraint", "calc"] = "constraint"
    name: str = ""
    # Formal parameter names referenced inside ``expr``.
    parameters: list[str] = Field(default_factory=list)
    expr: str
    # calc definitions may declare a result unit.
    unit: str = ""
    doc: str = ""


class DefinitionCreate(BaseModel):
    id: str
    type: Literal["constraint", "calc"] = "constraint"
    name: str = ""
    parameters: list[str] = Field(default_factory=list)
    expr: str
    unit: str = ""
    doc: str = ""


class DefinitionUpdate(BaseModel):
    type: Optional[Literal["constraint", "calc"]] = None
    name: Optional[str] = None
    parameters: Optional[list[str]] = None
    expr: Optional[str] = None
    unit: Optional[str] = None
    doc: Optional[str] = None
