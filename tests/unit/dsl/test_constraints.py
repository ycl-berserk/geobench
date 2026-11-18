"""Solving for coordinates: exact answers, and honest refusals.

The solver exists for the condition that is a *system*: three lengths, a
right angle, a midpoint at once.  A single condition usually has a
better answer as a construction (a rotation carries an angle exactly; a
point on a circle is what "AB = AC" means), and the skill says so.

What matters here is the **contract** (spec section 8): the answer is
numeric first, then rationalised, then **checked exactly**.  A solution
that does not survive the exact check is refused, not returned with a
warning -- because a coordinate is a fact about the paper, and a
coordinate that is nearly right is a figure that is nearly the problem.
"""

from __future__ import annotations

import pytest
import sympy as sp

from geobench.dsl import parse_dsl
from geobench.dsl.errors import DSLParseError
from geobench.evaluate import evaluate_figure
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry


@pytest.fixture(scope="module")
def registry() -> OperatorRegistry:
    reg = OperatorRegistry()
    register_builtins(reg)
    return reg


def _placements(source: str, registry: OperatorRegistry) -> dict[str, str]:
    figure = parse_dsl(source)
    evaluate_figure(figure, registry)
    return {
        node_id: f"({node.placement[0]}, {node.placement[1]})"
        for node_id, node in figure.nodes.items()
        if node.kind == "point" and node.placement is not None
    }


# -- exact answers ----------------------------------------------------------


def test_two_lengths_are_solved_exactly(registry: OperatorRegistry) -> None:
    """A 3-4-5 right triangle, found from a rough sketch."""
    placements = _placements(
        """
点 A(0,0) B(5,0) C(1,1)
约束 距离(A, C) = 3
约束 距离(B, C) = 4
""",
        registry,
    )
    assert placements["C"] == ("(9/5, 12/5)")
    assert placements["A"] == ("(0, 0)")
    assert placements["B"] == ("(5, 0)")


def test_a_root_is_written_as_a_root(registry: OperatorRegistry) -> None:
    """Three sides 5, 6, 7: the height is 12*sqrt(6)/5, and it stays exact."""
    placements = _placements(
        """
点 A(0,0) B(5,0) C(2,3)
约束 长度(AB) = 5
约束 长度(AC) = 6
约束 长度(BC) = 7
AB = 线段(A, B)
AC = 线段(A, C)
BC = 线段(B, C)
""",
        registry,
    )
    assert placements["C"] == "(6/5, 12*sqrt(6)/5)"


def test_a_judgement_can_be_a_constraint(registry: OperatorRegistry) -> None:
    """垂直 is the good way to say "a right angle": it is polynomial."""
    placements = _placements(
        """
点 A(0,0) B(5,0) C(1,1)
AB = 线段(A, B)
AC = 线段(A, C)
约束 垂直(AB, AC)
""",
        registry,
    )
    assert placements["C"] == ("(0, 1)")


def test_the_frame_stays_where_it_was(registry: OperatorRegistry) -> None:
    """|AC| = 3 does not care whether A or C moves; the frame wins."""
    placements = _placements(
        """
点 A(0,0) B(5,0) C(1,1)
约束 距离(A, C) = 3
约束 距离(B, C) = 4
""",
        registry,
    )
    assert placements["A"] == ("(0, 0)")
    assert placements["B"] == ("(5, 0)")


def test_a_satisfied_constraint_moves_nothing(registry: OperatorRegistry) -> None:
    placements = _placements(
        """
点 A(0,0) B(5,0) C(3,4)
约束 距离(A, C) = 5
""",
        registry,
    )
    assert placements["C"] == ("(3, 4)")


def test_the_report_says_what_moved(registry: OperatorRegistry) -> None:
    figure = parse_dsl(
        """
点 A(0,0) B(5,0) C(1,1)
约束 距离(A, C) = 3
约束 距离(B, C) = 4
"""
    )
    evaluate_figure(figure, registry)
    solution = figure.runtime["solution"]
    assert solution["moved"] == ["C"]
    assert solution["degrees_of_freedom"] == 0


# -- honest refusals --------------------------------------------------------


def test_a_transcendental_point_is_refused(registry: OperatorRegistry) -> None:
    """A 40-degree apex has no exact coordinate -- say so, do not round."""
    with pytest.raises(DSLParseError) as failure:
        parse_dsl(
            """
点 A(0,0) B(5,0) C(2,4)
约束 角度(B, A, C) = 40
"""
        )
    message = str(failure.value)
    assert "精确" in message, message
    # The refusal points at the tool that *can* draw it.
    assert "旋转" in message or "位似" in message, message


def test_a_constraint_that_cannot_be_solved_says_so(registry: OperatorRegistry) -> None:
    with pytest.raises(DSLParseError) as failure:
        parse_dsl(
            """
点 A(0,0) B(5,0) C(1,1)
约束 距离(A, C) = 3
约束 距离(B, C) = 100
"""
        )
    assert "解不出来" in str(failure.value) or "精确" in str(failure.value)


def test_a_constraint_needs_objects_that_exist(registry: OperatorRegistry) -> None:
    with pytest.raises(DSLParseError):
        parse_dsl(
            """
点 A(0,0) B(5,0)
约束 距离(A, Z) = 3
"""
        )


def test_a_measure_is_not_a_condition_on_its_own() -> None:
    """``约束 长度(AB)`` says nothing: a length is not a claim."""
    with pytest.raises(DSLParseError) as failure:
        parse_dsl(
            """
点 A(0,0) B(5,0)
AB = 线段(A, B)
约束 长度(AB)
"""
        )
    assert "不是一个条件" in str(failure.value)


def test_a_constraint_may_come_before_its_objects(registry: OperatorRegistry) -> None:
    """The script is solved after it is read, not line by line."""
    placements = _placements(
        """
点 A(0,0) B(5,0) C(1,1)
约束 垂直(AB, AC)
AB = 线段(A, B)
AC = 线段(A, C)
""",
        registry,
    )
    assert placements["C"] == ("(0, 1)")


def test_the_solution_is_exact_not_rounded(registry: OperatorRegistry) -> None:
    """The placements are exact expressions, so the exact path still works."""
    figure = parse_dsl(
        """
点 A(0,0) B(5,0) C(2,3)
约束 长度(AB) = 5
约束 长度(AC) = 6
约束 长度(BC) = 7
AB = 线段(A, B)
AC = 线段(A, C)
BC = 线段(B, C)
"""
    )
    evaluate_figure(figure, registry)
    placement = figure.nodes["C"].placement
    assert placement is not None
    assert placement[0] == "6/5"
    assert sp.simplify(sp.sympify(placement[1]) - 12 * sp.sqrt(6) / 5) == 0
