"""The numeric path: fast and approximate, for the screen only.

The exact path (:mod:`geobench.evaluate`) answers "what is this, for every
admissible placement of the free points"; this one answers "where is it on
screen, right now". The difference is not an optimisation detail -- it is
the difference between a proof and a picture.

Three facts make the split possible:

1. A derived object's *symbolic* expression does not depend on where the
   free points are placed. Dragging a point never invalidates it, so the
   algebra is done once per construction, not once per frame.
2. That expression can be **compiled** once into a plain float function,
   so the per-frame cost is a function call rather than algebra.
3. A degenerate configuration shows up at the numeric level as an
   exception or a non-finite value -- which is exactly where it should
   be detected, because "this placement is degenerate" is a statement
   about the placement, not about the construction.

**Nothing in this module may produce a verdict.** The judges use the
exact path; ``tests/contract`` asserts that they never import this one.
Floating point is allowed here, and only here (see D18).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from fractions import Fraction
from typing import Any

import sympy as sp
from sympy import Expr

from geobench.model import (
    CONDITION_NONNEGATIVE,
    CONDITION_NONZERO,
    CONDITION_ZERO,
    Figure,
    Node,
)

#: The cache keys the numeric path owns.
CACHE_FN = "numeric_fn"
CACHE_SYMBOLS = "numeric_symbols"
CACHE_VALUES = "numeric"
CACHE_CONDITION_FN = "numeric_condition_fn"
CACHE_CONDITION_SYMBOLS = "numeric_condition_symbols"
CACHE_UNDEFINED = "undefined"

#: The payload a node contributes to the picture, in order.
_PAYLOAD_KEYS = (
    "coords",
    "line",
    "circle",
    "segment",
    "polygon",
    "arc",
    "sector",
    "ray",
    "polyline",
    "value",
)


def payload_expressions(node: Node) -> tuple[Expr, ...]:
    """The numeric payload of a node: its coordinates, line, circle or segment.

    The payload is what the *shape* of the object is -- not where it
    happens to be. A line is three coefficients; a circle is a centre and
    a squared radius; a point is two coordinates.
    """
    for key in _PAYLOAD_KEYS:
        value = node.cache.get(key)
        if value is not None:
            return tuple(value)
    return ()


def _used_symbols(
    expressions: tuple[Expr, ...], symbols: tuple[sp.Symbol, ...]
) -> tuple[sp.Symbol, ...]:
    """The symbols an expression actually uses.

    A compiled function that takes *every* free symbol would cost a
    function call with hundreds of arguments per node per frame. A
    midpoint uses two; that is all it should take.
    """
    used: set[sp.Symbol] = set()
    for expression in expressions:
        used |= expression.free_symbols
    if used - set(symbols):
        # Something unexpected is in the expression; keep every symbol so
        # that the compiled function is still well formed.
        return symbols
    return tuple(symbol for symbol in symbols if symbol in used)


def compile_node(node: Node, symbols: tuple[sp.Symbol, ...]) -> None:
    """Compile the node's payload into a fast float function.

    The compiled function takes the values of the symbols it uses, in a
    fixed order, and returns the payload as a tuple of floats.
    """
    expressions = payload_expressions(node)
    if not expressions:
        return
    used = _used_symbols(expressions, symbols)
    node.cache[CACHE_SYMBOLS] = used
    node.cache[CACHE_FN] = sp.lambdify(used, expressions, modules="math")


def compile_conditions(node: Node, symbols: tuple[sp.Symbol, ...]) -> None:
    """Compile the conditions the node's answer depends on.

    An operator works on symbols, so it cannot see that *this* placement
    is degenerate. It publishes the conditions instead ("the discriminant
    must not be zero", "the point must lie on the circle"), and they are
    checked numerically, where the placement is known.

    Three kinds of condition:

    - ``must_be_nonzero`` -- the expression must **not** vanish (the
      three points must not be collinear);
    - ``must_be_zero`` -- the expression **must** vanish (the point of
      tangency must lie on the circle);
    - ``must_be_nonnegative`` -- the expression must not be **negative**
      (the point must not be inside the circle).

    Both are published rather than checked, because a symbolic expression
    that is not identically zero may still vanish at some placements.
    """
    checks: list[tuple[str, Expr, str]] = []
    for key, flag in (
        (CONDITION_NONZERO, "nonzero"),
        (CONDITION_ZERO, "zero"),
        (CONDITION_NONNEGATIVE, "nonnegative"),
    ):
        conditions = node.cache.get(key)
        if not isinstance(conditions, dict) or not conditions:
            continue
        for name in sorted(conditions):
            checks.append((name, conditions[name], flag))
    if not checks:
        return
    names = tuple(name for name, _, _ in checks)
    expressions = tuple(expression for _, expression, _ in checks)
    flags = tuple(flag for _, _, flag in checks)
    used = _used_symbols(expressions, symbols)
    # The condition has its own list of symbols: the payload's list says
    # which values the compiled payload takes, and overwriting it would
    # hand the payload the wrong arguments.
    node.cache[CACHE_CONDITION_SYMBOLS] = used
    node.cache[CACHE_CONDITION_FN] = (
        names,
        flags,
        sp.lambdify(used, expressions, modules="math"),
    )


def payload_keys() -> tuple[str, ...]:
    """The cache keys an operator may fill in with an object's shape."""
    return _PAYLOAD_KEYS


def clear_payload(node: Node) -> None:
    """Forget the shape of an object that has no value.

    An object with no value has no shape either: there is nothing to
    compile, nothing to draw, and nothing for the numeric path to
    evaluate.
    """
    for key in _PAYLOAD_KEYS:
        node.cache.pop(key, None)
    node.cache.pop(CACHE_FN, None)
    node.cache.pop(CACHE_SYMBOLS, None)


def format_float(value: float) -> str:
    """A short, readable decimal for a coordinate.

    The exact value lives in the node's symbolic expression; this is only
    what a person reads in the exported figure.
    """
    if value == int(value):
        return str(int(value))
    return f"{value:.12g}"


def point_on_circle(
    figure: Figure, circle_id: str, parameter: str
) -> tuple[float, float] | None:
    """Where a point attached to a circle is, for the display.

    The exact path knows the same thing symbolically; this is the fast
    version, so that dragging a point along a circle costs a sin and a
    cos instead of rebuilding -- and recompiling -- a symbolic
    expression on every frame.
    """
    values = figure.node(circle_id).cache.get(CACHE_VALUES) or {}
    circle = values.get("circle")
    if not circle or len(circle) < 3:
        return None
    cx, cy, r2 = circle[0], circle[1], circle[2]
    if r2 <= 0:
        return None
    t = placement_float(parameter)
    if t is None:
        return None
    angle = 2 * math.pi * t
    radius = math.sqrt(r2)
    return (cx + radius * math.cos(angle), cy + radius * math.sin(angle))


def _numeric_coords(figure: Figure, node_id: str) -> tuple[float, float] | None:
    """Where a point is, for the display."""
    values = figure.node(node_id).cache.get(CACHE_VALUES) or {}
    coords = values.get("coords")
    if not coords or len(coords) < 2:
        return None
    return (float(coords[0]), float(coords[1]))


def along_reference(
    figure: Figure, node_id: str
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """The base point and the direction that measure a parameter.

    The same rule the exact path uses: a segment is measured between
    its ends, a drawn line between the two points it was drawn through,
    and a built line along its own direction.
    """
    node = figure.node(node_id)
    values = node.cache.get(CACHE_VALUES) or {}
    if node.kind == "segment":
        segment = values.get("segment")
        if not segment or len(segment) < 4:
            return None
        x1, y1, x2, y2 = (float(v) for v in segment[:4])
        if x1 == x2 and y1 == y2:
            return None
        return (x1, y1), (x2 - x1, y2 - y1)
    drawn = [arg for arg in node.args if figure.node(arg).kind == "point"]
    if len(drawn) == 2:
        first = _numeric_coords(figure, drawn[0])
        second = _numeric_coords(figure, drawn[1])
        if first is None or second is None:
            return None
        if first == second:
            return None
        return first, (second[0] - first[0], second[1] - first[1])
    line = values.get("line")
    if not line or len(line) < 3:
        return None
    a, b, c = (float(v) for v in line[:3])
    denominator = a * a + b * b
    if denominator == 0:
        return None
    return (-a * c / denominator, -b * c / denominator), (b, -a)


def point_on_line(
    figure: Figure, node_id: str, parameter: str
) -> tuple[float, float] | None:
    """Where a point attached to a line or a segment is, for the display."""
    reference = along_reference(figure, node_id)
    if reference is None:
        return None
    (bx, by), (dx, dy) = reference
    t = placement_float(parameter)
    if t is None:
        return None
    return (bx + t * dx, by + t * dy)


def parameter_on_line(figure: Figure, node_id: str, x: float, y: float) -> str:
    """Where on a line or a segment a click landed, as the parameter.

    On a segment the point stays on the segment: the parameter is
    clamped to the two ends.
    """
    reference = along_reference(figure, node_id)
    if reference is None:
        return "0"
    (bx, by), (dx, dy) = reference
    denominator = dx * dx + dy * dy
    if denominator == 0:
        return "0"
    t = ((x - bx) * dx + (y - by) * dy) / denominator
    if figure.node(node_id).kind == "segment":
        t = min(1.0, max(0.0, t))
    return str(Fraction(t).limit_denominator(720))


def supporting_line(
    figure: Figure, node_id: str
) -> tuple[float, float, float] | None:
    """The coefficients of the line a line or a segment lies on."""
    node = figure.node(node_id)
    values = node.cache.get(CACHE_VALUES) or {}
    if node.kind == "segment":
        segment = values.get("segment")
        if not segment or len(segment) < 4:
            return None
        x1, y1, x2, y2 = (float(v) for v in segment[:4])
        return (y1 - y2, x2 - x1, x1 * y2 - x2 * y1)
    line = values.get("line")
    if not line or len(line) < 3:
        return None
    a, b, c = (float(v) for v in line[:3])
    if a == 0 and b == 0:
        return None
    return (a, b, c)


def intersection_near(
    figure: Figure, x: float, y: float, tolerance: float
) -> tuple[str, str] | None:
    """Two objects whose crossing is under the cursor, if any.

    Clicking where two lines cross should give their intersection --
    a point with no freedom of its own -- and not a free point that
    happens to be in the same place.
    """
    ids = [
        node.id
        for node in figure.nodes.values()
        if node.kind in {"line", "segment"} and node.style.visible
    ]
    for index, first in enumerate(ids):
        line1 = supporting_line(figure, first)
        if line1 is None:
            continue
        for second in ids[index + 1 :]:
            line2 = supporting_line(figure, second)
            if line2 is None:
                continue
            a1, b1, c1 = line1
            a2, b2, c2 = line2
            det = a1 * b2 - a2 * b1
            if abs(det) < 1e-12:
                # Parallel or coincident: no single crossing.
                continue
            px = (b1 * c2 - b2 * c1) / det
            py = (c1 * a2 - c2 * a1) / det
            if math.hypot(px - x, py - y) <= tolerance:
                return (first, second)
    return None


def placement_float(value: str) -> float | None:
    """A placement as a number, or None if it is not one.

    A placement is **exact**: it is a rational, written "101/100", or a
    whole number, written "3". Reading it with float() alone throws away
    every point that is not on a whole coordinate -- and then everything
    built on such a point has no value either, and the figure quietly
    falls apart.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    try:
        return float(Fraction(value))
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def free_values(figure: Figure) -> dict[sp.Symbol, float]:
    """The free points' current numeric positions."""
    values: dict[sp.Symbol, float] = {}
    for node in figure.nodes.values():
        if node.role != "free" or node.kind != "point":
            continue
        if node.coords is None or node.placement is None:
            continue
        x = placement_float(node.placement[0])
        y = placement_float(node.placement[1])
        if x is None or y is None:
            continue
        values[sp.Symbol(node.coords[0])] = x
        values[sp.Symbol(node.coords[1])] = y
    return values


def evaluate_node(node: Node, values: dict[sp.Symbol, float]) -> dict[str, Any] | None:
    """The node's numeric payload at this placement.

    Returns ``None`` when the node has no value here -- a degenerate
    configuration. GeoGebra calls this "undefined"; we do the same
    (decision D19), because a figure that loses one object is still a
    figure, while a figure that refuses to exist is not.
    """
    function = node.cache.get(CACHE_FN)
    symbols = node.cache.get(CACHE_SYMBOLS)
    if function is None or symbols is None:
        return None
    try:
        arguments = [values[symbol] for symbol in symbols]
    except KeyError:
        return None
    try:
        result = function(*arguments)
    except (ArithmeticError, ValueError, TypeError):
        return None
    try:
        numbers = [float(value) for value in result]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(number) for number in numbers):
        return None
    return {"numbers": numbers}


def failing_condition(node: Node, values: dict[sp.Symbol, float]) -> str | None:
    """The name of a condition that fails at this placement, if any."""
    compiled = node.cache.get(CACHE_CONDITION_FN)
    if compiled is None:
        return None
    names, flags, function = compiled
    symbols = node.cache.get(CACHE_CONDITION_SYMBOLS) or ()
    try:
        arguments = [values[symbol] for symbol in symbols]
        result = function(*arguments)
    except (ArithmeticError, ValueError, TypeError, KeyError):
        return None
    for name, value, flag in zip(names, result, flags, strict=False):
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(number):
            return str(name)
        if flag == "zero":
            if number != 0:
                return str(name)
        elif flag == "nonnegative":
            if number < 0:
                return str(name)
        elif number == 0:
            return str(name)
    return None


def symbols_of(figure: Figure) -> tuple[sp.Symbol, ...]:
    """The free points' symbols, in a stable order."""
    symbols: list[sp.Symbol] = []
    for node in figure.nodes.values():
        if node.role != "free" or node.kind != "point":
            continue
        if node.coords is None:
            continue
        symbols.append(sp.Symbol(node.coords[0]))
        symbols.append(sp.Symbol(node.coords[1]))
    return tuple(sorted(set(symbols), key=str))


def is_compiled(node: Node, symbols: Sequence[sp.Symbol]) -> bool:
    """Is the node's compiled function still valid for these symbols?"""
    return node.cache.get(CACHE_SYMBOLS) == tuple(symbols) and CACHE_FN in node.cache


NumericFunction = Callable[..., Any]
