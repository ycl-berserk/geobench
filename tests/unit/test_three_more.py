"""The vertex, the affine ratio and the polar.

Three commands that fit the shapes the figure already has: a polygon
already knows its vertices, a segment already knows its two ends, and
a circle already knows its centre and its radius.
"""

from __future__ import annotations

import math

import pytest

from geobench.dsl import parse_dsl
from geobench.evaluate import evaluate_figure
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry


@pytest.fixture(scope="module")
def registry() -> OperatorRegistry:
    reg = OperatorRegistry()
    register_builtins(reg)
    return reg


def _coords(registry: OperatorRegistry, source: str, node_id: str) -> tuple[float, float]:
    figure = parse_dsl(source)
    evaluate_figure(figure, registry)
    payload = figure.node(node_id).cache["numeric"]
    x, y = payload["coords"]
    return float(x), float(y)


def test_the_nth_vertex_of_a_polygon(registry: OperatorRegistry) -> None:
    source = """
点 A(0,0) B(6,0) C(2,4) D(5,5)
四 = 多边形(A,B,C,D)
V = 顶点(四, 3)
"""
    assert _coords(registry, source, "V") == pytest.approx((2.0, 4.0))


def test_the_point_that_divides_a_segment_in_a_ratio(registry: OperatorRegistry) -> None:
    source = """
点 A(0,0) B(6,0)
P = 仿射比(A, B, 1, 2)
"""
    # AP : PB = 1 : 2, so P is a third of the way along.
    assert _coords(registry, source, "P") == pytest.approx((2.0, 0.0))


def test_the_polar_of_a_point_on_the_circle_is_the_tangent(registry: OperatorRegistry) -> None:
    source = """
点 O(0,0) A(5,0) B(0,5)
圆 = 圆(O, 25)
极 = 极线(A, 圆)
切 = 切线(A, 圆)
"""
    figure = parse_dsl(source)
    evaluate_figure(figure, registry)
    polar = figure.node("极").cache["numeric"]["line"]
    tangent = figure.node("切").cache["numeric"]["line"]
    # The two lines are the same line, but a line's coefficients are only
    # defined up to a factor -- the tangent's formula carries the radius,
    # the polar's does not -- so both are put in the same scale first.
    assert _canonical(polar) == pytest.approx(_canonical(tangent))


def _canonical(line: tuple[float, float, float]) -> tuple[float, float, float]:
    a, b, c = line
    norm = math.hypot(a, b)
    return (a / norm, b / norm, c / norm)
