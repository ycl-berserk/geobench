"""The verdict cache.

An **identity** verdict does not change when a free point is dragged --
that is exactly what "identity" means (spec section 12.2). So the
verdict can be cached on the figure and reused, which is what lets the
screen keep showing it without re-running the proof on every frame.

An **instance** verdict does depend on the placement, so it is cached
under a key that includes the free points' positions.
"""

from __future__ import annotations

from geobench.evaluate import evaluate_exact, evaluate_numeric
from geobench.judges import IDENTITY, INSTANCE, JudgeRegistry, judge_relation
from geobench.model import FREE, POINT, Figure, Node
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry


def _figure() -> tuple[Figure, OperatorRegistry]:
    registry = OperatorRegistry()
    register_builtins(registry)
    figure = Figure(id="fig_cache")
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
    figure.add_node(
        Node(
            id="M",
            kind=POINT,
            role="derived",
            op="point.midpoint",
            args=["A", "B"],
        )
    )
    evaluate_exact(figure, registry)
    return figure, registry


def test_an_identity_verdict_is_reused_after_a_drag() -> None:
    figure, registry = _figure()
    judges = JudgeRegistry()
    first = judge_relation(figure, "collinear", ["A", "M", "B"], judges, scope=IDENTITY)
    assert first.verdict == "proved"

    figure.nodes["A"].placement = ("1", "2")
    evaluate_exact(figure, registry)
    evaluate_numeric(figure)
    second = judge_relation(figure, "collinear", ["A", "M", "B"], judges, scope=IDENTITY)

    assert second.verdict == first.verdict
    assert second.evidence == first.evidence


def test_a_changed_construction_invalidates_the_cache() -> None:
    """The cache must not hide a real change."""
    figure, registry = _figure()
    judges = JudgeRegistry()
    assert (
        judge_relation(figure, "collinear", ["A", "M", "B"], judges, scope=IDENTITY).verdict
        == "proved"
    )

    # M becomes the midpoint of A and C: A, M and B are no longer collinear.
    figure.nodes["M"].args = ["A", "C"]
    evaluate_exact(figure, registry)
    after = judge_relation(figure, "collinear", ["A", "M", "B"], judges, scope=IDENTITY)
    assert after.verdict == "refuted"


def test_an_instance_verdict_follows_the_placement() -> None:
    """An instance verdict is about *this* picture, so it must be re-checked."""
    figure, registry = _figure()
    judges = JudgeRegistry()
    before = judge_relation(figure, "collinear", ["A", "M", "B"], judges, scope=INSTANCE)
    assert before.verdict == "proved"

    figure.nodes["A"].placement = ("1", "2")
    evaluate_exact(figure, registry)
    evaluate_numeric(figure)
    after = judge_relation(figure, "collinear", ["A", "M", "B"], judges, scope=INSTANCE)

    # M is still the midpoint of A and B, so the three are still collinear:
    # the point is that the verdict was *recomputed*, not carried over.
    assert after.verdict == "proved"
    assert after is not before


def test_an_instance_verdict_that_becomes_false_is_reported() -> None:
    figure, registry = _figure()
    judges = JudgeRegistry()
    assert (
        judge_relation(figure, "collinear", ["A", "M", "B"], judges, scope=INSTANCE).verdict
        == "proved"
    )

    # M stops being the midpoint of A and B, but stays where it was: now A,
    # M and B are not collinear in this picture either.
    figure.nodes["M"].args = ["A", "C"]
    evaluate_exact(figure, registry)
    evaluate_numeric(figure)
    after = judge_relation(figure, "collinear", ["A", "M", "B"], judges, scope=INSTANCE)
    assert after.verdict == "refuted"
