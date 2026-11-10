"""Every relation the kernel can judge is on the panel.

The judges know seventeen relations; the panel used to offer seven,
and the ones missing were the ones a competition problem leans on:
比例相等, 等角, 点在, 相切, 三线共点. A claim you cannot check is a
claim you cannot use.

The picker changed with them: a relation is not a list of objects of
one kind. 点在 wants a point and then an object; 相切 wants a line and
then a circle. So the dialog has one slot per argument, and each slot
says what kind of object it wants.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication, QPushButton
except ImportError as exc:  # pragma: no cover - depends on the machine
    pytest.skip(f"Qt is not usable on this machine: {exc}", allow_module_level=True)

from geobench.app.controller import StudioController
from geobench.app.window import ObjectPicker, StudioWindow, _relations
from geobench.commands import COMMANDS, JUDGEMENT


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def controller() -> StudioController:
    controller = StudioController()
    controller.add_free_point(0, 0, "O")
    controller.add_free_point(4, 0, "A")
    controller.construct("circle.center_point", ["O", "A"], "w")
    return controller


def test_every_relation_the_judges_know_is_on_the_panel() -> None:
    """The panel is generated from the command table, so it cannot drift."""
    expected = {
        command.id
        for command in COMMANDS
        if command.kind == JUDGEMENT and command.implemented
    }
    assert expected, "the command table has no relations"
    on_the_panel = {spec.kind for spec in _relations()}
    assert expected <= on_the_panel, expected - on_the_panel
    # Seventeen relations, and the ones a competition leans on are among
    # them.
    assert len(on_the_panel) >= 17
    for wanted in ("ratio_equal", "angle_equal", "point_in", "tangent_to", "concurrency"):
        assert wanted in on_the_panel


def test_the_panel_has_a_button_for_each_relation(
    app: QApplication, controller: StudioController
) -> None:
    window = StudioWindow(controller)
    window.show()
    app.processEvents()
    labels = {
        button.text()
        for button in window.findChildren(QPushButton)
    }
    for spec in _relations():
        assert spec.label in labels, spec.label
    window.close()


def test_each_relation_knows_what_kinds_of_object_it_wants() -> None:
    """点在 wants a point and then an object; 相切 wants a line and a circle."""
    kinds = {spec.kind: spec.arg_kinds for spec in _relations()}
    assert kinds["point_in"] == ("point", "any")
    assert kinds["tangent_to"] == ("line", "circle")
    assert kinds["collinear"] == ("point", "point", "point")
    assert kinds["parallel"] == ("line", "line")


def test_the_picker_has_one_slot_per_argument(
    app: QApplication, controller: StudioController
) -> None:
    """A slot says what it wants, and offers only what it wants."""
    window = StudioWindow(controller)
    slots = [
        ("点", ["O", "A"]),
        ("圆", ["w"]),
    ]
    picker = ObjectPicker(window, slots, "检查点在")
    assert len(picker.combos) == 2
    assert picker.combos[0].count() == 2
    assert picker.combos[1].count() == 1
    assert picker.combos[1].currentText() == "w"
    window.close()
