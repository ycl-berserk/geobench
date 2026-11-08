"""Evaluation: turn a construction graph into exact geometry.

There are **two paths**, and keeping them apart is what makes the product
feel like a drawing tool while still proving things (decision D18).

- **The exact path** (:func:`evaluate_exact`) computes every derived
  node **symbolically**. A judge therefore sees an expression in the free
  points' symbols, and can decide whether a relation is an identity
  rather than a coincidence of one placement.
- **The numeric path** (:func:`evaluate_numeric`) evaluates those
  expressions at the free points' current positions. It is what the
  screen draws, it is fast, and it never produces a verdict.

The split works because a derived object's symbolic expression does not
depend on the placement: dragging a point invalidates nothing in the
exact path, and an identity verdict does not change either -- which is
precisely what "identity" means.

Free points carry two coordinate pairs (docs/spec.md section 3.2):

- ``coords``    -- symbolic, e.g. ``x_A`` / ``y_A``; this is what the judges see.
- ``placement`` -- numeric values used for drawing and for sampling.
"""

from __future__ import annotations

from typing import Any, cast

import sympy as sp
from sympy import Expr

from geobench import numeric
from geobench.errors import OpNotImplementedError, StateError
from geobench.field import FIELD
from geobench.model import Figure, Node
from geobench.operators import OpContext
from geobench.registry import OperatorRegistry

#: The cache key holding a node's evaluation signature.
CACHE_SIGNATURE = "signature"


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


def evaluate_exact(figure: Figure, registry: OperatorRegistry) -> Figure:
    """Evaluate every derived node symbolically, in place.

    This is the **exact path**. It produces the symbolic expression of
    each derived node -- what the judges see -- and compiles it into a
    float function for the numeric path.

    It is **incremental**: a node is recomputed only when something it
    depends on has changed. That matters because a derived object's
    symbolic expression does not depend on where the free points are
    placed, so dragging a point invalidates nothing here.

    The placement is *not* computed by this function; see
    :func:`evaluate_numeric`.
    """
    ctx = OpContext(figure)
    symbols = numeric.symbols_of(figure)
    for node_id in dependency_order(figure):
        node: Node = figure.nodes[node_id]
        if node.role != "derived" or not node.op:
            continue
        signature = _signature(node, figure)
        if node.cache.get(CACHE_SIGNATURE) == signature:
            # Nothing this node depends on has changed: its expression is
            # still the right one.
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
        node.cache[CACHE_SIGNATURE] = signature
        versions = figure.runtime.setdefault("versions", {})
        versions[node_id] = versions.get(node_id, 0) + 1
        if "coords" in result:
            coords = result["coords"]
            assert isinstance(coords, tuple)
            node.coords = (str(coords[0]), str(coords[1]))
        numeric.compile_node(node, symbols)
        numeric.compile_conditions(node, symbols)
    return figure


def evaluate_numeric(figure: Figure) -> Figure:
    """Recompute every derived node's numeric payload. Fast.

    This is the **numeric path**: it evaluates the compiled expressions at
    the free points' current positions. It is what the screen draws, and
    it is the only thing that runs while a point is being dragged.

    A node that has no value at this placement (a degenerate
    configuration) is marked *undefined* rather than raising: the rest of
    the figure is still worth showing.
    """
    values = numeric.free_values(figure)
    for node_id in dependency_order(figure):
        node = figure.nodes[node_id]
        if node.role == "free":
            if node.kind == "point" and node.placement is not None:
                try:
                    node.cache[numeric.CACHE_VALUES] = {
                        "coords": (
                            float(node.placement[0]),
                            float(node.placement[1]),
                        )
                    }
                except (TypeError, ValueError):
                    node.cache.pop(numeric.CACHE_VALUES, None)
            continue
        condition = numeric.failing_condition(node, values)
        if condition is not None:
            node.cache[numeric.CACHE_UNDEFINED] = condition
            node.cache.pop(numeric.CACHE_VALUES, None)
            node.placement = None
            continue
        payload = numeric.evaluate_node(node, values)
        if payload is None:
            node.cache[numeric.CACHE_UNDEFINED] = "no value at this placement"
            node.cache.pop(numeric.CACHE_VALUES, None)
            node.placement = None
            continue
        node.cache.pop(numeric.CACHE_UNDEFINED, None)
        numbers = payload["numbers"]
        node.cache[numeric.CACHE_VALUES] = {
            "coords": (numbers[0], numbers[1]) if node.kind == "point" else None,
            "line": tuple(numbers) if node.kind == "line" else None,
            "circle": tuple(numbers) if node.kind == "circle" else None,
            "segment": tuple(numbers) if node.kind == "segment" else None,
            "polygon": tuple(numbers) if node.kind == "polygon" else None,
            "arc": tuple(numbers) if node.kind == "arc" else None,
            "sector": tuple(numbers) if node.kind == "sector" else None,
            "ray": tuple(numbers) if node.kind == "ray" else None,
            "polyline": tuple(numbers) if node.kind == "polyline" else None,
            "value": numbers[0] if node.kind == "number" else None,
        }
        if node.kind == "point" and len(numbers) >= 2:
            node.placement = (
                numeric.format_float(numbers[0]),
                numeric.format_float(numbers[1]),
            )
    return figure


