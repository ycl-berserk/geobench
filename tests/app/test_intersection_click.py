"""A click at a crossing makes the crossing, whatever kinds of object meet.

This is the teacher's complaint: "交点不够智能" -- clicking exactly where a
line and a circle cross gave a point on the circle, and clicking where two
circles cross gave a point on one of them.

The rule implemented here: the nearest crossing wins when the click is at
it; a click along an object, away from the crossing, still attaches to the
object; and a crossing that is not on the drawn part of a segment is not a
crossing at all.
"""

from __future__ import annotations

import math
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


def _line_circle(segment_to: int = 2) -> StudioController:
    controller = StudioController()
    controller.add_free_point(-2, 0, "A")
    controller.add_free_point(segment_to, 0, "B")
    controller.add_free_point(0, 0, "P")
    controller.construct("segment.free", ["A", "B"], "s")
    # Centre and radius, so no free point sits on either crossing.
    controller.construct("circle.free", ["P", "1"], "w")
    return controller


def _two_circles() -> StudioController:
    controller = StudioController()
    controller.add_free_point(0, 0, "P")
    controller.add_free_point(1, 0, "Q")
    controller.add_free_point(2, 0, "R")
    controller.construct("circle.center_point", ["P", "Q"], "w1")
    controller.construct("circle.center_point", ["Q", "R"], "w2")
    return controller


def _two_segments() -> StudioController:
    controller = StudioController()
    controller.add_free_point(-2, 0, "A")
    controller.add_free_point(2, 0, "B")
    controller.add_free_point(0, -2, "C")
    controller.add_free_point(0, 2, "D")
    controller.construct("segment.free", ["A", "B"], "s1")
    controller.construct("segment.free", ["C", "D"], "s2")
    return controller


def _window(controller: StudioController) -> StudioWindow:
    window = StudioWindow(controller)
    window.resize(1000, 700)
    window.show()
    # These tests place points by clicking; the pointer is the default.
    point = next(
        tool for group in window._groups for tool in group.tools
        if tool.op == "point.free"
    )
    window._arm(point)
    return window


def _click_at(window: StudioWindow, sx: float, sy: float) -> None:
    for kind, buttons in (
        (QMouseEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
        (QMouseEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton),
    ):
        event = QMouseEvent(
            kind,
            QPointF(sx, sy),
            QPointF(sx, sy),
            Qt.MouseButton.LeftButton,
            buttons,
            Qt.KeyboardModifier.NoModifier,
        )
        if kind == QMouseEvent.Type.MouseButtonPress:
            window.canvas.mousePressEvent(event)
        else:
            window.canvas.mouseReleaseEvent(event)


def _click(window: StudioWindow, x: float, y: float) -> None:
    viewport = window.canvas._viewport()
    sx, sy = viewport.to_screen(x, y)
    _click_at(window, sx, sy)


def _made(controller: StudioController, op: str):
    nodes = [node for node in controller.figure().nodes.values() if node.op == op]
    assert nodes, [node.op for node in controller.figure().nodes.values()]
    return nodes[-1]


def test_line_and_circle_crossing_makes_the_intersection(
    app: QApplication,
) -> None:
    controller = _line_circle()
    window = _window(controller)
    app.processEvents()

    _click(window, 1.0, 0.0)
    app.processEvents()

    node = _made(controller, "point.intersect_line_circle")
    assert node.args == ["s", "w", "0"]
    assert node.placement is not None
    assert float(node.placement[0]) == pytest.approx(1.0, abs=1e-9)
    assert float(node.placement[1]) == pytest.approx(0.0, abs=1e-9)
    window.close()


def test_a_click_a_few_pixels_from_the_crossing_still_snaps(
    app: QApplication,
) -> None:
    """The eye aims between two strokes; 8 px is still the crossing."""
    controller = _line_circle()
    window = _window(controller)
    app.processEvents()
    scale = window.canvas._viewport().scale
    _click(window, 1.0 + 6.0 / scale, 0.0)
    app.processEvents()
    node = _made(controller, "point.intersect_line_circle")
    assert node.placement is not None
    assert float(node.placement[0]) == pytest.approx(1.0, abs=1e-6)
    window.close()


def test_the_other_branch_is_the_other_selector(app: QApplication) -> None:
    controller = _line_circle()
    window = _window(controller)
    app.processEvents()

    _click(window, -1.0, 0.0)
    app.processEvents()

    node = _made(controller, "point.intersect_line_circle")
    assert node.args == ["s", "w", "1"]
    assert node.placement is not None
    assert float(node.placement[0]) == pytest.approx(-1.0, abs=1e-9)
    window.close()


def test_two_circles_make_their_crossing(app: QApplication) -> None:
    controller = _two_circles()
    window = _window(controller)
    app.processEvents()

    _click(window, 0.5, math.sqrt(3) / 2)
    app.processEvents()

    node = _made(controller, "point.intersect_circles")
    assert node.args == ["w1", "w2", "0"]
    assert node.placement is not None
    assert float(node.placement[0]) == pytest.approx(0.5, abs=1e-9)
    assert float(node.placement[1]) == pytest.approx(math.sqrt(3) / 2, abs=1e-9)
    window.close()


def test_the_lower_circle_crossing_is_the_second_selector(
    app: QApplication,
) -> None:
    controller = _two_circles()
    window = _window(controller)
    app.processEvents()

    _click(window, 0.5, -math.sqrt(3) / 2)
    app.processEvents()

    node = _made(controller, "point.intersect_circles")
    assert node.args == ["w1", "w2", "1"]
    assert node.placement is not None
    assert float(node.placement[1]) == pytest.approx(-math.sqrt(3) / 2, abs=1e-9)
    window.close()


def test_a_click_on_the_circle_away_from_the_crossing_stays_on_the_circle(
    app: QApplication,
) -> None:
    controller = _line_circle()
    window = _window(controller)
    app.processEvents()

    _click(window, 0.0, 1.0)
    app.processEvents()

    node = _made(controller, "point.on_circle")
    assert node.args[0] == "w"
    window.close()


def test_a_click_on_the_line_away_from_the_crossing_stays_on_the_line(
    app: QApplication,
) -> None:
    controller = _line_circle(segment_to=5)
    window = _window(controller)
    app.processEvents()

    # Far enough from either crossing to mean the line itself.
    _click(window, 3.0, 0.0)
    app.processEvents()

    node = _made(controller, "point.on_line")
    assert node.args[0] == "s"
    window.close()


def test_a_click_a_pixel_from_a_line_crossing_is_still_the_crossing(
    app: QApplication,
) -> None:
    """The crossing has a small magnet, so a precise click need not be exact."""
    controller = _two_segments()
    window = _window(controller)
    app.processEvents()

    viewport = window.canvas._viewport()
    sx, sy = viewport.to_screen(0.0, 0.0)
    _click_at(window, sx + 1.5, sy - 1.0)
    app.processEvents()

    node = _made(controller, "point.intersect_lines")
    assert node.placement is not None
    assert float(node.placement[0]) == pytest.approx(0.0, abs=1e-9)
    window.close()


def test_a_crossing_beyond_the_drawn_segment_attaches_to_the_circle(
    app: QApplication,
) -> None:
    """The supporting line crosses the circle at (1, 0), but the segment stops at -1."""
    controller = _line_circle(segment_to=-1)
    window = _window(controller)
    app.processEvents()

    _click(window, 1.0, 0.0)
    app.processEvents()

    node = _made(controller, "point.on_circle")
    assert node.args[0] == "w"
    window.close()
