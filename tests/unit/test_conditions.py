"""The conditions a construction publishes, and how they are decided.

A construction works on symbols, so it cannot see that *this* placement
is degenerate. It publishes the conditions instead, and they are decided
where the placement is known.

There are three kinds, and each one is a different statement about an
expression:

- ``must_be_nonzero``  -- it must not vanish;
- ``must_be_zero``     -- it must vanish;
- ``must_be_nonnegative`` -- it must not be negative.

The third kind is not decoration: "this point must not be inside this
circle" is an order, not an equality, and no equality can say it.
"""

from __future__ import annotations

import sympy as sp

from geobench import numeric
from geobench.model import (
    CONDITION_NONNEGATIVE,
    CONDITION_NONZERO,
    CONDITION_ZERO,
    Node,
)


def _node_with(condition_key: str, expression: sp.Expr, symbol: sp.Symbol) -> Node:
    node = Node(id="x", kind="line", role="derived", op="line.free")
    node.cache[condition_key] = {"the_condition": expression}
    numeric.compile_conditions(node, (symbol,))
    return node


def test_a_condition_that_must_not_vanish_fails_when_it_does() -> None:
    symbol = sp.Symbol("d")
    node = _node_with(CONDITION_NONZERO, symbol, symbol)
    assert numeric.failing_condition(node, {symbol: 2.0}) is None
    assert numeric.failing_condition(node, {symbol: 0.0}) == "the_condition"


def test_a_condition_that_must_vanish_fails_when_it_does_not() -> None:
    symbol = sp.Symbol("d")
    node = _node_with(CONDITION_ZERO, symbol, symbol)
    assert numeric.failing_condition(node, {symbol: 0.0}) is None
    assert numeric.failing_condition(node, {symbol: 2.0}) == "the_condition"


def test_a_condition_that_must_not_be_negative_fails_when_it_is() -> None:
    symbol = sp.Symbol("g")
    node = _node_with(CONDITION_NONNEGATIVE, symbol, symbol)
    assert numeric.failing_condition(node, {symbol: 0.0}) is None
    assert numeric.failing_condition(node, {symbol: 1.0}) is None
    assert numeric.failing_condition(node, {symbol: -1.0}) == "the_condition"


def test_a_condition_that_is_not_a_number_fails() -> None:
    """An expression that came out as infinity is not a value."""
    symbol = sp.Symbol("d")
    node = _node_with(CONDITION_NONNEGATIVE, symbol, symbol)
    assert numeric.failing_condition(node, {symbol: float("inf")}) == "the_condition"
    assert numeric.failing_condition(node, {symbol: float("nan")}) == "the_condition"
