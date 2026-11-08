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
