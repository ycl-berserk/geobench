"""Performance budgets.

These are **regression** budgets, not absolute ones. A budget that a slow
CI machine can fail on its own is worse than no budget at all: it trains
people to ignore the gate.

So each budget here is generous -- roughly an order of magnitude above
the measured figure -- and tight enough to catch the kind of mistake that
actually happens: a path that accidentally stopped being incremental, or
a compiled function that started taking every symbol again.

The numbers they guard are in docs/plan.md section 7.
"""

from __future__ import annotations

import statistics
import time

import pytest

from geobench.evaluate import evaluate_exact, evaluate_numeric
from geobench.model import Figure, Node
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry

#: How many objects the benchmark figure has.
OBJECTS = 200

#: Regression budgets, in milliseconds. Compare with docs/plan.md
#: section 7: the measured figures are an order of magnitude smaller.
BUDGET_DRAG_FRAME_MS = 120.0
BUDGET_NEW_CONSTRUCTION_MS = 400.0
BUDGET_FIRST_BUILD_MS = 8000.0


def _registry() -> OperatorRegistry:
    registry = OperatorRegistry()
    register_builtins(registry)
    return registry


def _figure(count: int) -> Figure:
    """A figure with free points and derived objects."""
    figure = Figure(id="fig_perf")
    for index in range(count):
        name = f"P{index}"
        figure.add_node(
            Node(
                id=name,
                kind="point",
                role="free",
                coords=(f"x_{name}", f"y_{name}"),
                placement=(str(index % 7), str(index % 5)),
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
        figure.nodes["P0"].placement = ("1.5", "2.5")
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
