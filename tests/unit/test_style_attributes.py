"""Per-object appearance: a red segment is still the same segment.

The model has carried colour, width, point size and label position since
the beginning, but nothing read them: the screen, the SVG and the HTML
export all drew in one global style.  These tests are the contract that
they now read the object's own ink -- and that the ink is only ever
ink: appearance must not change a single coordinate.
"""

from __future__ import annotations

import pytest

from geobench.app.export_html import html_source
from geobench.dsl import parse_dsl, to_dsl
from geobench.dsl.errors import DSLParseError
from geobench.evaluate import evaluate_figure
from geobench.operators import register_builtins
from geobench.primitives import (
    FREE_POINT_COLOR,
    LabelPrimitive,
    PointPrimitive,
    SegmentPrimitive,
    figure_primitives,
)
from geobench.registry import OperatorRegistry
from geobench.render import render_svg
from geobench.style import COMPETITION


@pytest.fixture()
def registry() -> OperatorRegistry:
    ops = OperatorRegistry()
    register_builtins(ops)
    return ops


def _draw(source: str, registry: OperatorRegistry):
    figure = parse_dsl(source)
    evaluate_figure(figure, registry)
    return figure, figure_primitives(figure, COMPETITION)


def test_a_coloured_segment_is_red_on_screen_and_in_the_export(
    registry: OperatorRegistry,
) -> None:
    figure, primitives = _draw(
        "点 A(0,0) B(4,0)\nl = 线段(A,B)\n颜色 l 红\n", registry
    )
    segment = next(p for p in primitives if isinstance(p, SegmentPrimitive))
    assert segment.ink.color == "#c0392b"
    assert "#c0392b" in render_svg(figure, COMPETITION)


def test_the_width_override_is_only_that_object(registry: OperatorRegistry) -> None:
    _, primitives = _draw(
        "点 A(0,0) B(4,0) C(0,3)\n"
        "l = 线段(A,B)\n"
        "m = 线段(A,C)\n"
        "线宽 l 粗\n",
        registry,
    )
    widths = {
        p.id: p.ink.width for p in primitives if isinstance(p, SegmentPrimitive)
    }
    assert widths["l"] == 0.7
    assert widths["m"] is None


def test_the_label_moves_to_the_position_the_author_chose(
    registry: OperatorRegistry,
) -> None:
    _, primitives = _draw(
        "点 A(0,0) B(4,0)\n标签位置 A 右上\n", registry
    )
    label = next(
        p for p in primitives if isinstance(p, LabelPrimitive) and p.text == "A"
    )
    assert label.offset_x > 0.5 and label.offset_y > 0.5
    # The point itself did not move: this is appearance, not geometry.
    point = next(p for p in primitives if isinstance(p, PointPrimitive) and p.id == "A")
    assert (point.x, point.y) == (0.0, 0.0)


def test_a_free_point_is_blue_and_a_derived_point_is_black(
    registry: OperatorRegistry,
) -> None:
    """The blue dot is the one the hand can move; the rest are results."""
    _, primitives = _draw("点 A(0,0) B(4,0)\nM = 中点(A,B)\n", registry)
    points = {p.id: p for p in primitives if isinstance(p, PointPrimitive)}
    assert points["A"].free
    assert points["A"].ink.color == FREE_POINT_COLOR
    assert not points["M"].free
    assert points["M"].ink.color is None


def test_a_bigger_point_is_a_bigger_dot(registry: OperatorRegistry) -> None:
    _, primitives = _draw("点 A(0,0) B(4,0)\n点大小 A 大\n", registry)
    points = {p.id: p for p in primitives if isinstance(p, PointPrimitive)}
    assert points["A"].ink.point_size == 4.5
    assert points["B"].ink.point_size is None


def test_the_appearance_survives_the_round_trip(registry: OperatorRegistry) -> None:
    source = (
        "点 A(0,0) B(4,0) C(0,3)\n"
        "l = 线段(A,B)\n"
        "m = 线段(A,C)\n"
        "颜色 l 蓝\n"
        "线宽 l 0.8\n"
        "点大小 A 小\n"
        "标签位置 A 左下\n"
    )
    figure = parse_dsl(source)
    text = to_dsl(figure)
    assert "颜色 l 蓝" in text
    assert "线宽 l 0.8" in text
    again = parse_dsl(text)
    for node_id in ("l", "m", "A", "C"):
        assert again.nodes[node_id].style == figure.nodes[node_id].style, node_id


def test_the_default_colour_can_be_restored(registry: OperatorRegistry) -> None:
    figure, _ = _draw(
        "点 A(0,0) B(4,0)\nl = 线段(A,B)\n颜色 l 红\n颜色 l 默认\n", registry
    )
    assert figure.nodes["l"].style.color == "#000000"


def test_an_unknown_colour_is_refused_with_the_choices() -> None:
    with pytest.raises(DSLParseError) as caught:
        parse_dsl("点 A(0,0) B(4,0)\nl = 线段(A,B)\n颜色 l 荧光黄\n")
    assert "红" in str(caught.value)


def test_a_label_position_never_moves_the_geometry(
    registry: OperatorRegistry,
) -> None:
    figure, _ = _draw("点 A(0,0) B(4,0)\n标签位置 A 右上\n", registry)
    assert figure.nodes["A"].placement == ("0", "0")
    assert figure.nodes["A"].coords == ("x_A", "y_A")


def test_the_html_export_draws_the_same_colour(registry: OperatorRegistry) -> None:
    """The draggable page is the third backend, and it reads the same ink."""
    figure, _ = _draw(
        "点 A(0,0) B(4,0)\nl = 线段(A,B)\n颜色 l 红\n", registry
    )
    assert "#c0392b" in html_source(figure)