def evaluate_figure(figure: Figure, registry: OperatorRegistry) -> Figure:
    """Evaluate a figure: the exact path, then the numeric one.

    Both are incremental, so calling this on every change is cheap: the
    exact path does nothing unless the *construction* changed, and the
    numeric path is a function call per node.
    """
    evaluate_exact(figure, registry)
    evaluate_numeric(figure)
    return figure


def _signature(node: Node, figure: Figure) -> tuple[Any, ...]:
    """What this node's expression depends on.

    The signature is the operator, the arguments, and the *versions* of
    the arguments. A version changes exactly when the argument's
    expression changes, so an unchanged signature means an unchanged
    expression.
    """
    versions = figure.runtime.get("versions", {})
    parts: list[Any] = [node.op or "", tuple(node.args)]
    for arg in node.args:
        if arg in figure.nodes:
            parts.append(versions.get(arg, 0))
        else:
            parts.append(arg)
    return tuple(parts)


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


def undefined_nodes(figure: Figure) -> list[tuple[str, str]]:
    """The nodes that have no value at the current placement.

    Each entry is ``(node_id, reason)``. GeoGebra calls this state
    "undefined"; we keep the figure alive and mark the object instead of
    refusing the whole construction (decision D19).
    """
    out: list[tuple[str, str]] = []
    for node_id, node in figure.nodes.items():
        reason = node.cache.get(numeric.CACHE_UNDEFINED)
        if reason:
            out.append((node_id, str(reason)))
    return out


def _numeric_payload(
    figure: Figure, node_id: str, key: str
) -> tuple[float, ...] | None:
    """The node's numeric payload, when the numeric path has computed it."""
    values = figure.node(node_id).cache.get(numeric.CACHE_VALUES)
    if not values:
        return None
    payload = values.get(key)
    if payload is None:
        return None
    return tuple(payload)


def numeric_coords(
    figure: Figure, node_id: str, substitutions: dict[sp.Symbol, Expr] | None = None
) -> tuple[float, float]:
    """Numeric coordinates of a node under a placement.

    The fast path reads the payload the numeric path computed. The slow
    path substitutes into the symbolic expression, which is what a figure
    that was never numerically evaluated needs.
    """
    node = figure.node(node_id)
    if node.coords is None:
        raise StateError(f"node {node_id!r} has no coordinates")
    payload = _numeric_payload(figure, node_id, "coords")
    if payload is not None:
        return (payload[0], payload[1])
    subs = free_symbols(figure) if substitutions is None else substitutions
    x = _real(FIELD.coerce(node.coords[0]).subs(subs), node_id)
    y = _real(FIELD.coerce(node.coords[1]).subs(subs), node_id)
    return x, y


def symbolic_coords(figure: Figure, node_id: str) -> tuple[Expr, Expr]:
    node = figure.node(node_id)
    if node.coords is None:
        raise StateError(f"node {node_id!r} has no coordinates")
    return FIELD.coerce(node.coords[0]), FIELD.coerce(node.coords[1])


def _real(value: Expr, node_id: str) -> float:
    """A real number, or a clean refusal.

    A degenerate configuration can make a quantity complex -- the
    centre of a circle through three collinear points, for one. That is
    not a value, it is the absence of one, and it has to say so in a way
    the caller can catch: a raw TypeError from float() would escape
    through the paint event and take the application down with it.
    """
    try:
        return float(sp.N(value))
    except (TypeError, ValueError) as exc:
        raise StateError(
            f"node {node_id!r} has no real value at this placement"
        ) from exc


def numeric_line(
    figure: Figure, node_id: str, substitutions: dict[sp.Symbol, Expr] | None = None
) -> tuple[float, float, float]:
    payload = _numeric_payload(figure, node_id, "line")
    if payload is not None:
        return (payload[0], payload[1], payload[2])
    a, b, c = cast(tuple[Expr, Expr, Expr], figure.node(node_id).cache["line"])
    subs = free_symbols(figure) if substitutions is None else substitutions
    return (
        _real(a.subs(subs), node_id),
        _real(b.subs(subs), node_id),
        _real(c.subs(subs), node_id),
    )


def numeric_circle(
    figure: Figure, node_id: str, substitutions: dict[sp.Symbol, Expr] | None = None
) -> tuple[float, float, float]:
    payload = _numeric_payload(figure, node_id, "circle")
    if payload is not None:
        return (payload[0], payload[1], payload[2])
    cx, cy, r2 = cast(tuple[Expr, Expr, Expr], figure.node(node_id).cache["circle"])
    subs = free_symbols(figure) if substitutions is None else substitutions
    return (
        _real(cx.subs(subs), node_id),
        _real(cy.subs(subs), node_id),
        _real(r2.subs(subs), node_id),
    )


def numeric_segment(
    figure: Figure, node_id: str, substitutions: dict[sp.Symbol, Expr] | None = None
) -> tuple[float, float, float, float]:
    payload = _numeric_payload(figure, node_id, "segment")
    if payload is not None:
        return (payload[0], payload[1], payload[2], payload[3])
    x1, y1, x2, y2 = cast(
        tuple[Expr, Expr, Expr, Expr], figure.node(node_id).cache["segment"]
    )
    subs = free_symbols(figure) if substitutions is None else substitutions
    return (
        _real(x1.subs(subs), node_id),
        _real(y1.subs(subs), node_id),
        _real(x2.subs(subs), node_id),
        _real(y2.subs(subs), node_id),
    )
