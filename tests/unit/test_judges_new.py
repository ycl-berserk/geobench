"""The judges added in T033.

Every judge needs a positive case *and* a counterexample case. A judge
that cannot refute a mutated figure is not trustworthy (docs/spec.md
section 6.3).
"""

from __future__ import annotations

import pytest

from geobench.evaluate import evaluate_figure
from geobench.judges import (
    IDENTITY,
    INSTANCE,
    PROVED,
    REFUTED,
    JudgeRegistry,
    judge_relation,
)
from geobench.model import Figure, Node
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
    figure = Figure(id="fig_judge_new")
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


def _derived(figure: Figure, node_id: str, kind: str, op: str, args: list[str]) -> None:
    figure.add_node(
        Node(id=node_id, kind=kind, role="derived", op=op, args=args, label=node_id)
    )


def _verdict(
    figure: Figure, judges: JudgeRegistry, kind: str, args: list[str], scope: str = IDENTITY
) -> str:
    return judge_relation(figure, kind, args, judges, scope=scope).verdict


# -- parallel ---------------------------------------------------------------


def test_parallel_lines_are_proved(
    registry: OperatorRegistry, judges: JudgeRegistry
) -> None:
    """Two lines drawn parallel -- true of this picture, not of every one."""
    figure = _figure({"A": ("0", "0"), "B": ("4", "0"), "C": ("0", "3")})
    _derived(figure, "l1", "line", "line.free", ["A", "B"])
    _derived(figure, "l2", "line", "line.parallel_through", ["C", "l1"])
    evaluate_figure(figure, registry)
    assert _verdict(figure, judges, "parallel", ["l1", "l2"], INSTANCE) == PROVED


def test_a_constructed_parallel_holds_for_every_placement(
    registry: OperatorRegistry, judges: JudgeRegistry
) -> None:
    """A line drawn *parallel* to another is parallel for every placement."""
    figure = _figure({"A": ("0", "0"), "B": ("4", "0"), "C": ("0", "3")})
    _derived(figure, "l1", "line", "line.free", ["A", "B"])
    _derived(figure, "l2", "line", "line.parallel_through", ["C", "l1"])
    evaluate_figure(figure, registry)
    assert _verdict(figure, judges, "parallel", ["l1", "l2"], IDENTITY) == PROVED


def test_lines_that_are_not_parallel_are_refuted(
    registry: OperatorRegistry, judges: JudgeRegistry
) -> None:
    figure = _figure({"A": ("0", "0"), "B": ("4", "0"), "C": ("0", "3"), "D": ("4", "4")})
    _derived(figure, "l1", "line", "line.free", ["A", "B"])
    _derived(figure, "l2", "line", "line.free", ["C", "D"])
    evaluate_figure(figure, registry)
    assert _verdict(figure, judges, "parallel", ["l1", "l2"], INSTANCE) == REFUTED


# -- point_in ---------------------------------------------------------------


def test_a_point_on_a_circle_is_proved(registry: OperatorRegistry, judges: JudgeRegistry) -> None:
    figure = _figure({"A": ("0", "0"), "B": ("4", "0"), "C": ("2", "3")})
    _derived(figure, "c", "circle", "circle.through", ["A", "B", "C"])
    evaluate_figure(figure, registry)
    assert _verdict(figure, judges, "point_in", ["A", "c"]) == PROVED


def test_a_point_off_a_circle_is_refuted(registry: OperatorRegistry, judges: JudgeRegistry) -> None:
    figure = _figure({"A": ("0", "0"), "B": ("4", "0"), "C": ("2", "3"), "D": ("9", "9")})
    _derived(figure, "c", "circle", "circle.through", ["A", "B", "C"])
    evaluate_figure(figure, registry)
    assert _verdict(figure, judges, "point_in", ["D", "c"]) == REFUTED


def test_a_point_on_a_line_is_proved(
    registry: OperatorRegistry, judges: JudgeRegistry
) -> None:
    figure = _figure({"A": ("0", "0"), "B": ("4", "0"), "C": ("2", "0")})
    _derived(figure, "l1", "line", "line.free", ["A", "B"])
    evaluate_figure(figure, registry)
    assert _verdict(figure, judges, "point_in", ["C", "l1"], INSTANCE) == PROVED


# -- ratio_equal ------------------------------------------------------------


