"""Object attributes: hiding an object, and marking it auxiliary.

A competition figure needs exactly two of them, and GeoGebra has both in
the object's context menu: the scaffolding is hidden, and the
auxiliary line -- the altitude, the perpendicular bisector -- is drawn
dashed, because it supports the figure but is not part of the problem's
statement.

The model and the drawing already knew about both. What was missing was
anybody able to set them, and any way to save them.
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
from geobench.primitives import figure_primitives


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


def _drawn(controller: StudioController) -> set[str]:
    return {
        primitive.id
        for primitive in figure_primitives(controller.figure(), controller.style)
        if primitive.id
    }


def test_a_hidden_object_is_not_drawn(controller: StudioController) -> None:
    """It is still there; it is just not in the picture."""
    assert "l" in _drawn(controller)
    controller.set_hidden("l", True)
    assert "l" not in _drawn(controller)
    # the construction is untouched: the object is still in the figure
    assert "l" in controller.figure().nodes


def test_an_auxiliary_object_is_drawn_dashed(controller: StudioController) -> None:
    """Auxiliary objects are drawn first, so the figure is on top of them."""
    controller.set_auxiliary("l", True)
    primitives = [
        primitive
        for primitive in figure_primitives(controller.figure(), controller.style)
        if primitive.id == "l"
    ]
    assert primitives
    assert primitives[0].auxiliary is True


def test_the_attributes_can_be_undone(controller: StudioController) -> None:
    """Hiding is a step, like everything else."""
    controller.set_hidden("l", True)
    assert "l" not in _drawn(controller)
    assert controller.undo()
    assert "l" in _drawn(controller)


def test_the_attributes_are_in_the_file(controller: StudioController) -> None:
    """A figure that keeps its conventions when it is saved."""
    controller.set_hidden("B", True)
    controller.set_auxiliary("l", True)
    source = controller.to_text()
    assert "隐藏 B" in source
    assert "辅助 l" in source

    loaded = StudioController()
    loaded.load_text(source)
    assert loaded.figure().nodes["B"].style.visible is False
    assert loaded.figure().nodes["l"].style.line_style == "dashed"


def test_the_picture_keeps_its_conventions_when_exported(
    app: QApplication, controller: StudioController
) -> None:
    """A dashed auxiliary line is dashed in the export too."""
    from geobench.app.export import svg_source

    controller.set_auxiliary("l", True)
    svg = svg_source(controller.figure(), controller.style)
    assert "stroke-dasharray" in svg
