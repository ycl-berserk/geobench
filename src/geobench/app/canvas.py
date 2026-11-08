"""The drawing surface.

A plain ``QWidget`` that paints the figure's primitives with ``QPainter``.
Not ``QGraphicsView``: the figure has tens of objects, not thousands,
and painting them directly is simpler and faster than keeping a scene
graph in sync with the kernel.

The canvas owns the **viewport** -- the mapping between figure
coordinates and pixels. Zooming and panning change the viewport, never
the figure, so what is on screen is always the kernel's figure and not a
copy of it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from geobench.app.controller import StudioController
from geobench.primitives import (
    ArcPrimitive,
    CirclePrimitive,
    LabelPrimitive,
    LinePrimitive,
    PointPrimitive,
    SegmentPrimitive,
)
from geobench.render import View, fit_view
from geobench.style import FigureStyle

#: How far a click may miss a point and still grab it, in pixels.
GRAB_RADIUS_PX = 8.0


@dataclass(frozen=True)
class Viewport:
    """The mapping between figure coordinates and pixels."""

    view: View
    width_px: float
    height_px: float

    @property
    def scale(self) -> float:
        return self.width_px / self.view.width if self.view.width else 1.0

    def to_screen(self, x: float, y: float) -> tuple[float, float]:
        scale = self.scale
        return (
            (x - self.view.x_min) * scale,
            self.height_px - (y - self.view.y_min) * scale,
        )

    def to_figure(self, px: float, py: float) -> tuple[float, float]:
        scale = self.scale
        return (
            self.view.x_min + px / scale,
            self.view.y_min - (py - self.height_px) / scale,
        )


class FigureCanvas(QWidget):
    """Draws the figure and lets the user drag its free points."""

    constructRequested = Signal(str, list)

    def __init__(self, controller: StudioController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setMinimumSize(360, 280)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._view: View | None = None
        self._zoom = 1.0
        self._pan = (0.0, 0.0)
        self._dragging: str | None = None
        self._drag_offset = (0.0, 0.0)
        self._pending_points: list[str] = []
        self._tool: str | None = None
        self._tool_arg_count = 0
        self._tool_args: list[str] = []
        controller.on_change(self.update)

    # -- the viewport ------------------------------------------------------

    def fit(self) -> None:
        """Fit the whole figure into the widget."""
        self._view = None
        self._zoom = 1.0
        self._pan = (0.0, 0.0)
        self.update()

    def _viewport(self) -> Viewport:
        view = self._view or fit_view(self.controller.figure(), self.controller.style.padding)
        width = view.width * self._zoom
        height = view.height * self._zoom
        # Keep the aspect ratio of the widget, so nothing is squashed.
        widget_ratio = self.width() / self.height() if self.height() else 1.0
        figure_ratio = width / height if height else 1.0
        if figure_ratio < widget_ratio:
            width = height * widget_ratio
        else:
            height = width / widget_ratio
        centre_x = (view.x_min + view.x_max) / 2
        centre_y = (view.y_min + view.y_max) / 2
        zoomed = View(
            centre_x - width / 2 + self._pan[0],
            centre_y - height / 2 + self._pan[1],
            centre_x + width / 2 + self._pan[0],
            centre_y + height / 2 + self._pan[1],
        )
        return Viewport(zoomed, float(self.width()), float(self.height()))

    # -- painting ----------------------------------------------------------

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("white"))
        viewport = self._viewport()
        style = self.controller.style

        for primitive in self.controller.primitives():
            if isinstance(primitive, LinePrimitive):
                self._draw_line(painter, viewport, primitive, style)
            elif isinstance(primitive, SegmentPrimitive):
                self._draw_segment(painter, viewport, primitive, style)
            elif isinstance(primitive, CirclePrimitive):
                self._draw_circle(painter, viewport, primitive, style)
            elif isinstance(primitive, ArcPrimitive):
                self._draw_arc(painter, viewport, primitive, style)
            elif isinstance(primitive, PointPrimitive):
                self._draw_point(painter, viewport, primitive, style)
            elif isinstance(primitive, LabelPrimitive):
                self._draw_label(painter, viewport, primitive, style)

    def _pen(self, auxiliary: bool, style: FigureStyle) -> QPen:
        width = style.auxiliary_stroke_width if auxiliary else style.stroke_width
        pen = QPen(QColor(style.stroke), width)
        if auxiliary:
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setDashPattern([3, 2])
        return pen

    def _draw_line(
        self, painter: QPainter, viewport: Viewport, primitive: LinePrimitive, style: FigureStyle
    ) -> None:
        clipped = _clip_line(primitive.a, primitive.b, primitive.c, viewport)
        if clipped is None:
            return
        x1, y1 = viewport.to_screen(clipped[0], clipped[1])
        x2, y2 = viewport.to_screen(clipped[2], clipped[3])
        painter.setPen(self._pen(primitive.auxiliary, style))
        painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def _draw_segment(
        self, painter: QPainter, viewport: Viewport, primitive: SegmentPrimitive, style: FigureStyle
    ) -> None:
        x1, y1 = viewport.to_screen(primitive.x1, primitive.y1)
        x2, y2 = viewport.to_screen(primitive.x2, primitive.y2)
        painter.setPen(self._pen(primitive.auxiliary, style))
        painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def _draw_circle(
        self, painter: QPainter, viewport: Viewport, primitive: CirclePrimitive, style: FigureStyle
    ) -> None:
        cx, cy = viewport.to_screen(primitive.cx, primitive.cy)
        radius = primitive.radius * viewport.scale
        painter.setPen(self._pen(primitive.auxiliary, style))
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

    def _draw_arc(
        self, painter: QPainter, viewport: Viewport, primitive: ArcPrimitive, style: FigureStyle
    ) -> None:
        """One arc or sector.

        The screen's y points down, so the figure's counter-clockwise
        angle is the negative of the painter's angle, and the span
        changes sign with it.
        """
        cx, cy = viewport.to_screen(primitive.cx, primitive.cy)
        radius = primitive.radius * viewport.scale
        rect = QRectF(cx - radius, cy - radius, 2 * radius, 2 * radius)
        start = round(-primitive.start_angle * 16)
        span = round(-primitive.span_angle * 16)
        painter.setPen(self._pen(primitive.auxiliary, style))
        if primitive.filled:
            painter.setBrush(QBrush(QColor(style.sector_fill)))
            painter.drawPie(rect, start, span)
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(rect, start, span)

    def _draw_point(
        self, painter: QPainter, viewport: Viewport, primitive: PointPrimitive, style: FigureStyle
    ) -> None:
        if not (math.isfinite(primitive.x) and math.isfinite(primitive.y)):
            return
        x, y = viewport.to_screen(primitive.x, primitive.y)
        radius = style.point_radius if primitive.free else style.derived_point_radius
        if primitive.undefined:
            # An object with no value at this placement: hollow, so the
            # user can see that something is missing (GeoGebra's "undefined").
            pen = QPen(QColor(style.stroke), 0.6)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
        else:
            painter.setPen(QPen(QColor(style.stroke), 0.4))
            painter.setBrush(QColor(style.stroke))
        painter.drawEllipse(QPointF(x, y), radius, radius)

    def _draw_label(
        self, painter: QPainter, viewport: Viewport, primitive: LabelPrimitive, style: FigureStyle
    ) -> None:
        x, y = viewport.to_screen(primitive.x, primitive.y)
        offset = style.label_offset * viewport.scale
        font = QFont()
        font.setItalic(True)
        font.setPointSizeF(style.font_size)
        painter.setFont(font)
        painter.setPen(QColor(style.stroke))
        painter.drawText(
            QPointF(x + primitive.offset_x * offset, y - primitive.offset_y * offset),
            primitive.text,
        )

    # -- interaction -------------------------------------------------------

    def set_tool(self, op: str | None, arg_count: int = 0) -> None:
        """Arm a construction tool, or disarm it with ``None``.

        A tool with ``arg_count`` arguments waits for that many points to
        be clicked, then asks the window to build it.
        """
        self._tool = op
        self._tool_arg_count = arg_count
        self._tool_args = []
        self.update()

    def tool(self) -> str | None:
        return self._tool

    def pending_args(self) -> list[str]:
        """The points clicked so far for the armed tool."""
        return list(self._tool_args)

    def _hit_point(self, px: float, py: float) -> str | None:
        viewport = self._viewport()
        best: str | None = None
        best_distance = GRAB_RADIUS_PX
        for node_id, (x, y) in self.controller.point_positions().items():
            sx, sy = viewport.to_screen(x, y)
            distance = math.hypot(sx - px, sy - py)
            if distance <= best_distance:
                best = node_id
                best_distance = distance
        return best

    def mousePressEvent(self, event: object) -> None:
        position = event.position()  # type: ignore[attr-defined]
        px, py = position.x(), position.y()
        if event.button() == Qt.MouseButton.MiddleButton:  # type: ignore[attr-defined]
            self._dragging = "__pan__"
            self._drag_offset = (px, py)
            return
        if self._tool is not None:
            self._tool_click(px, py)
            return
        node_id = self._hit_point(px, py)
        if node_id is not None and node_id in self.controller.free_points():
            self._dragging = node_id
            viewport = self._viewport()
            fx, fy = viewport.to_figure(px, py)
            current = self.controller.point_positions()[node_id]
            self._drag_offset = (fx - current[0], fy - current[1])

    def mouseMoveEvent(self, event: object) -> None:
        position = event.position()  # type: ignore[attr-defined]
        px, py = position.x(), position.y()
        if self._dragging is None:
            self.setCursor(
                Qt.CursorShape.OpenHandCursor
                if self._hit_point(px, py)
                else Qt.CursorShape.ArrowCursor
            )
            return
        if self._dragging == "__pan__":
            self._pan = (
                self._pan[0] - (px - self._drag_offset[0]) / self._viewport().scale,
                self._pan[1] + (py - self._drag_offset[1]) / self._viewport().scale,
            )
            self._drag_offset = (px, py)
            self.update()
            return
        viewport = self._viewport()
        fx, fy = viewport.to_figure(px, py)
        self.controller.move_point(
            self._dragging, fx - self._drag_offset[0], fy - self._drag_offset[1]
        )

    def mouseReleaseEvent(self, _event: object) -> None:
        self._dragging = None

    def wheelEvent(self, event: object) -> None:
        delta = event.angleDelta().y()  # type: ignore[attr-defined]
        if delta == 0:
            return
        factor = 1.15 if delta > 0 else 1 / 1.15
        self._zoom = max(0.1, min(50.0, self._zoom * factor))
        self.update()

    def _tool_click(self, px: float, py: float) -> None:
        """A click while a construction tool is armed."""
        viewport = self._viewport()
        node_id = self._hit_point(px, py)
        if node_id is None:
            if self._tool == "point.free":
                fx, fy = viewport.to_figure(px, py)
                self.controller.add_free_point(fx, fy)
            return
        self._tool_args.append(node_id)
        if len(self._tool_args) >= self._tool_arg_count:
            args = list(self._tool_args)
            self._tool_args = []
            self.constructRequested.emit(self._tool or "", args)


def _clip_line(
    a: float, b: float, c: float, viewport: Viewport
) -> tuple[float, float, float, float] | None:
    """Clip an infinite line to the viewport, in figure coordinates."""
    view = viewport.view
    if abs(a) < 1e-12 and abs(b) < 1e-12:
        return None
    if abs(b) > 1e-12:
        px, py = 0.0, -c / b
    else:
        px, py = -c / a, 0.0
    dx, dy = b, -a
    low, high = -1e12, 1e12
    edges = [
        (1.0, 0.0, view.x_min),
        (-1.0, 0.0, -view.x_max),
        (0.0, 1.0, view.y_min),
        (0.0, -1.0, -view.y_max),
    ]
    for nx, ny, offset in edges:
        denominator = nx * dx + ny * dy
        numerator = offset - (nx * px + ny * py)
        if abs(denominator) < 1e-12:
            if numerator > 0:
                return None
            continue
        t = numerator / denominator
        if denominator > 0:
            low = max(low, t)
        else:
            high = min(high, t)
    if low > high:
        return None
    return (
        px + low * dx,
        py + low * dy,
        px + high * dx,
        py + high * dy,
    )


__all__ = ["GRAB_RADIUS_PX", "FigureCanvas", "Viewport"]
