"""The judgement pane follows the teacher, not the command table.

A teacher does not begin with "show me all seventeen relations"; they
begin by pointing at the figure -- these three points, this line and
that circle -- and asking a question about what they pointed at.

So the pane has two layers: a short list of claims that fit the current
selection, and the full catalogue folded away.  The verdict is a
sentence, the algebra is behind a fold, and a counterexample can be put
on the canvas to be seen.
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
from geobench.app.window import StudioWindow


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _controller(on: tuple[str, str] = ("A", "B")) -> StudioController:
    """A triangle, a midpoint, and a segment on each side."""
    controller = StudioController()
    controller.add_free_point(0, 0, "A")
    controller.add_free_point(6, 0, "B")
    controller.add_free_point(2, 4, "C")
    controller.construct("point.midpoint", list(on), "M")
    controller.construct("segment.free", ["A", "B"], "AB")
    controller.construct("segment.free", ["A", "C"], "AC")
    return controller


def _offered(window: StudioWindow) -> dict[str, QPushButton]:
    return {
        button.text(): button
        for button in window._context_box.findChildren(QPushButton)
    }


def test_selecting_three_points_offers_the_claim_about_them(
    app: QApplication,
) -> None:
    controller = _controller(("A", "B"))
    window = StudioWindow(controller)
    window.canvas.select("A")
    window.canvas.select("B", additive=True)
    window.canvas.select("M", additive=True)

    offered = _offered(window)
    assert "共线" in offered, offered
    # The catalogue is folded away: the teacher asked about three
    # points, not for all seventeen relations.
    assert window._all_relations.isHidden()
    window.close()


def test_the_claim_is_added_without_a_dialog(app: QApplication) -> None:
    controller = _controller(("A", "B"))
    window = StudioWindow(controller)
    controller.evaluate_exact()

    window.canvas.select("A")
    window.canvas.select("B", additive=True)
    window.canvas.select("M", additive=True)
    _offered(window)["共线"].click()

    relations = controller.figure().relations
    assert [(relation.kind, relation.args) for relation in relations] == [
        ("collinear", ["A", "B", "M"])
    ]
    window.close()


def test_a_line_and_a_line_get_parallel_not_collinear(app: QApplication) -> None:
    controller = _controller()
    window = StudioWindow(controller)
    window.canvas.select("AB")
    window.canvas.select("AC", additive=True)

    offered = _offered(window)
    assert "平行" in offered, offered
    assert "共线" not in offered
    assert "垂直（线·线）" in offered
    window.close()


def test_a_selection_that_fits_nothing_says_so(app: QApplication) -> None:
    controller = _controller()
    window = StudioWindow(controller)
    window.canvas.select("A")
    assert "没有能直接问的问题" in window._context_hint.text()
    window.close()


def _judge_now(window: StudioWindow) -> None:
    """Judge synchronously and show the verdicts, without a worker.

    The screen judges in a thread; a test that waits for a thread is a
    test that fails on a busy machine.  This is the same table fill,
    called directly.
    """
    controller = window.controller
    controller.evaluate_exact()
    verdicts = controller.judge()
    window._judge_request += 1
    window._on_verdicts(window._judge_request, verdicts)


def test_the_table_reads_as_sentences(app: QApplication) -> None:
    controller = _controller(("A", "B"))
    controller.add_relation("collinear", ["A", "B", "M"])
    window = StudioWindow(controller)
    _judge_now(window)

    assert window._verdicts
    assert window.judgements.item(0, 0).text() == "A、B、M 共线"
    assert window.judgements.item(0, 1).text() == "成立"
    assert window.judgements.item(0, 2).text() == "对任意图形都成立"
    window.close()


def test_a_counterexample_can_be_put_on_the_canvas(app: QApplication) -> None:
    """The claim is false: M is the midpoint of BC, not on AB."""
    controller = _controller(("B", "C"))
    controller.add_relation("collinear", ["A", "B", "M"])
    window = StudioWindow(controller)
    _judge_now(window)

    assert window._verdicts
    assert window.judgements.item(0, 1).text() == "不成立"
    window.judgements.selectRow(0)
    assert not window.witness_button.isHidden()
    assert "有一个合法的摆放" in window.evidence_summary.text()

    before = {name: controller.figure().nodes[name].placement for name in ("A", "B", "C")}
    window.witness_button.click()
    after = {name: controller.figure().nodes[name].placement for name in ("A", "B", "C")}
    assert after != before, "the counterexample did not move the free points"

    assert controller.undo()
    restored = {
        name: controller.figure().nodes[name].placement for name in ("A", "B", "C")
    }
    assert restored == before
    window.close()
