"""The AI panel: say what you want drawn, and let the parser decide.

The panel is deliberately small. It asks a question, it shows what
came back, and it shows what the parser made of it. If the parser
refused, the refusal is on the screen with its reason -- because a
refusal is the honest answer, and hiding it would only move the
problem somewhere less visible.

It also says **where the model service comes from**, because "it does
not work" is not an answer, and neither is "check your environment
variables" to somebody who does not know what an environment variable
is. When there is no service to talk to, the panel offers the settings
dialog, which knows how to look at the environment, at a key file, and
at what the user typed.

The model is called on a background thread. The studio's rule has
never been that the screen waits for anything, and a model that takes
ten seconds is no different from a judge that takes ten seconds.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from geobench.ai import Proposal, Provider, propose
from geobench.ai_settings import Resolution
from geobench.app.theme import button_words
from geobench.errors import GeobenchError
from geobench.registry import OperatorRegistry

__all__ = ["AIPanel"]


class AIPanel(QDialog):
    """Ask the model for a figure, and judge what comes back."""

    #: The model answered: the proposal, and the failure that stopped it
    #: ("" when there was none).
    answered = Signal(object, str)

    #: The user wants to set up the model service.
    configure_requested = Signal()

    def __init__(
        self,
        parent: QWidget,
        provider: Provider | None,
        registry: OperatorRegistry,
        current_dsl: str = "",
        resolution: Resolution | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI 作图")
        self.setMinimumSize(560, 520)
        self._provider = provider
        self._registry = registry
        self._current = current_dsl
        self._text = ""

        layout = QVBoxLayout(self)

        note = QLabel(
            "用一句话说你要什么图。模型写出作图代码，"
            "解析器负责判断它是不是一张图 —— 解析不了就改，不猜。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self.request_edit = QPlainTextEdit()
        self.request_edit.setPlaceholderText("例如：过 A 作 BC 的垂线")
        self.request_edit.setFixedHeight(70)
        layout.addWidget(self.request_edit)

        row = QHBoxLayout()
        self.ask_button = QPushButton("问模型")
        self.ask_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ask_button.clicked.connect(self._ask)
        row.addWidget(self.ask_button)
        self.settings_button = QPushButton("设置模型服务…")
        self.settings_button.setToolTip("换个模型服务，或者告诉它钥匙在哪")
        self.settings_button.clicked.connect(self.configure_requested.emit)
        row.addWidget(self.settings_button)
        row.addStretch(1)
        layout.addLayout(row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.result_edit = QPlainTextEdit()
        self.result_edit.setReadOnly(True)
        layout.addWidget(self.result_edit, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_words(buttons)
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setText("在画板上作图")
        self.ok_button.setEnabled(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.set_provider(provider, resolution)

    # -- the service -------------------------------------------------------

    def set_provider(
        self, provider: Provider | None, resolution: Resolution | None = None
    ) -> None:
        """Point the panel at a model service, and say where it came from."""
        self._provider = provider
        if provider is None:
            self.ask_button.setEnabled(False)
            self.status_label.setText(
                "没有找到模型服务。可以点「设置模型服务…」——"
                "它会先看你这台机器上已有的环境变量，再让你填。"
            )
            return
        self.ask_button.setEnabled(True)
        self.status_label.setText(f"模型：{provider.name}{self._source_text(resolution)}")

    def _source_text(self, resolution: Resolution | None) -> str:
        """Say where the key came from, in one clause."""
        if resolution is None or not resolution.source_kind:
            return ""
        if resolution.source_kind == "env":
            return f"（密钥来自环境变量 {resolution.source_name}）"
        if resolution.source_kind == "file":
            return f"（密钥来自密钥文件 {resolution.source_name}）"
        return ""

    # -- asking -------------------------------------------------------------

    def _ask(self) -> None:
        """Ask, on a background thread: the screen does not wait."""
        request = self.request_edit.toPlainText().strip()
        if not request:
            self.status_label.setText("先说说你要什么图。")
            return
        provider = self._provider
        if provider is None:
            return
        self.ask_button.setEnabled(False)
        self.status_label.setText("正在问模型……")
        current = self._current
        registry = self._registry

        def work() -> None:
            try:
                proposal = propose(provider, request, current, registry)
            except GeobenchError as exc:
                self.answered.emit(None, str(exc))
                return
            self.answered.emit(proposal, proposal.error or "")

        self.answered.connect(self._receive)
        threading.Thread(target=work, daemon=True).start()

    def _receive(self, proposal: object, error: str) -> None:
        """The model answered, on the main thread."""
        self.ask_button.setEnabled(True)
        if not isinstance(proposal, Proposal):
            self.ok_button.setEnabled(False)
            self.status_label.setText(f"没有拿到作图代码：{error}")
            return
        self._text = proposal.text
        self.result_edit.setPlainText(proposal.text)
        if error:
            self.ok_button.setEnabled(False)
            self.status_label.setText(f"解析器拒绝了这段代码：{error}")
            return
        if proposal.problems:
            # The code parsed, but the kernel found something wrong with
            # the figure.  Saying so is the whole point: a figure with an
            # object that cannot exist is exactly what a teacher would
            # bounce, and the teacher should not have to find it.
            self.ok_button.setEnabled(True)
            self.status_label.setText(
                "解析器接受了，但内核查出这张图有问题：\n"
                + "\n".join(f"· {problem.to_text()}" for problem in proposal.problems)
            )
            return
        if proposal.refused:
            # The model said the request cannot be done.  That is a
            # legitimate answer -- a figure is not better than an
            # honest "this does not exist".
            self.ok_button.setEnabled(False)
            self.status_label.setText("模型说这个任务做不到（上面就是它给的理由）。")
            return
        self.ok_button.setEnabled(True)
        self.status_label.setText(
            "解析器接受了，内核也查过这张图：没有问题。"
            "点「在画板上作图」把它画出来。"
        )

    # -- applying -----------------------------------------------------------

    def accepted_figure(self) -> str:
        """The DSL to draw, if the parser accepted it."""
        return self._text
