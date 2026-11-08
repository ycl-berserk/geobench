"""The measurement family: numbers in the figure.

A measurement is the one object that is not a shape. It has no place
on the canvas of its own -- it is a number *about* something, so it is
written next to that something: the middle of a segment, the vertex of
an angle, the inside of a polygon.
"""

from __future__ import annotations

import pytest

from geobench.dsl import parse_dsl
from geobench.evaluate import (
    evaluate_exact,
    evaluate_figure,
    evaluate_numeric,
    undefined_nodes,
)
from geobench.operators import register_builtins
from geobench.primitives import LabelPrimitive, figure_primitives
from geobench.registry import OperatorRegistry
from geobench.style import get_style


@pytest.fixture(scope="module")
def registry() -> OperatorRegistry:
    reg = OperatorRegistry()
    register_builtins(reg)
    return reg


def _value(registry: OperatorRegistry, source: str) -> float:
    """The numeric value of the last measurement in the script."""
    figure = parse_dsl(source)
    evaluate_figure(figure, registry)
    node_id = [node.id for node in figure.nodes.values() if node.kind == "number"][-1]
    payload = figure.node(node_id).cache["numeric"]
    value = payload["value"]
    assert value is not None
    return float(value)


def test_the_distance_between_two_points(registry: OperatorRegistry) -> None:
    assert _value(registry, "点 A(0,0) B(3,4)\nd = 距离(A, B)") == pytest.approx(5.0)


def test_the_length_of_a_segment(registry: OperatorRegistry) -> None:
    assert _value(registry, "点 A(0,0) B(6,0)\ns = 线段(A,B)\nl = 长度(s)") == pytest.approx(6.0)


def test_the_area_of_a_square(registry: OperatorRegistry) -> None:
    source = """
点 A(0,0) B(2,0) C(2,2) D(0,2)
四 = 多边形(A,B,C,D)
a = 面积(四)
"""
    assert _value(registry, source) == pytest.approx(4.0)


def test_the_perimeter_of_a_square(registry: OperatorRegistry) -> None:
    source = """
点 A(0,0) B(2,0) C(2,2) D(0,2)
四 = 多边形(A,B,C,D)
p = 周长(四)
"""
    assert _value(registry, source) == pytest.approx(8.0)


def test_the_angle_at_a_point_is_in_degrees(registry: OperatorRegistry) -> None:
    source = """
点 A(0,0) B(1,1) C(2,0)
ang = 角度(A, B, C)
"""
    assert _value(registry, source) == pytest.approx(90.0)


def test_the_radius_of_a_circle(registry: OperatorRegistry) -> None:
    source = """
点 A(0,0) B(3,4)
圆 = 圆(A, 25)
r = 半径(圆)
"""
    assert _value(registry, source) == pytest.approx(5.0)


def test_the_slope_of_a_line(registry: OperatorRegistry) -> None:
    source = """
点 A(0,0) B(1,1)
l = 直线(A, B)
k = 斜率(l)
"""
    assert _value(registry, source) == pytest.approx(1.0)


def test_a_vertical_line_has_no_slope(registry: OperatorRegistry) -> None:
    """Vertical is a fact about this drawing, not about the construction.

    The two points are not *identically* on a vertical line, so the
    exact path accepts the slope; the placement is what fails, and the
    number is marked undefined.
    """
    figure = parse_dsl("点 A(0,0) B(0,5)\nl = 直线(A, B)\nk = 斜率(l)")
    evaluate_exact(figure, registry)
    evaluate_numeric(figure)
    assert [node_id for node_id, _ in undefined_nodes(figure)] == ["k"]


def test_the_measurement_is_written_on_the_figure(registry: OperatorRegistry) -> None:
    figure = parse_dsl("点 A(0,0) B(3,4)\nd = 距离(A, B)")
    evaluate_figure(figure, registry)
    labels = [
        primitive
        for primitive in figure_primitives(figure, get_style("competition"))
        if isinstance(primitive, LabelPrimitive)
    ]
    values = [label.text for label in labels]
    assert "5" in values
    # The label sits at the middle of the segment it measures.
    measured = next(label for label in labels if label.text == "5")
    assert measured.x == pytest.approx(1.5)
    assert measured.y == pytest.approx(2.0)
