"""The lesson window: the canvas, the outline, and the kernel's verdict.

The model is faked here on purpose.  What is tested is the classroom
wiring: a lesson replaces the figure, a step reveals and highlights the
objects it talks about, the claim is checked by the kernel, and a
student's question can add an auxiliary line and point at it.
"""

from __future__ import annotations

import json
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
except ImportError as exc:  # pragma: no cover - depends on the machine
    pytest.skip(f"Qt is not usable on this machine: {exc}", allow_module_level=True)

from geobench.ai import Claim
from geobench.app.controller import StudioController
from geobench.app.tutor_panel import TutorPanel
from geobench.app.window import StudioWindow
from geobench.judges import IDENTITY
from geobench.tutor import Lesson, TutorStep

FIGURE = (
    "点 A(0,0) B(6,0) C(2,4)\n"
    "AB = 线段(A,B)\n"
    "M = 中点(A,B)\n"
    "隐藏 M\n"
)


class FakeProvider:
    name = "fake"

    def __init__(self, answer: str) -> None:
        self.answer = answer

    def complete(self, system: str, user: str) -> str:
        return self.answer


class BoomProvider:
    """A provider whose worker dies: the panel must not wait forever."""

    name = "boom"

    def complete(self, system: str, user: str) -> str:
        raise RuntimeError("service exploded")


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _lesson() -> Lesson:
    return Lesson(
        title="中点共线",
        problem="在 AB 上取中点 M",
        figure=FIGURE,
        goal="证明 A、M、B 共线",
        steps=(
            TutorStep(
                say="M 是 AB 的中点，所以 M 在 AB 上。",
                reveal=("M",),
                highlight=("A", "B", "M"),
                claim=Claim("collinear", ("A", "M", "B"), IDENTITY),
                ask="你能看出 M 为什么在 AB 上吗？",
            ),
        ),
    )


def _wait(app: QApplication, condition, timeout: float = 4.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


def _panel(
    app: QApplication, controller: StudioController
) -> tuple[TutorPanel, StudioWindow]:
    window = StudioWindow(controller)
    window.resize(1000, 700)
    window.show()
    app.processEvents()

    def apply(text: str) -> bool:
        controller.load_text(text)
        window.canvas.fit()
        return True

    panel = TutorPanel(
        window, controller, window.canvas, apply, None
    )
    panel.show()
    app.processEvents()
    return panel, window


def test_a_lesson_replaces_the_figure_and_walks_one_step(
    app: QApplication,
) -> None:
    controller = StudioController()
    panel, window = _panel(app, controller)
    panel._apply_lesson(_lesson())
    assert panel.outline.count() == 1
    assert panel.next_button.text() == "开始"
    assert not controller.figure().nodes["M"].style.visible

    panel._next_step()
    app.processEvents()

    # The hidden midpoint is now on the paper, and pointed at.
    assert controller.figure().nodes["M"].style.visible
    assert window.canvas._teach_highlight == {"A", "B", "M"}
    assert "第 1 步" in panel.transcript.toPlainText()

    # The kernel checks the claim; the transcript says what it found.
    assert _wait(
        app, lambda: "成立" in panel.transcript.toPlainText()
    ), panel.transcript.toPlainText()
    panel.close()
    window.close()


def test_a_student_question_can_add_an_auxiliary_line(
    app: QApplication,
) -> None:
    controller = StudioController()
    panel, window = _panel(app, controller)
    panel._apply_lesson(_lesson())
    panel._next_step()
    app.processEvents()

    answer = json.dumps(
        {
            "say": "把 AM 连起来看，AM 就在 AB 上。",
            "highlight": ["A", "M"],
            "construct": [
                {"op": "line.free", "args": ["A", "M"], "id": "AM"}
            ],
        },
        ensure_ascii=False,
    )
    panel._provider = FakeProvider(answer)
    panel.question_edit.setText("为什么要连 AM？")
    panel._ask()

    assert _wait(
        app,
        lambda: "AM" in controller.figure().nodes
        and "把 AM 连起来看" in panel.transcript.toPlainText(),
    ), panel.transcript.toPlainText()
    assert "AM" in window.canvas._teach_highlight
    panel.close()
    window.close()


def test_a_worker_crash_is_shown_and_does_not_leave_the_button_stuck(
    app: QApplication,
) -> None:
    controller = StudioController()
    panel, window = _panel(app, controller)
    panel._provider = BoomProvider()
    panel.problem_edit.setPlainText("随便问一个不是几何题的问题")
    panel._generate()
    assert _wait(
        app, lambda: "RuntimeError" in panel.status_label.text()
    ), panel.status_label.text()
    assert panel.lesson_button.text() == "生成课程"
    assert not panel._busy
    panel.close()
    window.close()


def test_a_timeout_releases_the_panel(app: QApplication) -> None:
    controller = StudioController()
    panel, window = _panel(app, controller)
    panel._busy = True
    panel._busy_token = 1
    panel.lesson_button.setText("停止")
    panel._timeout(1, "生成课程")
    assert not panel._busy
    assert panel.lesson_button.text() == "生成课程"
    assert "停止等待" in panel.status_label.text()
    panel.close()
    window.close()


def test_a_step_that_needs_no_model_still_checks_its_claim(
    app: QApplication,
) -> None:
    """The kernel check does not depend on the model being reachable."""
    controller = StudioController()
    panel, window = _panel(app, controller)
    panel._apply_lesson(_lesson())
    panel._next_step()
    assert _wait(app, lambda: "内核" in panel.transcript.toPlainText())
    panel.close()
    window.close()
