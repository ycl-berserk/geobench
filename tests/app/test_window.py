"""The window and the canvas, driven the way a user would drive them.

The tests run headless (Qt's ``offscreen`` platform), so they work on a
build machine as well as on a desk.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
except ImportError as exc:  # pragma: no cover - depends on the machine
    # Qt needs system libraries that some machines do not have. Skipping
    # is honest; a vacuous pass would not be.
    pytest.skip(f"Qt is not usable on this machine: {exc}", allow_module_level=True)

from geobench.app.canvas import FigureCanvas
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
    controller.construct("point.midpoint", ["A", "B"], "M")


def test_the_window_shows_three_panes(app: QApplication, controller: StudioController) -> None:
    window = StudioWindow(controller)
    window.show()
    app.processEvents()
    assert window.steps.count() == 0
    assert window.judgements.rowCount() == 0
    window.close()


def test_the_steps_pane_lists_the_construction(app: QApplication, controller: StudioController) -> None:
    window = StudioWindow(controller)
    _triangle(controller)
    window.refresh()
    texts = [window.steps.item(row).text() for row in range(window.steps.count())]
    assert any("A" in text for text in texts)
    assert any("point.midpoint" in text for text in texts)
    window.close()


def test_the_judgement_pane_shows_the_verdict(app: QApplication, controller: StudioController) -> None:
    window = StudioWindow(controller)
    _triangle(controller)
    controller.add_relation("collinear", ["A", "M", "B"])
    window.refresh()
    assert window.judgements.rowCount() == 1
    assert "proved" in window.judgements.item(0, 1).text()
    window.close()


def _drag(canvas: FigureCanvas, node_id: str, to_x: float, to_y: float) -> None:
    """Drag a point on the canvas, in pixels."""
    viewport = canvas._viewport()  # the test drives the widget directly
    positions = canvas.controller.point_positions()
    fx, fy = positions[node_id]
    sx, sy = viewport.to_screen(fx, fy)
    tx, ty = viewport.to_screen(to_x, to_y)
    press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(sx, sy),
        QPointF(sx, sy),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    move = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(tx, ty),
        QPointF(tx, ty),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    release = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPointF(tx, ty),
        QPointF(tx, ty),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    canvas.mousePressEvent(press)
    canvas.mouseMoveEvent(move)
    canvas.mouseReleaseEvent(release)


def test_dragging_a_point_on_the_canvas_moves_it(
    app: QApplication, controller: StudioController
) -> None:
    window = StudioWindow(controller)
    window.resize(900, 600)
    window.show()
    app.processEvents()
    _triangle(controller)
    app.processEvents()

    before = controller.point_positions()["A"]
    _drag(window.canvas, "A", 1.0, 2.0)
    app.processEvents()
    after = controller.point_positions()["A"]

    assert after != before
    assert after[0] == pytest.approx(1.0, abs=0.05)
    assert after[1] == pytest.approx(2.0, abs=0.05)
    window.close()


def test_the_canvas_paints_without_error(
    app: QApplication, controller: StudioController
) -> None:
    window = StudioWindow(controller)
    window.resize(900, 600)
    window.show()
    app.processEvents()
    _triangle(controller)
    app.processEvents()
    image = window.canvas.grab()
    assert image.width() > 0 and image.height() > 0
    window.close()
