"""The figure has to be able to leave the studio.

A geometry studio that cannot hand you its picture is a drawing tool,
not a product: the teacher needs the figure in the paper. These tests
check the way out -- an SVG file, a PNG file, and the clipboard, which
is the way a figure reaches a Word document.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtGui import QGuiApplication, QImage
    from PySide6.QtWidgets import QApplication
except ImportError as exc:  # pragma: no cover - depends on the machine
    pytest.skip(f"Qt is not usable on this machine: {exc}", allow_module_level=True)

from geobench.app.controller import StudioController
from geobench.app.export import (
    PNG_WIDTH,
    copy_image,
    png_image,
    svg_source,
    write_png,
    write_svg,
)


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def controller() -> StudioController:
    controller = StudioController()
    controller.add_free_point(0, 0, "A")
    controller.add_free_point(4, 0, "B")
    controller.add_free_point(0, 3, "C")
    controller.construct("line.free", ["A", "B"], "l")
    controller.construct("circle.center_point", ["A", "B"], "w")
    return controller


def test_the_svg_holds_the_figure(controller: StudioController) -> None:
    """The exported picture is the figure, not an empty page."""
    svg = svg_source(controller.figure(), controller.style)
    assert svg.startswith("<svg")
    assert "</svg>" in svg
    # the line, the circle and the labels are all in there
    assert "<line" in svg
    assert "<circle" in svg
    assert "<text" in svg
    assert ">A<" in svg


def test_the_exported_figure_looks_like_a_printed_figure(
    controller: StudioController,
) -> None:
    """The sizes on paper, not the sizes on the screen.

    The screen draws a hairline, because a hairline is what you want
    while you are working. The picture that goes into the paper is a
    different size, and its lines have to look like lines.
    """
    svg = svg_source(controller.figure(), controller.style)
    stroke = re.search(r'stroke-width="([0-9.]+)"', svg)
    assert stroke is not None
    assert float(stroke.group(1)) >= 1.0, svg[:400]

    font = re.search(r'font-size="([0-9.]+)"', svg)
    assert font is not None
    assert float(font.group(1)) >= 20.0, svg[:400]


def test_the_png_is_a_picture_of_the_figure(
    app: QApplication, controller: StudioController
) -> None:
    """Rasterised from the same source, so it is the same picture."""
    image = png_image(controller.figure(), controller.style)
    assert isinstance(image, QImage)
    assert image.width() == PNG_WIDTH
    assert image.height() > 0

    # The picture has ink in it: not a blank white page.
    inked = 0
    for x in range(0, image.width(), 7):
        for y in range(0, image.height(), 7):
            if image.pixelColor(x, y).name().lower() != "#ffffff":
                inked += 1
    assert inked > 20, inked


def test_the_files_are_written(
    app: QApplication, controller: StudioController, tmp_path: Path
) -> None:
    """A file the teacher can open again."""
    svg_path = tmp_path / "figure.svg"
    write_svg(controller.figure(), controller.style, svg_path)
    assert svg_path.exists()
    assert "<svg" in svg_path.read_text(encoding="utf-8")

    png_path = tmp_path / "figure.png"
    write_png(controller.figure(), controller.style, png_path)
    assert png_path.exists()
    image = QImage(str(png_path))
    assert not image.isNull()
    assert image.width() == PNG_WIDTH


def test_the_picture_can_be_pasted(
    app: QApplication, controller: StudioController
) -> None:
    """Pasting into Word is the ordinary way a figure gets into a paper."""
    copy_image(controller.figure(), controller.style)
    clipboard = QGuiApplication.clipboard()
    assert clipboard is not None
    image = clipboard.image()
    assert not image.isNull()
    assert image.width() == PNG_WIDTH


def test_the_studio_offers_the_way_out(
    app: QApplication, controller: StudioController
) -> None:
    """The export is in the menu, not hidden in a module."""
    from geobench.app.window import StudioWindow

    window = StudioWindow(controller)

    file_menu = None
    for action in window.menuBar().actions():
        menu = action.menu()
        if menu is not None and menu.title() == "文件":
            file_menu = menu
            break
    assert file_menu is not None

    titles = [action.text() for action in file_menu.actions()]
    assert "导出" in titles

    export_menu = None
    for action in file_menu.actions():
        if action.text() == "导出":
            export_menu = action.menu()
            break
    assert export_menu is not None
    exported = [action.text() for action in export_menu.actions()]
    assert "导出 SVG…" in exported
    assert "导出 PNG…" in exported
    assert "复制图形到剪贴板" in exported
    window.close()
