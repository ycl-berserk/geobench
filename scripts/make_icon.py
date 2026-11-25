"""The application icon, drawn rather than shipped.

A deep-blue rounded square, a white circumcircle and a triangle inside
it: the product in one small picture.  Rendered at 256 px and wrapped
into an .ico (a PNG payload, which is what Windows accepts for 256 px).
"""

from __future__ import annotations

import math
import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "packaging"
OUT.mkdir(exist_ok=True)

app = QGuiApplication.instance() or QGuiApplication([])

size = 256
image = QImage(size, size, QImage.Format.Format_ARGB32)
image.fill(Qt.GlobalColor.transparent)
painter = QPainter(image)
painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

# The ground: a deep-blue rounded square with a hint of paper at the top.
painter.setPen(Qt.PenStyle.NoPen)
painter.setBrush(QColor("#1f4e9e"))
painter.drawRoundedRect(QRectF(8, 8, size - 16, size - 16), 52, 52)

# The circumcircle.
painter.setBrush(Qt.BrushStyle.NoBrush)
painter.setPen(QPen(QColor("#ffffff"), 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
painter.drawEllipse(QPointF(128, 136), 76, 76)

# The triangle, inscribed.
centre = (128.0, 136.0)
radius = 76.0
points = [
    QPointF(
        centre[0] + radius * math.cos(math.radians(-90 + 120 * index)),
        centre[1] + radius * math.sin(math.radians(-90 + 120 * index)),
    )
    for index in range(3)
]
painter.setPen(QPen(QColor("#ffffff"), 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
painter.setBrush(Qt.BrushStyle.NoBrush)
painter.drawPolygon(points)

# A warm point at the top: the thing being looked at.
painter.setPen(Qt.PenStyle.NoPen)
painter.setBrush(QColor("#f2b134"))
painter.drawEllipse(points[0], 12, 12)
painter.end()

png = OUT / "icon.png"
image.save(str(png), "PNG")

# Wrap the PNG in a one-entry ICO (valid for 256 px on Vista and later).
payload = png.read_bytes()
header = struct.pack("<HHH", 0, 1, 1)
entry = struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(payload), 22)
(OUT / "geobench.ico").write_bytes(header + entry + payload)
print("wrote", png, "and", OUT / "geobench.ico", flush=True)
