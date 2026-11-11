"""The settings dialog: the user is told where the key comes from.

The question the user asked was "must this be an environment variable?",
and the answer has to be visible on the screen, not just true in the
code. So these tests drive the dialog the way a teacher would, and
check that what it says is what will happen.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
except ImportError as exc:  # pragma: no cover - depends on the machine
    pytest.skip(f"Qt is not usable on this machine: {exc}", allow_module_level=True)

from geobench.ai_settings import key_file_path, resolve_provider
from geobench.app.settings_dialog import SettingsDialog

KNOWN_KEY_VARS = (
    "GEOBENCH_AI_API_KEY",
    "GEOBENCH_AI_BASE_URL",
    "GEOBENCH_AI_MODEL",
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "SILICONFLOW_API_KEY",
    "DASHSCOPE_API_KEY",
    "MOONSHOT_API_KEY",
    "MINIMAX_API_KEY",
    "GROQ_API_KEY",
)


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    for name in KNOWN_KEY_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GEOBENCH_CONFIG_DIR", str(tmp_path / "config"))


def test_the_dialog_says_which_key_the_environment_holds(
    app: QApplication, monkeypatch
) -> None:
    """The user does not have to know what an environment variable is."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "from-the-environment")
    dialog = SettingsDialog()
    dialog._read_from_environment()
    assert dialog.key_edit.text() == "from-the-environment"
    assert "DEEPSEEK_API_KEY" in dialog.status_label.text()
    dialog.close()


def test_the_dialog_offers_a_way_in_when_there_is_no_key(app: QApplication) -> None:
    """No key anywhere: the dialog says what is missing, not "error"."""
    dialog = SettingsDialog()
    dialog.provider_combo.setCurrentIndex(dialog.provider_combo.findData("custom"))
    dialog.base_url_edit.setText("https://api.example.com/v1")
    dialog.model_edit.setText("some-model")
    assert "密钥" in dialog.status_label.text()
    dialog.close()


def test_the_dialog_reports_where_the_key_will_come_from(
    app: QApplication, monkeypatch
) -> None:
    """The status line is the answer to "where does it look?"."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "from-the-environment")
    dialog = SettingsDialog()
    dialog.provider_combo.setCurrentIndex(dialog.provider_combo.findData("deepseek"))
    text = dialog.status_label.text()
    assert "环境变量" in text
    assert "DEEPSEEK_API_KEY" in text
    dialog.close()


def test_a_typed_key_is_saved_to_the_key_file(app: QApplication) -> None:
    """The key goes into the key file, and the settings remember where."""
    dialog = SettingsDialog()
    dialog.provider_combo.setCurrentIndex(dialog.provider_combo.findData("deepseek"))
    dialog.key_edit.setText("typed-by-hand")
    dialog.accept()

    assert key_file_path().exists()
    resolution = resolve_provider()
    assert resolution.ok
    assert resolution.provider is not None
    assert resolution.provider.api_key == "typed-by-hand"


def test_the_settings_never_hold_the_key(app: QApplication) -> None:
    """A secret does not belong in a file a user might send to somebody."""
    from geobench.ai_settings import config_path

    dialog = SettingsDialog()
    dialog.provider_combo.setCurrentIndex(dialog.provider_combo.findData("deepseek"))
    dialog.key_edit.setText("typed-by-hand")
    dialog.accept()

    assert "typed-by-hand" not in config_path().read_text(encoding="utf-8")


def test_a_typed_key_is_used_when_the_environment_is_silent(app: QApplication) -> None:
    """The third tier: what the user typed is what the studio uses."""
    dialog = SettingsDialog()
    dialog.provider_combo.setCurrentIndex(dialog.provider_combo.findData("deepseek"))
    dialog.key_edit.setText("typed-by-hand")
    dialog.accept()

    resolution = resolve_provider()
    assert resolution.source_kind == "file"
    assert resolution.source_name == str(key_file_path())
