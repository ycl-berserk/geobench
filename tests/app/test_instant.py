"""The screen never waits for the exact layer.

A figure is drawn in milliseconds; its exact expressions are what takes
seconds (and, on a big enough figure, minutes).  So the picture comes
first and the exact evaluation follows on a copy, in a worker.  What a
teacher sees at once is a complete, draggable figure; what arrives later
is the ability to judge it.

These tests are the contract in one place: after ``evaluate()`` the
figure is *drawn* and *pending*, never half-built and never blocked.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
except ImportError as exc:  # pragma: no cover - depends on the machine
    pytest.skip(f"Qt is not usable on this machine: {exc}", allow_module_level=True)

from geobench import evaluate
from geobench.app.controller import StudioController
from geobench.app.window import StudioWindow
from geobench.judges import IDENTITY
from geobench.primitives import figure_primitives


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _triangle() -> StudioController:
    controller = StudioController()
    controller.add_free_point(0, 0, "A")
    controller.add_free_point(6, 0, "B")
    controller.add_free_point(2, 4, "C")
    controller.construct("point.midpoint", ["A", "B"], "M")
    controller.construct("line.free", ["A", "B"], "ab")
    return controller


def test_the_picture_is_on_screen_before_the_exact_pass() -> None:
    controller = _triangle()
    figure = controller.figure()
    assert figure.runtime["exact"]["status"] == "pending"
    # And it is a whole picture, not a promise: every point is placed.
    positions = controller.point_positions()
    assert positions["A"] == (0.0, 0.0)
    assert positions["M"] == (3.0, 0.0)
    assert len(controller.primitives()) >= 4


def test_a_drag_runs_while_the_exact_pass_is_still_pending() -> None:
    controller = _triangle()
    assert controller.exact_pending()
    controller.move_point("A", 2, 0)
    assert controller.point_positions()["M"] == (4.0, 0.0)


def test_the_exact_pass_arrives_and_can_be_judged() -> None:
    controller = _triangle()
    controller.add_relation("collinear", ["A", "M", "B"])
    controller.evaluate_exact()
    assert not controller.exact_pending()
    assert controller.judge()[0].verdict == "proved"


def test_nothing_is_judged_before_the_exact_pass_arrives(
    app: QApplication,
) -> None:
    """A verdict about a numerically drawn figure would be about nothing."""
    controller = _triangle()
    controller.add_relation("collinear", ["A", "M", "B"])
    assert controller.exact_pending()

    window = StudioWindow(controller)
    window._refresh_judgements()
    assert window._verdicts == []
    assert "精确求值" in window._judgement_note.text()
    window.close()


def test_a_figure_over_budget_is_still_drawn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact layer may give up.  The picture may not."""
    monkeypatch.setattr(evaluate, "EXACT_BUDGET_OPS", 1)
    controller = _triangle()
    controller.add_relation("collinear", ["A", "M", "B"])

    controller.evaluate_exact()
    figure = controller.figure()
    assert figure.runtime["exact"]["status"] == "too-big"

    # Drawn: the same picture, from the numbers.
    drawn = [p for p in figure_primitives(figure, controller.style)]
    assert len(drawn) >= 4
    assert controller.point_positions()["M"] == (3.0, 0.0)

    # Judged: not at all, and it says why (never "false").
    verdicts = controller.judge(IDENTITY)
    assert verdicts
    for verdict in verdicts:
        assert verdict.verdict == "undecided"
        assert "预算" in verdict.evidence or "too big" in verdict.evidence
