"""The tutor window: one problem, one figure, one step at a time.

The panel is a thin client over :mod:`geobench.tutor`.  It never decides
whether a step is true: the local kernel does, on a snapshot.  What the
panel adds is the classroom side -- showing the lesson, pointing at the
objects being discussed, revealing an auxiliary line when the step needs
it, and carrying the student's questions back to the model.
"""

from __future__ import annotations

import html
import threading
from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from geobench.ai import Claim, Provider
from geobench.ai_settings import Resolution, resolve_provider
from geobench.app.canvas import FigureCanvas
from geobench.app.controller import StudioController
from geobench.app.settings_dialog import SettingsDialog
from geobench.errors import GeobenchError
from geobench.judges import Verdict
from geobench.tutor import Lesson, TutorReply, answer_question, build_lesson

__all__ = ["TutorPanel"]

_VERDICT_ZH = {
    "proved": "成立（形式证明）",
    "refuted": "不成立",
    # Every sampled placement satisfied the relation, but the symbolic
    # field could not finish the identity proof.  Saying "检查通过" is
    # honest about what the kernel did, and it does not claim a proof it
    # does not have.
    "supported": "检查通过（未找到反例）",
    "undecided": "不能判定",
}


class TutorPanel(QDialog):
    """A non-modal lesson window, tied to the live canvas."""

    lessonReady = Signal(object, str)
    replyReady = Signal(object, str)
    verdictReady = Signal(int, object, str)

    def __init__(
        self,
        parent: QWidget,
        controller: StudioController,
        canvas: FigureCanvas,
        apply_figure: Callable[[str], bool],
        provider: Provider | None,
        resolution: Resolution | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI 讲题")
        self.setModal(False)
        self.resize(660, 760)
        self._controller = controller
        self._canvas = canvas
        self._apply_figure = apply_figure
        self._provider = provider
        self._resolution = resolution
        self._lesson: Lesson | None = None
        self._step_index = -1
        self._busy = False
        self._closed = False
        self._verdict_token = 0
        self._verdict_labels: dict[int, str] = {}
        self._history: list[tuple[str, str]] = []

        self._build()
        self.lessonReady.connect(self._on_lesson)
        self.replyReady.connect(self._on_reply)
        self.verdictReady.connect(self._on_verdict)
        self._show_provider()

    # -- construction ------------------------------------------------------

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        note = QLabel(
            "把题目贴进来：模型画图、拆步骤；每一条几何事实仍由本地内核核对。"
            "只有点「生成课程」或「问」时，才会把题目和当前图形发给你设置的服务。"
        )
        note.setObjectName("panelNote")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.problem_edit = QPlainTextEdit()
        self.problem_edit.setPlaceholderText(
            "例如：在△ABC中，AB=AC，D是BC的中点，证明 AD⊥BC。"
        )
        self.problem_edit.setFixedHeight(92)
        layout.addWidget(self.problem_edit)

        top_row = QHBoxLayout()
        self.lesson_button = QPushButton("生成课程")
        self.lesson_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lesson_button.clicked.connect(self._generate)
        top_row.addWidget(self.lesson_button)
        self.settings_button = QPushButton("设置模型…")
        self.settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_button.clicked.connect(self._configure)
        top_row.addWidget(self.settings_button)
        top_row.addStretch(1)
        layout.addLayout(top_row)

        self.status_label = QLabel("")
        self.status_label.setObjectName("panelNote")
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.status_label)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.outline = QListWidget()
        self.outline.setMinimumWidth(170)
        self.outline.currentRowChanged.connect(self._outline_selected)
        self.splitter.addWidget(self.outline)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)
        self.transcript = QTextBrowser()
        self.transcript.setOpenExternalLinks(False)
        self.transcript.setPlaceholderText(
            "课程会在这里一步步展开；你也可以随时问“为什么”。"
        )
        right_layout.addWidget(self.transcript, 1)
        ask_row = QHBoxLayout()
        self.question_edit = QLineEdit()
        self.question_edit.setPlaceholderText(
            "问教练：为什么？这一步怎么来的？也可以说说你的想法。"
        )
        self.question_edit.returnPressed.connect(self._ask)
        ask_row.addWidget(self.question_edit, 1)
        self.ask_button = QPushButton("问")
        self.ask_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ask_button.clicked.connect(self._ask)
        ask_row.addWidget(self.ask_button)
        right_layout.addLayout(ask_row)
        self.splitter.addWidget(right)
        self.splitter.setSizes([180, 480])
        layout.addWidget(self.splitter, 1)

        bottom = QHBoxLayout()
        self.next_button = QPushButton("开始")
        self.next_button.setEnabled(False)
        self.next_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_button.clicked.connect(self._next_step)
        bottom.addWidget(self.next_button)
        bottom.addStretch(1)
        self.close_button = QPushButton("关闭")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.clicked.connect(self.close)
        bottom.addWidget(self.close_button)
        layout.addLayout(bottom)

        self.ask_button.setEnabled(False)
        self.next_button.setEnabled(False)

    # -- the model service -------------------------------------------------

    def _show_provider(self) -> None:
        if self._provider is None:
            self.status_label.setText(
                "还没有配置模型服务。可以点「设置模型…」；"
                "不配也能继续用手工作图与右侧判定。"
            )
            return
        source = ""
        if self._resolution is not None and self._resolution.source_kind == "env":
            source = f"（密钥来自环境变量 {self._resolution.source_name}）"
        elif self._resolution is not None and self._resolution.source_kind == "file":
            source = f"（密钥来自密钥文件 {self._resolution.source_name}）"
        self.status_label.setText(f"模型：{self._provider.name}{source}")

    def _configure(self) -> None:
        dialog = SettingsDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        resolution = resolve_provider()
        self._provider = resolution.provider
        self._resolution = resolution
        self._show_provider()

    # -- generating the lesson ---------------------------------------------

    def _generate(self) -> None:
        if self._busy:
            return
        problem = self.problem_edit.toPlainText().strip()
        if not problem:
            self.status_label.setText("先把题目贴进来。")
            return
        if self._provider is None:
            self.status_label.setText(
                "还没有配置模型服务，不能生成课程。点「设置模型…」先配置。"
            )
            return
        self._busy = True
        self.lesson_button.setEnabled(False)
        self.next_button.setEnabled(False)
        self.status_label.setText("正在读题、画图、备课……")
        provider = self._provider
        registry = self._controller.registry

        def work() -> None:
            if self._closed:
                return
            try:
                lesson = build_lesson(provider, problem, registry)
            except GeobenchError as exc:
                self.lessonReady.emit(None, str(exc))
                return
            self.lessonReady.emit(lesson, "")

        threading.Thread(target=work, daemon=True).start()

    def _on_lesson(self, lesson: object, error: str) -> None:
        self._busy = False
        self.lesson_button.setEnabled(True)
        if error or not isinstance(lesson, Lesson):
            self.status_label.setText(f"这节课没备出来：{error or '模型没有返回课程'}")
            return
        self._apply_lesson(lesson)

    def _apply_lesson(self, lesson: Lesson) -> None:
        """Replace the canvas and put the outline on screen."""
        if not self._apply_figure(lesson.figure):
            self.status_label.setText("已取消：画布没有换，原来的图还在。")
            return
        self._lesson = lesson
        self._step_index = -1
        self._history = []
        self._verdict_labels.clear()
        self.transcript.clear()
        self.outline.clear()
        for index, step in enumerate(lesson.steps, 1):
            item = f"{index}. {step.say}"
            if len(item) > 46:
                item = item[:45] + "…"
            self.outline.addItem(item)
        self._append(
            "教练",
            f"{lesson.title}\n目标：{lesson.goal}\n\n点「开始」，我们一步一步看。",
        )
        self.next_button.setText("开始")
        self.next_button.setEnabled(True)
        self.ask_button.setEnabled(False)
        self.status_label.setText(
            f"课程：{lesson.title}（{len(lesson.steps)} 步）"
        )

    # -- walking the lesson ------------------------------------------------

    def _next_step(self) -> None:
        if self._lesson is None or self._busy:
            return
        index = self._step_index + 1
        if index >= len(self._lesson.steps):
            self.status_label.setText("讲完了。可以继续问问题，或者关闭窗口。")
            self.next_button.setEnabled(False)
            return
        self._show_step(index)

    def _show_step(self, index: int) -> None:
        assert self._lesson is not None
        step = self._lesson.steps[index]
        self._step_index = index
        if step.reveal:
            self._controller.set_style_many(list(step.reveal), visible=True)
        self._canvas.set_teaching_highlight(list(step.highlight))
        self._append("教练", f"第 {index + 1} 步：{step.say}")
        if step.ask:
            self._append("教练问", step.ask)
        self._history.append(("教练", f"第 {index + 1} 步：{step.say}"))
        if step.claim is not None:
            self._judge(step.claim, f"第 {index + 1} 步")
        self.outline.setCurrentRow(index)
        self.next_button.setText(
            "完成" if index + 1 >= len(self._lesson.steps) else "下一步"
        )
        self.next_button.setEnabled(True)
        self.ask_button.setEnabled(True)
        self.status_label.setText(
            f"第 {index + 1} / {len(self._lesson.steps)} 步"
        )
        self.question_edit.setFocus()

    def _outline_selected(self, row: int) -> None:
        """Clicking an outline item re-reads that step, on that step's figure."""
        if row < 0 or self._lesson is None or row == self._step_index:
            return
        if row >= len(self._lesson.steps):
            return
        step = self._lesson.steps[row]
        self._step_index = row
        if step.reveal:
            self._controller.set_style_many(list(step.reveal), visible=True)
        self._canvas.set_teaching_highlight(list(step.highlight))
        self._append("教练", f"回看第 {row + 1} 步：{step.say}")
        if step.ask:
            self._append("教练问", step.ask)
        self._history.append(("教练", f"回看第 {row + 1} 步：{step.say}"))
        if step.claim is not None:
            self._judge(step.claim, f"回看第 {row + 1} 步")
        self.next_button.setText(
            "完成" if row + 1 >= len(self._lesson.steps) else "下一步"
        )
        self.next_button.setEnabled(True)
        self.ask_button.setEnabled(True)
        self.status_label.setText(
            f"第 {row + 1} / {len(self._lesson.steps)} 步"
        )

    # -- asking ------------------------------------------------------------

    def _ask(self) -> None:
        if self._busy:
            return
        if self._lesson is None or self._step_index < 0:
            self.status_label.setText("先生成课程，点「开始」，再问。")
            return
        question = self.question_edit.text().strip()
        if not question:
            return
        if self._provider is None:
            self.status_label.setText("没有配置模型服务，不能回答问题。")
            return
        self._busy = True
        self.ask_button.setEnabled(False)
        self.next_button.setEnabled(False)
        self.status_label.setText("正在想……")
        self._append("你", question)
        self.question_edit.clear()
        self._history.append(("学生", question))
        provider = self._provider
        lesson = self._lesson
        step = self._step_index
        figure_dsl = self._controller.to_text()
        history = list(self._history)
        registry = self._controller.registry

        def work() -> None:
            if self._closed:
                return
            try:
                reply = answer_question(
                    provider, lesson, step, question, figure_dsl, history, registry
                )
            except GeobenchError as exc:
                self.replyReady.emit(None, str(exc))
                return
            self.replyReady.emit(reply, "")

        threading.Thread(target=work, daemon=True).start()

    def _on_reply(self, reply: object, error: str) -> None:
        self._busy = False
        self.ask_button.setEnabled(True)
        self.next_button.setEnabled(self._lesson is not None)
        if error or not isinstance(reply, TutorReply):
            self._append("教练", f"这个问题没答上来：{error or '没有返回内容'}")
            self.status_label.setText("没答上来，可以换个问法。")
            return
        self._append("教练", reply.say)
        self._history.append(("教练", reply.say))
        if reply.reveal:
            self._controller.set_style_many(list(reply.reveal), visible=True)
        new_ids: list[str] = []
        for action in reply.construct:
            try:
                self._controller.construct(
                    action.op, list(action.args), action.id
                )
            except GeobenchError as exc:
                self._append("提示", f"辅助对象 {action.id} 没画出来：{exc}")
                self._history.append(
                    ("提示", f"辅助对象 {action.id} 没画出来：{exc}")
                )
                break
            new_ids.append(action.id)
        highlight = list(reply.highlight) + new_ids
        if highlight:
            self._canvas.set_teaching_highlight(highlight)
        if reply.claim is not None:
            self._judge(reply.claim, "刚才这一步")
        if reply.ask:
            self._append("教练问", reply.ask)
        self.status_label.setText("可以继续问，或点「下一步」。")

    # -- the kernel's check -------------------------------------------------

    def _judge(self, claim: Claim, label: str) -> None:
        token = self._verdict_token + 1
        self._verdict_token = token
        self._verdict_labels[token] = label
        snapshot = self._controller.snapshot_figure()
        controller = self._controller

        def work() -> None:
            try:
                verdict = controller.judge_claim(
                    claim.kind, list(claim.args), claim.scope, snapshot
                )
            except Exception as exc:  # pragma: no cover - worker safety
                self._emit_verdict(token, None, str(exc))
                return
            self._emit_verdict(token, verdict, "")

        threading.Thread(target=work, daemon=True).start()

    def _emit_verdict(self, token: int, verdict: object, error: str) -> None:
        if self._closed:
            return
        self.verdictReady.emit(token, verdict, error)

    def _on_verdict(self, token: int, verdict: object, error: str) -> None:
        label = self._verdict_labels.pop(token, "内核")
        if error or not isinstance(verdict, Verdict):
            self._append("内核", f"{label}：没查成（{error or '没有结果'}）", "#8a6d3b")
            return
        text = _VERDICT_ZH.get(verdict.verdict, verdict.verdict)
        colour = {
            "proved": "#2e7d32",
            "refuted": "#c0392b",
            "supported": "#8a6d3b",
            "undecided": "#8a6d3b",
        }.get(verdict.verdict, "#555555")
        self._append("内核", f"{label}：{text}", colour)
        self._history.append(("内核", f"{label}：{text}"))

    # -- small things ------------------------------------------------------

    def _append(self, who: str, text: str, colour: str = "") -> None:
        body = html.escape(text).replace("\n", "<br>")
        style = f' style="color:{colour}"' if colour else ""
        self.transcript.append(f"<p{style}><b>{html.escape(who)}</b>：{body}</p>")
        bar = self.transcript.verticalScrollBar()
        bar.setValue(bar.maximum())

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._closed = True
        self._canvas.clear_teaching_highlight()
        event.accept()
