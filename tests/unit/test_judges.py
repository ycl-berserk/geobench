"""Judges: the layer that decides whether a relation holds.

Two scopes, and the difference matters:

``IDENTITY``  the relation holds for *every* admissible placement of the free
              points -- this is what makes a relation a theorem rather than a
              coincidence of the drawn figure.
``INSTANCE``  the relation holds for the configuration as drawn.

Every judge needs a positive case *and* a counterexample case. A judge that
cannot refute a mutated figure is not trustworthy and does not ship
(docs/spec.md section 6.3).
"""

from __future__ import annotations

import pytest

from geobench.errors import StateError
from geobench.evaluate import evaluate_figure
from geobench.judges import (
    IDENTITY,
    INSTANCE,
    PROVED,
    REFUTED,
    SUPPORTED,
    JudgeRegistry,
    judge_relation,
)
from geobench.model import Figure, Node, Relation
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry


@pytest.fixture(scope="module")
def registry() -> OperatorRegistry:
    reg = OperatorRegistry()
    register_builtins(reg)
    return reg


@pytest.fixture(scope="module")
def judges() -> JudgeRegistry:
    return JudgeRegistry()


def _figure(points: dict[str, tuple[str, str]]) -> Figure:
    """A figure whose free points are symbolic but placed at the given coordinates."""
    figure = Figure(id="fig_judge")
    for node_id, (x, y) in points.items():
        figure.add_node(
            Node(
                id=node_id,
                kind="point",
                role="free",
                coords=(f"x_{node_id}", f"y_{node_id}"),
                placement=(x, y),
                label=node_id,
            )
        )
    return figure


def _derived(figure: Figure, node_id: str, kind: str, op: str, args: list[str], label: str | None = None) -> None:
    figure.add_node(
        Node(id=node_id, kind=kind, role="derived", op=op, args=args, label=label or node_id)
    )


# -- identity scope --------------------------------------------------------


def test_midpoint_is_proved_for_every_placement(registry: OperatorRegistry, judges: JudgeRegistry) -> None:
    """M is the midpoint of AB -- true for any A and B, not just the drawn ones."""
    figure = _figure({"A": ("0", "0"), "B": ("4", "0")})
    _derived(figure, "M", "point", "point.midpoint", ["A", "B"], "M")
    evaluate_figure(figure, registry)
    verdict = judge_relation(figure, "midpoint_of", ["M", "A", "B"], judges, scope=IDENTITY)
    assert verdict.verdict == PROVED, verdict.evidence
    assert verdict.scope == IDENTITY


def test_midpoint_is_equidistant_from_its_endpoints(registry: OperatorRegistry, judges: JudgeRegistry) -> None:
    figure = _figure({"A": ("0", "0"), "B": ("4", "0")})
    _derived(figure, "M", "point", "point.midpoint", ["A", "B"], "M")
    evaluate_figure(figure, registry)
    verdict = judge_relation(figure, "equal_length", ["M", "A", "M", "B"], judges, scope=IDENTITY)
    assert verdict.verdict == PROVED, verdict.evidence


def test_collinear_can_be_proved(registry: OperatorRegistry, judges: JudgeRegistry) -> None:
    """A, M, B are collinear because M is on AB -- an identity."""
    figure = _figure({"A": ("0", "0"), "B": ("4", "0")})
    _derived(figure, "M", "point", "point.midpoint", ["A", "B"], "M")
    evaluate_figure(figure, registry)
    verdict = judge_relation(figure, "collinear", ["A", "M", "B"], judges, scope=IDENTITY)
    assert verdict.verdict == PROVED, verdict.evidence


def test_three_free_points_are_not_collinear_in_general(
    registry: OperatorRegistry, judges: JudgeRegistry
) -> None:
    """Three unconstrained free points are *not* collinear -- the scope matters."""
    figure = _figure({"A": ("0", "0"), "B": ("4", "0"), "C": ("2", "3")})
    evaluate_figure(figure, registry)
    verdict = judge_relation(figure, "collinear", ["A", "B", "C"], judges, scope=IDENTITY)
    assert verdict.verdict == REFUTED
    assert verdict.witness is not None


