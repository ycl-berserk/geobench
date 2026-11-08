"""Deleting an object.

Deleting a point deletes what depends on it and the claims about it:
an object and everything that only exists because of it go together,
and leaving half of it behind is worse than leaving all of it.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
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


def _figure(controller: StudioController) -> None:
    controller.add_free_point(0, 0, "A")
    controller.add_free_point(6, 0, "B")
    controller.add_free_point(2, 4, "C")
    controller.construct("point.midpoint", ["A", "B"])
    controller.add_relation("collinear", ["A", "M", "B"])


def test_deleting_a_point_takes_its_dependents_and_claims(
    controller: StudioController,
) -> None:
    _figure(controller)
    assert "M" in controller.figure().nodes
    assert controller.figure().relations

    controller.remove_node("A")

    assert "A" not in controller.figure().nodes
    # The midpoint depended on A, so it goes too.
    assert "M" not in controller.figure().nodes
    # And the claim named A, so it goes too.
    assert not controller.figure().relations
    # The rest of the figure is intact.
    assert {"B", "C"} <= set(controller.figure().nodes)


def test_a_delete_can_be_undone(controller: StudioController) -> None:
    _figure(controller)
    before = list(controller.figure().nodes)
    controller.remove_node("A")
    controller.undo()
    assert list(controller.figure().nodes) == before
    assert controller.figure().relations


def test_the_steps_pane_deletes_the_selected_object(
    app: QApplication, controller: StudioController
) -> None:
    window = StudioWindow(controller)
    window.show()
    app.processEvents()
    _figure(controller)
    app.processEvents()

    # Select the row for "C" and delete it.
    rows = [
        row
        for row in range(window.steps.count())
        if window.steps.item(row).text().startswith("C ")
    ]
    assert rows, [window.steps.item(row).text() for row in range(window.steps.count())]
    window.steps.setCurrentRow(rows[0])
    window.steps.item(rows[0]).setSelected(True)
    window._delete_selected_step()
    app.processEvents()

    assert "C" not in controller.figure().nodes
    window.close()


def test_deleting_a_relation_keeps_the_objects(
    app: QApplication, controller: StudioController
) -> None:
    window = StudioWindow(controller)
    window.show()
    app.processEvents()
    _figure(controller)
    app.processEvents()

    relation_rows = [
        row
        for row in range(window.steps.count())
        if window.steps.item(row).text().startswith("断言")
    ]
    assert relation_rows
    window.steps.setCurrentRow(relation_rows[0])
    window._delete_selected_step()
    app.processEvents()

    assert not controller.figure().relations
    assert {"A", "B", "C", "M"} <= set(controller.figure().nodes)
    window.close()


def test_the_canvas_asks_for_a_point_to_be_deleted(
    app: QApplication, controller: StudioController
) -> None:
    """A right click on a point emits the point's id."""
    window = StudioWindow(controller)
    window.resize(900, 600)
    window.show()
    app.processEvents()
    canvas = window.canvas
    controller.add_free_point(0, 0, "A")
    app.processEvents()

    asked: list[str] = []
    canvas.deleteRequested.connect(asked.append)
    from PySide6.QtCore import QPoint as _QPoint
    from PySide6.QtGui import QContextMenuEvent

    centre = canvas.rect().center()
    event = QContextMenuEvent(
        QContextMenuEvent.Reason.Mouse,
        _QPoint(centre.x(), centre.y()),
        canvas.mapToGlobal(_QPoint(centre.x(), centre.y())),
    )
    canvas.contextMenuEvent(event)
    app.processEvents()

    assert asked == ["A"]
    window.close()
