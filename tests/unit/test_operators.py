"""Operator behaviour that the oracle battery does not pin down.

The oracle checks that an operator produces the *right geometry*. It cannot
check everything: an operator may return a correct answer for the wrong
reason, or be correct only because of an accident of the parameterisation.
These tests pin down the conventions the oracle deliberately leaves free.
"""

from __future__ import annotations

import pytest

from geobench.errors import AmbiguousIntersectionError
from geobench.evaluate import evaluate_figure, undefined_nodes
from geobench.model import CIRCLE, DERIVED, FREE, LINE, POINT, SEGMENT, Figure, Node
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry


def _registry() -> OperatorRegistry:
    registry = OperatorRegistry()
    register_builtins(registry)
    return registry


def _figure_with_a_line_through_the_origin() -> Figure:
    """A, B, C with A at the origin; the line AD passes through the origin."""
    figure = Figure(id="fig_origin")
    for name, x, y in (("A", "0", "0"), ("B", "6", "0"), ("C", "2", "4")):
        figure.add_node(
            Node(
                id=name,
                kind=POINT,
                role=FREE,
                coords=(f"x_{name}", f"y_{name}"),
                placement=(x, y),
                label=name,
            )
        )
    figure.add_node(Node(id="BC", kind=SEGMENT, role=DERIVED, op="segment.free", args=["B", "C"]))
    figure.add_node(Node(id="O", kind=CIRCLE, role=DERIVED, op="circle.through", args=["A", "B", "C"]))
    figure.add_node(Node(id="D", kind=POINT, role=DERIVED, op="point.foot", args=["A", "BC"]))
    figure.add_node(Node(id="AD", kind=LINE, role=DERIVED, op="line.free", args=["A", "D"]))
    return figure


def _evaluate(figure: Figure) -> Figure:
    registry = _registry()
    evaluate_figure(figure, registry)
    return figure


@pytest.mark.slow
def test_the_other_intersection_works_when_the_known_point_is_at_the_base() -> None:
    """Regression: the known point sat at the base of the parameterisation.

    The line AD passes through the origin, so the point A known to lie on
    the circle is also the base of the line's parameterisation -- the
    parameter of A is zero.

    The two roots of the quadratic satisfy ``t1 + t2 = -quad_b / quad_a``,
    so the other root follows by *subtraction*. The earlier form used the
    product (``t1 * t2 = quad_c / quad_a``), which divides by the known
    root; when that root is zero the answer was ``0 / 0`` and the operator
    silently returned NaN.
    """
    figure = _figure_with_a_line_through_the_origin()
    figure.add_node(
        Node(
            id="P",
            kind=POINT,
            role=DERIVED,
            op="point.intersect_line_circle",
            args=["AD", "O", "other"],
        )
    )
    evaluate_figure(figure, _registry())

    placement = figure.nodes["P"].placement
    assert placement is not None
    # The circle through A(0,0), B(6,0), C(2,4) has centre (3,1) and
    # r^2 = 10; the line AD is y = x, so the second intersection is (4,4):
    # (4-3)^2 + (4-1)^2 = 10.
    assert placement == ("4", "4")


def test_the_two_indices_are_the_two_different_intersections() -> None:
    """Index 0 and index 1 must be the two roots, and they must differ."""
    placements = []
    for index in ("0", "1"):
        figure = _figure_with_a_line_through_the_origin()
        figure.add_node(
            Node(
                id="P",
                kind=POINT,
                role=DERIVED,
                op="point.intersect_line_circle",
                args=["AD", "O", index],
            )
        )
        evaluate_figure(figure, _registry())
        placement = figure.nodes["P"].placement
        assert placement is not None
        placements.append(placement)
    assert placements[0] != placements[1]
    # One of them is the known point A itself.
    assert ("0", "0") in placements


@pytest.mark.slow
def test_the_other_intersection_agrees_with_one_of_the_indices() -> None:
    """"Other" must be one of the two indexed roots -- not a third point."""
    points = []
    for selector in ("0", "1", "other"):
        figure = _figure_with_a_line_through_the_origin()
        figure.add_node(
            Node(
                id="P",
                kind=POINT,
                role=DERIVED,
                op="point.intersect_line_circle",
                args=["AD", "O", selector],
            )
        )
        evaluate_figure(figure, _registry())
        placement = figure.nodes["P"].placement
        assert placement is not None
        points.append(placement)
    assert points[2] in points[:2]


@pytest.mark.slow
def test_the_other_intersection_needs_a_known_point_on_the_circle() -> None:
    """Without a known point on the circle, "other" is ambiguous -- not a guess."""
    figure = Figure(id="fig_ambiguous")
    for name, x, y in (("X", "0", "0"), ("Y", "4", "0"), ("Z", "2", "4")):
        figure.add_node(
            Node(
                id=name,
                kind=POINT,
                role=FREE,
                coords=(f"x_{name}", f"y_{name}"),
                placement=(x, y),
            )
        )
    figure.add_node(Node(id="O", kind=CIRCLE, role=DERIVED, op="circle.through", args=["X", "Y", "Z"]))
    # The line is built from two points that are *not* on the circle.
    for name, x, y in (("P1", "0", "8"), ("P2", "6", "8")):
        figure.add_node(
            Node(
                id=name,
                kind=POINT,
                role=FREE,
                coords=(f"x_{name}", f"y_{name}"),
                placement=(x, y),
            )
        )
    figure.add_node(Node(id="l1", kind=LINE, role=DERIVED, op="line.free", args=["P1", "P2"]))
    figure.add_node(
        Node(
            id="P",
            kind=POINT,
            role=DERIVED,
            op="point.intersect_line_circle",
            args=["l1", "O", "other"],
        )
    )
    try:
        evaluate_figure(figure, _registry())
    except AmbiguousIntersectionError:
        return
    raise AssertionError("an ambiguous 'other intersection' must be refused")


@pytest.mark.slow
def test_a_tangent_line_has_no_second_point() -> None:
    """A tangent line meets the circle once; there is no 'other' point.

    GeoGebra's answer is that the object is *undefined*, not that the
    whole construction fails -- and so is ours (decision D19). The figure
    survives; the point does not.
    """
    figure = Figure(id="fig_tangent")
    for name, x, y in (("A", "0", "0"), ("B", "2", "0"), ("C", "1", "1")):
        figure.add_node(
            Node(
                id=name,
                kind=POINT,
                role=FREE,
                coords=(f"x_{name}", f"y_{name}"),
                placement=(x, y),
            )
        )
    figure.add_node(Node(id="O", kind=CIRCLE, role=DERIVED, op="circle.through", args=["A", "B", "C"]))
    # x = 0 is tangent to the circle at A.
    figure.add_node(Node(id="T", kind=POINT, role=FREE, coords=("x_T", "y_T"), placement=("0", "3")))
    figure.add_node(Node(id="l1", kind=LINE, role=DERIVED, op="line.free", args=["A", "T"]))
    figure.add_node(
        Node(
            id="P",
            kind=POINT,
            role=DERIVED,
            op="point.intersect_line_circle",
            args=["l1", "O", "other"],
        )
    )
    evaluate_figure(figure, _registry())
    undefined = undefined_nodes(figure)
    assert ("P", "discriminant") in undefined, (
        f"a tangent line must leave the point undefined, got {undefined}"
    )
    assert figure.nodes["P"].placement is None
