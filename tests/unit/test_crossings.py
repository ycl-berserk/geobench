"""Clicks at a crossing mean the crossing -- line with line, line with circle,
circle with circle.

The point tool used to look only for line-line crossings, so a click at a
line-circle crossing became a point *on the circle*, and a click at a
circle-circle crossing became a point on whichever circle was checked
first.  A teacher who points at a crossing means the crossing.

What is checked here is the geometry of the decision: the nearest
crossing, the right branch (the kernel numbers the two answers), and the
fact that a segment is not its supporting line.
"""

from __future__ import annotations

import math

import pytest

from geobench.dsl import parse_dsl
from geobench.evaluate import evaluate_figure
from geobench.numeric import Crossing, crossing_near
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry


@pytest.fixture()
def registry() -> OperatorRegistry:
    ops = OperatorRegistry()
    register_builtins(ops)
    return ops


def _figure(source: str, registry: OperatorRegistry):
    figure = parse_dsl(source)
    evaluate_figure(figure, registry)
    return figure


def _crossing(figure, x: float, y: float, tolerance: float = 0.05) -> Crossing:
    found = crossing_near(figure, x, y, tolerance)
    assert found is not None, (x, y)
    return found


def test_two_segments_cross_where_they_cross(registry: OperatorRegistry) -> None:
    figure = _figure(
        "点 A(-2,0) B(2,0) C(0,-2) D(0,2)\n"
        "s1 = 线段(A,B)\n"
        "s2 = 线段(C,D)\n",
        registry,
    )
    crossing = _crossing(figure, 0.01, -0.01)
    assert crossing.kind == "lines"
    assert {crossing.first, crossing.second} == {"s1", "s2"}
    assert crossing.operation() == ("point.intersect_lines", [crossing.first, crossing.second])


def test_the_nearest_line_circle_crossing_is_chosen(registry: OperatorRegistry) -> None:
    """Both crossings are within reach of a sloppy click; the nearer wins."""
    figure = _figure(
        "点 A(-2,0) B(2,0) P(0,0) Q(1,0)\n"
        "s = 线段(A,B)\n"
        "w = 圆(P,Q)\n",
        registry,
    )
    right = _crossing(figure, 1.0, 0.0)
    left = _crossing(figure, -1.0, 0.0)
    assert right.kind == left.kind == "line_circle"
    assert right.x == pytest.approx(1.0)
    assert left.x == pytest.approx(-1.0)
    # The branches are the kernel's own numbering: "0" is (1, 0) here.
    assert right.selector == "0"
    assert left.selector == "1"
    assert right.operation() == ("point.intersect_line_circle", ["s", "w", "0"])
    assert left.operation() == ("point.intersect_line_circle", ["s", "w", "1"])


def test_a_circle_circle_crossing_picks_the_branch_that_was_clicked(
    registry: OperatorRegistry,
) -> None:
    figure = _figure(
        "点 P(0,0) Q(1,0) R(2,0)\n"
        "w1 = 圆(P,Q)\n"
        "w2 = 圆(Q,R)\n",
        registry,
    )
    upper = _crossing(figure, 0.5, math.sqrt(3) / 2)
    lower = _crossing(figure, 0.5, -math.sqrt(3) / 2)
    assert upper.kind == lower.kind == "circles"
    assert upper.y == pytest.approx(math.sqrt(3) / 2)
    assert lower.y == pytest.approx(-math.sqrt(3) / 2)
    assert upper.selector == "0"
    assert lower.selector == "1"


def test_a_segment_is_not_its_supporting_line(registry: OperatorRegistry) -> None:
    """The lines cross at (0,0), but the drawn segment stops before it."""
    figure = _figure(
        "点 A(-2,0) B(-1,0) C(0,-1) D(0,1)\n"
        "s1 = 线段(A,B)\n"
        "s2 = 线段(C,D)\n",
        registry,
    )
    assert crossing_near(figure, 0.0, 0.0, 0.05) is None


def test_a_line_circle_crossing_off_the_segment_is_not_offered(
    registry: OperatorRegistry,
) -> None:
    figure = _figure(
        "点 A(-2,0) B(-1,0) P(0,0) Q(1,0)\n"
        "s = 线段(A,B)\n"
        "w = 圆(P,Q)\n",
        registry,
    )
    assert crossing_near(figure, 1.0, 0.0, 0.05) is None


def test_nothing_near_the_click_is_no_crossing(registry: OperatorRegistry) -> None:
    figure = _figure(
        "点 A(-2,0) B(2,0) C(0,-2) D(0,2)\n"
        "s1 = 线段(A,B)\n"
        "s2 = 线段(C,D)\n",
        registry,
    )
    assert crossing_near(figure, 1.5, 1.5, 0.1) is None


def test_hidden_objects_do_not_cross(registry: OperatorRegistry) -> None:
    """A hidden line is not on the paper, so its crossings are not either."""
    figure = _figure(
        "点 A(-2,0) B(2,0) C(0,-2) D(0,2)\n"
        "s1 = 线段(A,B)\n"
        "s2 = 线段(C,D)\n隐藏 s2\n",
        registry,
    )
    assert crossing_near(figure, 0.0, 0.0, 0.05) is None
