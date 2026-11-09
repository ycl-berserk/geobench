"""The studio has to look like one thing, not like a pile of defaults.

These are small checks -- the theme applies, every tool has an icon, the
panes have headings, a verdict is coloured by what it says -- and they
are cheap. They catch the drift that makes an interface look as though
nobody ever looked at it.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication, QLabel, QToolButton
except ImportError as exc:  # pragma: no cover - depends on the machine
    pytest.skip(f"Qt is not usable on this machine: {exc}", allow_module_level=True)

from geobench.app.controller import StudioController
from geobench.app.icons import GLYPHS, group_icon, tool_icon
from geobench.app.theme import PALETTE, apply_theme
from geobench.app.tools import build_toolbar
from geobench.app.window import HEAD_ROLE, TAIL_ROLE, VERDICT_ROLE, StudioWindow
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _tools() -> list:
    registry = OperatorRegistry()
    register_builtins(registry)
    return [tool for group in build_toolbar(registry) for tool in group.tools]


def test_the_theme_applies(app: QApplication) -> None:
    """One stylesheet, one palette, one font."""
    apply_theme(app)
    assert app.styleSheet()
    assert PALETTE.accent in app.styleSheet()
    assert app.font().pointSize() > 0


def test_every_tool_has_an_icon() -> None:
    """A tool with no icon would be a word where a picture belongs."""
    missing = [tool.op for tool in _tools() if tool.op not in GLYPHS]
    assert not missing, missing


def test_every_icon_is_actually_drawn(app: QApplication) -> None:
    """An icon that draws nothing is worse than no icon."""
    for tool in _tools():
        icon = tool_icon(tool.op)
        assert not icon.isNull(), tool.op
        assert not icon.pixmap(22, 22).isNull(), tool.op
    for family in ("点", "线", "多边形", "圆", "变换", "测量"):
        assert not group_icon(family).isNull(), family


def test_the_panes_have_headings(app: QApplication) -> None:
    """A pane with no heading is a box."""
    window = StudioWindow(StudioController())
    window.show()
    app.processEvents()
    titles = {
        label.text()
        for label in window.findChildren(QLabel)
        if label.objectName() == "panelTitle"
    }
    assert titles == {"构造", "画板", "判定"}
    window.close()


def test_the_armed_tool_shows_in_the_toolbar(app: QApplication) -> None:
    """What is in force must be visible."""
    window = StudioWindow(StudioController())
    window.show()
    app.processEvents()
    armed = [
        button.text()
        for button in window.findChildren(QToolButton)
        if button.isChecked()
    ]
    assert armed == ["点"]
    window.close()


def test_a_verdict_is_coloured_by_what_it_says(app: QApplication) -> None:
    """Green for proved, red for refuted: the table reads before the words."""
    controller = StudioController()
    controller.add_free_point(0, 0, "A")
    controller.add_free_point(6, 0, "B")
    controller.add_free_point(2, 4, "C")
    controller.construct("point.midpoint", ["A", "B"], "M")
    controller.add_relation("collinear", ["A", "M", "B"])
    controller.add_relation("collinear", ["A", "B", "C"])

    window = StudioWindow(controller)
    window.show()
    app.processEvents()

    colours = {
        window.judgements.item(row, 1).data(VERDICT_ROLE)
        for row in range(window.judgements.rowCount())
    }
    assert PALETTE.ok in colours
    assert PALETTE.danger in colours
    window.close()


def test_the_steps_are_drawn_in_two_tones(app: QApplication) -> None:
    """The name is the subject; the call is the explanation."""
    controller = StudioController()
    controller.add_free_point(0, 0, "A")
    controller.add_free_point(6, 0, "B")
    controller.construct("point.midpoint", ["A", "B"], "M")

    window = StudioWindow(controller)
    window.show()
    app.processEvents()
    item = window.steps.item(window.steps.count() - 1)
    assert item is not None
    assert item.data(HEAD_ROLE) == "M "
    assert item.data(TAIL_ROLE) == "= 中点(A, B)"
    window.close()
