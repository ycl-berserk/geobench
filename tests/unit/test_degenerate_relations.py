"""A construction that produces nothing is not a counterexample.

This file holds the regression tests for the failure a teacher's own
problem found.  The problem was:

    in an acute triangle ABC with AB < AC, let O be the circumcentre and
    H the orthocentre, D the midpoint of BC; the line through D
    perpendicular to BC meets the line AH at P; E on AB with DE || AC and
    F on AC with DF || AB.  Prove that P, E and F are collinear.

The point P does not exist.  The line through D perpendicular to BC is
the perpendicular bisector of BC, and AH is the altitude from A, so AH
is perpendicular to BC as well: the two lines are parallel and never
meet.  AB < AC says precisely that they are *distinct* lines, which is
why P is not there.

The kernel used to answer "the relation does not hold" -- a refutation,
with a counterexample and all -- because the point it could not build
left a 0/0 in the expression, and a 0/0 is not zero.  A judge that
refutes a true theorem is worse than a judge that says nothing, so the
rule is now mechanical: **a counterexample must be an admissible
configuration** (docs/spec.md section 6.1), and a placement where the
construction has no value is not admissible.
"""

from __future__ import annotations

import time

import pytest
import sympy as sp

from geobench.dsl import parse_dsl
from geobench.evaluate import evaluate_figure, undefined_nodes
from geobench.field import FIELD
from geobench.judges import (
    IDENTITY,
    INSTANCE,
    PROVED,
    REFUTED,
    SUPPORTED,
    UNDECIDED,
    JudgeRegistry,
    judge_relation,
)
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry

#: The problem as it was written, in the kernel's own DSL.
PROBLEM = """
点 A(2,3) B(0,0) C(5,0)
O = 外心(A,B,C)
H = 垂心(A,B,C)
D = 中点(B,C)
bc = 直线(B,C)
d = 垂直(D, bc)
ah = 直线(A,H)
P = 交点(d, ah)
ab = 直线(A,B)
ac = 直线(A,C)
de = 平行(D, ac)
df = 平行(D, ab)
E = 交点(de, ab)
F = 交点(df, ac)
"""

#: The same problem with its point P put where it can exist: the foot of
#: the altitude from A.  Then the claim is the **nine-point circle** --
#: the midpoint of a side, the midpoints of the other two sides, and the
#: foot of the altitude all lie on one circle.
NINE_POINT_CIRCLE = """
点 A(2,3) B(0,0) C(5,0)
O = 外心(A,B,C)
H = 垂心(A,B,C)
D = 中点(B,C)
bc = 直线(B,C)
ah = 直线(A,H)
P = 垂足(A, bc)
ab = 直线(A,B)
ac = 直线(A,C)
de = 平行(D, ac)
df = 平行(D, ab)
E = 交点(de, ab)
F = 交点(df, ac)
"""


@pytest.fixture(scope="module")
def registry() -> OperatorRegistry:
    reg = OperatorRegistry()
    register_builtins(reg)
    return reg


@pytest.fixture(scope="module")
def judges() -> JudgeRegistry:
    return JudgeRegistry()


@pytest.fixture(scope="module")
def problem(registry: OperatorRegistry):
    """The problem's figure, evaluated."""
    return evaluate_figure(parse_dsl(PROBLEM), registry)


# -- the object that cannot exist ------------------------------------------


def test_the_point_that_cannot_exist_has_no_value(problem) -> None:
    """P is not a point that went missing: it never was one."""
    undefined = dict(undefined_nodes(problem))
    assert "P" in undefined, "the parallel lines should leave P without a value"
    assert "parallel" in undefined["P"]


def test_the_rest_of_the_figure_survives(problem) -> None:
    """One impossible object must not take the rest of the figure with it."""
    undefined = dict(undefined_nodes(problem))
    assert "E" not in undefined
    assert "F" not in undefined
    assert problem.node("E").coords is not None
    assert problem.node("F").coords is not None


