"""Evaluation: turn a construction graph into exact geometry.

The evaluation pass walks the construction graph in dependency order and
computes every derived node **symbolically**. A judge therefore sees an
expression in the free points' symbols, and can decide whether a relation is
an identity rather than a coincidence of one placement.

Free points carry two coordinate pairs (docs/spec.md section 3.2):

- ``coords``    -- symbolic, e.g. ``x_A`` / ``y_A``; this is what the judges see.
- ``placement`` -- exact numeric values used for drawing and for sampling.
"""

from __future__ import annotations

from typing import cast

import sympy as sp
from sympy import Expr

from geobench.errors import DegenerateError, OpNotImplementedError, StateError
from geobench.field import FIELD
from geobench.model import Figure, Node
from geobench.operators import OpContext
from geobench.registry import OperatorRegistry


def free_symbols(figure: Figure) -> dict[sp.Symbol, Expr]:
    """Map every free point's symbols to its numeric placement."""
    mapping: dict[sp.Symbol, Expr] = {}
    for node in figure.nodes.values():
        if node.role != "free" or node.kind != "point":
            continue
        if node.coords is None or node.placement is None:
            continue
        x_sym = FIELD.coerce(node.coords[0])
        y_sym = FIELD.coerce(node.coords[1])
        mapping[x_sym] = FIELD.coerce(node.placement[0])
        mapping[y_sym] = FIELD.coerce(node.placement[1])
    return mapping


def dependency_order(figure: Figure) -> list[str]:
    """Node ids in dependency order (a node comes after all its arguments)."""
    order: list[str] = []
    state: dict[str, int] = {}

    def visit(node_id: str) -> None:
        mark = state.get(node_id, 0)
        if mark == 2:
            return
        if mark == 1:
            raise StateError(f"dependency cycle at node {node_id!r}")
        state[node_id] = 1
        for arg in figure.node(node_id).args:
            if arg in figure.nodes:
                visit(arg)
        state[node_id] = 2
        order.append(node_id)

    for node_id in figure.nodes:
        visit(node_id)
    return order


def evaluate_figure(figure: Figure, registry: OperatorRegistry) -> Figure:
    """Evaluate every derived node in dependency order, in place.

    Two coordinate systems are produced for each derived node:

    - ``coords`` -- the symbolic expression, which is what the judges see;
    - ``placement`` -- the same expression with the free points substituted
      by their numeric values, which is what the renderer draws.

    Returns the same figure for convenience. Raises on the first operator
    that fails; the failure message names the operator and the node.
    """
    ctx = OpContext(figure)
    subs = free_symbols(figure)
    for node_id in dependency_order(figure):
        node: Node = figure.nodes[node_id]
        if node.role != "derived" or not node.op:
            continue
        impl = registry.implementation(node.op)
        if impl is None:
            raise OpNotImplementedError(
                f"node {node_id!r} needs operator {node.op!r}, which has no implementation"
            )
        try:
            result = impl(ctx, list(node.args))
        except StateError as exc:
            raise _with_context(exc, node_id, node.op) from None
        node.cache.update(result)
        _check_conditions(node_id, node.op, result.get("must_be_nonzero"), subs)
        if "coords" in result:
            coords = result["coords"]
            assert isinstance(coords, tuple)
            node.coords = (str(coords[0]), str(coords[1]))
            placement = _numeric_pair(coords, subs)
            _check_finite(node_id, node.op, placement)
            node.placement = placement
    return figure


def _with_context(exc: StateError, node_id: str, op: str) -> StateError:
    """The same failure, with the node it happened in.

    The *type* of the error is part of the contract: the MCP layer turns
    it into a machine-readable code, and a degenerate configuration must
    not be reported as a generic failure. So the exception is rebuilt as
    its own class rather than as a plain ``StateError``.
    """
    message = f"node {node_id!r} (operator {op!r}): {exc}"
    try:
        return type(exc)(message)
    except TypeError:
        # Some error classes need more than a message; keep the original
        # object and just rewrite what it says.
        exc.args = (message,)
        return exc


