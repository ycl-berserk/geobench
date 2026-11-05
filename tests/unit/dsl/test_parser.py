"""The DSL parser: what it accepts, and what it refuses."""

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
    figure = parse_dsl("点 A(0,0) B(4,0) C(2,4)\n△ABC\nD = BC 上 A 的垂足")
    assert figure.node("D").op == "point.foot"
    assert figure.node("D").kind == "point"


def test_midpoint_is_built() -> None:
    figure = parse_dsl("点 A(0,0) B(4,0)\nE = AB 中点")
    assert figure.node("E").op == "point.midpoint"
    assert figure.node("E").args == ["A", "B"]


def test_triangle_centre_points_are_built() -> None:
    source = "点 A(0,0) B(4,0) C(2,4)\nI = △ABC 的内心\nO = △ABC 的外心\nH = △ABC 的垂心\nG = △ABC 的重心"
    figure = parse_dsl(source)
    assert figure.node("I").op == "point.incenter"
    assert figure.node("O").op == "point.circumcenter"
    assert figure.node("H").op == "point.orthocenter"
    assert figure.node("G").op == "point.centroid"


def test_circle_through_three_points() -> None:
    figure = parse_dsl("点 A(0,0) B(4,0) C(2,4)\n⊙O = 过 A B C")
    assert figure.node("O").op == "circle.through"
    assert figure.node("O").kind == "circle"


def test_circle_with_centre_and_radius() -> None:
    figure = parse_dsl("点 A(0,0)\n⊙O = 以 A 为圆心 半径 2")
    assert figure.node("O").op == "circle.free"
    assert figure.node("O").args == ["A", "2"]


def test_perpendicular_and_parallel_lines() -> None:
    source = "点 A(0,0) B(4,0) C(2,4)\nk = 过 A 的 BC 的垂线\nm = 过 A 的 BC 的平行线"
    figure = parse_dsl(source)
    assert figure.node("k").op == "line.perpendicular_through"
    assert figure.node("m").op == "line.parallel_through"


def test_intersection_of_two_lines() -> None:
    source = "点 A(0,0) B(4,0) C(2,4)\nP = AB 与 CA 的交点"
    figure = parse_dsl(source)
    assert figure.node("P").op == "point.intersect_lines"


def test_intersection_with_a_circle() -> None:
    source = "点 A(0,0) B(4,0) C(2,4)\n⊙O = 过 A B C\nP = AB 与 ⊙O 的交点"
    figure = parse_dsl(source)
    assert figure.node("P").op == "point.intersect_line_circle"


def test_the_other_intersection_uses_the_reference_point() -> None:
    source = "点 A(0,0) B(4,0) C(2,4)\n⊙O = 过 A B C\nP = AB 与 ⊙O 的另一交点"
    figure = parse_dsl(source)
    assert figure.node("P").op == "point.intersect_line_circle"


def test_assertions_become_relations() -> None:
    source = (
        "点 A(0,0) B(4,0) C(2,4) D(1,1)\n△ABC\n"
        "断言 A B C 共线\n"
        "断言 A B C D 共圆\n"
        "断言 AB = AC\n"
        "断言 AB ⊥ AC\n"
    )
    figure = parse_dsl(source)
    kinds = [relation.kind for relation in figure.relations]
    assert kinds == ["collinear", "concyclic", "equal_length", "perpendicular"]


def test_a_parsed_figure_evaluates(registry: OperatorRegistry) -> None:
    source = "点 A(0,0) B(6,0) C(2,4)\n△ABC\nD = BC 上 A 的垂足\nM = AB 中点"
    figure = parse_dsl(source)
    evaluate_figure(figure, registry)
    assert figure.node("M").placement == ("3", "0")
    assert figure.node("D").placement is not None


# -- refusals --------------------------------------------------------------


def test_unknown_object_is_refused() -> None:
    with pytest.raises(DSLParseError) as excinfo:
        parse_dsl("点 A(0,0)\nD = BC 上 A 的垂足")
    assert "未定义" in str(excinfo.value)


def test_unknown_clause_is_refused_with_a_position() -> None:
    with pytest.raises(DSLParseError) as excinfo:
        parse_dsl("点 A(0,0) B(1,1)\nD = AB 的某种神秘构造")
    assert excinfo.value.span.line == 2
    assert excinfo.value.span.col > 0


def test_missing_coordinate_is_refused() -> None:
    with pytest.raises(DSLParseError):
        parse_dsl("点 A(0)")


def test_unknown_statement_is_refused() -> None:
    with pytest.raises(DSLParseError):
        parse_dsl("随便写点什么")


def test_unsupported_relation_is_refused() -> None:
    with pytest.raises(DSLParseError) as excinfo:
        parse_dsl("点 A(0,0) B(4,0)\n断言 AB ∥ AB")
    assert "尚未实现" in str(excinfo.value)


def test_error_message_points_at_the_problem() -> None:
    with pytest.raises(DSLParseError) as excinfo:
        parse_dsl("点 A(0,0) B(4,0)\nD = AB 中点\nE = XY 中点")
    message = str(excinfo.value)
    assert "第 3 行" in message


# -- round trip ------------------------------------------------------------


def test_round_trip_preserves_the_figure() -> None:
    source = "点 A(0,0) B(6,0) C(2,4)\n△ABC\nD = BC 上 A 的垂足\nM = AB 中点"
    figure = parse_dsl(source)
    text = to_dsl(figure)
    again = parse_dsl(text)
    assert set(again.nodes) == set(figure.nodes)
    assert {relation.kind for relation in again.relations} == {
        relation.kind for relation in figure.relations
    }