def test_equal_ratios_are_proved(judges: JudgeRegistry) -> None:
    # AB = 2, CD = 4, EF = 3, GH = 6: AB/CD = EF/GH = 1/2.
    figure = _figure(
        {
            "A": ("0", "0"),
            "B": ("2", "0"),
            "C": ("0", "0"),
            "D": ("4", "0"),
            "E": ("0", "0"),
            "F": ("3", "0"),
            "G": ("0", "0"),
            "H": ("6", "0"),
        }
    )
    assert (
        _verdict(
            figure, judges, "ratio_equal", ["A", "B", "C", "D", "E", "F", "G", "H"], INSTANCE
        )
        == PROVED
    )


def test_unequal_ratios_are_refuted(judges: JudgeRegistry) -> None:
    figure = _figure(
        {
            "A": ("0", "0"),
            "B": ("2", "0"),
            "C": ("0", "0"),
            "D": ("4", "0"),
            "E": ("0", "0"),
            "F": ("5", "0"),
            "G": ("0", "0"),
            "H": ("6", "0"),
        }
    )
    assert (
        _verdict(
            figure, judges, "ratio_equal", ["A", "B", "C", "D", "E", "F", "G", "H"], INSTANCE
        )
        == REFUTED
    )


# -- the centres ------------------------------------------------------------


def test_the_circumcentre_is_proved(registry: OperatorRegistry, judges: JudgeRegistry) -> None:
    figure = _figure({"A": ("0", "0"), "B": ("6", "0"), "C": ("2", "4")})
    _derived(figure, "O", "point", "point.circumcenter", ["A", "B", "C"])
    evaluate_figure(figure, registry)
    assert _verdict(figure, judges, "circumcenter_of", ["O", "A", "B", "C"]) == PROVED


def test_a_point_that_is_not_the_circumcentre_is_refuted(
    registry: OperatorRegistry, judges: JudgeRegistry
) -> None:
    figure = _figure({"A": ("0", "0"), "B": ("6", "0"), "C": ("2", "4"), "P": ("1", "1")})
    _derived(figure, "O", "point", "point.circumcenter", ["A", "B", "C"])
    evaluate_figure(figure, registry)
    assert _verdict(figure, judges, "circumcenter_of", ["P", "A", "B", "C"]) == REFUTED


def test_the_orthocentre_is_proved(registry: OperatorRegistry, judges: JudgeRegistry) -> None:
    figure = _figure({"A": ("0", "0"), "B": ("6", "0"), "C": ("2", "4")})
    _derived(figure, "H", "point", "point.orthocenter", ["A", "B", "C"])
    evaluate_figure(figure, registry)
    assert _verdict(figure, judges, "orthocenter_of", ["H", "A", "B", "C"]) == PROVED


def test_the_centroid_is_proved(registry: OperatorRegistry, judges: JudgeRegistry) -> None:
    figure = _figure({"A": ("0", "0"), "B": ("6", "0"), "C": ("2", "4")})
    _derived(figure, "G", "point", "point.centroid", ["A", "B", "C"])
    evaluate_figure(figure, registry)
    assert _verdict(figure, judges, "centroid_of", ["G", "A", "B", "C"]) == PROVED


# -- angle_equal ------------------------------------------------------------


def test_two_right_angles_are_equal(judges: JudgeRegistry) -> None:
    """The angles ABC and DEF are both right angles."""
    figure = _figure(
        {
            "A": ("0", "0"),
            "B": ("1", "0"),
            "C": ("1", "1"),
            "D": ("0", "0"),
            "E": ("1", "0"),
            "F": ("1", "-1"),
        }
    )
    verdict = judge_relation(
        figure, "angle_equal", ["A", "B", "C", "D", "E", "F"], judges, scope=INSTANCE
    )
    assert verdict.verdict == PROVED


def test_supplementary_angles_are_not_equal(judges: JudgeRegistry) -> None:
    """The two angles add up to 180 degrees; they are not equal.

    This is the case that a squared cosine would wrongly accept, and
    the reason the judge keeps the sign of the cosine.
    """
    figure = _figure(
        {
            "A": ("0", "0"),
            "B": ("1", "0"),
            "C": ("1", "1"),
            "D": ("0", "0"),
            "E": ("1", "0"),
            "F": ("-1", "1"),
        }
    )
    verdict = judge_relation(
        figure, "angle_equal", ["A", "B", "C", "D", "E", "F"], judges, scope=INSTANCE
    )
    assert verdict.verdict == REFUTED


def test_the_instance_scope_sees_the_picture_as_drawn(judges: JudgeRegistry) -> None:
    figure = _figure({"A": ("0", "0"), "B": ("1", "0"), "C": ("1", "1")})
    assert (
        judge_relation(figure, "collinear", ["A", "B", "C"], judges, scope=INSTANCE).verdict
        == REFUTED
    )
