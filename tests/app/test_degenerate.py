"""The screen must tell the truth about a construction that produces nothing.

The kernel's verdict for a figure with a missing object is "cannot
decide" -- but a teacher reads the screen, not the kernel.  So the
screen has to say two things:

* the object that is missing is marked as missing, in the teacher's
  language, with the reason;
* the claim about it is "cannot decide", never "does not hold".

This is the file-level regression for the problem whose point P could
not exist: the line through the midpoint of BC perpendicular to BC is
the perpendicular bisector of BC, and the altitude from A is
perpendicular to BC too, so the two lines are parallel and P is not
there to be talked about.
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
from geobench.app.window import StudioWindow, _evidence_text, _undefined_text

#: The problem as it was written.
PROBLEM = """
点 A(2,3) B(0,0) C(5,0)
O = 外心(A,B,C)
H = 垂心(A,B,C)
D = 中点(B,C)
bc = 直线(B,C)
d = 垂直(D, bc)
ah = 直线(A,H)
P = 交点(d, ah)
ab = 直线(A,B)
ac = 直线(A,C)
de = 平行(D, ac)
df = 平行(D, ab)
E = 交点(de, ab)
F = 交点(df, ac)
"""


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def controller() -> StudioController:
    controller = StudioController()
    controller.load_text(PROBLEM)
    return controller


def test_the_missing_object_is_marked_as_missing(
    app: QApplication, controller: StudioController
) -> None:
    """P is hollow, and the steps pane says why -- in Chinese."""
    window = StudioWindow(controller)
    window.show()
    app.processEvents()

    tooltips = [
        window.steps.item(row).toolTip()
        for row in range(window.steps.count())
    ]
    missing = [tip for tip in tooltips if "没有值" in tip]
    assert missing, "the missing object is not marked in the steps pane"
    assert any("平行" in tip for tip in missing), missing
    window.close()


def test_the_claim_is_not_reported_as_false(
    app: QApplication, controller: StudioController
) -> None:
    """The judgement table must not say the theorem is false."""
    window = StudioWindow(controller)
    window.show()
    app.processEvents()
    controller.add_relation("collinear", ["P", "E", "F"])
    window._refresh_judgements()
    app.processEvents()

    # The proof runs in a thread; give it a moment to answer.
    for _ in range(50):
        app.processEvents()
        if window._verdicts:
            break

    verdicts = window._verdicts
    assert verdicts, "the panel produced no verdict"
    for verdict in verdicts:
        assert verdict.verdict != "refuted", verdict.evidence
    collinear = [verdict for verdict in verdicts if verdict.kind == "collinear"]
    assert collinear, "the claim about P, E and F was not judged"
    for verdict in collinear:
        assert verdict.verdict == "undecided", verdict.evidence
        assert verdict.witness is None
    window.close()


def test_the_reasons_are_in_the_teacher_s_language() -> None:
    """The kernel's words are translated; nothing is left in English."""
    assert "两条直线平行，没有交点" == _undefined_text("parallel_lines")
    assert (
        "两条直线平行，没有交点"
        == _undefined_text("the two lines are parallel; there is no intersection")
    )
    text = _evidence_text("node 'P' has no value: the two lines are parallel; there is no intersection")
    assert "没有值" in text
    assert "平行" in text
    assert "node" not in text
    assert "parallel" not in text
