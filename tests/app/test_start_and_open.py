"""Starting a lesson: an empty page that offers a way in, and files that open.

The first screen used to be a blank canvas with a one-line hint.  A
teacher does not want to learn a toolbar before seeing a figure; they
want a figure.  So the blank page offers the three real starting
points -- an example, a sentence, a file -- and opening a file shows
the whole figure rather than a corner of it.

The `.ggb` route matters most: the teacher already has figures in
GeoGebra, and the program not being able to open them is the difference
between a tool and a toy.
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication, QPushButton
except ImportError as exc:  # pragma: no cover - depends on the machine
    pytest.skip(f"Qt is not usable on this machine: {exc}", allow_module_level=True)

from geobench.app.controller import StudioController
from geobench.app.window import StudioWindow

GGB_XML = """<?xml version="1.0" encoding="utf-8"?>
<geogebra format="5.0">
  <construction>
    <element type="point" label="A"><coords x="0" y="0" z="1"/></element>
    <element type="point" label="B"><coords x="4" y="0" z="1"/></element>
    <command name="Segment"><input a0="A" a1="B"/><output a0="f"/></command>
  </construction>
</geogebra>
"""


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _window(app: QApplication) -> StudioWindow:
    window = StudioWindow(StudioController())
    window.resize(1200, 800)
    window.show()
    app.processEvents()
    return window


def test_the_empty_canvas_offers_a_way_in(app: QApplication) -> None:
    window = _window(app)
    texts = {button.text() for button in window._empty_state.findChildren(QPushButton)}
    assert {"从零开始画图", "打开一个示例", "用一句话作图", "打开文件…"} <= texts
    assert not window._empty_state.isHidden()
    window.close()


def test_the_first_screen_offers_a_blank_figure(app: QApplication) -> None:
    window = _window(app)
    labels = {
        button.text(): button
        for button in window._empty_state.findChildren(QPushButton)
    }
    labels["从零开始画图"].click()
    app.processEvents()
    assert not window.controller.figure().nodes
    assert window.canvas.tool() is not None
    assert window.canvas.tool().op == "point.free"
    window.close()


def test_the_example_is_a_figure_and_a_proof(app: QApplication) -> None:
    window = _window(app)
    labels = {
        button.text(): button
        for button in window._empty_state.findChildren(QPushButton)
    }
    labels["打开一个示例"].click()
    app.processEvents()

    assert window.controller.figure().nodes
    assert window._empty_state.isHidden()
    verdicts = window.controller.judge()
    assert verdicts and all(verdict.verdict == "proved" for verdict in verdicts)
    window.close()


def test_opening_a_file_shows_the_whole_figure(
    app: QApplication, tmp_path: Path
) -> None:
    window = _window(app)
    path = tmp_path / "far.geobench"
    path.write_text(
        "点 A(100,100) B(104,100) C(102,104)\nAB = 线段(A,B)\n",
        encoding="utf-8",
    )
    window._load_path(path)
    app.processEvents()

    view = window.canvas._view
    assert view.x_min < 100 < view.x_max
    assert view.y_min < 100 < view.y_max
    assert window._empty_state.isHidden()
    window.close()


def test_a_geogebra_file_opens_from_the_app(
    app: QApplication, tmp_path: Path
) -> None:
    window = _window(app)
    path = tmp_path / "lesson.ggb"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("geogebra.xml", GGB_XML)

    window._load_path(path)
    app.processEvents()

    assert set(window.controller.figure().nodes) >= {"A", "B"}
    assert any(
        node.kind == "segment" for node in window.controller.figure().nodes.values()
    )
    window.close()
