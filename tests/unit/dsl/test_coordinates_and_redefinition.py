"""Coordinates are exact numbers, and a name may be defined twice.

Two holes the evaluation set found (T044):

- ``C(2, 2*sqrt(3))`` could not be written: a coordinate was a number
  or a fraction, and nothing else.  A competition figure needs the
  exact root: the third vertex of an equilateral triangle is not on a
  rational coordinate, and rounding it would make the figure a lie.
- ``D = 旋转(...)`` then ``D = 位似(...)`` could not be written: a name
  may only be defined once.  GeoGebra allows the redefinition, and a
  construction often wants two steps under one name.

The edge cases matter as much as the features: a coordinate must not
be a *program* (``sqrt(a)`` with a free symbol is refused), and a
definition must not run through itself.
"""

from __future__ import annotations

import math

import pytest

from geobench import numeric
from geobench.dsl import parse_dsl
from geobench.dsl.errors import DSLParseError
from geobench.evaluate import evaluate_figure, evaluate_numeric
from geobench.judges import INSTANCE, JudgeRegistry, judge_relation
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry


@pytest.fixture(scope="module")
def registry() -> OperatorRegistry:
    reg = OperatorRegistry()
    register_builtins(reg)
    return reg


def _placed(source: str, registry: OperatorRegistry, name: str) -> tuple[float, float]:
    figure = evaluate_figure(parse_dsl(source), registry)
    evaluate_numeric(figure)
    placement = figure.nodes[name].placement
    assert placement is not None
    # The same reading the numeric path uses: a placement may be exact
    # ("2*sqrt(3)"), so float() alone is not enough.
    x = numeric.placement_float(placement[0])
    y = numeric.placement_float(placement[1])
    assert x is not None and y is not None
    return (x, y)


# -- coordinates are exact numbers ------------------------------------------


def test_a_coordinate_can_be_a_root(registry: OperatorRegistry) -> None:
    """An equilateral triangle has a vertex off the rational grid."""
    x, y = _placed("点 A(0,0) B(4,0) C(2, 2*sqrt(3))", registry, "C")
    assert x == 2.0
    assert y == pytest.approx(2 * math.sqrt(3))


def test_a_coordinate_keeps_the_exact_expression(registry: OperatorRegistry) -> None:
    """The placement stays exact: the number is not rounded on the way in."""
    figure = evaluate_figure(
        parse_dsl("点 A(0,0) B(4,0) C(2, 2*sqrt(3))"), registry
    )
    assert figure.nodes["C"].placement == ("2", "2*sqrt(3)")


def test_a_coordinate_may_be_a_sum_and_a_quotient(registry: OperatorRegistry) -> None:
    """``(1+sqrt(5))/2`` is a number, and it is exact."""
    x, _ = _placed("点 A(0,0) B(1,0) C((1+sqrt(5))/2, 0)", registry, "C")
    assert x == pytest.approx((1 + math.sqrt(5)) / 2)


def test_a_decimal_coordinate_becomes_the_rational_it_is(
    registry: OperatorRegistry,
) -> None:
    """``2.5`` is ``5/2``: the kernel never sees a float."""
    figure = evaluate_figure(parse_dsl("点 A(2.5, 0)"), registry)
    assert figure.nodes["A"].placement == ("5/2", "0")


def test_a_coordinate_may_not_contain_a_letter() -> None:
    """A coordinate is a number, not a program."""
    with pytest.raises(DSLParseError) as failure:
        parse_dsl("点 A(0,0) B(4,0) C(2, 2*sqrt(a))")
    message = str(failure.value)
    assert "不是数" in message and "字母" in message, message


def test_an_unknown_function_is_refused() -> None:
    """Only ``sqrt`` -- anything else is a mistake, not a feature."""
    with pytest.raises(DSLParseError) as failure:
        parse_dsl("点 A(0,0) B(1,0) C(log(2), 0)")
    assert "只有 sqrt" in str(failure.value)


# -- a name may be defined twice --------------------------------------------


def test_a_name_may_be_defined_again(registry: OperatorRegistry) -> None:
    """Rotate, then scale: two steps, one name."""
    figure = evaluate_figure(
        parse_dsl(
            """
点 A(0,0) B(5,0)
E = 旋转(B, 60, A)
D = 中点(A, B)
D = 位似(E, 3/5, A)
"""
        ),
        registry,
    )
    evaluate_numeric(figure)
    assert figure.nodes["D"].op == "transform.dilate"
    x, y = (float(value) for value in figure.nodes["D"].placement)
    assert x == pytest.approx(1.5)
    assert y == pytest.approx(3 * math.sqrt(3) / 2)


def test_everything_that_used_the_name_follows_the_new_definition(
    registry: OperatorRegistry,
) -> None:
    """Dependents point at the id, so a redefinition reaches them."""
    figure = evaluate_figure(
        parse_dsl(
            """
点 A(0,0) B(10,0)
D = 中点(A, B)
M = 中点(A, D)
D = 位似(B, 1/5, A)
"""
        ),
        registry,
    )
    evaluate_numeric(figure)
    assert figure.nodes["D"].placement == ("2", "0")
    assert figure.nodes["M"].placement == ("1", "0")


def test_a_free_point_may_be_moved_by_defining_it_again(
    registry: OperatorRegistry,
) -> None:
    figure = evaluate_figure(
        parse_dsl(
            """
点 A(0,0) B(4,0)
点 B(6,0)
"""
        ),
        registry,
    )
    evaluate_numeric(figure)
    assert figure.nodes["B"].placement == ("6", "0")


def test_a_definition_that_runs_through_itself_is_refused() -> None:
    """``D = 位似(D, ...)`` has no answer -- and the error says what to do."""
    with pytest.raises(DSLParseError) as failure:
        parse_dsl(
            """
点 A(0,0) B(5,0)
D = 旋转(B, 60, A)
D = 位似(D, 3/5, A)
"""
        )
    message = str(failure.value)
    assert "绕回了它自己" in message, message
    assert "换个名字" in message, message


def test_an_indirect_cycle_is_refused_too() -> None:
    with pytest.raises(DSLParseError) as failure:
        parse_dsl(
            """
点 A(0,0) B(4,0)
E = 中点(A, B)
D = 中点(E, B)
E = 中点(D, A)
"""
        )
    assert "绕回了它自己" in str(failure.value)


def test_the_definition_may_not_grow_the_object(registry: OperatorRegistry) -> None:
    """A redefinition replaces the object; it does not add a second one."""
    figure = evaluate_figure(
        parse_dsl(
            """
点 A(0,0) B(5,0)
D = 中点(A, B)
D = 中点(B, A)
"""
        ),
        registry,
    )
    assert list(figure.nodes).count("D") == 1
    assert figure.nodes["D"].kind == "point"


def test_a_point_placed_with_a_root_takes_part_in_exact_geometry(
    registry: OperatorRegistry,
) -> None:
    """The equilateral triangle is exactly equilateral, not approximately."""
    figure = evaluate_figure(
        parse_dsl(
            """
点 A(0,0) B(4,0) C(2, 2*sqrt(3))
AB = 线段(A, B)
AC = 线段(A, C)
断言 相等(AB, AC)
"""
        ),
        registry,
    )
    relation = figure.relations[-1]
    verdict = judge_relation(
        figure, relation.kind, list(relation.args), JudgeRegistry(), scope=INSTANCE
    )
    assert verdict.verdict == "proved", verdict.evidence
