"""A figure too big to judge is still a figure.

The contract: the exact path has a budget, the picture does not.

- A normal figure is evaluated exactly and judged.
- A figure whose exact expressions blow up is **called too big** -- the
  exact path stops, and the *numeric* path draws it: the same operators,
  run on numbers instead of symbols.
- The picture is the same, dragging is the same, and claims are refused
  with a reason instead of being decided on decimals.

The second half is the important one: the numeric-direct pass must give
the same numbers as the compiled numeric path, or the fallback draws a
different figure from the one the kernel would have drawn.
"""

from __future__ import annotations

import pytest

from geobench import evaluate
from geobench.dsl import parse_dsl
from geobench.evaluate import (
    evaluate_figure,
    evaluate_numeric,
    evaluate_numeric_direct,
)
from geobench.operators import register_builtins
from geobench.primitives import figure_primitives
from geobench.registry import OperatorRegistry
from geobench.style import COMPETITION

NORMAL = """
点 A(0,0) B(5,0) C(2,4)
AB = 线段(A, B)
BC = 线段(B, C)
CA = 线段(C, A)
M = 中点(B, C)
O = 外心(A, B, C)
w = 外接圆(A, B, C)
D = 垂足(A, BC)
"""


@pytest.fixture(scope="module")
def registry() -> OperatorRegistry:
    reg = OperatorRegistry()
    register_builtins(reg)
    return reg


def test_a_normal_figure_is_exact(registry: OperatorRegistry) -> None:
    figure = evaluate_figure(parse_dsl(NORMAL), registry)
    assert figure.runtime["exact"]["status"] == "ok"


def test_a_figure_over_budget_is_called_too_big(
    registry: OperatorRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The budget is a number, so a test can lower it to see the path."""
    monkeypatch.setattr(evaluate, "EXACT_BUDGET_OPS", 10)
    figure = evaluate_figure(parse_dsl(NORMAL), registry)
    assert figure.runtime["exact"]["status"] == "too-big"
    assert "预算" in figure.runtime["exact"]["reason"]
    assert any(node.cache.get("no_value") for node in figure.nodes.values())


def test_the_picture_is_drawn_even_when_the_sum_does_not(
    registry: OperatorRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drawn numerically: the figure is still a figure."""
    monkeypatch.setattr(evaluate, "EXACT_BUDGET_OPS", 10)
    figure = evaluate_figure(parse_dsl(NORMAL), registry)
    evaluate_numeric_direct(figure, registry)
    primitives = figure_primitives(figure, COMPETITION)
    assert len(primitives) >= 6, len(primitives)


def test_the_numbers_agree_with_the_compiled_path(registry: OperatorRegistry) -> None:
    """The fallback must not draw a different figure.

    The compiled numeric path evaluates the exact expressions; the
    direct pass runs the operators on numbers.  They are the same
    arithmetic, and this is what says so.
    """
    figure = evaluate_figure(parse_dsl(NORMAL), registry)
    evaluate_numeric(figure)
    compiled = {
        node_id: node.cache.get("numeric", {}).get("coords")
        for node_id, node in figure.nodes.items()
        if node.kind == "point"
    }

    other = evaluate_figure(parse_dsl(NORMAL), registry)
    evaluate_numeric_direct(other, registry)
    direct = {
        node_id: node.cache.get("numeric", {}).get("coords")
        for node_id, node in other.nodes.items()
        if node.kind == "point"
    }

    for node_id, expected in compiled.items():
        got = direct.get(node_id)
        assert got is not None, node_id
        assert expected is not None, node_id
        for left, right in zip(got, expected, strict=True):
            assert abs(left - right) <= 1e-9 * max(1.0, abs(right)), node_id


def test_the_fallback_reaches_every_object(registry: OperatorRegistry) -> None:
    """Not just the points: the lines and the circle too."""
    figure = evaluate_figure(parse_dsl(NORMAL), registry)
    evaluate_numeric_direct(figure, registry)
    keys = {"point": "coords", "segment": "segment", "circle": "circle", "line": "line"}
    drawn = {
        node.kind
        for node in figure.nodes.values()
        if node.cache.get("numeric", {}).get(keys.get(node.kind, node.kind))
    }
    assert {"point", "segment", "circle"} <= drawn