def _check_conditions(
    node_id: str,
    op: str,
    conditions: object,
    subs: dict[sp.Symbol, Expr],
) -> None:
    """Refuse a construction whose non-degeneracy condition fails.

    An operator works on *symbols*, so it cannot see that this particular
    placement is degenerate: three points are collinear for some
    placements, not identically, so the determinant it divides by is not
    the zero expression.

    An operator therefore publishes the conditions its answer depends on
    -- "the discriminant must not be zero", "the determinant must not be
    zero" -- and they are checked here, where the placement is known.
    """
    if not isinstance(conditions, dict):
        return
    for name, expression in conditions.items():
        try:
            value = FIELD.coerce(expression).subs(subs)
        except Exception:  # pragma: no cover - defensive
            continue
        if FIELD.simplify_to_zero(value):
            raise DegenerateError(
                f"node {node_id!r} (operator {op!r}) is degenerate: "
                f"{name} is zero under the current placement"
            )


def _check_finite(node_id: str, op: str, placement: tuple[str, str]) -> None:
    """Reject a placement that is not a finite number.

    A free point is a *symbol*, so the operators cannot tell that three
    points are collinear: their determinant is not identically zero, only
    zero under this particular placement. The symptom is a division by
    zero, and the result is ``zoo`` or ``nan``.

    Catching it here is what lets the server answer "degraded" instead of
    quietly drawing a point at infinity.
    """
    for value in placement:
        if FIELD.coerce(value).is_finite is False:
            raise DegenerateError(
                f"node {node_id!r} (operator {op!r}) has no finite value under the "
                "current placement; the configuration is degenerate"
            )


def _numeric_pair(
    coords: tuple[Expr, Expr], subs: dict[sp.Symbol, Expr]
) -> tuple[str, str]:
    """Substitute the free points' placements into an exact coordinate pair."""
    out: list[str] = []
    for value in coords:
        try:
            out.append(str(sp.simplify(value.subs(subs))))
        except Exception:  # pragma: no cover - defensive
            out.append(str(value))
    return (out[0], out[1])


def numeric_coords(
    figure: Figure, node_id: str, substitutions: dict[sp.Symbol, Expr] | None = None
) -> tuple[float, float]:
    """Numeric coordinates of a node under a placement.

    A derived node's placement was computed during evaluation, so it is used
    directly; a free node's placement is substituted on the spot.
    """
    node = figure.node(node_id)
    if node.coords is None:
        raise StateError(f"node {node_id!r} has no coordinates")
    if node.role == "derived" and node.placement is not None:
        return (
            float(sp.N(FIELD.coerce(node.placement[0]))),
            float(sp.N(FIELD.coerce(node.placement[1]))),
        )
    subs = free_symbols(figure) if substitutions is None else substitutions
    x = float(sp.N(FIELD.coerce(node.coords[0]).subs(subs)))
    y = float(sp.N(FIELD.coerce(node.coords[1]).subs(subs)))
    return x, y


def symbolic_coords(figure: Figure, node_id: str) -> tuple[Expr, Expr]:
    node = figure.node(node_id)
    if node.coords is None:
        raise StateError(f"node {node_id!r} has no coordinates")
    return FIELD.coerce(node.coords[0]), FIELD.coerce(node.coords[1])


def numeric_line(
    figure: Figure, node_id: str, substitutions: dict[sp.Symbol, Expr] | None = None
) -> tuple[float, float, float]:
    a, b, c = cast(tuple[Expr, Expr, Expr], figure.node(node_id).cache["line"])
    subs = free_symbols(figure) if substitutions is None else substitutions
    return (
        float(sp.N(a.subs(subs))),
        float(sp.N(b.subs(subs))),
        float(sp.N(c.subs(subs))),
    )


def numeric_circle(
    figure: Figure, node_id: str, substitutions: dict[sp.Symbol, Expr] | None = None
) -> tuple[float, float, float]:
    cx, cy, r2 = cast(tuple[Expr, Expr, Expr], figure.node(node_id).cache["circle"])
    subs = free_symbols(figure) if substitutions is None else substitutions
    return (
        float(sp.N(cx.subs(subs))),
        float(sp.N(cy.subs(subs))),
        float(sp.N(r2.subs(subs))),
    )


def numeric_segment(
    figure: Figure, node_id: str, substitutions: dict[sp.Symbol, Expr] | None = None
) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = cast(
        tuple[Expr, Expr, Expr, Expr], figure.node(node_id).cache["segment"]
    )
    subs = free_symbols(figure) if substitutions is None else substitutions
    return (
        float(sp.N(x1.subs(subs))),
        float(sp.N(y1.subs(subs))),
        float(sp.N(x2.subs(subs))),
        float(sp.N(y2.subs(subs))),
    )
