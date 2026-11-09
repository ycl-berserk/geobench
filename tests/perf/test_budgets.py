"""Performance budgets.

These are **regression** budgets, not absolute ones. A budget that a slow
CI machine can fail on its own is worse than no budget at all: it trains
people to ignore the gate.

So each budget here is generous -- roughly an order of magnitude above
the measured figure -- and tight enough to catch the kind of mistake that
actually happens: a path that accidentally stopped being incremental, or
a compiled function that started taking every symbol again.

The numbers they guard are in docs/plan.md section 7.

Two of them guard the **screen**, and they exist because of a bug the
other budgets missed: the picture fell back to the exact path whenever
a node had no numeric value, and a rational placement -- "101/100" --
was exactly such a node. The screen then spent minutes in a repaint.
So the budgets below measure the picture itself, and the figure they
measure has **rational** placements, which is what a dragged point has.
"""

from __future__ import annotations

import statistics
import time

import pytest

from geobench.evaluate import evaluate_exact, evaluate_numeric
from geobench.model import Figure, Node
from geobench.operators import register_builtins
from geobench.primitives import figure_primitives
from geobench.registry import OperatorRegistry
from geobench.style import COMPETITION

#: How many objects the benchmark figure has.
OBJECTS = 200

#: Regression budgets, in milliseconds. Compare with docs/plan.md
#: section 7: the measured figures are an order of magnitude smaller.
BUDGET_DRAG_FRAME_MS = 120.0
BUDGET_NEW_CONSTRUCTION_MS = 400.0
BUDGET_FIRST_BUILD_MS = 8000.0
#: The picture the screen draws. The measured figure is a fraction of a
#: millisecond; the budget is there to catch a fall back into the exact
#: path, which took minutes.
BUDGET_PICTURE_MS = 40.0
#: A drag frame, as the app does it: the placement changes and the
#: picture is rebuilt.
BUDGET_APP_FRAME_MS = 60.0


def _registry() -> OperatorRegistry:
    registry = OperatorRegistry()
    register_builtins(registry)
    return registry


def _figure(count: int) -> Figure:
    """A figure with free points and derived objects.

    The placements are **rational**: a point that has been dragged has
    a placement like "101/100", and that is the case that broke.
    """
    figure = Figure(id="fig_perf")
    for index in range(count):
        name = f"P{index}"
        figure.add_node(
            Node(
                id=name,
                kind="point",
                role="free",
                coords=(f"x_{name}", f"y_{name}"),
                placement=(f"{index % 7}/2", f"{index % 5}/3"),
            )
        )
    for index in range(count - 1):
        figure.add_node(
            Node(
                id=f"M{index}",
                kind="point",
                role="derived",
                op="point.midpoint",
                args=[f"P{index}", f"P{index + 1}"],
            )
        )
    return figure


def _median_ms(action, repeats: int) -> float:
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        action()
        samples.append((time.perf_counter() - start) * 1000)
    return statistics.median(samples)


@pytest.fixture(scope="module")
def figure() -> Figure:
    built = _figure(OBJECTS)
    evaluate_exact(built, _registry())
    evaluate_numeric(built)
    return built


def test_a_drag_frame_is_within_budget(figure: Figure) -> None:
    """The frame the user actually feels: move a point, redraw."""
    registry = _registry()

    def frame() -> None:
        figure.nodes["P0"].placement = ("3/2", "5/2")
        evaluate_exact(figure, registry)
        evaluate_numeric(figure)

    elapsed = _median_ms(frame, 20)
    assert elapsed < BUDGET_DRAG_FRAME_MS, (
        f"a drag frame took {elapsed:.1f} ms for {OBJECTS} objects "
        f"(budget {BUDGET_DRAG_FRAME_MS} ms)"
    )


def test_the_exact_path_does_nothing_when_nothing_changed(figure: Figure) -> None:
    """The exact path must be incremental, or dragging becomes algebra."""
    registry = _registry()
    elapsed = _median_ms(lambda: evaluate_exact(figure, registry), 20)
    assert elapsed < BUDGET_DRAG_FRAME_MS, (
        f"re-checking an unchanged construction took {elapsed:.1f} ms "
        f"(budget {BUDGET_DRAG_FRAME_MS} ms)"
    )


def test_the_picture_is_within_budget(figure: Figure) -> None:
    """What the screen draws must be cheap, whatever the figure holds.

    This is the budget that would have caught the slow picture: the
    primitives used to fall back to the exact path, and a rational
    placement made every point such a node.
    """
    elapsed = _median_ms(lambda: figure_primitives(figure, COMPETITION), 10)
    assert elapsed < BUDGET_PICTURE_MS, (
        f"drawing the picture took {elapsed:.1f} ms for {OBJECTS} objects "
        f"(budget {BUDGET_PICTURE_MS} ms)"
    )


def test_a_drag_frame_with_a_picture_is_within_budget(figure: Figure) -> None:
    """Move a point and draw the picture again: the frame the user feels."""

    def frame() -> None:
        figure.nodes["P0"].placement = ("3/2", "5/2")
        evaluate_numeric(figure)
        figure_primitives(figure, COMPETITION)

    elapsed = _median_ms(frame, 20)
    assert elapsed < BUDGET_APP_FRAME_MS, (
        f"a drag frame with a picture took {elapsed:.1f} ms for {OBJECTS} objects "
        f"(budget {BUDGET_APP_FRAME_MS} ms)"
    )


def test_a_rational_placement_keeps_its_value(figure: Figure) -> None:
    """A dragged point has a rational placement, and it still has a value.

    The placement is exact -- "101/100" -- and reading it as a plain
    decimal threw it away. Then everything built on that point had no
    value either, and the figure quietly fell apart.
    """
    node = figure.nodes["P3"]
    node.placement = ("101/100", "3/7")
    evaluate_numeric(figure)
    values = node.cache.get("numeric")
    assert values is not None
    assert values["coords"] == pytest.approx((1.01, 3 / 7))
    # And the object built on it is not undefined.
    midpoint = figure.nodes["M3"]
    assert midpoint.cache.get("undefined") is None


def test_adding_a_construction_is_within_budget() -> None:
    """One more object on a finished figure."""
    registry = _registry()
    figure = _figure(OBJECTS)
    evaluate_exact(figure, registry)
    evaluate_numeric(figure)

    def add() -> None:
        figure.add_node(
            Node(
                id="M_new",
                kind="point",
                role="derived",
                op="point.midpoint",
                args=["P0", "P1"],
            )
        )
        evaluate_exact(figure, registry)
        evaluate_numeric(figure)
        figure.nodes.pop("M_new")

    elapsed = _median_ms(add, 10)
    assert elapsed < BUDGET_NEW_CONSTRUCTION_MS, (
        f"adding a construction took {elapsed:.1f} ms "
        f"(budget {BUDGET_NEW_CONSTRUCTION_MS} ms)"
    )


def test_building_a_figure_from_scratch_is_within_budget() -> None:
    """The worst case: every object computed exactly, once."""
    registry = _registry()

    def build() -> None:
        built = _figure(OBJECTS)
        evaluate_exact(built, registry)

    elapsed = _median_ms(build, 3)
    assert elapsed < BUDGET_FIRST_BUILD_MS, (
        f"building {OBJECTS} objects took {elapsed:.1f} ms "
        f"(budget {BUDGET_FIRST_BUILD_MS} ms)"
    )
