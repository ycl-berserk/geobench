"""The construction protocol, played.

The steps pane on the left already lists how the figure was built.
These buttons play it back: the picture grows one step at a time, so
a student can see what a construction does before being told.

The picture on the canvas is the same picture -- the playback only
decides how many of the steps are drawn. Nothing is rebuilt, nothing
is destroyed, and the figure is whole again when the playback ends.
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
from geobench.app.window import StudioWindow


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def controller() -> StudioController:
    controller = StudioController()
    controller.add_free_point(0, 0, "O")
    controller.add_free_point(4, 0, "A")
    controller.construct("circle.center_point", ["O", "A"], "w")
    return controller


def _ink(window: StudioWindow) -> int:
    """How much of the canvas is drawn on."""
    image = window.canvas.grab().toImage()
    dark = 0
    for x in range(0, image.width(), 3):
        for y in range(0, image.height(), 3):
            if image.pixelColor(x, y).name().lower() not in {"#ffffff", "#fbfcfd"}:
                dark += 1
    return dark


def test_the_steps_are_the_nodes_in_the_order_they_were_made(
    app: QApplication, controller: StudioController
) -> None:
    window = StudioWindow(controller)
    assert window._construction_steps() == ["O", "A", "w"]
    window.close()


def test_the_playback_grows_the_picture_one_step_at_a_time(
    app: QApplication, controller: StudioController
) -> None:
    window = StudioWindow(controller)
    window.resize(900, 600)
    window.show()
    app.processEvents()

    whole = _ink(window)

    window._play_construction()
    app.processEvents()
    assert window.canvas._playback_limit == 0

    window._playback_tick()
    app.processEvents()
    assert window.canvas._playback_limit == 1
    first = _ink(window)

    # The circle has not been built yet: less is drawn.
    assert first < whole

    window._playback_tick()
    app.processEvents()
    assert window.canvas._playback_limit == 2
    window._playback_tick()
    app.processEvents()
    assert window.canvas._playback_limit == 3
    assert _ink(window) == whole

    window.close()


def test_stopping_gives_the_whole_figure_back(
    app: QApplication, controller: StudioController
) -> None:
    window = StudioWindow(controller)
    window.resize(900, 600)
    window.show()
    app.processEvents()
    whole = _ink(window)

    window._play_construction()
    window._playback_tick()
    app.processEvents()
    window._stop_playback()
    app.processEvents()

    assert window.canvas._playback_limit is None
    assert _ink(window) == whole
    window.close()


def test_a_single_step_moves_one_step_on(
    app: QApplication, controller: StudioController
) -> None:
    window = StudioWindow(controller)
    window._step_forward()
    assert window.canvas._playback_limit == 1
    window._step_forward()
    assert window.canvas._playback_limit == 2
    window.close()
