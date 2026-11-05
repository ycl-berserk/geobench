"""``geo_evaluate`` -- evaluate a geometric quantity exactly.

Two values come back for every expression:

- the **exact** value, in terms of the free points' symbols (``x_A``,
  ``y_A``, ...). This is the value a proof is about: it holds for every
  placement, not just the one on screen.
- the **approximation**, under the figure's current placement. This is what
  a human reads.

An expression that names something the figure does not contain is an
**error**, never a guess: an agent that wrote ``Angle(B,A,Q)`` meant a
point called ``Q``, and silently measuring some other point would produce a
plausible-looking wrong answer.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from typing import Any

import sympy as sp
from sympy import Expr

from geobench.errors import GeobenchError
from geobench.evaluate import evaluate_figure, free_symbols, numeric_coords, symbolic_coords
from geobench.field import FIELD
from geobench.model import Figure
from geobench.registry import OperatorRegistry
from geobench.state import FigureStore
from geobench.tools.errors import to_error_info
from geobench.tools.models import ErrorInfo, EvaluateResponse
from geobench.tools.spec import TOOL_SPECS_BY_NAME
from geobench.tools.state import DEFAULT_FIGURE_ID

#: The functions the evaluator understands.
SUPPORTED_FUNCTIONS: tuple[str, ...] = ("Angle", "Distance", "Area")

_CALL = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_]*)\s*\(([^()]*)\)\s*$")

_ARITY = {"Angle": 3, "Distance": 2, "Area": 3}


class ExpressionError(Exception):
    """The expression could not be understood, or names something absent."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        node_id: str | None = None,
        known_node_ids: list[str] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.node_id = node_id
        self.known_node_ids = list(known_node_ids or [])
        super().__init__(message)

    def to_error_info(self) -> ErrorInfo:
        """The structured form of this failure."""
        return ErrorInfo(
            code=self.code,
            message=self.message,
            node_id=self.node_id,
            known_node_ids=list(self.known_node_ids),
        )


def parse_expression(expr: str) -> tuple[str, list[str]]:
    """Split ``"Angle(B,A,C)"`` into ``("Angle", ["B", "A", "C"])``."""
    match = _CALL.match(expr)
    if match is None:
        raise ExpressionError(
            "syntax",
            f"{expr!r} is not a supported expression; expected one of "
            f"{', '.join(SUPPORTED_FUNCTIONS)}(...)",
        )
    name = match.group(1)
    body = match.group(2).strip()
    args = [part.strip() for part in body.split(",")] if body else []
    if name not in SUPPORTED_FUNCTIONS:
        raise ExpressionError(
            "unknown_function",
            f"unknown function {name!r}; supported functions are "
            f"{', '.join(SUPPORTED_FUNCTIONS)}",
        )
    expected = _ARITY[name]
    if len(args) != expected:
        raise ExpressionError(
            "argument_count",
            f"{name} takes {expected} point name(s) but got {len(args)}",
        )
    if any(not arg.isidentifier() for arg in args):
        raise ExpressionError(
            "syntax", f"{expr!r} contains an argument that is not a point name"
        )
    return name, args


def _point(figure: Figure, node_id: str) -> tuple[Expr, Expr]:
    """The symbolic coordinates of a point, or an actionable error."""
    if node_id not in figure.nodes:
        raise ExpressionError(
            "unknown_node",
            f"unknown node id {node_id!r}; known node ids: "
            + (", ".join(sorted(figure.nodes)) or "(the figure has no nodes yet)"),
            node_id=node_id,
            known_node_ids=sorted(figure.nodes),
        )
    node = figure.nodes[node_id]
    if node.kind != "point":
        raise ExpressionError(
            "not_a_point",
            f"node {node_id!r} is a {node.kind}, not a point",
            node_id=node_id,
        )
    try:
        return symbolic_coords(figure, node_id)
    except GeobenchError as exc:
        raise ExpressionError(
            "no_coordinates", str(exc), node_id=node_id
        ) from None


