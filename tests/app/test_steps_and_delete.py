"""The construction list: numbered, deletable in bulk, coloured by verdict.

Three small things that make the left pane part of the lesson instead of
a debug log: a step number to refer to, Delete that means the selection
rather than the last click, and a claim that turns green or red once it
has been judged.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
except ImportError as exc:  # pragma: no cover - depends on the machine
    pytest.skip(f"Qt is not usable on this machine: {exc}", allow_module_level=True)

from geobench.app.controller import StudioController
from geobench.app.theme import PALETTE
from geobench.app.window import NUMBER_ROLE, TINT_ROLE, StudioWindow


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _figure() -> StudioController:
    controller = StudioController()
    controller.add_free_point(0, 0, "A")
    controller.add_free_point(6, 0, "B")
    controller.add_free_point(2, 4, "C")
    controller.construct("point.midpoint", ["A", "B"], "M")
    controller.add_relation("collinear", ["A", "M", "B"])
    controller.add_relation("collinear", ["A", "C", "B"])
    return controller


def test_the_steps_are_numbered(app: QApplication) -> None:
    controller = _figure()
    window = StudioWindow(controller)
    window.show()
    app.processEvents()

    texts = [window.steps.item(row).text() for row in range(window.steps.count())]
    numbers = [
        window.steps.item(row).data(NUMBER_ROLE)
        for row in range(window.steps.count())
    ]
    assert numbers == list(range(1, len(texts) + 1))
    assert texts[0].startswith("1.")
    # The relations continue the numbering: they are steps too.
    figure = controller.figure()
    first_relation = len(figure.nodes) + 1
    assert texts[first_relation - 1].startswith(f"{first_relation}.")
    assert texts[-1].startswith(f"{len(figure.nodes) + len(figure.relations)}.")
    window.close()


def test_delete_removes_the_whole_selection_in_one_step(app: QApplication) -> None:
    controller = StudioController()
    for name in ("A", "B", "C"):
        controller.add_free_point(0, 0, name)
    window = StudioWindow(controller)
    window.show()
    app.processEvents()

    window.canvas.select("A")
    window.canvas.select("C", additive=True)
    window.canvas.setFocus()
    QTest.keyClick(window.canvas, Qt.Key.Key_Delete)
    app.processEvents()

    assert set(controller.figure().nodes) == {"B"}
    assert controller.undo()
    app.processEvents()
    assert set(controller.figure().nodes) == {"A", "B", "C"}
    window.close()


def test_a_proved_claim_and_a_refuted_claim_are_coloured(
    app: QApplication,
) -> None:
    controller = _figure()
    window = StudioWindow(controller)
    window.show()
    app.processEvents()

    controller.evaluate_exact()
    verdicts = controller.judge()
    window._judge_request += 1
    window._on_verdicts(window._judge_request, verdicts)

    relations = controller.figure().relations
    proved_row = window._relation_rows[relations[0].id]
    refuted_row = window._relation_rows[relations[1].id]
    assert window.steps.item(proved_row).data(TINT_ROLE) == PALETTE.ok
    assert window.steps.item(refuted_row).data(TINT_ROLE) == PALETTE.danger
    assert "成立" in window.steps.item(proved_row).toolTip()
    assert "不成立" in window.steps.item(refuted_row).toolTip()
    window.close()
