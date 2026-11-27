"""The judgement pane's front door is one sentence.

The old pane asked the teacher to pick one of seventeen relations and
then fill its slots.  The new pane asks for a sentence; the model only
translates it, and the local kernel still gives the verdict.  These
tests pin the two halves: the sentence box is what is on screen, and a
translated claim reaches the same table through the same judges.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
except ImportError as exc:  # pragma: no cover - depends on the machine
    pytest.skip(f"Qt is not usable on this machine: {exc}", allow_module_level=True)

from geobench.ai import Claim
from geobench.app.controller import StudioController
from geobench.app.window import StudioWindow
from geobench.judges import IDENTITY


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _controller() -> StudioController:
    controller = StudioController()
    controller.add_free_point(0, 0, "A")
    controller.add_free_point(6, 0, "B")
    controller.add_free_point(2, 4, "C")
    controller.construct("point.midpoint", ["A", "B"], "M")
    controller.construct("segment.free", ["A", "B"], "AB")
    return controller


def _judge_now(window: StudioWindow) -> None:
    controller = window.controller
    controller.evaluate_exact()
    verdicts = controller.judge()
    window._judge_request += 1
    window._on_verdicts(window._judge_request, verdicts)


def test_the_default_view_is_a_sentence_box(app: QApplication) -> None:
    window = StudioWindow(_controller())
    assert window.claim_edit.placeholderText()
    assert window.claim_button.text() == "判定"
    # The old chips and catalogue are there for offline use, but folded.
    assert window._manual_box.isHidden()
    window.close()


def test_without_a_model_the_manual_way_is_offered(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = StudioWindow(_controller())
    monkeypatch.setattr(
        "geobench.app.window.resolve_provider",
        lambda: type("Resolution", (), {"provider": None})(),
    )
    window.claim_edit.setText("A、B、M 共线吗？")
    window._ask_judgement()
    assert not window._manual_box.isHidden()
    assert "没有配置模型服务" in window.claim_status.text()
    window.close()


def test_a_translated_claim_is_judged_by_the_kernel(app: QApplication) -> None:
    controller = _controller()
    window = StudioWindow(controller)
    window._accept_claims(
        [Claim("collinear", ("A", "B", "M"), IDENTITY)]
    )
    assert [
        (relation.kind, relation.args) for relation in controller.figure().relations
    ] == [("collinear", ["A", "B", "M"])]

    _judge_now(window)
    assert window.judgements.item(0, 0).text() == "A、B、M 共线"
    assert window.judgements.item(0, 1).text() == "成立"
    window.close()


def test_too_many_wrong_objects_never_reach_the_kernel(app: QApplication) -> None:
    controller = _controller()
    window = StudioWindow(controller)
    window._accept_claims(
        [Claim("collinear", ("A", "B", "Z"), IDENTITY)]
    )
    assert controller.figure().relations == []
    assert "Z" in window.claim_status.text()
    window.close()


def test_a_relation_and_its_objects_must_fit(app: QApplication) -> None:
    controller = _controller()
    window = StudioWindow(controller)
    # collinear takes three points; AB is a segment.
    window._accept_claims([Claim("collinear", ("A", "B", "AB"), IDENTITY)])
    assert controller.figure().relations == []
    assert "AB" in window.claim_status.text()
    window.close()


def test_a_claim_already_asked_is_not_added_twice(app: QApplication) -> None:
    controller = _controller()
    controller.add_relation("collinear", ["A", "B", "M"])
    window = StudioWindow(controller)
    window._accept_claims(
        [Claim("collinear", ("A", "B", "M"), IDENTITY)]
    )
    assert len(controller.figure().relations) == 1
    assert "已经问过" in window.claim_status.text()
    window.close()
