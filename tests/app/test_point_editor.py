"""A point can be put exactly where the teacher says.

Dragging puts a point near where the mouse was. A competition figure
wants it at exactly (3/2, 7/4), and the way to say that is to type it:
a double click on a point, two boxes, and what is typed is taken as
the exact number it is.
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
from geobench.errors import GeobenchError


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def controller() -> StudioController:
    controller = StudioController()
    controller.add_free_point(0, 0, "A")
    return controller


def test_a_point_can_be_put_exactly_where_it_is_said(
    controller: StudioController,
) -> None:
    controller.set_point_position("A", "3/2", "7/4")
    placement = controller.figure().nodes["A"].placement
    assert placement == ("3/2", "7/4")


def test_a_decimal_becomes_the_rational_it_stands_for(
    controller: StudioController,
) -> None:
    """The kernel holds no floats, and a figure a teacher typed is one they meant."""
    controller.set_point_position("A", "0.5", "1.25")
    assert controller.figure().nodes["A"].placement == ("1/2", "5/4")


def test_nonsense_is_refused(controller: StudioController) -> None:
    with pytest.raises(GeobenchError):
        controller.set_point_position("A", "here", "0")
    # the point did not move
    assert controller.figure().nodes["A"].placement == ("0", "0")


def test_a_derived_point_cannot_be_moved_by_hand(
    controller: StudioController,
) -> None:
    """A derived point is where the construction says it is."""
    controller.add_free_point(4, 0, "B")
    controller.construct("point.midpoint", ["A", "B"], "M")
    with pytest.raises(GeobenchError):
        controller.set_point_position("M", "1", "1")


def test_a_double_click_asks_for_the_position(
    app: QApplication, controller: StudioController
) -> None:
    """A double click on a point is a request to type where it goes."""
    window = StudioWindow(controller)
    window.resize(900, 600)
    window.show()
    app.processEvents()

    asked: list[str] = []
    # The window's own slot opens a modal dialog, which nobody would
    # close here. The signal is what this test is about.
    window.canvas.pointEditRequested.disconnect()
    window.canvas.pointEditRequested.connect(asked.append)

    viewport = window.canvas._viewport()
    sx, sy = viewport.to_screen(0.0, 0.0)
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonDblClick,
        QPointF(sx, sy),
        QPointF(sx, sy),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.canvas.mouseDoubleClickEvent(event)
    app.processEvents()

    assert asked == ["A"]
    window.close()
