"""The DSL parser: what it accepts, and what it refuses.

The syntax is function-call with GeoGebra's Chinese command names
(decision D17), and GeoGebra's English names work too -- a teacher who
types ``Midpoint(A,B)`` in GeoGebra types the same thing here.
"""

from __future__ import annotations

import pytest

from geobench.dsl import DSLParseError, parse_dsl, to_dsl
from geobench.evaluate import evaluate_figure
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry


@pytest.fixture(scope="module")
def registry() -> OperatorRegistry:
    reg = OperatorRegistry()
    register_builtins(reg)
    return reg


def test_points_are_declared() -> None:
    figure = parse_dsl("点 A(0,0) B(4,0) C(2,4)")
    assert set(figure.nodes) == {"A", "B", "C"}
    assert figure.node("B").placement == ("4", "0")
    assert figure.node("C").coords == ("x_C", "y_C")


def test_triangle_creates_three_sides() -> None:
    figure = parse_dsl("点 A(0,0) B(4,0) C(2,4)\n△ABC")
    assert {"AB", "BC", "CA"} <= set(figure.nodes)
    assert figure.node("BC").kind == "segment"
    assert figure.node("BC").args == ["B", "C"]


def test_foot_is_built() -> None:
    figure = parse_dsl("点 A(0,0) B(4,0) C(2,4)\n△ABC\nD = 垂足(A,BC)")
    assert figure.node("D").op == "point.foot"
    assert figure.node("D").kind == "point"
    assert figure.node("D").args == ["A", "BC"]


def test_midpoint_is_built() -> None:
    figure = parse_dsl("点 A(0,0) B(4,0)\nE = 中点(A,B)")
    assert figure.node("E").op == "point.midpoint"
    assert figure.node("E").args == ["A", "B"]


def test_triangle_centre_points_are_built() -> None:
    source = (
        "点 A(0,0) B(4,0) C(2,4)\n"
        "I = 内心(A,B,C)\nO = 外心(A,B,C)\nH = 垂心(A,B,C)\nG = 重心(A,B,C)"
    )
    figure = parse_dsl(source)
    assert figure.node("I").op == "point.incenter"
    assert figure.node("O").op == "point.circumcenter"
    assert figure.node("H").op == "point.orthocenter"
    assert figure.node("G").op == "point.centroid"


def test_circle_through_three_points() -> None:
    figure = parse_dsl("点 A(0,0) B(4,0) C(2,4)\nO = 外接圆(A,B,C)")
    assert figure.node("O").op == "circle.through"
    assert figure.node("O").kind == "circle"


def test_circle_with_centre_and_radius() -> None:
    figure = parse_dsl("点 A(0,0)\nO = 圆(A,2)")
    assert figure.node("O").op == "circle.free"
    assert figure.node("O").args == ["A", "2"]


def test_perpendicular_and_parallel_lines() -> None:
    source = "点 A(0,0) B(4,0) C(2,4)\nk = 垂直(A,BC)\nm = 平行(A,BC)"
    figure = parse_dsl(source)
    assert figure.node("k").op == "line.perpendicular_through"
    assert figure.node("m").op == "line.parallel_through"


def test_intersection_of_two_lines() -> None:
    source = "点 A(0,0) B(4,0) C(2,4)\nP = 交点(AB,CA)"
    figure = parse_dsl(source)
    assert figure.node("P").op == "point.intersect_lines"


def test_intersection_with_a_circle() -> None:
    source = "点 A(0,0) B(4,0) C(2,4)\nO = 外接圆(A,B,C)\nP = 交点(AB,O,第一交点)"
    figure = parse_dsl(source)
    assert figure.node("P").op == "point.intersect_line_circle"


def test_the_other_intersection_uses_the_reference_point() -> None:
    source = "点 A(0,0) B(4,0) C(2,4)\nO = 外接圆(A,B,C)\nP = 交点(AB,O,另一交点)"
    figure = parse_dsl(source)
    assert figure.node("P").op == "point.intersect_line_circle"
    assert figure.node("P").args == ["AB", "O", "other"]


def test_assertions_become_relations() -> None:
    source = (
        "点 A(0,0) B(4,0) C(2,4) D(1,1)\n△ABC\n"
        "断言 共线(A,B,C)\n"
        "断言 共圆(A,B,C,D)\n"
        "断言 相等(AB,AC)\n"
    )
    figure = parse_dsl(source)
    kinds = [relation.kind for relation in figure.relations]
    assert kinds == ["collinear", "concyclic", "equal_length"]


def test_a_relation_about_two_segments_becomes_four_points() -> None:
    """``断言 相等(AB,AC)`` is how a paper writes it; the relation is
    about A, B, A and C."""
    figure = parse_dsl("点 A(0,0) B(4,0) C(2,4)\n断言 相等(AB,AC)")
    assert figure.relations[0].kind == "equal_length"
    assert figure.relations[0].args == ["A", "B", "A", "C"]


