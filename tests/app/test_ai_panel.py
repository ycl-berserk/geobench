"""The panel says where the model service came from.

The user asked whether the key had to be an environment variable, and
the answer has to be on the screen, not only in the code. A panel that
names the model and the variable the key came from answers the
question before it is asked, and a panel that cannot talk to a model
offers the way out right where the problem is.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
except ImportError as exc:  # pragma: no cover - depends on the machine
    pytest.skip(f"Qt is not usable on this machine: {exc}", allow_module_level=True)

from geobench.ai_settings import Resolution
from geobench.app.ai_panel import AIPanel
from geobench.app.controller import StudioController


class FakeProvider:
    name = "fake"

    def complete(self, system: str, user: str) -> str:  # pragma: no cover
        return ""


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def registry():
    return StudioController().registry


def test_the_panel_says_where_the_key_came_from(app: QApplication, registry) -> None:
    resolution = Resolution(
        provider=FakeProvider(),  # type: ignore[arg-type]
        source_kind="env",
        source_name="DEEPSEEK_API_KEY",
    )
    panel = AIPanel(None, resolution.provider, registry, "", resolution)
    text = panel.status_label.text()
    assert "DEEPSEEK_API_KEY" in text
    assert "环境变量" in text
    panel.close()


def test_the_panel_offers_a_way_to_set_the_service_up(
    app: QApplication, registry
) -> None:
    """No service: the button that fixes it is right there."""
    panel = AIPanel(None, None, registry)
    assert panel.ask_button.isEnabled() is False
    assert panel.settings_button.isEnabled() is True
    assert "设置模型服务" in panel.settings_button.text()
    panel.close()


def test_the_settings_button_is_always_there(app: QApplication, registry) -> None:
    """Even when a service works, the user may want a different one."""
    resolution = Resolution(provider=FakeProvider())  # type: ignore[arg-type]
    panel = AIPanel(None, resolution.provider, registry, "", resolution)
    assert panel.settings_button.isEnabled() is True
    assert panel.ask_button.isEnabled() is True
    panel.close()


def test_setting_a_service_later_turns_the_panel_on(app: QApplication, registry) -> None:
    """The button in the panel leads back to the panel."""
    panel = AIPanel(None, None, registry)
    assert panel.ask_button.isEnabled() is False
    resolution = Resolution(provider=FakeProvider())  # type: ignore[arg-type]
    panel.set_provider(resolution.provider, resolution)
    assert panel.ask_button.isEnabled() is True
    panel.close()
