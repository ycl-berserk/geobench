"""A point placed on a circle stays on the circle.

This is the user's complaint: a point made on a circle was free, and
slid off. Placing a point on an object is a **construction** -- the
parameter is part of it, and it is in the file -- so the point follows
the circle when the circle moves, and the judge can prove that it is on
the circle.
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


def _circle(controller: StudioController) -> None:
    controller.add_free_point(0, 0, "O")
    controller.add_free_point(4, 0, "A")
    controller.construct("circle.center_point", ["O", "A"], "w")


def test_a_point_on_a_circle_is_on_the_circle(controller: StudioController) -> None:
    """The coordinates come from the circle, so the point cannot leave it."""
    _circle(controller)
    controller.construct("point.on_circle", ["w", "1/4"], "P")
    figure = controller.figure()
    # A quarter turn from east: straight up from the centre. The
    # placement is a display value, so it is a float and compared as one.
    placement = figure.nodes["P"].placement
    assert placement is not None
    assert float(placement[0]) == pytest.approx(0.0, abs=1e-9)
    assert float(placement[1]) == pytest.approx(4.0, abs=1e-9)

    controller.add_relation("point_in", ["P", "w"])
    verdicts = controller.judge("identity")
    assert verdicts[0].verdict == "proved"


def test_the_point_follows_the_circle(controller: StudioController) -> None:
    """Move the centre and the point moves with it -- it is on the circle."""
    _circle(controller)
    controller.construct("point.on_circle", ["w", "1/4"], "P")
    controller.move_point("O", 10, 10)
    controller.finish_move()
    # The circle's radius is |OA|, and A has not moved: so the point is
    # straight above the new centre, at the new radius.
    node = controller.figure().nodes["P"]
    assert node.placement is not None
    assert float(node.placement[0]) == pytest.approx(10.0, abs=0.01)
    assert float(node.placement[1]) == pytest.approx(10 + ((-6) ** 2 + (-10) ** 2) ** 0.5, abs=0.01)


def test_dragging_a_point_on_a_circle_slides_it(controller: StudioController) -> None:
    """Dragging changes where on the circle it is, never whether."""
    _circle(controller)
    controller.construct("point.on_circle", ["w", "0"], "P")

    controller.move_point("P", 0, 4.0)  # drag it to the top of the circle
    figure = controller.figure()
    node = figure.nodes["P"]
    assert node.role == "attached"
    assert node.args[1] == "1/4"
    assert node.placement is not None
    assert float(node.placement[0]) == pytest.approx(0.0, abs=0.01)
    assert float(node.placement[1]) == pytest.approx(4.0, abs=0.01)


def test_the_constraint_is_in_the_file(controller: StudioController) -> None:
    """The construction, not a hidden promise: it survives a save."""
    _circle(controller)
    controller.construct("point.on_circle", ["w", "1/4"], "P")
    source = controller.to_text()
    assert "P = 圆上的点(w, 1/4)" in source

    loaded = StudioController()
    loaded.load_text(source)
    node = loaded.figure().nodes["P"]
    assert node.role == "attached"
    assert node.args == ["w", "1/4"]


def test_the_point_tool_lands_on_a_circle(
    app: QApplication, controller: StudioController
) -> None:
    """Clicking on a circle with the point tool makes a point on it."""
    window = StudioWindow(controller)
    window.resize(1000, 700)
    window.show()
    app.processEvents()
    _circle(controller)
    app.processEvents()

    viewport = window.canvas._viewport()
    sx, sy = viewport.to_screen(0.0, 4.0)  # on the circle, and not on a point
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
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.canvas.mousePressEvent(press)
    window.canvas.mouseReleaseEvent(release)
    app.processEvents()

    attached = [n for n in controller.figure().nodes.values() if n.role == "attached"]
    assert attached, [n.id for n in controller.figure().nodes.values()]
    assert attached[0].args[0] == "w"
    window.close()
