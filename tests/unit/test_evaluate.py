"""The two evaluation paths.

The exact path answers "what is this, for every admissible placement";
the numeric path answers "where is it on screen, right now". They are
separate because a product that feels like a drawing tool has to be
fast, and a product that proves things has to be exact -- and the two
requirements do not have to be met by the same computation.

What these tests pin down:

- moving a free point does **not** invalidate the exact expressions
  (they do not depend on the placement);
- the numeric path follows the placement;
- the two paths agree;
- a degenerate configuration leaves one object undefined and the rest of
  the figure intact.
"""

from __future__ import annotations

from geobench.evaluate import (
    evaluate_exact,
    evaluate_numeric,
    numeric_coords,
    undefined_nodes,
)
from geobench.model import CIRCLE, DERIVED, FREE, LINE, POINT, SEGMENT, Figure, Node
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry


def _registry() -> OperatorRegistry:
    registry = OperatorRegistry()
    register_builtins(registry)
    return registry


def _triangle() -> Figure:
    figure = Figure(id="fig_eval")
    for name, x, y in (("A", "0", "0"), ("B", "6", "0"), ("C", "2", "4")):
        figure.add_node(
            Node(
                id=name,
                kind=POINT,
                role=FREE,
                coords=(f"x_{name}", f"y_{name}"),
                placement=(x, y),
            )
        )
    figure.add_node(Node(id="BC", kind=SEGMENT, role=DERIVED, op="segment.free", args=["B", "C"]))
    figure.add_node(Node(id="O", kind=CIRCLE, role=DERIVED, op="circle.through", args=["A", "B", "C"]))
    figure.add_node(Node(id="D", kind=POINT, role=DERIVED, op="point.foot", args=["A", "BC"]))
    figure.add_node(Node(id="M", kind=POINT, role=DERIVED, op="point.midpoint", args=["A", "B"]))
    return figure


def test_the_exact_path_produces_symbolic_expressions() -> None:
    figure = _triangle()
    evaluate_exact(figure, _registry())
    assert figure.nodes["M"].coords == ("x_A/2 + x_B/2", "y_A/2 + y_B/2")


def test_the_numeric_path_produces_the_placement() -> None:
    figure = _triangle()
    evaluate_exact(figure, _registry())
    evaluate_numeric(figure)
    assert figure.nodes["M"].placement == ("3", "0")
    assert figure.nodes["D"].placement == ("3", "3")


def test_moving_a_point_does_not_invalidate_the_exact_expressions() -> None:
    """The expression of a midpoint does not depend on where A is.

    This is the fact the whole split rests on: dragging a point must
    not cost an algebraic evaluation.
    """
    figure = _triangle()
    evaluate_exact(figure, _registry())
    before = figure.nodes["M"].coords

    figure.nodes["A"].placement = ("1", "2")
    evaluate_exact(figure, _registry())

    assert figure.nodes["M"].coords == before


def test_the_numeric_path_follows_the_placement() -> None:
    figure = _triangle()
    evaluate_exact(figure, _registry())
    evaluate_numeric(figure)
    assert figure.nodes["M"].placement == ("3", "0")

    figure.nodes["A"].placement = ("1", "2")
    evaluate_numeric(figure)
    assert figure.nodes["M"].placement == ("3.5", "1")


def test_the_two_paths_agree() -> None:
    """The numeric placement is the exact expression, evaluated."""
    figure = _triangle()
    evaluate_exact(figure, _registry())
    evaluate_numeric(figure)
    x, y = numeric_coords(figure, "M")
    assert abs(x - 3.0) < 1e-9
    assert abs(y - 0.0) < 1e-9


def test_a_degenerate_object_is_undefined_and_the_rest_survives() -> None:
    """Three collinear points have no circumcircle; the figure stays.

    GeoGebra calls this state "undefined" and so do we (decision D19):
    the object that has no value is marked, and everything else is still
    drawn.
    """
    figure = Figure(id="fig_degenerate")
    for name, x, y in (("A", "0", "0"), ("B", "4", "0"), ("C", "8", "0")):
        figure.add_node(
            Node(
                id=name,
                kind=POINT,
                role=FREE,
                coords=(f"x_{name}", f"y_{name}"),
                placement=(x, y),
            )
        )
    figure.add_node(
        Node(id="O", kind=CIRCLE, role=DERIVED, op="circle.through", args=["A", "B", "C"])
    )
    evaluate_exact(figure, _registry())
    evaluate_numeric(figure)

    undefined = undefined_nodes(figure)
    assert [node_id for node_id, _ in undefined] == ["O"]
    assert figure.nodes["O"].placement is None
    # The points are untouched: the figure is still a figure.
    assert figure.nodes["A"].placement == ("0", "0")


def test_an_illegal_construction_is_still_refused() -> None:
    """Two identical points have no midpoint -- that is a mistake, not a state."""
    figure = Figure(id="fig_illegal")
    figure.add_node(
        Node(
            id="A",
            kind=POINT,
            role=FREE,
            coords=("x_A", "y_A"),
            placement=("0", "0"),
        )
    )
    figure.add_node(
        Node(
            id="M",
            kind=POINT,
            role=DERIVED,
            op="point.midpoint",
            args=["A", "A"],
        )
    )
    try:
        evaluate_exact(figure, _registry())
    except Exception as exc:
        assert "midpoint" in str(exc)
        return
    raise AssertionError("the midpoint of a point with itself must be refused")


def test_a_copy_keeps_the_cached_expressions() -> None:
    """A copy is the same construction, so its cache is still valid."""
    figure = _triangle()
    evaluate_exact(figure, _registry())
    clone = figure.copy()
    assert clone.nodes["M"].coords == figure.nodes["M"].coords
    assert "signature" in clone.nodes["M"].cache


def test_a_changed_input_is_recomputed() -> None:
    """The incrementality must not hide a real change."""
    figure = _triangle()
    evaluate_exact(figure, _registry())
    figure.nodes["M"].args = ["A", "C"]
    evaluate_exact(figure, _registry())
    assert figure.nodes["M"].coords == ("x_A/2 + x_C/2", "y_A/2 + y_C/2")


def test_a_new_object_is_computed() -> None:
    figure = _triangle()
    evaluate_exact(figure, _registry())
    figure.add_node(
        Node(id="N", kind=POINT, role=DERIVED, op="point.midpoint", args=["B", "C"])
    )
    evaluate_exact(figure, _registry())
    assert figure.nodes["N"].coords == ("x_B/2 + x_C/2", "y_B/2 + y_C/2")


def test_a_line_and_a_circle_get_numeric_payloads() -> None:
    from geobench.evaluate import numeric_circle, numeric_line, numeric_segment

    figure = _triangle()
    figure.add_node(
        Node(id="l1", kind=LINE, role=DERIVED, op="line.free", args=["B", "C"])
    )
    evaluate_exact(figure, _registry())
    evaluate_numeric(figure)

    a, b, c = numeric_line(figure, "l1")
    # A line is defined up to a non-zero factor, so check the equation
    # rather than the coefficients: B(6,0) and C(2,4) must satisfy it.
    for px, py in ((6.0, 0.0), (2.0, 4.0)):
        assert abs(a * px + b * py + c) < 1e-9

    x1, y1, x2, y2 = numeric_segment(figure, "BC")
    assert (round(x1, 9), round(y1, 9), round(x2, 9), round(y2, 9)) == (6, 0, 2, 4)

    cx, cy, r2 = numeric_circle(figure, "O")
    assert abs(cx - 3.0) < 1e-9
    assert abs(cy - 1.0) < 1e-9
    assert abs(r2 - 10.0) < 1e-9
