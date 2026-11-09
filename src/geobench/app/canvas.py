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
from PySide6.QtGui import QBrush, QColor, QFont, QKeyEvent, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from geobench.app.controller import StudioController
from geobench.app.tools import ToolArg, ToolSpec
from geobench.primitives import (
    ArcPrimitive,
    CirclePrimitive,
    LabelPrimitive,
    LinePrimitive,
    PointPrimitive,
    PolygonPrimitive,
    RayPrimitive,
    SegmentPrimitive,
    hit_test,
)
from geobench.render import View, clip_ray, fit_view
from geobench.style import FigureStyle

#: The view the canvas starts with: a square of ten units, which is
#: about the size of a competition figure before anything is drawn.
DEFAULT_VIEW = View(-10.0, -10.0, 10.0, 10.0)

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
    deleteRequested = Signal(str)
    valueRequested = Signal(str)

    def __init__(self, controller: StudioController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setMinimumSize(360, 280)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # The view is **fixed**. If it were recomputed from the figure
        # every time, the picture would jump under the cursor as soon as
        # a point was added -- and the click would land on a different
        # point than the one the user aimed at. "适应窗口" recomputes it
        # when the user asks for it.
        self._view: View = DEFAULT_VIEW
        self._zoom = 1.0
        self._pan = (0.0, 0.0)
        self._dragging: str | None = None
        self._drag_offset = (0.0, 0.0)
        self._pending_points: list[str] = []
        self._tool: ToolSpec | None = None
        self._tool_args: list[str] = []
        self._awaiting_value = False
        controller.on_change(self.update)

    # -- the viewport ------------------------------------------------------

    def fit(self) -> None:
        """Fit the whole figure into the widget."""
        self._view = fit_view(self.controller.figure(), self.controller.style.padding)
        self._zoom = 1.0
        self._pan = (0.0, 0.0)
        self.update()

    def _viewport(self) -> Viewport:
        view = self._view
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
            elif isinstance(primitive, RayPrimitive):
                self._draw_ray(painter, viewport, primitive, style)
            elif isinstance(primitive, CirclePrimitive):
                self._draw_circle(painter, viewport, primitive, style)
            elif isinstance(primitive, ArcPrimitive):
                self._draw_arc(painter, viewport, primitive, style)
            elif isinstance(primitive, PolygonPrimitive):
                self._draw_polygon(painter, viewport, primitive, style)
            elif isinstance(primitive, PointPrimitive):
                self._draw_point(painter, viewport, primitive, style)
            elif isinstance(primitive, LabelPrimitive):
                self._draw_label(painter, viewport, primitive, style)
        self._draw_hint(painter, style)

    def _draw_hint(self, painter: QPainter, style: FigureStyle) -> None:
        """Say, on the canvas itself, what a click will do.

        The status bar is at the bottom of the window and easy to miss;
        the canvas is where the eye is.
        """
        hint = self.armed_hint()
        if not hint:
            return
        font = QFont()
        font.setPointSizeF(style.font_size)
        painter.setFont(font)
        painter.setPen(QColor("#666666"))
        painter.drawText(QPointF(10.0, 18.0), hint)

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

    def _draw_polygon(
        self,
        painter: QPainter,
        viewport: Viewport,
        primitive: PolygonPrimitive,
        style: FigureStyle,
    ) -> None:
        points = [
            QPointF(*viewport.to_screen(primitive.vertices[2 * i], primitive.vertices[2 * i + 1]))
            for i in range(len(primitive.vertices) // 2)
        ]
        if len(points) < 2:
            return
        painter.setPen(self._pen(primitive.auxiliary, style))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if primitive.closed:
            painter.drawPolygon(QPolygonF(points))
        else:
            painter.drawPolyline(QPolygonF(points))

    def _draw_ray(
        self, painter: QPainter, viewport: Viewport, primitive: RayPrimitive, style: FigureStyle
    ) -> None:
        clipped = clip_ray(
            primitive.x0, primitive.y0, primitive.x1, primitive.y1, viewport.view
        )
        if clipped is None:
            return
        x1, y1 = viewport.to_screen(clipped[0], clipped[1])
        x2, y2 = viewport.to_screen(clipped[2], clipped[3])
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
        offset = style.label_offset
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

    def set_tool(self, tool: ToolSpec | None) -> None:
        """Arm a construction tool, or disarm it with ``None``.

        The tool knows what it needs: a click on a point, a click on a
        circle, a number typed in. The canvas asks for them one at a
        time, in the order the operator takes them.
        """
        self._tool = tool
        self._tool_args = []
        self._awaiting_value = False
        if tool is None:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()
            return
        self.setCursor(
            Qt.CursorShape.CrossCursor
            if tool.op == "point.free"
            else Qt.CursorShape.PointingHandCursor
        )
        self.update()
        self._ask_for_next()

    def tool(self) -> ToolSpec | None:
        return self._tool

    def pending_args(self) -> list[str]:
        """What has been collected so far for the armed tool."""
        return list(self._tool_args)

    def reset_pending(self) -> None:
        """Forget what was collected; the tool starts again from nothing."""
        self._tool_args = []
        self._awaiting_value = False
        self.update()
        self._ask_for_next()

    def armed_hint(self) -> str:
        """What the canvas is waiting for."""
        tool = self._tool
        if tool is None:
            return ""
        arg = self._next_arg()
        if arg is None:
            return tool.hint
        if tool.variable:
            return f"{tool.hint}（已经点了 {len(self._tool_args)} 个）"
        if arg.clickable:
            waiting = len(self._tool_args)
            if waiting == 0:
                return tool.hint
            return f"{tool.hint}（已经选了 {waiting} 个）"
        return f"{tool.hint}（请输入{arg.text}）"

    # -- collecting the arguments -----------------------------------------

    def _next_arg(self) -> ToolArg | None:
        """The argument the tool is waiting for, if any."""
        tool = self._tool
        if tool is None:
            return None
        index = len(self._tool_args)
        if tool.variable:
            if index < len(tool.args):
                return tool.args[index]
            return ToolArg(kind=tool.var_kind)
        if index < len(tool.args):
            return tool.args[index]
        return None

    def _ask_for_next(self) -> None:
        """If the next argument cannot be clicked, ask the window for it."""
        arg = self._next_arg()
        if arg is None or arg.clickable:
            return
        self._awaiting_value = True
        self.valueRequested.emit(arg.kind)

    def supply_value(self, text: str) -> None:
        """The window's answer to a request for a number or a choice."""
        if not self._awaiting_value:
            return
        self._awaiting_value = False
        self._tool_args.append(text)
        self._finish_or_ask()

    def _finish_or_ask(self) -> None:
        tool = self._tool
        if tool is None:
            return
        if not tool.variable and len(self._tool_args) >= len(tool.args):
            args = list(self._tool_args)
            self._tool_args = []
            self.constructRequested.emit(tool.op, args)
            self._ask_for_next()
            return
        self._ask_for_next()

    def _finish_variable_tool(self) -> None:
        """Build what the variable tool has collected so far."""
        tool = self._tool
        if tool is None or not tool.variable:
            return
        if len(self._tool_args) < tool.min_args:
            return
        args = list(self._tool_args)
        self._tool_args = []
        self.constructRequested.emit(tool.op, args)
        self.update()

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
        """What a press means.

        Three rules, and they are worth writing down because they are
        what a drawing program is expected to do:

        - the middle button pans, always;
        - a press on an **existing point** grabs that point, so it can
          be dragged -- unless another tool is armed and waiting for
          arguments, in which case the press *picks* the point;
        - a press on empty canvas does what the armed tool says, and
          with no tool armed it does nothing.
        """
        position = event.position()  # type: ignore[attr-defined]
        px, py = position.x(), position.y()
        if event.button() == Qt.MouseButton.MiddleButton:  # type: ignore[attr-defined]
            self._dragging = "__pan__"
            self._drag_offset = (px, py)
            return
        node_id = self._hit_point(px, py)
        if (
            node_id is not None
            and node_id in self.controller.free_points()
            and (self._tool is None or self._tool.op == "point.free")
        ):
            # Grab it. The point tool is the one tool whose clicks on a
            # point mean "move it" rather than "use it as an argument".
            self.controller.push_undo()
            self._dragging = node_id
            viewport = self._viewport()
            fx, fy = viewport.to_figure(px, py)
            current = self.controller.point_positions()[node_id]
            self._drag_offset = (fx - current[0], fy - current[1])
            return
        if self._tool is not None:
            self._tool_click(px, py)
            return

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

    def contextMenuEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        """Right-click on a point: ask the window to delete it."""
        node_id = self._hit_point(event.pos().x(), event.pos().y())
        if node_id is None:
            return
        self.deleteRequested.emit(node_id)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """The return key finishes a variable tool."""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._finish_variable_tool()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event: object) -> None:
        delta = event.angleDelta().y()  # type: ignore[attr-defined]
        if delta == 0:
            return
        factor = 1.15 if delta > 0 else 1 / 1.15
        self._zoom = max(0.1, min(50.0, self._zoom * factor))
        self.update()

    def _tool_click(self, px: float, py: float) -> None:
        """A click while a construction tool is armed."""
        tool = self._tool
        if tool is None:
            return
        viewport = self._viewport()
        if tool.op == "point.free":
            fx, fy = viewport.to_figure(px, py)
            self.controller.add_free_point(fx, fy)
            return
        arg = self._next_arg()
        if arg is None or not arg.clickable:
            return
        node_id = self._hit_object(px, py, _KIND_KINDS.get(arg.kind, (arg.kind,)))
        if node_id is None:
            return
        if self._tool_args and self._tool_args[-1] == node_id:
            # The same object twice in a row: a double click, not a
            # second argument. A line through one point is not a line.
            return
        self._tool_args.append(node_id)
        self._finish_or_ask()

    def _hit_object(
        self, px: float, py: float, kinds: tuple[str, ...]
    ) -> str | None:
        """The nearest object of these kinds under the click, if any.

        The geometry lives in the primitives; the canvas only turns the
        click into figure coordinates and hands over the tolerance.
        """
        viewport = self._viewport()
        x, y = viewport.to_figure(px, py)
        tolerance = GRAB_RADIUS_PX / viewport.scale
        figure = self.controller.figure()
        candidates = [
            primitive
            for primitive in self.controller.primitives()
            if primitive.id
            and primitive.id in figure.nodes
            and figure.nodes[primitive.id].kind in kinds
        ]
        return hit_test(candidates, x, y, tolerance)


#: The node kinds that answer to each argument kind. A construction that
#: wants a line is happy with a segment: "the foot on BC" means the same
#: thing whether BC is drawn as a segment or as a line.
_KIND_KINDS: dict[str, tuple[str, ...]] = {
    "point": ("point",),
    "line": ("line", "segment", "ray"),
    "segment": ("segment",),
    "circle": ("circle",),
    "polygon": ("polygon",),
}


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
