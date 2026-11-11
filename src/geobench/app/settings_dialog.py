"""Where the model service comes from -- asked in the studio, not in a shell.

Every agent tool has to answer the same question: *which model service,
and where is the key?* The tools answer it in three tiers -- an
environment variable, the operating system's credential store, and the
application's own settings -- and the studio does the same. What is
different here is that the user is a teacher, not a developer, and a
terminal is not where a teacher wants to be.

So this dialog says all three things at once:

- which service, and which model;
- **where the key will come from** -- the environment, the key file, or
  the box in front of the user;
- and, when there is nothing to talk to, exactly what is missing.

The precedence is the one every agent tool uses: **the environment
wins**. A user who already exported ``DEEPSEEK_API_KEY`` is not asked
again. The key file is the app's own tier, and the box is the last one
-- but a user who typed a key into this application means that key,
and can say so with one checkbox.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from geobench.ai_settings import (
    OVERRIDE_ENV,
    PROVIDERS,
    AISettings,
    ProviderPreset,
    environment_services,
    key_file_path,
    read_settings,
    requires_key,
    resolve_provider,
    write_key_file,
    write_settings,
)
from geobench.app.theme import button_words

__all__ = ["SettingsDialog"]


class SettingsDialog(QDialog):
    """Say which service to talk to, and where the key is."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("模型服务设置")
        self.setMinimumWidth(520)
        self._settings = read_settings()

        layout = QVBoxLayout(self)

        note = QLabel(
            "钥匙按老办法找：先看环境变量，再看密钥文件，最后才是这里输入的。"
            "你已经导出的密钥不会被悄悄覆盖。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        form = QFormLayout()
        layout.addLayout(form)

        self.provider_combo = QComboBox()
        for provider_id, preset in PROVIDERS.items():
            self.provider_combo.addItem(preset.label, provider_id)
        form.addRow("服务", self.provider_combo)

        self.base_url_edit = QLineEdit()
        form.addRow("服务地址", self.base_url_edit)

        self.model_edit = QLineEdit()
        form.addRow("模型", self.model_edit)

        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("留空则用环境变量或密钥文件")
        key_row = QHBoxLayout()
        key_row.addWidget(self.key_edit)
        self.from_env_button = QPushButton("从环境变量读取")
        self.from_env_button.setToolTip("看看这台机器上已经设了哪些密钥")
        self.from_env_button.clicked.connect(self._read_from_environment)
        key_row.addWidget(self.from_env_button)
        form.addRow("密钥", key_row)

        self.key_file_edit = QLineEdit()
        self.key_file_edit.setPlaceholderText(str(key_file_path()))
        file_row = QHBoxLayout()
        file_row.addWidget(self.key_file_edit)
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse_key_file)
        file_row.addWidget(browse)
        form.addRow("密钥文件", file_row)

        self.prefer_stored_check = QCheckBox("优先用这里保存的密钥（覆盖环境变量）")
        form.addRow("", self.prefer_stored_check)

        self.note_label = QLabel("")
        self.note_label.setWordWrap(True)
        layout.addWidget(self.note_label)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_words(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load()
        self.provider_combo.currentIndexChanged.connect(self._preset_changed)
        self._update_status()

    # -- loading -----------------------------------------------------------

    def _load(self) -> None:
        """Put what is already known on the screen."""
        settings = self._settings
        index = self.provider_combo.findData(settings.provider)
        if index < 0:
            index = self.provider_combo.findData("deepseek")
        self.provider_combo.setCurrentIndex(max(0, index))
        self.base_url_edit.setText(settings.base_url)
        self.model_edit.setText(settings.model)
        self.key_file_edit.setText(settings.key_file)
        self.prefer_stored_check.setChecked(settings.prefer_stored_key)
        self._preset_changed()

    def _current_preset(self) -> ProviderPreset | None:
        provider_id = self.provider_combo.currentData()
        return PROVIDERS.get(str(provider_id))

    def _preset_changed(self) -> None:
        """Choosing a service fills in what that service is."""
        preset = self._current_preset()
        if preset is None:
            return
        if preset.base_url:
            self.base_url_edit.setText(preset.base_url)
        if preset.model:
            self.model_edit.setText(preset.model)
        self.note_label.setText(preset.note)
        self._update_status()

    # -- the environment ---------------------------------------------------

    def _read_from_environment(self) -> None:
        """Take whatever the environment already holds.

        The user does not have to know which variable to look at: the
        dialog looks at all of them and reports what it found.
        """
        override = os.environ.get(OVERRIDE_ENV, "").strip()
        if override:
            self.key_edit.setText(override)
            self._announce(f"读到了环境变量 {OVERRIDE_ENV}。")
            return

        found = environment_services()
        if not found:
            self.status_label.setText(
                "这台机器上没找到常见的密钥环境变量"
                "（DEEPSEEK_API_KEY、OPENAI_API_KEY 等）。"
                "可以直接把密钥填在上面的框里。"
            )
            return

        provider_id, name = found[0]
        index = self.provider_combo.findData(provider_id)
        if index >= 0:
            self.provider_combo.setCurrentIndex(index)
        self.key_edit.setText(os.environ.get(name, "").strip())
        self._announce(f"读到了环境变量 {name}。")

    def _announce(self, message: str) -> None:
        """Say what was found, without losing the standing explanation.

        The status line normally explains where the key will come from;
        a one-off message ("读到了环境变量 X") is an addition to that,
        not a replacement -- so it is kept in a second line.
        """
        self.status_label.setText(f"{message}\n{self._standing_text()}")

    # -- the key file ------------------------------------------------------

    def _browse_key_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择密钥文件", str(Path.home()), "所有文件 (*)"
        )
        if path:
            self.key_file_edit.setText(path)

    # -- saving ------------------------------------------------------------

    def accept(self) -> None:
        """Save, and say what the studio will now do."""
        settings = self._current_settings()
        write_settings(settings)
        key = self.key_edit.text().strip()
        if key:
            write_key_file(self._key_file(), key)
        super().accept()

    def _current_settings(self) -> AISettings:
        return AISettings(
            provider=str(self.provider_combo.currentData() or ""),
            base_url=self.base_url_edit.text().strip(),
            model=self.model_edit.text().strip(),
            key_file=self.key_file_edit.text().strip(),
            prefer_stored_key=self.prefer_stored_check.isChecked(),
        )

    def _key_file(self) -> Path:
        text = self.key_file_edit.text().strip()
        return Path(text) if text else key_file_path()

    # -- what will happen --------------------------------------------------

    def _update_status(self) -> None:
        """Say where the key will come from, or what is missing.

        This is the whole point of the dialog: the user should never
        have to guess why it does not work.
        """
        self.status_label.setText(self._standing_text())

    def _standing_text(self) -> str:
        """The standing explanation: where the key comes from."""
        settings = self._current_settings()
        typed = self.key_edit.text().strip()
        resolution = resolve_provider(settings)
        if resolution.ok and resolution.provider is not None:
            name = resolution.provider.name
            if typed and not settings.prefer_stored_key:
                return (
                    f"将使用：{name} —— 密钥会存进密钥文件；"
                    "环境变量里的密钥仍然优先。"
                )
            if resolution.source_kind:
                return (
                    f"将使用：{name} —— "
                    f"密钥来自{self._where(resolution.source_kind, resolution.source_name)}。"
                )
            return f"将使用：{name} —— 本机服务，不需要钥匙。"

        if resolution.reason == "missing-key" and not requires_key(settings.base_url):
            return "还缺模型名：填一个模型的名字。"
        reason = {
            "missing-key": "还缺密钥：环境变量和密钥文件里都没有。可以在上面的框里输入一个。",
            "missing-url": "还缺服务地址：选一个服务，或自己填一个。",
            "missing-model": "还缺模型名：填一个模型的名字。",
        }.get(resolution.reason, "还差一点什么。")
        return reason

    def _where(self, kind: str, name: str) -> str:
        if kind == "env":
            return f"环境变量 {name}"
        if kind == "file":
            return f"密钥文件 {name}"
        return name
