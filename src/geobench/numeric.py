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
from typing import Any

import sympy as sp
from sympy import Expr

from geobench.model import Figure, Node

#: The cache keys the numeric path owns.
CACHE_FN = "numeric_fn"
CACHE_SYMBOLS = "numeric_symbols"
CACHE_VALUES = "numeric"
CACHE_CONDITION_FN = "numeric_condition_fn"
CACHE_UNDEFINED = "undefined"

#: The payload a node contributes to the picture, in order.
_PAYLOAD_KEYS = ("coords", "line", "circle", "segment")


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

    Two kinds of condition:

    - ``must_be_nonzero`` -- the expression must **not** vanish (the
      three points must not be collinear);
    - ``must_be_zero`` -- the expression **must** vanish (the point of
      tangency must lie on the circle).

    Both are published rather than checked, because a symbolic expression
    that is not identically zero may still vanish at some placements.
    """
    checks: list[tuple[str, Expr, bool]] = []
    for key, must_vanish in (("must_be_nonzero", False), ("must_be_zero", True)):
        conditions = node.cache.get(key)
        if not isinstance(conditions, dict) or not conditions:
            continue
        for name in sorted(conditions):
            checks.append((name, conditions[name], must_vanish))
    if not checks:
        return
    names = tuple(name for name, _, _ in checks)
    expressions = tuple(expression for _, expression, _ in checks)
    vanish = tuple(flag for _, _, flag in checks)
    used = _used_symbols(expressions, symbols)
    node.cache[CACHE_SYMBOLS] = used
    node.cache[CACHE_CONDITION_FN] = (
        names,
        vanish,
        sp.lambdify(used, expressions, modules="math"),
    )


def format_float(value: float) -> str:
    """A short, readable decimal for a coordinate.

    The exact value lives in the node's symbolic expression; this is only
    what a person reads in the exported figure.
    """
    if value == int(value):
        return str(int(value))
    return f"{value:.12g}"


def free_values(figure: Figure) -> dict[sp.Symbol, float]:
    """The free points' current numeric positions."""
    values: dict[sp.Symbol, float] = {}
    for node in figure.nodes.values():
        if node.role != "free" or node.kind != "point":
            continue
        if node.coords is None or node.placement is None:
            continue
        try:
            values[sp.Symbol(node.coords[0])] = float(node.placement[0])
            values[sp.Symbol(node.coords[1])] = float(node.placement[1])
        except (TypeError, ValueError):
            continue
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
    names, vanish, function = compiled
    symbols = node.cache.get(CACHE_SYMBOLS) or ()
    try:
        arguments = [values[symbol] for symbol in symbols]
        result = function(*arguments)
    except (ArithmeticError, ValueError, TypeError, KeyError):
        return None
    for name, value, must_vanish in zip(names, result, vanish, strict=False):
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(number):
            return str(name)
        if must_vanish:
            if number != 0:
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
