"""The canvas has to be usable, not merely paint.

The earlier tests called ``mousePressEvent`` directly, which proves the
handler works but says nothing about whether a click ever *reaches* the
canvas. These tests go through Qt's own event dispatch, on the same
platform the user is on.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QToolBar
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


def test_a_tool_is_armed_from_the_start(app: QApplication, controller: StudioController) -> None:
    """An idle canvas looks like a broken program.

    With no tool armed a click does nothing, and nothing says so. The
    point tool is the obvious first move, so it is armed for the user.
    """
    window = StudioWindow(controller)
    window.show()
    app.processEvents()
    assert window.canvas.tool() == "point.free"
    window.close()


def test_a_click_places_a_point_where_the_user_clicked(
    app: QApplication, controller: StudioController
) -> None:
    """The click must land on the pixel the user aimed at.

    The view used to be recomputed from the figure on every paint, so
    the picture moved under the cursor as soon as a point was added and
    the next click landed somewhere else entirely.
    """
    window = StudioWindow(controller)
    window.resize(900, 600)
    window.show()
    app.processEvents()
    canvas = window.canvas

    target = QPoint(canvas.width() // 2, canvas.height() // 2)
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=target)
    app.processEvents()

    positions = controller.point_positions()
    assert len(positions) == 1
    x, y = next(iter(positions.values()))
    # The default view is centred on the origin, so the middle of the
    # canvas is the origin. A pixel of slack, because the middle of an
    # odd-sized widget is half a pixel off.
    assert x == pytest.approx(0.0, abs=0.05)
    assert y == pytest.approx(0.0, abs=0.05)
    window.close()


def test_the_view_stays_put_when_the_figure_changes(
    app: QApplication, controller: StudioController
) -> None:
    window = StudioWindow(controller)
    window.resize(900, 600)
    window.show()
    app.processEvents()
    canvas = window.canvas

    before = canvas._viewport().view
    for x, y in ((100, 100), (400, 300)):
        QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(x, y))
        app.processEvents()
    after = canvas._viewport().view

    assert before == after
    window.close()


def test_a_click_on_an_existing_point_drags_it(
    app: QApplication, controller: StudioController
) -> None:
    """Dragging a point is something every drawing program does."""
    window = StudioWindow(controller)
    window.resize(900, 600)
    window.show()
    app.processEvents()
    canvas = window.canvas

    centre = QPoint(canvas.width() // 2, canvas.height() // 2)
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=centre)
    app.processEvents()
    assert len(controller.point_positions()) == 1

    # Press on the point itself, then move away from it.
    target = QPoint(centre.x() + 60, centre.y() + 40)
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=centre)
    QTest.mouseMove(canvas, target)
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=target)
    app.processEvents()

    # The point moved, and no second point appeared.
    assert len(controller.point_positions()) == 1
    x, y = next(iter(controller.point_positions().values()))
    assert (x, y) != pytest.approx((0.0, 0.0))
    window.close()


def test_the_canvas_says_what_a_click_will_do(
    app: QApplication, controller: StudioController
) -> None:
    window = StudioWindow(controller)
    window.show()
    app.processEvents()
    assert "点" in window.canvas.armed_hint()
    window.close()


def _arm(window: StudioWindow, name: str) -> None:
    """Arm a tool the way the user does: from the toolbar."""
    toolbar = window.findChildren(QToolBar)[0]
    for action in toolbar.actions():
        if action.text() == name:
            action.trigger()
            return
    raise AssertionError(f"there is no tool called {name!r}")


def test_a_variable_tool_waits_for_the_return_key(
    app: QApplication, controller: StudioController
) -> None:
    """A polygon has three, four or five vertices: the user says when to stop."""
    window = StudioWindow(controller)
    window.resize(900, 600)
    window.show()
    app.processEvents()
    canvas = window.canvas

    corners = ((120, 420), (420, 420), (270, 180))
    for x, y in corners:
        QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(x, y))
        app.processEvents()
    assert len(controller.figure().nodes) == 3

    _arm(window, "多边形")
    for x, y in corners:
        QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(x, y))
        app.processEvents()
    # Nothing is built yet: the tool is still collecting.
    assert len(controller.figure().nodes) == 3
    assert canvas.pending_args() == ["A", "B", "C"]

    QTest.keyClick(canvas, Qt.Key.Key_Return)
    app.processEvents()
    assert len(controller.figure().nodes) == 4
    assert any(node.kind == "polygon" for node in controller.figure().nodes.values())
    window.close()


def test_the_return_key_with_too_few_points_does_nothing(
    app: QApplication, controller: StudioController
) -> None:
    window = StudioWindow(controller)
    window.resize(900, 600)
    window.show()
    app.processEvents()
    canvas = window.canvas

    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(120, 420))
    app.processEvents()
    _arm(window, "多边形")
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(120, 420))
    app.processEvents()
    QTest.keyClick(canvas, Qt.Key.Key_Return)
    app.processEvents()
    # A polygon needs three vertices.
    assert len(controller.figure().nodes) == 1
    window.close()


def test_a_measurement_tool_writes_the_number_on_the_figure(
    app: QApplication, controller: StudioController
) -> None:
    window = StudioWindow(controller)
    window.resize(900, 600)
    window.show()
    app.processEvents()
    canvas = window.canvas

    for x, y in ((120, 420), (420, 420)):
        QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(x, y))
        app.processEvents()
    _arm(window, "距离")
    for x, y in ((120, 420), (420, 420)):
        QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(x, y))
        app.processEvents()

    numbers = [
        node for node in controller.figure().nodes.values() if node.kind == "number"
    ]
    assert len(numbers) == 1
    window.close()
