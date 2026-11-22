"""Coordinates on the paper: axes and ticks, screen only.

A teacher writes "let A be the origin" and a student reads "B(6, 0)".
The grid alone gives neither.  The axes are a screen aid: the exported
figure is the figure, not the worksheet.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
except ImportError as exc:  # pragma: no cover - depends on the machine
    pytest.skip(f"Qt is not usable on this machine: {exc}", allow_module_level=True)

from geobench.app.canvas import _tick_step
from geobench.app.controller import StudioController
from geobench.app.window import StudioWindow


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _window(app: QApplication) -> StudioWindow:
    controller = StudioController()
    controller.add_free_point(0, 0, "A")
    controller.add_free_point(6, 0, "B")
    controller.add_free_point(2, 4, "C")
    window = StudioWindow(controller)
    window.resize(1000, 700)
    window.show()
    app.processEvents()
    return window


def test_tick_steps_are_round_numbers() -> None:
    assert _tick_step(50) == 2.0
    assert _tick_step(14) == 5.0
    assert _tick_step(100) == 1.0
    assert _tick_step(400) == 0.2


def test_the_axes_are_on_by_default_and_can_be_hidden(app: QApplication) -> None:
    window = _window(app)
    assert window.canvas.show_axes
    assert window._axes_action.isChecked()

    window._axes_action.setChecked(False)
    app.processEvents()
    assert not window.canvas.show_axes

    window._axes_action.setChecked(True)
    app.processEvents()
    assert window.canvas.show_axes
    window.close()


def test_the_axis_is_darker_than_the_grid(app: QApplication) -> None:
    """The x-axis is drawn, and it is visible against the paper."""
    window = _window(app)
    viewport = window.canvas._viewport()
    # Between two grid lines and away from the tick labels.
    sx, sy = viewport.to_screen(4.37, 0.0)
    x, y = round(sx), round(sy)

    on = window.canvas.grab().toImage().pixelColor(x, y).lightness()
    window.canvas.set_show_axes(False)
    off = window.canvas.grab().toImage().pixelColor(x, y).lightness()

    assert on < off, (on, off)
    window.close()
