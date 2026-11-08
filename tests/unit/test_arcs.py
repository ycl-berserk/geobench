"""The arc and the sector: the circle family's curved pieces (T028b).

An arc is a *choice* of one of the two arcs between two points, and
which one is meant is a question about the drawing, not about the
symbols. So the angles are settled when the figure is drawn -- and
settled once, so that the screen and the export agree.
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
from geobench.primitives import ArcPrimitive, figure_primitives
from geobench.registry import OperatorRegistry
from geobench.render import render_svg
from geobench.style import get_style


@pytest.fixture(scope="module")
def registry() -> OperatorRegistry:
    reg = OperatorRegistry()
    register_builtins(reg)
    return reg


def _figure(registry: OperatorRegistry, source: str):
    figure = parse_dsl(source)
    evaluate_figure(figure, registry)
    return figure


def _arcs(figure) -> list[ArcPrimitive]:
    return [p for p in figure_primitives(figure, get_style("competition")) if isinstance(p, ArcPrimitive)]


def test_the_arc_through_three_points_is_drawn(registry: OperatorRegistry) -> None:
    figure = _figure(
        registry,
        "点 A(4,0) B(0,4) C(-4,0)\n弧 = 圆弧(A, B, C)",
    )
    arcs = _arcs(figure)
    assert len(arcs) == 1
    arc = arcs[0]
    assert (arc.cx, arc.cy) == (0.0, 0.0)
    assert arc.radius == pytest.approx(4.0)
    # From A at 0 degrees, counter-clockwise, to C at 180 degrees.
    assert arc.start_angle == pytest.approx(0.0)
    assert arc.span_angle == pytest.approx(180.0)
    assert not arc.filled


def test_the_arc_takes_the_side_the_middle_point_is_on(registry: OperatorRegistry) -> None:
    """The arc from A to B that passes through C is the long one."""
    figure = _figure(
        registry,
        "点 A(4,0) B(0,4) C(-4,0)\n弧 = 圆弧(A, C, B)",
    )
    arc = _arcs(figure)[0]
    # Counter-clockwise from A to B is 90 degrees and does not contain
    # C, so the arc runs the other way: 270 degrees.
    assert arc.span_angle == pytest.approx(270.0)


def test_the_sector_is_a_filled_wedge(registry: OperatorRegistry) -> None:
    figure = _figure(
        registry,
        "点 O(0,0) A(4,0) B(0,4)\n扇 = 三点扇形(O, A, B)",
    )
    arcs = _arcs(figure)
    assert len(arcs) == 1
    sector = arcs[0]
    assert (sector.cx, sector.cy) == (0.0, 0.0)
    assert sector.radius == pytest.approx(4.0)
    assert sector.span_angle == pytest.approx(90.0)
    assert sector.filled


def test_the_arc_is_drawn_as_an_svg_path(registry: OperatorRegistry) -> None:
    figure = _figure(
        registry,
        "点 A(4,0) B(0,4) C(-4,0)\n弧 = 圆弧(A, B, C)",
    )
    svg = render_svg(figure)
    assert "<path" in svg
    assert " A " in svg


def test_three_collinear_points_leave_the_arc_undefined(registry: OperatorRegistry) -> None:
    """Collinear is not a mistake, it is a placement with no circle.

    The three points are not *identically* collinear, so the exact
    path cannot refuse them; the placement is what fails, and the node
    is marked undefined while the rest of the figure stays intact.
    """
    figure = parse_dsl("点 A(0,0) B(1,0) C(2,0)\n弧 = 圆弧(A, B, C)")
    evaluate_exact(figure, registry)
    evaluate_numeric(figure)
    assert [node_id for node_id, _ in undefined_nodes(figure)] == ["弧"]
    assert figure.nodes["A"].placement == ("0", "0")
