"""The tangent to a circle: at a point of it, and from a point outside it.

Two cases, one formula, and a third case where there is no tangent at
all -- a point inside the circle.  The checks are made on the *drawn*
line (the numeric path), because that is the line the teacher sees.
"""

from __future__ import annotations

import math

import pytest

from geobench.dsl import parse_dsl
from geobench.evaluate import evaluate_figure, evaluate_numeric, undefined_nodes
from geobench.judges import INSTANCE, JudgeRegistry, judge_relation
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry


@pytest.fixture(scope="module")
def registry() -> OperatorRegistry:
    reg = OperatorRegistry()
    register_builtins(reg)
    return reg


def _drawn_line(figure, node_id: str = "t") -> tuple[float, float, float] | None:
    """The line as it is drawn, in the coordinate system of the figure."""
    node = figure.nodes.get(node_id)
    if node is None:
        return None
    return node.cache.get("numeric", {}).get("line")


def _placed(figure, name: str) -> tuple[float, float]:
    placement = figure.nodes[name].placement
    assert placement is not None
    return (float(placement[0]), float(placement[1]))


def _normal(figure, node_id: str = "t") -> tuple[float, float]:
    """The direction the line faces, as a unit vector."""
    line = _drawn_line(figure, node_id)
    assert line is not None
    a, b, _ = line
    norm = math.hypot(a, b)
    assert norm > 0
    return (a / norm, b / norm)


def test_the_tangent_at_a_point_of_the_circle_is_perpendicular_to_the_radius(
    registry: OperatorRegistry,
) -> None:
    figure = evaluate_figure(
        parse_dsl("点 O(0,0) A(1,0) P(1,0)\nc = 圆(O, A)\nt = 切线(P, c)\n"), registry
    )
    evaluate_numeric(figure)
    normal = _normal(figure)
    # The radius OP is horizontal, so the tangent at P is the vertical
    # line x = 1 -- and a vertical line's normal is horizontal.
    assert math.isclose(abs(normal[0]), 1.0, abs_tol=1e-9)
    assert math.isclose(abs(normal[1]), 0.0, abs_tol=1e-9)


def test_the_tangent_from_a_point_outside_is_tangent_and_passes_through_it(
    registry: OperatorRegistry,
) -> None:
    figure = evaluate_figure(
        parse_dsl("点 O(1,1) A(3,1) P(7,2)\nc = 圆(O, A)\nt = 切线(P, c)\n"), registry
    )
    evaluate_numeric(figure)
    line = _drawn_line(figure)
    assert line is not None
    a, b, c = line
    ox, oy = _placed(figure, "O")
    px, py = _placed(figure, "P")
    radius = math.dist((ox, oy), _placed(figure, "A"))
    norm = math.hypot(a, b)
    # The distance from the centre to the line is the radius: that is
    # what "tangent" means.
    assert math.isclose(abs(a * ox + b * oy + c) / norm, radius, rel_tol=1e-9)
    # And the line goes through the point it was drawn from.
    assert math.isclose(abs(a * px + b * py + c) / norm, 0.0, abs_tol=1e-9)


def test_the_tangent_from_a_point_inside_does_not_exist(
    registry: OperatorRegistry,
) -> None:
    """A point inside the circle has no tangent -- and the figure says so."""
    figure = evaluate_figure(
        parse_dsl("点 O(0,0) A(2,0) P(1,0)\nc = 圆(O, A)\nt = 切线(P, c)\n"), registry
    )
    evaluate_numeric(figure)
    undefined = undefined_nodes(figure)
    assert undefined, "a tangent from inside the circle was not caught"
    assert undefined[0][0] == "t"
    assert _drawn_line(figure) is None


def test_the_tangent_is_tangent_as_the_judge_sees_it(registry: OperatorRegistry) -> None:
    """The judge confirms it in the drawn configuration."""
    figure = evaluate_figure(
        parse_dsl(
            "点 O(1,1) A(3,1) P(7,2)\nc = 圆(O, A)\nt = 切线(P, c)\n断言 相切(t, c)\n"
        ),
        registry,
    )
    relation = figure.relations[-1]
    verdict = judge_relation(
        figure, relation.kind, list(relation.args), JudgeRegistry(), scope=INSTANCE
    )
    assert verdict.verdict == "proved", verdict.evidence


def test_a_point_on_the_circle_still_gets_the_tangent_at_that_point(
    registry: OperatorRegistry,
) -> None:
    """The old meaning is still there: the tangent at a point of the circle."""
    figure = evaluate_figure(
        parse_dsl("点 O(0,0) A(2,0) P(0,2)\nc = 圆(O, A)\nt = 切线(P, c)\n"), registry
    )
    evaluate_numeric(figure)
    normal = _normal(figure)
    # The radius OP is vertical, so the tangent at P is the horizontal
    # line y = 2 -- and a horizontal line's normal is vertical.
    assert math.isclose(abs(normal[0]), 0.0, abs_tol=1e-9)
    assert math.isclose(abs(normal[1]), 1.0, abs_tol=1e-9)
