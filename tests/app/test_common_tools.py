"""The five constructions a lesson keeps reaching for, on the first level.

Midpoint, intersection, perpendicular, parallel, circle were all one
click down inside their family menus.  A teacher asks for them ten times
a lesson; the toolbar should not ask them to remember which family each
one belongs to.
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
from geobench.app.tools import COMMON_OPS, build_toolbar
from geobench.app.window import StudioWindow
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _groups():
    registry = OperatorRegistry()
    register_builtins(registry)
    return build_toolbar(registry)


def test_the_common_group_comes_first() -> None:
    groups = _groups()
    assert groups[0].key == "common"
    assert groups[0].label == "常用"
    assert [tool.op for tool in groups[0].tools] == list(COMMON_OPS)


def test_the_common_tools_are_still_in_their_own_families() -> None:
    """A second door, not a move: the point family still has its midpoint."""
    groups = _groups()
    point_group = next(group for group in groups if group.key == "点")
    assert "point.midpoint" in {tool.op for tool in point_group.tools}


def test_one_click_arms_the_midpoint(app: QApplication) -> None:
    window = StudioWindow(StudioController())
    window.show()
    app.processEvents()

    window._tool_buttons["common"].click()
    app.processEvents()

    tool = window.canvas.tool()
    assert tool is not None
    assert tool.op == "point.midpoint"
    window.close()


def test_the_common_menu_holds_all_five(app: QApplication) -> None:
    window = StudioWindow(StudioController())
    window.show()
    app.processEvents()

    menu = window._tool_buttons["common"].menu()
    assert menu is not None
    labels = [action.text() for action in menu.actions()]
    for wanted in ("中点", "交点", "垂直", "平行", "外接圆"):
        assert any(label.startswith(wanted) for label in labels), labels
    assert len(labels) == len(COMMON_OPS)
    window.close()
