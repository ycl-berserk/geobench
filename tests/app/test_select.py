"""The pointer: pick an object exactly, and delete it.

The user asked for this: "选择", so that a point can be picked exactly
instead of being fished for with a click.

And the verdicts arrive when they arrive: a proof can take seconds, and
the screen must not wait for it.
"""

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QToolButton
except ImportError as exc:  # pragma: no cover - depends on the machine
    pytest.skip(f"Qt is not usable on this machine: {exc}", allow_module_level=True)

from geobench.app.controller import StudioController
from geobench.app.tools import SELECT_TOOL
from geobench.app.window import HEAD_ROLE, StudioWindow


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


def _arm_select(window: StudioWindow) -> None:
    """Arm the pointer, the way the user does."""
    for button in window.findChildren(QToolButton):
        if button.text() == SELECT_TOOL.label:
            button.click()
            return
    raise AssertionError("there is no 选择 button on the toolbar")


def _screen_of(canvas, node_id: str) -> QPoint:
    viewport = canvas._viewport()
    x, y = canvas.controller.point_positions()[node_id]
    sx, sy = viewport.to_screen(x, y)
    return QPoint(int(sx), int(sy))


def _right_drag(canvas, start: QPoint, end: QPoint) -> None:
    press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(start),
        QPointF(start),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    move = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(end),
        QPointF(end),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    release = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPointF(end),
        QPointF(end),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    canvas.mousePressEvent(press)
    canvas.mouseMoveEvent(move)
    canvas.mouseReleaseEvent(release)


def test_right_drag_selects_everything_in_the_rectangle(
    app: QApplication, controller: StudioController
) -> None:
    window = StudioWindow(controller)
    window.resize(1000, 700)
    window.show()
    app.processEvents()
    _triangle(controller)
    app.processEvents()
    _arm_select(window)
    app.processEvents()
    canvas = window.canvas
    viewport = canvas._viewport()
    start = QPoint(*map(round, viewport.to_screen(-1, -1)))
    end = QPoint(*map(round, viewport.to_screen(7, 5)))
    _right_drag(canvas, start, end)
    app.processEvents()
    assert {"A", "B", "C"} <= set(canvas.selected())
    window.close()


def test_a_long_segment_crossing_the_rectangle_is_selected(
    app: QApplication, controller: StudioController
) -> None:
    """A small band on a long segment must not fall between samples.

    The rectangle is a fifth of a unit across on a segment twenty units
    long; sampling the segment every unit and a half would step over it.
    """
    controller.add_free_point(-10, -10, "A")
    controller.add_free_point(10, 10, "B")
    controller.construct("segment.free", ["A", "B"], "s")
    window = StudioWindow(controller)
    window.resize(1000, 700)
    window.show()
    app.processEvents()
    _arm_select(window)
    app.processEvents()
    canvas = window.canvas
    viewport = canvas._viewport()
    start = QPoint(*map(round, viewport.to_screen(0.75, -0.5)))
    end = QPoint(*map(round, viewport.to_screen(0.55, 0.75)))
    _right_drag(canvas, start, end)
    app.processEvents()
    assert "s" in canvas.selected()
    window.close()


def test_a_multi_selection_can_be_recoloured_and_deleted(
    app: QApplication, controller: StudioController
) -> None:
    _triangle(controller)
    controller.set_style_many(["A", "B"], color="#c0392b")
    assert controller.figure().nodes["A"].style.color == "#c0392b"
    assert controller.figure().nodes["B"].style.color == "#c0392b"
    controller.remove_nodes(["A", "B"])
    assert "A" not in controller.figure().nodes


def test_the_pointer_picks_an_object(app: QApplication, controller: StudioController) -> None:
    """A click with the pointer selects exactly what is under it."""
    window = StudioWindow(controller)
    window.resize(1000, 700)
    window.show()
    app.processEvents()
    _triangle(controller)
    app.processEvents()

    _arm_select(window)
    app.processEvents()
    assert window.canvas.tool() is not None
    assert window.canvas.tool().op == "select"

    QTest.mouseClick(
        window.canvas, Qt.MouseButton.LeftButton, pos=_screen_of(window.canvas, "C")
    )
    app.processEvents()
    assert window.canvas.selected() == ["C"]

    # The steps pane points at it.
    assert window.steps.currentRow() >= 0
    assert (window.steps.currentItem().data(HEAD_ROLE) or "").startswith("C")
    window.close()


def test_the_pointer_picks_a_line(app: QApplication, controller: StudioController) -> None:
    """Not only points: the pointer picks whatever can be seen."""
    window = StudioWindow(controller)
    window.resize(1000, 700)
    window.show()
    app.processEvents()
    _triangle(controller)
    controller.construct("segment.free", ["A", "B"], "AB")
    app.processEvents()

    _arm_select(window)
    app.processEvents()

    viewport = window.canvas._viewport()
    ax, ay = controller.point_positions()["A"]
    bx, by = controller.point_positions()["B"]
    sx, sy = viewport.to_screen((ax + bx) / 2, (ay + by) / 2)
    QTest.mouseClick(
        window.canvas, Qt.MouseButton.LeftButton, pos=QPoint(int(sx), int(sy))
    )
    app.processEvents()
    assert window.canvas.selected() == ["AB"]
    window.close()


def test_the_delete_key_removes_the_selected_object(
    app: QApplication, controller: StudioController
) -> None:
    """What is selected is what the Delete key removes."""
    window = StudioWindow(controller)
    window.resize(1000, 700)
    window.show()
    app.processEvents()
    _triangle(controller)
    app.processEvents()

    _arm_select(window)
    QTest.mouseClick(
        window.canvas, Qt.MouseButton.LeftButton, pos=_screen_of(window.canvas, "B")
    )
    app.processEvents()
    assert window.canvas.selected() == ["B"]

    QTest.keyClick(window.canvas, Qt.Key.Key_Delete)
    app.processEvents()
    assert "B" not in controller.figure().nodes
    window.close()


def test_the_verdicts_arrive_when_they_arrive(
    app: QApplication, controller: StudioController
) -> None:
    """A proof runs in the background; the screen does not wait for it."""
    window = StudioWindow(controller)
    window.show()
    app.processEvents()
    _triangle(controller)
    controller.construct("point.midpoint", ["A", "B"], "M")
    controller.add_relation("collinear", ["A", "M", "B"])
    app.processEvents()

    window.refresh()
    # The request went out; the answer has not come back yet.
    assert window._judge_request >= 1

    deadline = time.time() + 10.0
    while window.judgements.rowCount() < 1 and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    assert window.judgements.rowCount() == 1
    assert "成立" in window.judgements.item(0, 1).text()
    window.close()
