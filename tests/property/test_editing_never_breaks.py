"""Editing a figure at random must never break it.

Every one of the crashes this test rules out was found the same way: a
person clicked around and the paint event died. The invariant is
simple, and worth stating once: **whatever the user does, the figure
can be drawn**.

The sessions are seeded, so a failure is reproducible.
"""

from __future__ import annotations

import os
import random

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from geobench.app.controller import StudioController
from geobench.primitives import figure_primitives

OPS: tuple[tuple[str, int], ...] = (
    ("point.midpoint", 2),
    ("point.centroid", 3),
    ("point.circumcenter", 3),
    ("line.perpendicular_bisector", 2),
    ("line.angle_bisector", 3),
    ("circle.through", 3),
    ("arc.three_points", 3),
    ("sector.three_points", 3),
    ("polygon.free", 3),
    ("measure.distance", 2),
    ("measure.angle", 3),
)

RELATIONS = ("collinear", "equal_length", "concyclic", "parallel")


def _session(seed: int, steps: int = 30) -> None:
    rng = random.Random(seed)
    controller = StudioController()
    for _ in range(steps):
        choice = rng.random()
        points = sorted(controller.point_positions())
        if choice < 0.22 or not points:
            controller.add_free_point(
                float(rng.randint(-8, 8)), float(rng.randint(-8, 8))
            )
        elif choice < 0.55:
            op, arity = OPS[rng.randrange(len(OPS))]
            if len(points) >= arity:
                controller.construct(op, points[:arity])
        elif choice < 0.63:
            controller.undo()
        elif choice < 0.69:
            controller.redo()
        elif choice < 0.76:
            controller.move_point(
                points[0], rng.uniform(-8, 8), rng.uniform(-8, 8)
            )
        elif choice < 0.83:
            if len(points) >= 3:
                controller.add_relation(
                    RELATIONS[rng.randrange(len(RELATIONS))], points[:3]
                )
        elif choice < 0.88:
            relations = list(controller.figure().relations)
            if relations:
                controller.remove_relation(relations[0].id)
        elif choice < 0.94:
            controller.load_text("点 A(0,0) B(6,0) C(2,4)\nl1 = 直线(A, B)\n")
        else:
            derived = [
                node for node in controller.figure().nodes.values() if node.role == "derived"
            ]
            if derived:
                controller.remove_node(derived[0].id)
        # The point of the whole exercise: the picture can be built.
        figure_primitives(controller.figure(), controller.style)


@pytest.mark.parametrize("seed", range(16))
def test_a_random_editing_session_never_breaks_the_picture(seed: int) -> None:
    _session(seed)


def test_a_point_dragged_to_a_fraction_keeps_the_figure_exact() -> None:
    """A placement is an exact rational, not a float.

    A dragged point lands on a fraction of a pixel, and the exact path
    refuses floats: a placement written as "1.5" made every judge fail
    with "expression contains a floating point part".
    """
    controller = StudioController()
    controller.add_free_point(0, 0, "A")
    controller.add_free_point(6, 0, "B")
    controller.add_free_point(2, 4, "C")
    controller.add_relation("collinear", ["A", "B", "C"])

    controller.move_point("C", 1.5, 2.25)
    placement = controller.figure().nodes["C"].placement
    assert placement == ("3/2", "9/4")
    # And the judge still runs on the moved figure.
    verdicts = controller.judge()
    assert verdicts[0].verdict in {"proved", "refuted", "supported", "undecided"}
