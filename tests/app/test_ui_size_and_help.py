"""The interface size, and a help menu that says what the shortcuts are.

Two small things a first-time teacher needs: larger type for a
projector, and somewhere to learn `Shift`-click, `Ctrl+Z` and `Delete`
without reading the source.  Both live in the menu bar, and the size is
remembered between sessions.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
except ImportError as exc:  # pragma: no cover - depends on the machine
    pytest.skip(f"Qt is not usable on this machine: {exc}", allow_module_level=True)

from geobench.app.controller import StudioController
from geobench.app.theme import UI_SIZES, apply_theme, set_ui_size
from geobench.app.window import StudioWindow, _about_text, _shortcuts_text


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def restore_theme(app: QApplication):
    yield
    set_ui_size("标准")
    apply_theme(app)
    QSettings("geobench", "studio").remove("ui/size")


def test_the_sizes_are_ordered() -> None:
    assert UI_SIZES["紧凑"] < UI_SIZES["标准"] < UI_SIZES["大"]


def test_a_size_changes_the_font(restore_theme, app: QApplication) -> None:
    set_ui_size("大")
    apply_theme(app)
    assert app.font().pointSizeF() == UI_SIZES["大"]


def test_the_menu_changes_the_size_and_remembers_it(
    restore_theme, app: QApplication
) -> None:
    set_ui_size("标准")
    apply_theme(app)
    window = StudioWindow(StudioController())
    window._size_actions["大"].trigger()

    assert app.font().pointSizeF() == UI_SIZES["大"]
    assert QSettings("geobench", "studio").value("ui/size") == "大"
    assert window._size_actions["大"].isChecked()
    assert not window._size_actions["标准"].isChecked()
    window.close()


def test_the_help_menu_is_there(app: QApplication) -> None:
    window = StudioWindow(StudioController())
    titles = [action.text() for action in window.menuBar().actions()]
    assert "帮助" in titles
    assert "Shift" in _shortcuts_text()
    assert "Ctrl+Z" in _shortcuts_text()
    assert "geobench" in _about_text()
    window.close()


def test_quick_start_opens_the_example(app: QApplication) -> None:
    window = StudioWindow(StudioController())
    window._quick_start()
    assert window.controller.figure().nodes
    window.close()
