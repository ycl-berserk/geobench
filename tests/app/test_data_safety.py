"""Data safety: a lesson must not disappear with the window.

These cover the four promises the studio makes: a change shows in the
title, the figure is saved where the teacher asked, a crash leaves an
autosave behind, and closing does not silently throw work away.
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
except ImportError as exc:  # pragma: no cover - depends on the machine
    pytest.skip(f"Qt is not usable on this machine: {exc}", allow_module_level=True)

from geobench.app.controller import StudioController
from geobench.app.window import StudioWindow

FIGURE = """点 A(0, 0) B(4, 0) C(1, 3)
M = 中点(A, B)
c = 外接圆(A, B, C)
"""


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def window(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> StudioWindow:
    monkeypatch.setenv("GEOBENCH_DATA_DIR", str(tmp_path / "data"))
    controller = StudioController()
    controller.load_text(FIGURE)
    return StudioWindow(controller)


def test_a_change_shows_in_the_title(window: StudioWindow) -> None:
    controller = window.controller
    assert window._dirty is False
    controller.add_free_point(5, 5, "D")
    assert window._dirty is True
    assert window.windowTitle().endswith("（未命名*）")


def test_saving_clears_the_mark(window: StudioWindow, tmp_path: Path) -> None:
    target = tmp_path / "lesson.geobench"
    window._dirty = True
    window._write_path(target)
    assert target.read_text(encoding="utf-8").startswith("点 ")
    assert window._dirty is False
    assert "*" not in window.windowTitle()
    assert target.name in window.windowTitle()


def test_autosave_is_recoverable_after_a_crash(
    app: QApplication, window: StudioWindow, tmp_path: Path
) -> None:
    window.controller.add_free_point(5, 5, "D")
    window._write_recovery()
    assert window.has_recovery()

    # A second window is the next launch: same data directory, no figure.
    other = StudioWindow(StudioController())
    assert other.has_recovery()
    other.restore_recovery()
    assert "D" in other.controller.figure().nodes
    assert other._dirty is True


def test_new_clears_the_figure(window: StudioWindow) -> None:
    window._dirty = False
    window._new_file()
    assert window.controller.figure().nodes == {}
    assert window._path is None
    assert window._dirty is False


def test_a_clean_close_removes_the_autosave(window: StudioWindow) -> None:
    window.controller.add_free_point(5, 5, "D")
    window._write_recovery()
    assert window.has_recovery()
    window.close()
    assert window.has_recovery() is False


def test_a_geogebra_open_does_not_become_the_save_target(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Saving a .ggb import must not overwrite the teacher's original."""
    monkeypatch.setenv("GEOBENCH_DATA_DIR", str(tmp_path / "data"))
    xml = """<?xml version="1.0" encoding="utf-8"?>
    <geogebra format="5.0"><construction>
      <element type="point" label="A"><coords x="0" y="0" z="1"/></element>
      <element type="point" label="B"><coords x="4" y="0" z="1"/></element>
      <command name="Segment"><input a0="A" a1="B"/><output a0="f"/></command>
    </construction></geogebra>"""
    path = tmp_path / "original.ggb"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("geogebra.xml", xml)
    window = StudioWindow(StudioController())
    window._load_path(path)
    assert window._path is None
    assert window._dirty is False
