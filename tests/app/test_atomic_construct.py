"""A construction that cannot be evaluated rolls back.

The line tool, given the same point twice, asks for a line through one
point. The operator refuses, and that refusal must leave nothing behind:
a node in the figure with no value makes every later evaluation fail,
and the figure is poisoned for good.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QToolButton
except ImportError as exc:  # pragma: no cover - depends on the machine
    pytest.skip(f"Qt is not usable on this machine: {exc}", allow_module_level=True)

from geobench.app.controller import StudioController
from geobench.app.window import StudioWindow
from geobench.errors import GeobenchError
from geobench.primitives import figure_primitives


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def controller() -> StudioController:
    return StudioController()


def test_a_refused_construction_leaves_nothing_behind() -> None:
    controller = StudioController()
    controller.add_free_point(0, 0, "A")
    before = list(controller.figure().nodes)

    with pytest.raises(GeobenchError):
        controller.construct("line.free", ["A", "A"])

    assert list(controller.figure().nodes) == before
    # And the figure still draws and still judges.
    figure_primitives(controller.figure(), controller.style)
    assert controller.judge() == []


def test_the_figure_survives_after_a_refusal() -> None:
    """Adding a point after a refused construction still works."""
    controller = StudioController()
    controller.add_free_point(0, 0, "A")
    with pytest.raises(GeobenchError):
        controller.construct("line.free", ["A", "A"])

    controller.add_free_point(4, 0)
    controller.construct("point.midpoint", ["A", "B"])
    assert "M" in controller.figure().nodes
    figure_primitives(controller.figure(), controller.style)


def test_a_double_click_on_a_point_does_not_pick_it_twice(
    app: QApplication, controller: StudioController
) -> None:
    """The line tool needs two points; the same point twice is a no-op."""
    window = StudioWindow(controller)
    window.resize(1000, 700)
    window.show()
    app.processEvents()
    controller.add_free_point(0, 0, "A")
    app.processEvents()

    for button in window.findChildren(QToolButton):
        menu = button.menu()
        if menu is None:
            continue
        for action in menu.actions():
            if action.text() == "直线":
                action.trigger()
                break
    app.processEvents()

    viewport = window.canvas._viewport()
    x, y = controller.point_positions()["A"]
    sx, sy = viewport.to_screen(x, y)
    point = QPoint(int(sx), int(sy))
    QTest.mouseClick(window.canvas, Qt.MouseButton.LeftButton, pos=point)
    QTest.mouseClick(window.canvas, Qt.MouseButton.LeftButton, pos=point)
    app.processEvents()

    assert window.canvas.pending_args() == ["A"]
    assert list(controller.figure().nodes) == ["A"]
    window.close()
