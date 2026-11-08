"""Undo and redo.

Drawing a figure is full of second thoughts, and there is no way back
except undo. A figure is a few dozen objects, so the undo stack keeps
**snapshots** rather than a list of inverse operations: an inverse
operation can be wrong, and a snapshot cannot.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
except ImportError as exc:  # pragma: no cover - depends on the machine
    pytest.skip(f"Qt is not usable on this machine: {exc}", allow_module_level=True)

from geobench.app.controller import StudioController
from geobench.app.window import StudioWindow


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def controller() -> StudioController:
    return StudioController()


def _triangle(controller: StudioController) -> None:
    controller.add_free_point(0, 0, "A")
    controller.add_free_point(6, 0, "B")
    controller.add_free_point(2, 4, "C")


def test_a_construction_can_be_undone(controller: StudioController) -> None:
    _triangle(controller)
    controller.construct("point.midpoint", ["A", "B"])
    assert len(controller.figure().nodes) == 4

    assert controller.undo() is True
    assert len(controller.figure().nodes) == 3
    assert "M" not in controller.figure().nodes


def test_a_point_can_be_undone(controller: StudioController) -> None:
    _triangle(controller)
    assert controller.undo() is True
    assert len(controller.figure().nodes) == 2
    assert controller.undo() is True
    assert len(controller.figure().nodes) == 1


def test_undo_and_redo_walk_back_and_forth(controller: StudioController) -> None:
    _triangle(controller)
    controller.construct("point.midpoint", ["A", "B"])
    before = list(controller.figure().nodes)

    controller.undo()
    assert "M" not in controller.figure().nodes
    assert controller.redo() is True
    assert list(controller.figure().nodes) == before


def test_a_new_change_clears_the_redo_stack(controller: StudioController) -> None:
    _triangle(controller)
    controller.undo()
    assert controller.can_redo() is True
    controller.add_free_point(1, 1, "D")
    assert controller.can_redo() is False


def test_there_is_nothing_to_undo_at_the_start(controller: StudioController) -> None:
    assert controller.can_undo() is False
    assert controller.undo() is False
    assert controller.redo() is False


def test_a_drag_is_one_step_not_one_per_frame(
    app: QApplication, controller: StudioController
) -> None:
    """A drag of thirty frames undoes in one go."""
    window = StudioWindow(controller)
    window.resize(900, 600)
    window.show()
    app.processEvents()
    canvas = window.canvas

    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(200, 400))
    app.processEvents()
    assert len(controller.figure().nodes) == 1
    before = controller.point_positions()["A"]

    steps = 20
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(200, 400))
    for step in range(steps):
        QTest.mouseMove(canvas, QPoint(200 + step, 400))
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(200 + steps, 400))
    app.processEvents()

    moved = controller.point_positions()["A"]
    assert moved != pytest.approx(before)

    # One undo puts the point back where it was.
    controller.undo()
    assert controller.point_positions()["A"] == pytest.approx(before)
    window.close()