def test_perpendicular_can_be_proved(registry: OperatorRegistry, judges: JudgeRegistry) -> None:
    """A line through A perpendicular to AB is perpendicular to AB by construction."""
    figure = _figure({"A": ("0", "0"), "B": ("4", "0")})
    _derived(figure, "l1", "line", "line.free", ["A", "B"], "AB")
    _derived(figure, "l2", "line", "line.perpendicular_through", ["A", "l1"], "l")
    evaluate_figure(figure, registry)
    verdict = judge_relation(figure, "perpendicular", ["l1", "l2"], judges, scope=IDENTITY)
    assert verdict.verdict == PROVED, verdict.evidence


@pytest.mark.slow
def test_concyclic_of_two_altitude_feet_is_proved(
    registry: OperatorRegistry, judges: JudgeRegistry
) -> None:
    """D (foot from A) and E (foot from B) both see AB at a right angle.

    So A, B, D, E lie on the circle with diameter AB -- an identity that
    holds for every triangle, not just the drawn one.
    """
    figure = _figure({"A": ("0", "0"), "B": ("6", "0"), "C": ("2", "4")})
    _derived(figure, "l1", "line", "line.free", ["B", "C"], "BC")
    _derived(figure, "l2", "line", "line.free", ["C", "A"], "CA")
    _derived(figure, "D", "point", "point.foot", ["A", "l1"], "D")
    _derived(figure, "E", "point", "point.foot", ["B", "l2"], "E")
    evaluate_figure(figure, registry)
    verdict = judge_relation(figure, "concyclic", ["A", "B", "D", "E"], judges, scope=IDENTITY)
    assert verdict.verdict == PROVED, verdict.evidence


def test_concyclic_claim_that_is_false_is_refuted(
    registry: OperatorRegistry, judges: JudgeRegistry
) -> None:
    """The same four points with a vertex swapped is *not* a circle."""
    figure = _figure({"A": ("0", "0"), "B": ("6", "0"), "C": ("2", "4")})
    _derived(figure, "l1", "line", "line.free", ["B", "C"], "BC")
    _derived(figure, "l2", "line", "line.free", ["C", "A"], "CA")
    _derived(figure, "D", "point", "point.foot", ["A", "l1"], "D")
    _derived(figure, "E", "point", "point.foot", ["B", "l2"], "E")
    evaluate_figure(figure, registry)
    verdict = judge_relation(figure, "concyclic", ["B", "D", "C", "E"], judges, scope=IDENTITY)
    assert verdict.verdict == REFUTED


# -- instance scope --------------------------------------------------------


def test_instance_scope_checks_the_drawn_configuration(
    registry: OperatorRegistry, judges: JudgeRegistry
) -> None:
    figure = _figure({"A": ("0", "0"), "B": ("4", "0"), "C": ("4", "3"), "D": ("0", "3")})
    evaluate_figure(figure, registry)
    verdict = judge_relation(figure, "concyclic", ["A", "B", "C", "D"], judges, scope=INSTANCE)
    assert verdict.verdict == PROVED, verdict.evidence
    assert verdict.scope == INSTANCE


def test_instance_scope_refutes_a_false_claim(registry: OperatorRegistry, judges: JudgeRegistry) -> None:
    figure = _figure({"A": ("0", "0"), "B": ("4", "0"), "C": ("4", "3"), "D": ("0", "5")})
    evaluate_figure(figure, registry)
    verdict = judge_relation(figure, "concyclic", ["A", "B", "C", "D"], judges, scope=INSTANCE)
    assert verdict.verdict == REFUTED


def test_equal_length_is_refuted_when_the_segments_differ(
    registry: OperatorRegistry, judges: JudgeRegistry
) -> None:
    figure = _figure({"A": ("0", "0"), "B": ("5", "0"), "C": ("0", "0"), "D": ("0", "4")})
    evaluate_figure(figure, registry)
    verdict = judge_relation(figure, "equal_length", ["A", "B", "C", "D"], judges, scope=INSTANCE)
    assert verdict.verdict == REFUTED


