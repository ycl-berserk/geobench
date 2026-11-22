"""One dialog, one undo step, one intention.

"Make this the key point: red, bigger, label on the right" used to be
three menu visits.  The dialog changes appearance only, and the
controller applies all of it at once.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
except ImportError as exc:  # pragma: no cover - depends on the machine
    pytest.skip(f"Qt is not usable on this machine: {exc}", allow_module_level=True)

from geobench.app.appearance_dialog import AppearanceDialog
from geobench.app.controller import StudioController
from geobench.app.window import StudioWindow


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def controller() -> StudioController:
    controller = StudioController()
    controller.add_free_point(0, 0, "A")
    controller.add_free_point(4, 0, "B")
    controller.construct("segment.free", ["A", "B"], "l")
    return controller


def test_every_appearance_change_is_one_undo_step(
    controller: StudioController,
) -> None:
    before = controller.figure().nodes["A"].style
    controller.set_appearance(
        "A",
        color="#c0392b",
        line_width=0.7,
        point_size=4.5,
        label_pos="右上",
        label="D",
    )
    style = controller.figure().nodes["A"].style
    assert style.color == "#c0392b"
    assert style.line_width == 0.7
    assert style.point_size == 4.5
    assert style.label_pos == "右上"
    assert style.label == "D"

    assert controller.undo()
    assert controller.figure().nodes["A"].style == before


def test_appearance_never_moves_the_geometry(controller: StudioController) -> None:
    coords = controller.figure().nodes["A"].coords
    placement = controller.figure().nodes["A"].placement
    controller.set_appearance("A", color="#1f4e9e", point_size=4.5, label="P")
    node = controller.figure().nodes["A"]
    assert node.coords == coords
    assert node.placement == placement


def test_no_change_pushes_no_undo(controller: StudioController) -> None:
    depth = len(controller._undo)
    controller.set_appearance("A", color="#000000")
    assert len(controller._undo) == depth


def test_the_dialog_shows_what_is_already_set(
    app: QApplication, controller: StudioController
) -> None:
    controller.set_color("A", "#c0392b")
    controller.set_point_size("A", 4.5)
    controller.set_label_pos("A", "右上")
    window = StudioWindow(controller)
    dialog = AppearanceDialog(window, controller.figure().nodes["A"])
    values = dialog.values()
    assert values["color"] == "#c0392b"
    assert values["point_size"] == 4.5
    assert values["label_pos"] == "右上"
    window.close()


def test_the_dialog_returns_every_field_at_once(
    app: QApplication, controller: StudioController
) -> None:
    window = StudioWindow(controller)
    dialog = AppearanceDialog(window, controller.figure().nodes["A"])
    dialog.label_edit.setText("D")
    dialog.size_box.setCurrentIndex(dialog.size_box.findData(2.0))
    dialog.width_box.setCurrentIndex(dialog.width_box.findData(0.7))
    dialog.position_box.setCurrentIndex(dialog.position_box.findData("左下"))
    dialog._pick("#7d3c98")

    values = dialog.values()
    assert values["label"] == "D"
    assert values["point_size"] == 2.0
    assert values["line_width"] == 0.7
    assert values["label_pos"] == "左下"
    assert values["color"] == "#7d3c98"
    window.close()


def test_a_segment_has_no_point_only_fields(
    app: QApplication, controller: StudioController
) -> None:
    window = StudioWindow(controller)
    dialog = AppearanceDialog(window, controller.figure().nodes["l"])
    assert not hasattr(dialog, "size_box")
    assert not hasattr(dialog, "position_box")
    assert set(dialog.values()) == {"color", "line_width", "label"}
    window.close()


def test_the_menu_has_the_properties_entry(
    app: QApplication, controller: StudioController
) -> None:
    window = StudioWindow(controller)
    menu = window.canvas._object_menu("A")
    assert any(action.text() == "属性…" for action in menu.actions())
    window.close()