def test_the_kernel_can_still_prove_why(problem, judges: JudgeRegistry) -> None:
    """The reason P is missing is itself a theorem, and the kernel proves it."""
    parallel = judge_relation(problem, "parallel", ["d", "ah"], judges, scope=IDENTITY)
    assert parallel.verdict == PROVED, parallel.evidence

    altitude = judge_relation(problem, "perpendicular", ["ah", "bc"], judges, scope=IDENTITY)
    assert altitude.verdict == PROVED, altitude.evidence


# -- the verdict -----------------------------------------------------------


def test_a_missing_object_is_never_a_counterexample(problem, judges: JudgeRegistry) -> None:
    """The claim about P, E and F cannot be refuted: P is not there.

    This is the regression.  The judge used to answer "refuted", with a
    counterexample whose value was a 0/0.
    """
    for scope in (IDENTITY, INSTANCE):
        verdict = judge_relation(problem, "collinear", ["P", "E", "F"], judges, scope=scope)
        assert verdict.verdict != REFUTED, verdict.evidence
        assert verdict.verdict == UNDECIDED, verdict.evidence
        assert verdict.witness is None


def test_the_verdict_says_why(problem, judges: JudgeRegistry) -> None:
    """'Cannot decide' is not enough; the teacher needs the reason."""
    verdict = judge_relation(problem, "collinear", ["P", "E", "F"], judges, scope=IDENTITY)
    assert "parallel" in verdict.evidence


# -- a degenerate placement, rather than an impossible construction -------


@pytest.fixture(scope="module")
def parallel_here(registry: OperatorRegistry):
    """Two lines that are parallel in this drawing, but not in general."""
    figure = evaluate_figure(
        parse_dsl(
            """
点 A(0,0) B(4,0) C(1,3) D(5,3)
l1 = 直线(A,B)
l2 = 直线(C,D)
P = 交点(l1,l2)
"""
        ),
        registry,
    )
    return figure


def test_a_degenerate_placement_has_no_value(parallel_here) -> None:
    """The intersection of two lines that are parallel *here* is undefined here."""
    undefined = dict(undefined_nodes(parallel_here))
    assert "P" in undefined


def test_a_degenerate_placement_is_not_a_counterexample(parallel_here, judges: JudgeRegistry) -> None:
    """The relation holds wherever it is defined; here it is not defined."""
    verdict = judge_relation(parallel_here, "collinear", ["A", "B", "P"], judges, scope=INSTANCE)
    assert verdict.verdict != REFUTED, verdict.evidence
    assert verdict.verdict == UNDECIDED, verdict.evidence


def test_the_identity_scope_survives_a_degenerate_placement(
    parallel_here, judges: JudgeRegistry
) -> None:
    """The theorem is about every placement, not about this one.

    P lies on AB wherever the two lines meet, so the relation is an
    identity -- and the identity does not care that *this* drawing has
    the two lines parallel.
    """
    verdict = judge_relation(parallel_here, "collinear", ["A", "B", "P"], judges, scope=IDENTITY)
    assert verdict.verdict == PROVED, verdict.evidence


# -- the same problem, with a point that can exist -------------------------


@pytest.fixture(scope="module")
def nine_point(registry: OperatorRegistry):
    """The same figure, with P where it can exist: the altitude's foot."""
    return evaluate_figure(parse_dsl(NINE_POINT_CIRCLE), registry)


def test_the_nine_point_circle_holds_for_the_drawn_figure(
    nine_point, judges: JudgeRegistry
) -> None:
    """D, E, F and the foot of the altitude lie on one circle.

    E and F are the midpoints of AB and AC (the midline theorem), so
    D, E, F are the three side midpoints; with the foot of the altitude
    they are four of the nine points of the nine-point circle.
    """
    verdict = judge_relation(nine_point, "concyclic", ["D", "E", "F", "P"], judges, scope=INSTANCE)
    assert verdict.verdict == PROVED, verdict.evidence


