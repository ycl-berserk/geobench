"""Dragging a point: the picture follows at once, the verdicts settle after.

The screen has to keep up with the mouse. So a drag runs only the
**numeric** path -- the construction has not changed -- and the verdicts
are recomputed when the mouse comes up, not on every frame.
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
    controller.construct("point.midpoint", ["A", "B"], "M")


def test_a_move_is_a_move_and_not_a_change(controller: StudioController) -> None:
    """The two channels are different, and the drag uses the cheap one."""
    changes: list[int] = []
    moves: list[str] = []
    controller.on_change(lambda: changes.append(1))
    controller.on_move(moves.append)

    _triangle(controller)
    changes.clear()
    moves.clear()

    controller.move_point("A", 1.5, 2.25)
    assert moves == ["A"]
    # Nothing was *changed*: the construction did not change.
    assert changes == []

    controller.finish_move()
    assert changes == [1]


def test_a_rational_placement_keeps_the_figure_whole(
    controller: StudioController,
) -> None:
    """A dragged point lands on a rational, and everything still has a value."""
    _triangle(controller)
    controller.move_point("A", 1.5, 2.25)
    controller.finish_move()

    figure = controller.figure()
    for node_id, node in figure.nodes.items():
        assert node.cache.get("undefined") is None, node_id

    from geobench.primitives import figure_primitives

    primitives = figure_primitives(figure, controller.style)
    # Every point of the figure is in the picture.
    drawn = [p for p in primitives if p.__class__.__name__ == "PointPrimitive"]
    assert len(drawn) == len(figure.nodes)


def test_the_drag_moves_the_picture(app: QApplication, controller: StudioController) -> None:
    """The point follows the mouse."""
    window = StudioWindow(controller)
    window.resize(900, 600)
    window.show()
    app.processEvents()
    _triangle(controller)
    app.processEvents()

    before = controller.point_positions()["A"]
    canvas = window.canvas
    viewport = canvas._viewport()
    sx, sy = viewport.to_screen(*before)
    tx, ty = viewport.to_screen(3.0, 1.0)

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
    app.processEvents()

    after = controller.point_positions()["A"]
    assert after != before
    assert after[0] == pytest.approx(3.0, abs=0.1)
    assert after[1] == pytest.approx(1.0, abs=0.1)
    window.close()