def test_midpoint_of_is_refuted_when_the_point_is_off_the_midpoint(
    registry: OperatorRegistry, judges: JudgeRegistry
) -> None:
    figure = _figure({"A": ("0", "0"), "B": ("4", "0"), "M": ("1", "0")})
    evaluate_figure(figure, registry)
    verdict = judge_relation(figure, "midpoint_of", ["M", "A", "B"], judges, scope=INSTANCE)
    assert verdict.verdict == REFUTED


# -- counterexample discipline ---------------------------------------------


def test_every_judge_can_refute_a_false_relation(
    registry: OperatorRegistry, judges: JudgeRegistry
) -> None:
    """A judge that cannot refute anything is not a judge."""
    figure = _figure(
        {
            "A": ("0", "0"),
            "B": ("4", "0"),
            "C": ("1", "3"),
            "D": ("0", "7"),
            "P": ("2", "1"),
        }
    )
    _derived(figure, "l1", "line", "line.free", ["A", "B"], "AB")
    _derived(figure, "l2", "line", "line.free", ["C", "D"], "CD")
    _derived(figure, "l3", "line", "line.free", ["D", "A"], "DA")
    _derived(figure, "c1", "circle", "circle.through", ["A", "B", "C"], "⊙O")
    evaluate_figure(figure, registry)

    cases = [
        ("collinear", ["A", "B", "C"]),
        ("perpendicular", ["l1", "l2"]),
        ("concyclic", ["A", "B", "C", "D"]),
        ("equal_length", ["A", "B", "C", "D"]),
        ("midpoint_of", ["P", "A", "B"]),
        ("angle_bisector", ["P", "A", "B", "C"]),
        ("tangent_to", ["l1", "c1"]),
        ("concurrency", ["l1", "l2", "l3"]),
    ]
    for kind, args in cases:
        verdict = judge_relation(figure, kind, args, judges, scope=INSTANCE)
        assert verdict.verdict == REFUTED, (
            f"judge {kind!r} failed to refute a false relation "
            f"(got {verdict.verdict}: {verdict.evidence})"
        )


def test_verdicts_are_never_silently_upgraded(
    registry: OperatorRegistry, judges: JudgeRegistry
) -> None:
    """A relation that holds in samples but is not an identity is at best 'supported'."""
    figure = _figure({"A": ("0", "0"), "B": ("4", "0"), "C": ("2", "3")})
    _derived(figure, "M", "point", "point.midpoint", ["A", "B"], "M")
    evaluate_figure(figure, registry)
    verdict = judge_relation(figure, "midpoint_of", ["M", "A", "C"], judges, scope=IDENTITY)
    assert verdict.verdict != PROVED
    assert verdict.verdict in {REFUTED, SUPPORTED}


# -- API discipline --------------------------------------------------------


def test_unknown_judge_is_an_error(judges: JudgeRegistry) -> None:
    with pytest.raises(StateError):
        judge_relation(Figure(), "no_such_judge", [], judges)


def test_relation_with_wrong_arity_is_an_error(
    registry: OperatorRegistry, judges: JudgeRegistry
) -> None:
    figure = _figure({"A": ("0", "0"), "B": ("4", "0")})
    evaluate_figure(figure, registry)
    with pytest.raises(StateError):
        judge_relation(figure, "collinear", ["A", "B"], judges)


def test_relations_can_be_adjudicated_from_the_figure(
    registry: OperatorRegistry, judges: JudgeRegistry
) -> None:
    """The figure's own relation list drives the judgement."""
    figure = _figure({"A": ("0", "0"), "B": ("4", "0"), "C": ("2", "3")})
    _derived(figure, "M", "point", "point.midpoint", ["A", "B"], "M")
    figure.add_relation(
        Relation(id="r1", kind="collinear", args=["A", "M", "C"], expected=False)
    )
    evaluate_figure(figure, registry)
    relation = figure.relations[0]
    verdict = judge_relation(figure, relation.kind, relation.args, judges, scope=IDENTITY)
    assert verdict.verdict == REFUTED
    assert relation.expected is False
