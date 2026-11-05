"""``geo_state`` -- read the current figure.

The tool is the agent's window onto the kernel: whatever the agent believes
about the figure, this is what the kernel actually holds. That makes it the
first thing to call and the first thing to check after a construction.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from geobench.errors import ModelError
from geobench.state import FigureStore
from geobench.tools.models import (
    DegeneracySummary,
    ErrorInfo,
    StateResponse,
    ValidationSummary,
)
from geobench.tools.spec import TOOL_SPECS_BY_NAME

DEFAULT_FIGURE_ID = "default"


def make_state_tool(store: FigureStore) -> Callable[..., Any]:
    """Build the ``geo_state`` tool bound to ``store``."""

    def geo_state(figure_id: str | None = None) -> StateResponse:
        fid = figure_id or DEFAULT_FIGURE_ID
        figure = store.figure(fid)

        errors: list[ErrorInfo] = []
        try:
            figure.validate()
        except ModelError as exc:
            errors.append(ErrorInfo(code="invalid_figure", message=str(exc)))

        return StateResponse(
            status="error" if errors else "ok",
            figure_id=fid,
            figure=figure.to_dict(),
            node_count=len(figure.nodes),
            relation_count=len(figure.relations),
            validation=ValidationSummary(
                ok=not errors, errors=[error.message for error in errors]
            ),
            degeneracy=DegeneracySummary(),
            errors=errors,
        )

    geo_state.__name__ = "geo_state"
    geo_state.__doc__ = TOOL_SPECS_BY_NAME["geo_state"].description
    return geo_state