def _exact_distance(figure: Figure, args: list[str]) -> tuple[Expr, str, str]:
    (x1, y1) = _point(figure, args[0])
    (x2, y2) = _point(figure, args[1])
    squared = (x1 - x2) ** 2 + (y1 - y2) ** 2
    return sp.sqrt(squared), "length", "length"


def _exact_area(figure: Figure, args: list[str]) -> tuple[Expr, str, str]:
    (x1, y1) = _point(figure, args[0])
    (x2, y2) = _point(figure, args[1])
    (x3, y3) = _point(figure, args[2])
    cross = (x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1)
    return sp.Abs(cross) / 2, "area", "area"


def _exact_angle(figure: Figure, args: list[str]) -> tuple[Expr, str, str]:
    (xb, yb) = _point(figure, args[0])
    (xa, ya) = _point(figure, args[1])
    (xc, yc) = _point(figure, args[2])
    ux, uy = xb - xa, yb - ya
    vx, vy = xc - xa, yc - ya
    dot = ux * vx + uy * vy
    norm_u = sp.sqrt(ux**2 + uy**2)
    norm_v = sp.sqrt(vx**2 + vy**2)
    # The cosine law in vector form: the angle in [0, pi], exactly.
    cosine = dot / (norm_u * norm_v)
    return sp.acos(cosine), "radian", "degree"


_EXACT = {
    "Distance": _exact_distance,
    "Area": _exact_area,
    "Angle": _exact_angle,
}


def _approx_numeric(figure: Figure, name: str, args: list[str]) -> float:
    """The value under the figure's current placement."""
    if name == "Angle":
        (ax, ay) = numeric_coords(figure, args[1])
        (bx, by) = numeric_coords(figure, args[0])
        (cx, cy) = numeric_coords(figure, args[2])
        ux, uy = bx - ax, by - ay
        vx, vy = cx - ax, cy - ay
        cross = ux * vy - uy * vx
        dot = ux * vx + uy * vy
        if math.hypot(ux, uy) == 0 or math.hypot(vx, vy) == 0:
            raise ExpressionError(
                "degenerate", "an angle needs two distinct rays from its vertex"
            )
        # atan2 of the absolute cross product is the unsigned angle in
        # [0, pi]; acos would be exact but loses precision near 0 and pi.
        return math.degrees(math.atan2(abs(cross), dot))
    exact, _, _ = _EXACT[name](figure, args)
    return FIELD.to_float(exact.subs(free_symbols(figure)))


def _is_evaluated(figure: Figure) -> bool:
    return all(
        node.coords is not None for node in figure.nodes.values() if node.role == "derived"
    )


def make_evaluate_tool(
    store: FigureStore, registry: OperatorRegistry
) -> Callable[..., Any]:
    """Build the ``geo_evaluate`` tool bound to ``store`` and ``registry``."""

    def geo_evaluate(expr: str, figure_id: str | None = None) -> EvaluateResponse:
        fid = figure_id or DEFAULT_FIGURE_ID
        try:
            name, args = parse_expression(expr)
        except ExpressionError as exc:
            return EvaluateResponse(
                status="error",
                expr=expr,
                errors=[exc.to_error_info()],
            )

        try:
            figure = store.figure(fid)
            if not _is_evaluated(figure):
                figure = figure.copy()
                evaluate_figure(figure, registry)
            exact, exact_unit, approx_unit = _EXACT[name](figure, args)
            approx = _approx_numeric(figure, name, args)
        except ExpressionError as exc:
            return EvaluateResponse(
                status="error",
                expr=expr,
                errors=[exc.to_error_info()],
            )
        except GeobenchError as exc:
            return EvaluateResponse(
                status="error",
                expr=expr,
                errors=[to_error_info(exc)],
            )

        return EvaluateResponse(
            status="ok",
            expr=expr,
            exact=sp.sstr(exact),
            exact_unit=exact_unit,
            approx=approx,
            approx_unit=approx_unit,
        )

    geo_evaluate.__name__ = "geo_evaluate"
    geo_evaluate.__doc__ = TOOL_SPECS_BY_NAME["geo_evaluate"].description
    return geo_evaluate
