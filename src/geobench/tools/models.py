"""The request and response shapes of the MCP tools.

Every response carries a machine-readable ``status``:

- ``ok``        -- the request was understood and fully carried out;
- ``error``     -- the request was wrong (unknown node, bad argument,
                   unknown expression); nothing was changed;
- ``degraded``  -- the request was right but the geometry could not be
                   completed (a degenerate configuration, for instance).

The distinction matters to an agent: ``error`` means "fix your request",
``degraded`` means "the answer is partial, and here is what is missing".
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Status = Literal["ok", "error", "degraded"]


class ErrorInfo(BaseModel):
    """One failure, in a form an agent can act on."""

    code: str
    message: str
    op: str | None = None
    """The operator the failure belongs to, when there is one."""
    index: int | None = None
    """The index of the offending argument, when there is one."""
    node_id: str | None = None
    """The node id that could not be resolved, when there is one."""
    known_node_ids: list[str] = Field(default_factory=list)
    """The node ids that *are* legal, when the failure was an unknown id."""


class ValidationSummary(BaseModel):
    """The result of the structural check on a figure."""

    ok: bool
    errors: list[str] = Field(default_factory=list)


class DegeneracySummary(BaseModel):
    """The degeneracy report.

    The detectors land in a later task; until then the report says so
    rather than pretending the figure is clean.
    """

    status: Literal["clean", "not_implemented"] = "not_implemented"
    reports: list[dict[str, Any]] = Field(default_factory=list)


class StateResponse(BaseModel):
    """``geo_state`` -- the current figure and a summary of its health."""

    status: Status
    figure_id: str
    figure: dict[str, Any] = Field(default_factory=dict)
    node_count: int = 0
    relation_count: int = 0
    validation: ValidationSummary = Field(default_factory=lambda: ValidationSummary(ok=True))
    degeneracy: DegeneracySummary = Field(default_factory=DegeneracySummary)
    errors: list[ErrorInfo] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ConstructOp(BaseModel):
    """One operation in a ``geo_construct`` batch."""

    id: str | None = None
    """The id of the node to create. Omit it and the kernel picks one."""
    op: str
    """An operator id, or ``point.free`` / ``relation.add``."""
    args: list[Any] = Field(default_factory=list)


class ConstructResponse(BaseModel):
    """``geo_construct`` -- what the batch did, or why it did not."""

    status: Status
    figure_id: str
    mode: Literal["apply", "dry-run"]
    created: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    errors: list[ErrorInfo] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class EvaluateResponse(BaseModel):
    """``geo_evaluate`` -- an exact value and its display approximation."""

    status: Status
    expr: str
    exact: str | None = None
    """The exact value, in terms of the free points' symbols."""
    exact_unit: str | None = None
    """``radian``, ``length`` or ``area`` -- the unit of ``exact``."""
    approx: float | None = None
    """The value under the figure's current placement."""
    approx_unit: str | None = None
    """``degree``, ``length`` or ``area`` -- the unit of ``approx``."""
    errors: list[ErrorInfo] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
