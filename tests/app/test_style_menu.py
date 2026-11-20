"""The object menu sets appearance, and it is one undo step.

The menu is where a teacher actually picks "make this line red": the DSL
is for people who like text, the menu is for people who like menus.  Both
go through the same controller calls, so they can never disagree.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication, QMenu
except ImportError as exc:  # pragma: no cover - depends on the machine
    pytest.skip(f"Qt is not usable on this machine: {exc}", allow_module_level=True)

from geobench.app.controller import StudioController
from geobench.app.window import StudioWindow
from geobench.primitives import SegmentPrimitive, figure_primitives


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


def _submenu(menu: QMenu, title: str) -> QMenu | None:
    for action in menu.actions():
        if action.text() == title and action.menu() is not None:
            return action.menu()
    return None


def _action(menu: QMenu, title: str):
    for action in menu.actions():
        if action.text() == title:
            return action
    return None


def test_the_menu_colours_a_segment(
    app: QApplication, controller: StudioController
) -> None:
    window = StudioWindow(controller)
    menu = window.canvas._object_menu("l")
    colors = _submenu(menu, "颜色")
    assert colors is not None
    action = _action(colors, "红")
    assert action is not None
    action.trigger()

    assert controller.figure().nodes["l"].style.color == "#c0392b"
    segment = next(
        p
        for p in figure_primitives(controller.figure(), controller.style)
        if isinstance(p, SegmentPrimitive)
    )
    assert segment.ink.color == "#c0392b"
    window.close()


def test_the_menu_sets_the_width_and_can_undo_it(
    app: QApplication, controller: StudioController
) -> None:
    window = StudioWindow(controller)
    menu = window.canvas._object_menu("l")
    widths = _submenu(menu, "线宽")
    assert widths is not None
    _action(widths, "粗").trigger()
    assert controller.figure().nodes["l"].style.line_width == 0.7

    assert controller.undo()
    assert controller.figure().nodes["l"].style.line_width is None
    window.close()


def test_a_segment_has_no_point_only_menus(
    app: QApplication, controller: StudioController
) -> None:
    window = StudioWindow(controller)
    menu = window.canvas._object_menu("l")
    assert _submenu(menu, "点大小") is None
    assert _submenu(menu, "标签位置") is None
    window.close()


def test_a_point_has_size_and_label_position(
    app: QApplication, controller: StudioController
) -> None:
    window = StudioWindow(controller)
    menu = window.canvas._object_menu("A")
    sizes = _submenu(menu, "点大小")
    positions = _submenu(menu, "标签位置")
    assert sizes is not None and positions is not None
    _action(sizes, "大").trigger()
    _action(positions, "右上").trigger()

    style = controller.figure().nodes["A"].style
    assert style.point_size == 4.5
    assert style.label_pos == "右上"
    window.close()


def test_the_menu_reflects_what_is_already_set(
    app: QApplication, controller: StudioController
) -> None:
    controller.set_color("l", "#c0392b")
    window = StudioWindow(controller)
    colors = _submenu(window.canvas._object_menu("l"), "颜色")
    assert colors is not None
    red = _action(colors, "红")
    assert red is not None and red.isChecked()
    window.close()
