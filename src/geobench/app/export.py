"""Getting the figure out of the studio.

A geometry studio that cannot hand you its picture is a drawing tool,
not a product: the teacher needs the figure *in the paper*, and
pasting a picture into Word is the ordinary way that happens.

Two kinds of output, and they are the same picture. SVG is for print
and for editing -- it is a vector file, so it stays sharp in a
document. PNG is for pasting: it goes onto the clipboard as an image,
so a figure lands in a Word file the way a figure should.

Both come from the drawing primitives, which the screen draws too
(decision D20) -- so what is exported is what was on screen, minus the
grid, which is a guide and not part of the figure.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

from geobench.model import Figure
from geobench.render import render_svg
from geobench.style import COMPETITION, FigureStyle

__all__ = [
    "PNG_WIDTH",
    "SVG_WIDTH",
    "copy_image",
    "copy_svg_source",
    "png_image",
    "svg_source",
    "write_png",
    "write_svg",
]

#: The width of an exported SVG, in pixels. An SVG is a vector file, so
#: this is the size of the *page*, not the size of the drawing: it can
#: be scaled afterwards without losing anything.
SVG_WIDTH = 1200

#: The width of an exported picture, in pixels. A picture has no scale
#: of its own, so this is the resolution it is pasted at.
PNG_WIDTH = 1600

#: The paper the picture is drawn on. A pasted picture needs an opaque
#: background; the SVG stays transparent, because a document gives it
#: its own page.
PAPER = "#ffffff"


def svg_source(figure: Figure, style: FigureStyle | None = None) -> str:
    """The figure as SVG source.

    The same picture the screen draws, without the grid.
    """
    return render_svg(figure, style or COMPETITION, width_px=SVG_WIDTH)


def png_image(
    figure: Figure,
    style: FigureStyle | None = None,
    width: int = PNG_WIDTH,
) -> QImage:
    """The figure as a picture.

    It is rasterised from the SVG rather than drawn a second time: one
    picture, two ways out of it.
    """
    svg = render_svg(
        figure,
        replace(style or COMPETITION, background=PAPER),
        width_px=width,
    )
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    size = renderer.defaultSize()
    height = max(1, round(size.height() * width / size.width())) if size.width() else width
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor(PAPER))
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, width, height))
    painter.end()
    return image


def write_svg(figure: Figure, style: FigureStyle | None, path: Path) -> None:
    """Write the figure to an SVG file."""
    path.write_text(svg_source(figure, style), encoding="utf-8")


def write_png(
    figure: Figure, style: FigureStyle | None, path: Path, width: int = PNG_WIDTH
) -> None:
    """Write the figure to a PNG file."""
    image = png_image(figure, style, width)
    if not image.save(str(path)):
        raise OSError(f"could not write {path}")


def copy_image(figure: Figure, style: FigureStyle | None, width: int = PNG_WIDTH) -> None:
    """Put the figure on the clipboard as a picture."""
    clipboard = QApplication.clipboard()
    if clipboard is None:
        raise OSError("there is no clipboard")
    clipboard.setImage(png_image(figure, style, width))


def copy_svg_source(figure: Figure, style: FigureStyle | None) -> None:
    """Put the SVG source on the clipboard, for a document that wants it."""
    clipboard = QApplication.clipboard()
    if clipboard is None:
        raise OSError("there is no clipboard")
    clipboard.setText(svg_source(figure, style))
