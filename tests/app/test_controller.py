"""The studio's behaviour, without a window.

The controller is the model behind the window, and it is where the
interesting behaviour lives: adding a point, building on it, dragging it,
and asking what is true. None of that needs Qt, so none of it is tested
through Qt.
"""

from __future__ import annotations

import pytest

from geobench.app.controller import StudioController
from geobench.errors import GeobenchError


def _triangle() -> StudioController:
    controller = StudioController()
    controller.add_free_point(0, 0, "A")
    controller.add_free_point(6, 0, "B")
    controller.add_free_point(2, 4, "C")
    controller.construct("point.midpoint", ["A", "B"], "M")
    return controller


def test_a_free_point_gets_a_position() -> None:
    controller = StudioController()
    node_id = controller.add_free_point(3, 5)
    assert controller.point_positions()[node_id] == (3.0, 5.0)


def test_free_points_are_labelled_in_order() -> None:
    controller = StudioController()
    assert controller.add_free_point(0, 0) == "A"
    assert controller.add_free_point(1, 0) == "B"
    assert controller.add_free_point(2, 0) == "C"


def test_a_construction_follows_its_inputs() -> None:
    controller = _triangle()
    assert controller.point_positions()["M"] == (3.0, 0.0)


def test_dragging_a_point_moves_what_depends_on_it() -> None:
    """This is the whole product in one call: drag A, and M follows."""
    controller = _triangle()
    controller.move_point("A", 2, 0)
    assert controller.point_positions()["M"] == (4.0, 0.0)


def test_the_judgement_survives_a_drag() -> None:
    """An identity verdict is about every placement, so it cannot change."""
    controller = _triangle()
    controller.add_relation("collinear", ["A", "M", "B"])
    before = controller.judge()[0]
    assert before.verdict == "proved"

    controller.move_point("A", 1, 3)
    after = controller.judge()[0]
    assert after.verdict == "proved"


def test_a_false_claim_is_refuted() -> None:
    controller = _triangle()
    controller.add_relation("collinear", ["A", "M", "C"])
    assert controller.judge()[0].verdict == "refuted"


def test_a_refutation_carries_a_counterexample() -> None:
    controller = _triangle()
    controller.add_relation("collinear", ["A", "M", "C"])
    verdict = controller.judge()[0]
    assert verdict.verdict == "refuted"
    assert verdict.witness, "a refutation must say where it fails"


def test_an_unknown_node_is_refused_with_the_legal_ids() -> None:
    controller = _triangle()
    with pytest.raises(GeobenchError) as failure:
        controller.construct("point.midpoint", ["A", "Q"])
    message = str(failure.value)
    assert "'Q'" in message
    assert "A" in message and "B" in message


def test_a_degenerate_construction_leaves_the_object_undefined() -> None:
    """Three collinear points have no circumcircle; the rest survives."""
    controller = StudioController()
    controller.add_free_point(0, 0, "A")
    controller.add_free_point(4, 0, "B")
    controller.add_free_point(8, 0, "C")
    controller.construct("point.circumcenter", ["A", "B", "C"], "O")
    undefined = dict(controller.undefined())
    assert "O" in undefined
    assert controller.point_positions()["A"] == (0.0, 0.0)


def test_removing_a_point_removes_what_depends_on_it() -> None:
    controller = _triangle()
    controller.remove_node("A")
    assert "M" not in controller.figure().nodes
    assert "A" not in controller.figure().nodes


def test_the_primitives_follow_the_figure() -> None:
    controller = _triangle()
    labels = {
        primitive.label
        for primitive in controller.primitives()
        if hasattr(primitive, "label")
    }
    assert {"A", "B", "C", "M"} <= labels
