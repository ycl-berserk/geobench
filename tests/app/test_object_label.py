"""The object's label: the name on the paper, not the name in the file.

A competition figure has to call its objects what the problem calls
them.  A midpoint built as ``M`` may be ``D`` in the statement, and a
figure that says M while the paper says D is a figure with a mistake in
it -- so the label is something the teacher can change, without
renaming the construction (which would break every relation that names
it).

The label is a *style* attribute, so it never touches the geometry, and
the picture already reads it (``primitives`` prefers
``node.style.label`` over the node's own name).
"""

from __future__ import annotations

import pytest

from geobench.app.controller import StudioController
from geobench.operators import register_builtins
from geobench.primitives import figure_primitives
from geobench.registry import OperatorRegistry
from geobench.style import COMPETITION


@pytest.fixture()
def controller() -> StudioController:
    registry = OperatorRegistry()
    register_builtins(registry)
    return StudioController(registry)


def _labels(controller: StudioController) -> dict[str, str]:
    """What each point is called on the drawing."""
    primitives = figure_primitives(controller.figure(), COMPETITION)
    return {
        primitive.id: primitive.label
        for primitive in primitives
        if primitive.__class__.__name__ == "PointPrimitive"
    }


def test_a_point_is_called_by_its_name_until_something_else_is_asked(
    controller: StudioController,
) -> None:
    point = controller.add_free_point(2.0, 3.0, "M")
    assert _labels(controller)[point] == "M"


def test_the_label_can_be_changed_without_renaming_the_object(
    controller: StudioController,
) -> None:
    """The construction keeps ``M``; the paper says ``D``."""
    point = controller.add_free_point(2.0, 3.0, "M")
    controller.set_label(point, "D")
    assert point in controller.figure().nodes
    assert _labels(controller)[point] == "D"


def test_an_empty_label_falls_back_to_the_name(controller: StudioController) -> None:
    point = controller.add_free_point(2.0, 3.0, "M")
    controller.set_label(point, "D")
    controller.set_label(point, "")
    assert _labels(controller)[point] == "M"


def test_the_label_change_can_be_undone(controller: StudioController) -> None:
    point = controller.add_free_point(2.0, 3.0, "M")
    controller.set_label(point, "D")
    controller.undo()
    assert _labels(controller)[point] == "M"


def test_a_label_does_not_change_the_geometry(controller: StudioController) -> None:
    point = controller.add_free_point(2.0, 3.0, "M")
    before = controller.figure().nodes[point].coords
    controller.set_label(point, "D")
    assert controller.figure().nodes[point].coords == before
