"""The icons of the studio, drawn rather than shipped.

An icon file is a binary nobody can review, and it stops matching the
palette the moment the palette changes. These are drawn with QPainter out
of a dozen shapes, so they follow the theme, stay sharp at any size, and
live in the same repository as the code that uses them.

Every glyph is the *idea* of the command, not a picture of it: a dot for
a point, a triangle for a polygon, a circle for a circle. A teacher
recognises them the way they recognise a symbol.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap

from geobench.app.theme import PALETTE

#: The size of an icon, in pixels.
SIZE = 24

#: The centre of an icon.
MID = SIZE / 2

#: The radius of the shapes inside an icon.
R = SIZE * 0.32


# --- the drawing helpers -------------------------------------------------


def _pen(painter: QPainter, colour: str, width: float = 1.9) -> None:
    pen = QPen(QColor(colour))
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)


def _dashed(painter: QPainter, colour: str, width: float = 1.6) -> None:
    pen = QPen(QColor(colour))
    pen.setWidthF(width)
    pen.setStyle(Qt.PenStyle.DashLine)
    pen.setDashPattern([2.5, 2.0])
    painter.setPen(pen)


def _fill(painter: QPainter, colour: str) -> None:
    painter.setBrush(QBrush(QColor(colour)))


def _hollow(painter: QPainter) -> None:
    painter.setBrush(Qt.BrushStyle.NoBrush)


def _dot(painter: QPainter, x: float, y: float, radius: float, colour: str) -> None:
    _fill(painter, colour)
    painter.drawEllipse(QPointF(x, y), radius, radius)


def _ring(painter: QPainter, x: float, y: float, radius: float) -> None:
    _hollow(painter)
    painter.drawEllipse(QPointF(x, y), radius, radius)


def _head(painter: QPainter, at: QPointF, dx: float, dy: float, size: float = 3.2) -> None:
    """The barbs of an arrowhead, pointing along (dx, dy)."""
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    tip = QPointF(at.x() + ux * size, at.y() + uy * size)
    painter.drawLine(tip, QPointF(at.x() + px * size * 0.62, at.y() + py * size * 0.62))
    painter.drawLine(tip, QPointF(at.x() - px * size * 0.62, at.y() - py * size * 0.62))


def _vertices(count: int, radius: float = R, rotation: float = -90.0) -> list[QPointF]:
    points: list[QPointF] = []
    for index in range(count):
        angle = math.radians(rotation + index * 360.0 / count)
        points.append(
            QPointF(MID + radius * math.cos(angle), MID + radius * math.sin(angle))
        )
    return points


# --- the glyphs ----------------------------------------------------------


def _g_point(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.5)
    _ring(painter, MID, MID, 4.2)
    _dot(painter, MID, MID, 1.9, colour)


def _g_midpoint(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.4)
    painter.drawLine(QPointF(3.0, MID + 2), QPointF(SIZE - 3.0, MID + 2))
    _dot(painter, 3.4, MID + 2, 2.0, colour)
    _dot(painter, SIZE - 3.4, MID + 2, 2.0, colour)
    _pen(painter, colour, 1.7)
    _ring(painter, MID, MID + 2, 2.6)


def _g_centroid(painter: QPainter, colour: str) -> None:
    points = _vertices(3)
    _pen(painter, colour, 1.5)
    _hollow(painter)
    painter.drawPolygon(points)
    _dot(painter, MID, MID + 1.0, 2.2, colour)


def _g_circumcenter(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.5)
    _hollow(painter)
    painter.drawEllipse(QPointF(MID, MID), R, R)
    _dot(painter, MID, MID, 2.2, colour)


def _g_incenter(painter: QPainter, colour: str) -> None:
    points = _vertices(3)
    _pen(painter, colour, 1.5)
    _hollow(painter)
    painter.drawPolygon(points)
    _pen(painter, colour, 1.2)
    painter.drawEllipse(QPointF(MID, MID + 0.8), 2.4, 2.4)
    _dot(painter, MID, MID + 0.8, 1.2, colour)


def _g_orthocenter(painter: QPainter, colour: str) -> None:
    points = _vertices(3)
    _pen(painter, colour, 1.4)
    _hollow(painter)
    painter.drawPolygon(points)
    _dashed(painter, colour, 1.2)
    painter.drawLine(points[0], QPointF(MID, MID + R * 0.87))
    _dot(painter, points[0].x(), points[0].y(), 2.1, colour)


def _g_foot(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.5)
    painter.drawLine(QPointF(2.5, SIZE - 4.5), QPointF(SIZE - 2.5, SIZE - 4.5))
    painter.drawLine(QPointF(MID + 3.0, SIZE - 4.5), QPointF(MID + 3.0, 3.0))
    _pen(painter, colour, 1.1)
    painter.drawLine(QPointF(MID + 3.0, SIZE - 8.0), QPointF(MID + 6.5, SIZE - 8.0))
    painter.drawLine(QPointF(MID + 6.5, SIZE - 8.0), QPointF(MID + 6.5, SIZE - 4.5))


def _g_cross(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.5)
    painter.drawLine(QPointF(2.5, 2.5), QPointF(SIZE - 2.5, SIZE - 2.5))
    painter.drawLine(QPointF(2.5, SIZE - 2.5), QPointF(SIZE - 2.5, 2.5))
    _dot(painter, MID, MID, 2.3, colour)


def _g_line_circle(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.5)
    _hollow(painter)
    painter.drawEllipse(QPointF(MID + 2.0, MID), R * 0.78, R * 0.78)
    painter.drawLine(QPointF(2.0, MID + 3.0), QPointF(SIZE - 2.0, MID - 3.0))
    _dot(painter, MID - 1.0, MID + 1.0, 2.2, colour)


def _g_two_circles(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.5)
    _hollow(painter)
    painter.drawEllipse(QPointF(MID - 2.4, MID), R * 0.72, R * 0.72)
    painter.drawEllipse(QPointF(MID + 2.4, MID), R * 0.72, R * 0.72)
    _dot(painter, MID, MID - 3.2, 2.1, colour)


def _g_nearest(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.5)
    painter.drawLine(QPointF(2.5, SIZE - 4.0), QPointF(SIZE - 2.5, SIZE - 4.0))
    _dot(painter, MID - 3.0, 4.0, 2.1, colour)
    _dashed(painter, colour, 1.2)
    painter.drawLine(QPointF(MID - 3.0, 4.0), QPointF(MID - 3.0, SIZE - 4.0))


def _g_vertex(painter: QPainter, colour: str) -> None:
    points = _vertices(3)
    _pen(painter, colour, 1.4)
    _hollow(painter)
    painter.drawPolygon(points)
    _dot(painter, points[0].x(), points[0].y(), 3.2, colour)


def _g_ratio(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.5)
    painter.drawLine(QPointF(2.5, MID + 2), QPointF(SIZE - 2.5, MID + 2))
    _dot(painter, 2.8, MID + 2, 1.9, colour)
    _dot(painter, SIZE - 2.8, MID + 2, 1.9, colour)
    _pen(painter, colour, 1.4)
    painter.drawLine(QPointF(MID, MID - 2.5), QPointF(MID, MID + 5.5))


def _g_line(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.6)
    painter.drawLine(QPointF(2.0, MID), QPointF(SIZE - 2.0, MID))


def _g_segment(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.6)
    painter.drawLine(QPointF(4.0, MID), QPointF(SIZE - 4.0, MID))
    _pen(painter, colour, 1.3)
    painter.drawLine(QPointF(4.0, MID - 3.4), QPointF(4.0, MID + 3.4))
    painter.drawLine(QPointF(SIZE - 4.0, MID - 3.4), QPointF(SIZE - 4.0, MID + 3.4))


def _g_ray(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.6)
    painter.drawLine(QPointF(3.5, MID), QPointF(SIZE - 4.0, MID))
    _head(painter, QPointF(SIZE - 4.0, MID), 1.0, 0.0)


def _g_parallel(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.6)
    painter.drawLine(QPointF(3.0, MID - 4.0), QPointF(SIZE - 3.0, MID - 4.0))
    painter.drawLine(QPointF(3.0, MID + 4.0), QPointF(SIZE - 3.0, MID + 4.0))


def _g_perpendicular(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.6)
    painter.drawLine(QPointF(4.0, SIZE - 4.5), QPointF(SIZE - 4.5, SIZE - 4.5))
    painter.drawLine(QPointF(SIZE - 4.5, SIZE - 4.5), QPointF(SIZE - 4.5, 3.5))
    _pen(painter, colour, 1.1)
    painter.drawLine(QPointF(SIZE - 8.5, SIZE - 4.5), QPointF(SIZE - 8.5, SIZE - 8.5))
    painter.drawLine(QPointF(SIZE - 8.5, SIZE - 8.5), QPointF(SIZE - 4.5, SIZE - 8.5))


def _g_bisector(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.6)
    painter.drawLine(QPointF(MID - 4.0, SIZE - 4.0), QPointF(MID - 4.0, MID + 2.0))
    painter.drawLine(QPointF(MID - 4.0, SIZE - 4.0), QPointF(SIZE - 3.5, 4.0))
    _dashed(painter, colour, 1.3)
    painter.drawLine(QPointF(MID - 4.0, SIZE - 4.0), QPointF(MID + 3.0, 5.0))


def _g_tangent(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.5)
    _hollow(painter)
    painter.drawEllipse(QPointF(MID - 1.5, MID), R * 0.72, R * 0.72)
    painter.drawLine(QPointF(2.0, MID - 4.5), QPointF(SIZE - 2.0, MID - 8.0))


def _g_polar(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.5)
    _hollow(painter)
    painter.drawEllipse(QPointF(MID - 2.5, MID), R * 0.68, R * 0.68)
    painter.drawLine(QPointF(MID - 6.5, MID - 2.0), QPointF(SIZE - 3.0, MID - 6.5))
    _dot(painter, SIZE - 3.0, MID - 6.5, 2.1, colour)


def _g_circle(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.5)
    _hollow(painter)
    painter.drawEllipse(QPointF(MID, MID), R, R)
    _dot(painter, MID, MID, 1.9, colour)
    painter.drawLine(QPointF(MID, MID), QPointF(MID + R * 0.72, MID))


def _g_circle_three(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.5)
    _hollow(painter)
    painter.drawEllipse(QPointF(MID, MID), R, R)
    for angle in (215.0, 330.0, 80.0):
        radians = math.radians(angle)
        x = MID + R * math.cos(radians)
        y = MID + R * math.sin(radians)
        _dot(painter, x, y, 1.9, colour)


def _g_arc(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.6)
    _hollow(painter)
    painter.drawArc(
        QRectF(MID - R, MID - R, 2 * R, 2 * R), 20 * 16, 140 * 16
    )


def _g_sector(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.5)
    painter.drawPie(QRectF(MID - R, MID - R, 2 * R, 2 * R), 20 * 16, 140 * 16)


def _g_triangle(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.6)
    _hollow(painter)
    painter.drawPolygon(_vertices(3))


def _g_pentagon(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.6)
    _hollow(painter)
    painter.drawPolygon(_vertices(5))


def _g_polyline(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.6)
    painter.drawPolyline(
        [
            QPointF(3.0, SIZE - 4.5),
            QPointF(MID, MID - 1.0),
            QPointF(SIZE - 3.0, SIZE - 4.5),
        ]
    )


def _g_angle(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.6)
    painter.drawLine(QPointF(4.0, SIZE - 4.0), QPointF(SIZE - 4.0, SIZE - 4.0))
    painter.drawLine(QPointF(4.0, SIZE - 4.0), QPointF(SIZE - 5.0, 4.0))
    _pen(painter, colour, 1.2)
    painter.drawArc(QRectF(4.0, SIZE - 13.0, 9.0, 9.0), 0 * 16, -90 * 16)


def _g_distance(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.6)
    painter.drawLine(QPointF(4.5, MID), QPointF(SIZE - 4.5, MID))
    _head(painter, QPointF(4.5, MID), -1.0, 0.0)
    _head(painter, QPointF(SIZE - 4.5, MID), 1.0, 0.0)


def _g_area(painter: QPainter, colour: str) -> None:
    points = _vertices(3)
    _pen(painter, colour, 1.5)
    _fill(painter, colour)
    painter.setOpacity(0.35)
    painter.drawPolygon(points)
    painter.setOpacity(1.0)
    _pen(painter, colour, 1.5)
    _hollow(painter)
    painter.drawPolygon(points)


def _g_perimeter(painter: QPainter, colour: str) -> None:
    points = _vertices(3)
    _pen(painter, colour, 1.5)
    _hollow(painter)
    painter.drawPolygon(points)
    _pen(painter, colour, 1.3)
    painter.drawArc(
        QRectF(MID - R - 3.0, MID - R - 3.0, 2 * (R + 3.0), 2 * (R + 3.0)),
        200 * 16,
        120 * 16,
    )
    _head(painter, QPointF(MID - R - 1.2, MID + R - 0.6), 0.45, -0.9, 2.6)


def _g_radius(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.5)
    _hollow(painter)
    painter.drawEllipse(QPointF(MID, MID), R, R)
    _pen(painter, colour, 1.4)
    painter.drawLine(QPointF(MID, MID), QPointF(MID + R * 0.72, MID - R * 0.5))
    _dot(painter, MID, MID, 1.8, colour)


def _g_slope(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.6)
    painter.drawLine(QPointF(3.5, SIZE - 4.5), QPointF(SIZE - 3.5, 3.5))
    _pen(painter, colour, 1.1)
    painter.drawLine(QPointF(3.5, SIZE - 4.5), QPointF(SIZE - 8.0, SIZE - 4.5))
    painter.drawLine(QPointF(SIZE - 8.0, SIZE - 4.5), QPointF(SIZE - 8.0, SIZE - 8.0))


def _g_arrow(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.6)
    painter.drawLine(QPointF(3.0, MID), QPointF(SIZE - 6.0, MID))
    _head(painter, QPointF(SIZE - 6.0, MID), 1.0, 0.0, 4.0)


def _g_rotate(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.6)
    painter.drawArc(QRectF(4.0, 4.0, SIZE - 8.0, SIZE - 8.0), 30 * 16, 280 * 16)
    _head(painter, QPointF(SIZE - 5.6, MID - 4.2), 0.35, -0.94, 3.2)


def _g_dilate(painter: QPainter, colour: str) -> None:
    _pen(painter, colour, 1.6)
    painter.drawLine(QPointF(7.0, MID), QPointF(SIZE - 6.0, MID))
    _head(painter, QPointF(SIZE - 6.0, MID), 1.0, 0.0, 3.4)
    _dot(painter, 4.0, MID, 2.1, colour)


def _g_mirror(painter: QPainter, colour: str) -> None:
    _dashed(painter, colour, 1.4)
    painter.drawLine(QPointF(MID, 2.0), QPointF(MID, SIZE - 2.0))
    _pen(painter, colour, 1.5)
    _hollow(painter)
    painter.drawPolygon(
        [
            QPointF(4.0, SIZE - 5.0),
            QPointF(9.5, 6.0),
            QPointF(9.5, SIZE - 5.0),
        ]
    )


def _g_incirlce(painter: QPainter, colour: str) -> None:
    points = _vertices(3)
    _pen(painter, colour, 1.5)
    _hollow(painter)
    painter.drawPolygon(points)
    painter.drawEllipse(QPointF(MID, MID + 0.8), 2.6, 2.6)


def _g_select(painter: QPainter, colour: str) -> None:
    """The arrow: the tool that points instead of making."""
    _pen(painter, colour, 1.7)
    _hollow(painter)
    painter.drawPolygon(
        [
            QPointF(6.0, 2.5),
            QPointF(6.0, 17.5),
            QPointF(10.4, 13.2),
            QPointF(13.2, 19.0),
            QPointF(15.8, 17.6),
            QPointF(12.9, 12.0),
            QPointF(18.6, 11.6),
        ]
    )


def _g_fit(painter: QPainter, colour: str) -> None:
    """Four corners: the frame that fits the figure."""
    _pen(painter, colour, 1.5)
    inset = 3.5
    length = 5.0
    for x, y, dx, dy in (
        (inset, inset, 1.0, 1.0),
        (SIZE - inset, inset, -1.0, 1.0),
        (inset, SIZE - inset, 1.0, -1.0),
        (SIZE - inset, SIZE - inset, -1.0, -1.0),
    ):
        painter.drawLine(QPointF(x, y), QPointF(x + dx * length, y))
        painter.drawLine(QPointF(x, y), QPointF(x, y + dy * length))


#: The glyph each command is drawn with.
GLYPHS: dict[str, str] = {
    "__fit__": "fit",
    "__select__": "select",
    "point.free": "point",
    "point.midpoint": "midpoint",
    "point.centroid": "centroid",
    "point.circumcenter": "circumcenter",
    "point.incenter": "incenter",
    "point.orthocenter": "orthocenter",
    "point.foot": "foot",
    "point.intersect_lines": "cross",
    "point.intersect_line_circle": "line_circle",
    "point.intersect_circles": "two_circles",
    "point.nearest_on_object": "nearest",
    "point.polygon_vertex": "vertex",
    "point.affine_ratio": "ratio",
    "line.free": "line",
    "line.perpendicular_through": "perpendicular",
    "line.parallel_through": "parallel",
    "line.perpendicular_bisector": "perpendicular",
    "line.angle_bisector": "bisector",
    "line.tangent": "tangent",
    "line.polar": "polar",
    "segment.free": "segment",
    "ray.free": "ray",
    "polyline.free": "polyline",
    "polygon.free": "triangle",
    "polygon.regular": "pentagon",
    "circle.free": "circle",
    "circle.center_point": "circle",
    "circle.through": "circle_three",
    "circle.incircle": "incircle",
    "arc.three_points": "arc",
    "sector.three_points": "sector",
    "transform.translate": "arrow",
    "transform.rotate": "rotate",
    "transform.dilate": "dilate",
    "transform.mirror": "mirror",
    "measure.distance": "distance",
    "measure.length": "segment",
    "measure.area": "area",
    "measure.perimeter": "perimeter",
    "measure.angle": "angle",
    "measure.radius": "radius",
    "measure.slope": "slope",
    "measure.direction": "arrow",
}

#: The glyphs, by name.
_DRAWERS = {
    "fit": _g_fit,
    "select": _g_select,
    "point": _g_point,
    "midpoint": _g_midpoint,
    "centroid": _g_centroid,
    "circumcenter": _g_circumcenter,
    "incenter": _g_incenter,
    "orthocenter": _g_orthocenter,
    "foot": _g_foot,
    "cross": _g_cross,
    "line_circle": _g_line_circle,
    "two_circles": _g_two_circles,
    "nearest": _g_nearest,
    "vertex": _g_vertex,
    "ratio": _g_ratio,
    "line": _g_line,
    "segment": _g_segment,
    "ray": _g_ray,
    "parallel": _g_parallel,
    "perpendicular": _g_perpendicular,
    "bisector": _g_bisector,
    "tangent": _g_tangent,
    "polar": _g_polar,
    "circle": _g_circle,
    "circle_three": _g_circle_three,
    "arc": _g_arc,
    "sector": _g_sector,
    "triangle": _g_triangle,
    "pentagon": _g_pentagon,
    "polyline": _g_polyline,
    "angle": _g_angle,
    "distance": _g_distance,
    "area": _g_area,
    "perimeter": _g_perimeter,
    "radius": _g_radius,
    "slope": _g_slope,
    "arrow": _g_arrow,
    "rotate": _g_rotate,
    "dilate": _g_dilate,
    "mirror": _g_mirror,
    "incircle": _g_incirlce,
}

#: The glyph a family gets when a command has none of its own.
FAMILY_GLYPHS: dict[str, str] = {
    "点": "point",
    "线": "line",
    "多边形": "triangle",
    "圆": "circle",
    "变换": "arrow",
    "测量": "distance",
}


def _draw(glyph: str, colour: str, size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    drawer = _DRAWERS.get(glyph, _g_point)
    drawer(painter, colour)
    painter.end()
    return pixmap


def tool_icon(op: str, tone: str = "normal", size: int = SIZE) -> QIcon:
    """The icon of a command.

    ``tone`` is ``"normal"`` for an idle tool and ``"active"`` for the
    one that is armed -- the armed tool should look armed.
    """
    glyph = GLYPHS.get(op, "point")
    colour = PALETTE.accent if tone == "active" else PALETTE.icon
    icon = QIcon()
    icon.addPixmap(_draw(glyph, colour, size))
    return icon


def group_icon(family: str, tone: str = "normal", size: int = SIZE) -> QIcon:
    """The icon of a family of commands."""
    glyph = FAMILY_GLYPHS.get(family, "point")
    colour = PALETTE.accent if tone == "active" else PALETTE.icon
    icon = QIcon()
    icon.addPixmap(_draw(glyph, colour, size))
    return icon


__all__ = ["FAMILY_GLYPHS", "GLYPHS", "SIZE", "group_icon", "tool_icon"]
