"""Every tool on the toolbar must actually work from the interface.

A command that is implemented but unreachable is a command nobody has.
This walks the whole generated toolbar and drives each tool the way the
user does: arm it, click the objects it asks for, answer its prompt.
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
from geobench.app.tools import build_toolbar
from geobench.app.window import StudioWindow
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _all_tools() -> list:
    registry = OperatorRegistry()
    register_builtins(registry)
    return [tool for group in build_toolbar(registry) for tool in group.tools]


def _arm(window: StudioWindow, tool) -> None:
    for button in window.findChildren(QToolButton):
        menu = button.menu()
        if menu is None:
            continue
        for action in menu.actions():
            if action.text() == tool.label:
                action.trigger()
                return
    raise AssertionError(f"the toolbar has no button for {tool.label!r}")


def _screen_centre(canvas, point_id: str) -> QPoint:
    """Where a point is on the canvas, in widget pixels."""
    viewport = canvas._viewport()
    x, y = canvas.controller.point_positions()[point_id]
    sx, sy = viewport.to_screen(x, y)
    return QPoint(int(sx), int(sy))


def _click(canvas, point_id: str) -> None:
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=_screen_centre(canvas, point_id))


def _middle_of(canvas, first: str, second: str) -> QPoint:
    a = _screen_centre(canvas, first)
    b = _screen_centre(canvas, second)
    return QPoint((a.x() + b.x()) // 2, (a.y() + b.y()) // 2)


def _seed(controller: StudioController) -> None:
    """A figure with every kind of object a tool might ask for."""
    for node_id, (x, y) in {
        "A": (0, 0),
        "B": (4, 0),
        "C": (2, 3),
        "D": (5, 2),
    }.items():
        controller.add_free_point(float(x), float(y), node_id)
    controller.construct("segment.free", ["A", "B"], "AB")
    controller.construct("circle.center_point", ["A", "B"], "c")
    controller.construct("polygon.free", ["A", "B", "C"], "poly")


def _feed(canvas, window, tool) -> None:
    """Give the armed tool whatever it asks for."""
    controller = window.controller
    kinds = [arg.kind for arg in tool.args]
    for kind in kinds:
        if kind == "point":
            _click(canvas, "C" if tool.op != "point.midpoint" else "A")
        elif kind == "line":
            QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=_middle_of(canvas, "A", "B"))
        elif kind == "segment":
            QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=_middle_of(canvas, "A", "B"))
        elif kind == "circle":
            # A point on the circle, taken from what the kernel says it is.
            from geobench.evaluate import numeric_circle

            viewport = canvas._viewport()
            cx, cy, r2 = numeric_circle(controller.figure(), "c")
            sx, sy = viewport.to_screen(cx + r2**0.5, cy)
            QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(int(sx), int(sy)))
        elif kind == "polygon":
            # Anywhere inside the triangle A(0,0) B(4,0) C(2,3).
            viewport = canvas._viewport()
            sx, sy = viewport.to_screen(2.0, 0.8)
            QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(int(sx), int(sy)))
    if tool.variable:
        for _ in range(tool.min_args):
            _click(canvas, "A")
        QTest.keyClick(canvas, Qt.Key.Key_Return)


@pytest.mark.parametrize("index", range(len(_all_tools())))
def test_every_tool_on_the_toolbar_builds_something(app: QApplication, index: int) -> None:
    tool = _all_tools()[index]
    if tool.op == "point.free":
        pytest.skip("the point tool is covered by its own tests")

    controller = StudioController()
    window = StudioWindow(controller)
    window.resize(1100, 700)
    window.show()
    app.processEvents()
    _seed(controller)
    app.processEvents()

    # Answer any prompt without a dialog.
    window._value_for = lambda kind: "0" if kind == "selector" else "2"  # type: ignore[method-assign]

    before = len(controller.figure().nodes)
    _arm(window, tool)
    app.processEvents()
    assert window.canvas.tool() is not None, tool.label
    assert window.canvas.tool().op == tool.op, tool.label

    _feed(window.canvas, window, tool)
    app.processEvents()

    after = len(controller.figure().nodes)
    assert after > before, (
        f"{tool.label} ({tool.op}) built nothing; "
        f"status: {window.statusBar().currentMessage()}"
    )
    window.close()
