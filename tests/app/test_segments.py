"""Segments are first-class, and a click at a crossing is the crossing.

Two complaints from the teacher:

* "画垂线和平行线都要求线是直线而不能是线段, 但实际上竞赛当中大部分都是线段"
  -- a perpendicular or a parallel to a *segment* has to work, because a
  competition figure is made of segments.

* "我没有办法点出两条线/线段的交点, 不管怎么点都会有自由度" -- clicking
  where two objects cross should give their crossing, which is a point
  with no freedom of its own, and not a free point that happens to be
  in the same place.
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
    controller = StudioController()
    controller.add_free_point(-2, 0, "A")
    controller.add_free_point(2, 0, "B")
    controller.add_free_point(0, -2, "C")
    controller.add_free_point(0, 2, "D")
    controller.construct("segment.free", ["A", "B"], "s1")
    controller.construct("segment.free", ["C", "D"], "s2")
    return controller


def _click(window: StudioWindow, x: float, y: float) -> None:
    viewport = window.canvas._viewport()
    sx, sy = viewport.to_screen(x, y)
    press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(sx, sy),
        QPointF(sx, sy),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    release = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPointF(sx, sy),
        QPointF(sx, sy),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.canvas.mousePressEvent(press)
    window.canvas.mouseReleaseEvent(release)


def _attached(controller: StudioController) -> list:
    return [n for n in controller.figure().nodes.values() if n.role == "attached"]


def test_a_perpendicular_to_a_segment(controller: StudioController) -> None:
    """The foot of a perpendicular on a segment is a foot on a line."""
    controller.construct("line.perpendicular_through", ["A", "s1"], "p")
    node = controller.figure().nodes["p"]
    assert node.kind == "line"


def test_a_parallel_to_a_segment(controller: StudioController) -> None:
    controller.construct("line.parallel_through", ["C", "s1"], "p")
    assert controller.figure().nodes["p"].kind == "line"


def test_the_parallel_is_parallel_to_the_segment(controller: StudioController) -> None:
    """Not just any line: the same direction as the segment."""
    controller.construct("line.parallel_through", ["C", "s1"], "p")
    figure = controller.figure()
    segment = figure.nodes["s1"]
    parallel = figure.nodes["p"]
    assert segment.cache["segment"] is not None
    assert parallel.cache["line"] is not None


def test_the_point_tool_on_a_segment_makes_a_point_on_it(
    app: QApplication, controller: StudioController
) -> None:
    """A point on a segment is a construction, like a point on a circle."""
    window = StudioWindow(controller)
    window.resize(1000, 700)
    window.show()
    app.processEvents()

    _click(window, -1.0, 0.0)  # a quarter of the way along s1
    app.processEvents()

    points = _attached(controller)
    assert points, [n.id for n in controller.figure().nodes.values()]
    node = points[0]
    assert node.op == "point.on_line"
    assert node.args[0] == "s1"
    assert node.args[1] == "1/4"
    window.close()


def test_the_point_tool_at_a_crossing_makes_the_crossing(
    app: QApplication, controller: StudioController
) -> None:
    """A point with no freedom of its own: the intersection."""
    window = StudioWindow(controller)
    window.resize(1000, 700)
    window.show()
    app.processEvents()

    _click(window, 0.0, 0.0)  # where s1 and s2 cross
    app.processEvents()

    derived = [
        n
        for n in controller.figure().nodes.values()
        if n.op == "point.intersect_lines"
    ]
    assert derived, [n.id for n in controller.figure().nodes.values()]
    node = derived[0]
    assert node.role == "derived"
    assert sorted(node.args) == ["s1", "s2"]
    assert node.placement is not None
    assert float(node.placement[0]) == pytest.approx(0.0, abs=1e-9)
    assert float(node.placement[1]) == pytest.approx(0.0, abs=1e-9)
    window.close()


def test_dragging_a_point_on_a_segment_slides_it(controller: StudioController) -> None:
    """It moves along the segment, and stays on it."""
    controller.construct("point.on_line", ["s1", "0"], "P")
    controller.move_point("P", 1.0, 0.0)
    controller.finish_move()

    node = controller.figure().nodes["P"]
    assert node.role == "attached"
    assert node.args[1] == "3/4"
    assert node.placement is not None
    assert float(node.placement[0]) == pytest.approx(1.0, abs=1e-6)
    assert float(node.placement[1]) == pytest.approx(0.0, abs=1e-6)


def test_a_point_cannot_be_dragged_off_its_segment(controller: StudioController) -> None:
    """The parameter is clamped: the point stays on the segment."""
    controller.construct("point.on_line", ["s1", "1/2"], "P")
    controller.move_point("P", 50.0, 50.0)
    controller.finish_move()

    node = controller.figure().nodes["P"]
    assert node.placement is not None
    assert float(node.placement[0]) == pytest.approx(2.0, abs=1e-6)
    assert float(node.placement[1]) == pytest.approx(0.0, abs=1e-6)


def test_the_judge_proves_the_point_is_on_the_segment(
    controller: StudioController,
) -> None:
    """The constraint is a theorem, not a promise."""
    controller.construct("point.on_line", ["s1", "3/8"], "P")
    controller.add_relation("point_in", ["P", "s1"])
    verdicts = controller.judge("identity")
    assert verdicts[0].verdict == "proved"


def test_the_constraint_is_in_the_file(controller: StudioController) -> None:
    """It survives a save."""
    controller.construct("point.on_line", ["s1", "1/4"], "P")
    source = controller.to_text()
    assert "P = 线上的点(s1, 1/4)" in source

    loaded = StudioController()
    loaded.load_text(source)
    node = loaded.figure().nodes["P"]
    assert node.role == "attached"
    assert node.args == ["s1", "1/4"]