@pytest.mark.slow
def test_the_identity_proof_is_bounded(nine_point, judges: JudgeRegistry) -> None:
    """The identity scope gives up rather than taking half an hour.

    Clearing the denominators of this determinant produces hundreds of
    millions of terms -- more memory than the machine has.  Expanding it
    anyway is not a proof, it is an outage: the same expression was
    measured at 70 seconds, 19 minutes and 32 minutes on the same
    machine.  So the kernel says "holds in the samples, not proved",
    and says why.
    """
    verdict = judge_relation(nine_point, "concyclic", ["D", "E", "F", "P"], judges, scope=IDENTITY)
    assert verdict.verdict == SUPPORTED, verdict.evidence
    assert "budget" in verdict.evidence


def test_the_nine_point_circle_is_true_for_every_triangle(
    registry: OperatorRegistry, judges: JudgeRegistry
) -> None:
    """Not just for the triangle that was drawn.

    The *identity* scope does not depend on the placement, so the
    interesting check here is the drawn configuration: the same four
    points, in four different triangles.
    """
    for ax, ay, cx in ((2, 3, 5), (1, 3, 5), (3, 2, 6), (-1, 4, 5)):
        dsl = NINE_POINT_CIRCLE.replace("A(2,3)", f"A({ax},{ay})").replace("C(5,0)", f"C({cx},0)")
        figure = evaluate_figure(parse_dsl(dsl), registry)
        verdict = judge_relation(figure, "concyclic", ["D", "E", "F", "P"], judges, scope=INSTANCE)
        assert verdict.verdict == PROVED, (f"A({ax},{ay}) C({cx},0): {verdict.evidence}")


def test_the_nine_point_circle_has_no_missing_object(nine_point) -> None:
    """Every object in it has a value, so nothing is missing."""
    assert undefined_nodes(nine_point) == []


# -- the arithmetic underneath ---------------------------------------------


def test_a_quotient_by_nothing_is_not_the_zero_expression() -> None:
    """0/0 is not 0, and the kernel must not treat it as one."""
    x, y = sp.symbols("x y")
    # A divisor that vanishes identically without being literally zero.
    divisor = (x + y) * (x - y) - (x**2 - y**2)
    assert divisor != 0
    assert sp.simplify(divisor) == 0

    expression = (x + 1) / divisor
    assert FIELD.has_zero_divisor(expression)
    assert not FIELD.simplify_to_zero(expression)


def test_a_ratio_that_is_genuinely_zero_still_counts() -> None:
    """The guard must not swallow the relations that do hold."""
    x, y = sp.symbols("x y")
    zero_ratio = ((x + y) * (x - y) - (x**2 - y**2)) / (x - y)
    assert FIELD.simplify_to_zero(zero_ratio)
    assert not FIELD.has_zero_divisor(zero_ratio)


def test_the_zero_test_answers_completely() -> None:
    """For a rational function, 'is this zero' is a decision, not a search."""
    x, y = sp.symbols("x y")
    assert FIELD.zero_status(sp.Integer(0)) is True
    assert FIELD.zero_status(x - x) is True
    assert FIELD.zero_status(x) is False
    assert FIELD.zero_status((x + 1) / (x - y)) is False
    # Something that is not a rational function of its symbols: the
    # honest answer is "I do not know".
    assert FIELD.zero_status(sp.sin(x) ** 2 + sp.cos(x) ** 2 - 1) is None


def test_an_enormous_expansion_is_refused_before_it_is_attempted() -> None:
    """The budget is about the *expansion*, not the expression.

    A determinant cleared of its denominators is a few hundred
    operations long and expands to hundreds of millions of terms.  The
    size of the expression says nothing about what expanding it costs,
    so the budget counts terms -- and it refuses before the work starts.
    """
    x, y = sp.symbols("x y")
    huge = sp.prod((x + index * y) ** 40 for index in range(1, 12))
    assert sp.count_ops(huge) < FIELD.identity_budget_ops, "the fixture should be small"
    assert FIELD.expansion_size(huge) > FIELD.expand_term_budget

    start = time.perf_counter()
    assert not FIELD.simplify_to_zero(huge)
    elapsed = time.perf_counter() - start
    assert elapsed < 5.0, f"refusing the expansion took {elapsed:.1f} s"