def test_the_new_line_commands_are_built() -> None:
    source = (
        "点 A(0,0) B(6,0) C(2,4)\n"
        "m = 中垂线(A,B)\n"
        "b = 角平分线(A,B,C)\n"
        "O = 外接圆(A,B,C)\n"
        "t = 切线(A,O)\n"
    )
    figure = parse_dsl(source)
    assert figure.node("m").op == "line.perpendicular_bisector"
    assert figure.node("b").op == "line.angle_bisector"
    assert figure.node("t").op == "line.tangent"
    assert figure.node("t").args == ["A", "O"]


def test_a_polygon_takes_any_number_of_vertices() -> None:
    """A polygon is three or four or five vertices; the contract says so."""
    figure = parse_dsl("点 A(0,0) B(6,0) C(2,4)\nP = 多边形(A,B,C)")
    assert figure.node("P").op == "polygon.free"
    assert figure.node("P").kind == "polygon"
    figure = parse_dsl("点 A(0,0) B(6,0) C(2,4) D(5,5)\nP = 多边形(A,B,C,D)")
    assert figure.node("P").args == ["A", "B", "C", "D"]


def test_a_parsed_figure_evaluates(registry: OperatorRegistry) -> None:
    source = "点 A(0,0) B(6,0) C(2,4)\n△ABC\nD = 垂足(A,BC)\nM = 中点(A,B)"
    figure = parse_dsl(source)
    evaluate_figure(figure, registry)
    assert figure.node("M").placement == ("3", "0")
    assert figure.node("D").placement is not None


# -- the English names work too --------------------------------------------


def test_the_english_command_names_work() -> None:
    """GeoGebra's input bar accepts English in every language, so ours does."""
    source = (
        "Point A(0,0) B(6,0) C(2,4)\n"
        "M=Midpoint(A,B)\n"
        "O=Circumcircle(A,B,C)\n"
        "AreCollinear(A,M,B)\n"
    )
    figure = parse_dsl(source)
    assert figure.node("M").op == "point.midpoint"
    assert figure.node("O").op == "circle.through"
    assert figure.relations[0].kind == "collinear"


def test_the_two_languages_mean_the_same_thing() -> None:
    chinese = parse_dsl("点 A(0,0) B(6,0)\nM = 中点(A,B)")
    english = parse_dsl("Point A(0,0) B(6,0)\nM=Midpoint(A,B)")
    assert chinese.node("M").op == english.node("M").op
    assert chinese.node("M").args == english.node("M").args


def test_an_overloaded_name_is_resolved_by_the_arguments() -> None:
    """``交点`` is line-line, line-circle or circle-circle."""
    source = (
        "点 A(0,0) B(4,0) C(2,4)\n"
        "O = 外接圆(A,B,C)\n"
        "P = 交点(AB,CA)\n"
        "Q = 交点(AB,O,第一交点)\n"
    )
    figure = parse_dsl(source)
    assert figure.node("P").op == "point.intersect_lines"
    assert figure.node("Q").op == "point.intersect_line_circle"


# -- refusals --------------------------------------------------------------


def test_unknown_object_is_refused() -> None:
    with pytest.raises(DSLParseError) as excinfo:
        parse_dsl("点 A(0,0)\nD = 垂足(A,BC)")
    assert "未定义" in str(excinfo.value)


def test_unknown_command_is_refused_with_a_position() -> None:
    with pytest.raises(DSLParseError) as excinfo:
        parse_dsl("点 A(0,0) B(1,1)\nD = 某种神秘构造(A,B)")
    assert excinfo.value.span.line == 2
    assert excinfo.value.span.col > 0


def test_missing_coordinate_is_refused() -> None:
    with pytest.raises(DSLParseError):
        parse_dsl("点 A(0)")


def test_unknown_statement_is_refused() -> None:
    with pytest.raises(DSLParseError):
        parse_dsl("随便写点什么")


def test_unimplemented_command_is_refused() -> None:
    with pytest.raises(DSLParseError) as excinfo:
        parse_dsl("点 A(0,0) B(4,0)\nP = 区域内点(A,B)")
    assert "尚未实现" in str(excinfo.value)


def test_error_message_points_at_the_problem() -> None:
    with pytest.raises(DSLParseError) as excinfo:
        parse_dsl("点 A(0,0) B(4,0)\nD = 中点(A,B)\nE = 中点(X,Y)")
    message = str(excinfo.value)
    assert "第 3 行" in message


# -- round trip ------------------------------------------------------------


def test_round_trip_preserves_the_figure() -> None:
    source = "点 A(0,0) B(6,0) C(2,4)\n△ABC\nD = 垂足(A,BC)\nM = 中点(A,B)"
    figure = parse_dsl(source)
    text = to_dsl(figure)
    again = parse_dsl(text)
    assert set(again.nodes) == set(figure.nodes)
    assert {relation.kind for relation in again.relations} == {
        relation.kind for relation in figure.relations
    }
