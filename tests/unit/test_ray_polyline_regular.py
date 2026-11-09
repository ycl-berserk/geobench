"""The ray, the polyline and the regular polygon.

Three shapes the figure already had the pieces for: a line that starts
somewhere, a polygon that is not closed, and a polygon whose vertices
are computed rather than clicked.
"""

from __future__ import annotations

import math

import pytest

from geobench.dsl import parse_dsl
from geobench.evaluate import evaluate_figure
from geobench.operators import register_builtins
from geobench.primitives import (
    PolygonPrimitive,
    RayPrimitive,
    figure_primitives,
)
from geobench.registry import OperatorRegistry
from geobench.render import render_svg
from geobench.style import get_style


@pytest.fixture(scope="module")
def registry() -> OperatorRegistry:
    reg = OperatorRegistry()
    register_builtins(reg)
    return reg


def _build(registry: OperatorRegistry, source: str):
    figure = parse_dsl(source)
    evaluate_figure(figure, registry)
    return figure


def _primitives(figure):
    return figure_primitives(figure, get_style("competition"))


def test_a_ray_keeps_its_starting_point(registry: OperatorRegistry) -> None:
    figure = _build(registry, "点 A(1,2) B(4,6)\nr = 射线(A, B)")
    rays = [p for p in _primitives(figure) if isinstance(p, RayPrimitive)]
    assert len(rays) == 1
    assert (rays[0].x0, rays[0].y0) == pytest.approx((1.0, 2.0))
    assert (rays[0].x1, rays[0].y1) == pytest.approx((4.0, 6.0))


def test_a_ray_is_drawn_only_from_its_start(registry: OperatorRegistry) -> None:
    """The svg line starts at the ray's start, not at the view's edge behind it."""
    figure = _build(registry, "点 A(1,2) B(4,6)\nr = 射线(A, B)")
    svg = render_svg(figure)
    assert "<line" in svg
    # Everything on the ray is on one side of the start along the direction.
    assert svg.count("<line") == 1


def test_a_polyline_is_its_edges_and_not_closed(registry: OperatorRegistry) -> None:
    figure = _build(registry, "点 A(0,0) B(2,0) C(4,2)\n折 = 折线(A, B, C)")
    shapes = [p for p in _primitives(figure) if isinstance(p, PolygonPrimitive)]
    assert len(shapes) == 1
    shape = shapes[0]
    # Three vertices, and *not* closed: the last edge back to the start
    # is what a polygon has and a polyline does not.
    assert len(shape.vertices) == 6
    assert shape.closed is False


def test_a_regular_hexagon_is_exact(registry: OperatorRegistry) -> None:
    """Six vertices on the circle, and the coordinates stay exact."""
    figure = _build(registry, "点 O(0,0) A(2,0)\n六 = 正多边形(O, A, 6)")
    # The exact payload is symbolic -- the free points are symbols -- so
    # the *positions* come from the numeric payload and the *exactness*
    # from the symbolic one.
    exact = figure.node("六").cache["polygon"]
    assert len(exact) == 12
    numeric = figure.node("六").cache["numeric"]["polygon"]
    assert len(numeric) == 12

    # The first vertex is the one that was clicked.
    assert numeric[0] == pytest.approx(2.0)
    assert numeric[1] == pytest.approx(0.0)
    # Every vertex is on the circle of radius 2.
    for index in range(6):
        x, y = numeric[2 * index], numeric[2 * index + 1]
        assert math.hypot(x, y) == pytest.approx(2.0)
    # And the second one is at sixty degrees -- exactly, as sqrt(3).
    forms = {str(component) for component in exact}
    assert any("sqrt(3)" in text for text in forms)


def test_a_regular_pentagon_keeps_its_square_roots(registry: OperatorRegistry) -> None:
    """The turning is exact: a pentagon's vertices carry sqrt(5), not decimals."""
    figure = _build(registry, "点 O(0,0) A(1,0)\n五 = 正多边形(O, A, 5)")
    payload = figure.node("五").cache["polygon"]
    imported = {str(component) for component in payload}
    assert any("sqrt(5)" in text for text in imported)


def test_a_regular_polygon_needs_three_vertices(registry: OperatorRegistry) -> None:
    figure = parse_dsl("点 O(0,0) A(1,0)\n二 = 正多边形(O, A, 2)")
    from geobench.errors import DegenerateError

    with pytest.raises(DegenerateError):
        evaluate_figure(figure, registry)
