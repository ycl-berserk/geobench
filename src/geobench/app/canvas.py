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
from dataclasses import dataclass, replace

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QKeyEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QInputDialog,
    QMenu,
    QMessageBox,
    QWidget,
)

from geobench.app.appearance_dialog import AppearanceDialog
from geobench.app.controller import StudioController
from geobench.app.theme import PALETTE
from geobench.app.tools import ToolArg, ToolSpec
from geobench.errors import GeobenchError
from geobench.model import Node
from geobench.primitives import (
    ArcPrimitive,
    CirclePrimitive,
    Ink,
    LabelPrimitive,
    LinePrimitive,
    PointPrimitive,
    PolygonPrimitive,
    RayPrimitive,
    SegmentPrimitive,
    TextPrimitive,
    distance_to,
    hit_test,
)
from geobench.render import View, clip_ray, fit_view
from geobench.style import (
    COLOR_CHOICES,
    LABEL_DIRECTIONS,
    LINE_WIDTHS,
    POINT_SIZES,
    FigureStyle,
)

#: The view the canvas starts with: a square of ten units, which is
#: about the size of a competition figure before anything is drawn.
DEFAULT_VIEW = View(-10.0, -10.0, 10.0, 10.0)

#: The small pointer used everywhere on the drawing surface.  The system
#: arrow is large enough to cover the point under it; this one is drawn
#: at 18 px, in one ink colour (no white halo).
_PRECISION_CURSOR: QCursor | None = None


def precision_cursor() -> QCursor:
    global _PRECISION_CURSOR
    if _PRECISION_CURSOR is not None:
        return _PRECISION_CURSOR
    size = 18
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    arrow = QPolygonF(
        [
            QPointF(2.0, 1.0),
            QPointF(2.0, 14.0),
            QPointF(5.0, 10.5),
            QPointF(7.4, 16.2),
            QPointF(9.4, 15.2),
            QPointF(7.0, 9.7),
            QPointF(12.0, 9.7),
        ]
    )
    painter.setPen(QPen(QColor(PALETTE.text), 0.9))
    painter.setBrush(QColor(PALETTE.text))
    painter.drawPolygon(arrow)
    painter.end()
    _PRECISION_CURSOR = QCursor(pixmap, 2, 1)
    return _PRECISION_CURSOR

#: How far a click may miss a point and still grab it, in pixels.
GRAB_RADIUS_PX = 8.0

#: How much closer a crossing has to be than the object it lies on, in
#: pixels, before the click means "their intersection".  On the crossing
#: itself both distances are zero; a click a few pixels along the line
#: means the line.  This is that few pixels.
CROSSING_MAGNET_PX = 4.0

#: The colour of the paper the figure is drawn on.
PAPER = "#ffffff"

#: The corner radius of the paper, in pixels.
PAPER_RADIUS = 10.0

#: How far one click of the zoom buttons goes.
ZOOM_STEP = 1.2

#: The thinnest a stroke may be on the screen. The paper's 0.4pt is
#: right for print and too thin to work with.
SCREEN_MIN_STROKE = 1.2
SCREEN_MIN_AUX_STROKE = 0.9


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
    #: Delete with several objects selected: one action, one undo step.
    deleteManyRequested = Signal(list)
    pointEditRequested = Signal(str)
    valueRequested = Signal(str)
    #: The selected object changed. The list is in the order the objects
    #: were picked, because a claim is about *these* objects in *this*
    #: order ("a point, on this circle"), and an unordered set would
    #: leave the window guessing.
    selectionChanged = Signal(list)

    def __init__(self, controller: StudioController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        #: How many steps of the construction are drawn; None is all of them.
        self._playback_limit: int | None = None
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
        #: Coordinates on the paper.  Screen only: the export is the
        #: figure, not the worksheet.  Off by default: a competition
        #: figure is paper, not graph paper.
        self.show_axes = False
        self._dragging: str | None = None
        self._drag_moved = False
        self._drag_offset = (0.0, 0.0)
        self._pan_from_select = False
        self._pan_moved = False
        #: The latest drag position, applied at most once per timer tick.
        #: Mouse events can arrive far faster than a figure can be
        #: recomputed; the dropped intermediate frames are invisible.
        self._drag_target: tuple[float, float] | None = None
        self._drag_timer = QTimer(self)
        self._drag_timer.setSingleShot(True)
        self._drag_timer.setInterval(16)
        self._drag_timer.timeout.connect(self._apply_drag)
        self._pending_points: list[str] = []
        #: Proved claims worth drawing: equal lengths get ticks, a right
        #: angle gets its square.  The table says what is true; the
        #: figure says it where the eye looks.
        self._proof_marks: list[tuple[str, tuple[str, ...]]] = []
        self._tool: ToolSpec | None = None
        self._tool_args: list[str] = []
        self._awaiting_value = False
        self._selected: list[str] = []
        controller.on_change(self.update)
        controller.on_move(self._moved)

    # -- the viewport ------------------------------------------------------

    def fit(self) -> None:
        """Fit the whole figure into the widget."""
        self._view = fit_view(self.controller.figure(), self.controller.style.padding)
        self._zoom = 1.0
        self._pan = (0.0, 0.0)
        self.update()

    def zoom(self, factor: float) -> None:
        """Zoom in or out, about the middle of the picture.

        The wheel does this too; the buttons are for the people who do
        not know that, and for a projector without one.
        """
        self._zoom = max(0.1, min(50.0, self._zoom * factor))
        self.update()

    def zoom_in(self) -> None:
        self.zoom(ZOOM_STEP)

    def zoom_out(self) -> None:
        self.zoom(1 / ZOOM_STEP)

    def set_proof_marks(self, marks: list[tuple[str, tuple[str, ...]]]) -> None:
        """Draw the claims the kernel proved, in the figure itself."""
        self._proof_marks = list(marks)
        self.update()

    def set_show_axes(self, shown: bool) -> None:
        """Show or hide the axes and their numbers."""
        self.show_axes = shown
        self.update()

    def set_playback_limit(self, limit: int | None) -> None:
        """Show only the first steps of the construction.

        None means the whole figure, which is what the studio shows
        while you are working on it.
        """
        self._playback_limit = limit
        self.update()

    def _viewport(self) -> Viewport:
        view = self._view
        # A larger zoom means a *smaller* slice of the plane on screen.
        width = view.width / self._zoom
        height = view.height / self._zoom
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
        viewport = self._viewport()
        style = self.controller.style

        # The sheet of paper the figure is drawn on. Everything is
        # clipped to it, so the rounded corners are real.
        paper = QPainterPath()
        paper.addRoundedRect(QRectF(self.rect()), PAPER_RADIUS, PAPER_RADIUS)
        painter.fillPath(paper, QColor(PAPER))
        painter.setClipPath(paper)
        self._draw_grid(painter, viewport)

        primitives = self.controller.primitives()
        if self._playback_limit is not None:
            # The playback shows the construction being built: only the
            # steps up to the one being reached are drawn.
            allowed = set(list(self.controller.figure().nodes)[: self._playback_limit])
            primitives = [
                primitive
                for primitive in primitives
                if not primitive.id or primitive.id in allowed
            ]

        for primitive in primitives:
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
            elif isinstance(primitive, TextPrimitive):
                self._draw_text(painter, viewport, primitive, style)
        self._draw_proof_marks(painter, viewport)
        self._draw_selection(painter, viewport, style)
        self._draw_hint(painter, style)

    # -- proof marks -------------------------------------------------------

    def _numeric(self, node_id: str, key: str) -> tuple[float, ...] | None:
        node = self.controller.figure().nodes.get(node_id)
        if node is None:
            return None
        values = (node.cache.get("numeric") or {}).get(key)
        if values is None:
            return None
        if isinstance(values, (int, float)):
            return (float(values),)
        return tuple(float(value) for value in values)

    def _point_xy(self, node_id: str) -> tuple[float, float] | None:
        coords = self._numeric(node_id, "coords")
        if coords is None or len(coords) < 2:
            return None
        return coords[0], coords[1]

    def _line_coeffs(self, node_id: str) -> tuple[float, float, float] | None:
        line = self._numeric(node_id, "line")
        if line is not None and len(line) >= 3:
            return line[0], line[1], line[2]
        segment = self._numeric(node_id, "segment")
        if segment is not None and len(segment) == 4:
            x1, y1, x2, y2 = segment
            return y1 - y2, x2 - x1, x1 * y2 - x2 * y1
        return None

    def _draw_proof_marks(self, painter: QPainter, viewport: Viewport) -> None:
        if not self._proof_marks:
            return
        painter.save()
        painter.setPen(QPen(QColor(PALETTE.ok), 1.6))
        tick_index = 0
        angle_index = 0
        for kind, args in self._proof_marks:
            if kind == "equal_length" and len(args) == 4:
                tick_index += 1
                count = (tick_index - 1) % 3 + 1
                first = (self._point_xy(args[0]), self._point_xy(args[1]))
                second = (self._point_xy(args[2]), self._point_xy(args[3]))
                if all(point is not None for pair in (first, second) for point in pair):
                    self._tick(painter, viewport, first, count)
                    self._tick(painter, viewport, second, count)
            elif kind == "perpendicular" and len(args) == 2:
                self._right_angle(painter, viewport, args[0], args[1])
            elif kind == "angle_equal" and len(args) == 6:
                angle_index += 1
                count = (angle_index - 1) % 3 + 1
                # The paper writes ∠ABC with the vertex in the middle.
                self._angle_mark(
                    painter, viewport, args[1], args[0], args[2], count
                )
                self._angle_mark(
                    painter, viewport, args[4], args[3], args[5], count
                )
        painter.restore()

    def _tick(
        self,
        painter: QPainter,
        viewport: Viewport,
        pair: tuple[tuple[float, float] | None, tuple[float, float] | None],
        count: int,
    ) -> None:
        start, end = pair
        if start is None or end is None:
            return
        x1, y1 = viewport.to_screen(*start)
        x2, y2 = viewport.to_screen(*end)
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length < 2.0:
            return
        ux, uy = dx / length, dy / length
        nx, ny = -uy, ux
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        for index in range(count):
            offset = (index - (count - 1) / 2) * 4.0
            cx, cy = mx + nx * offset, my + ny * offset
            half = 5.0
            painter.drawLine(
                QPointF(cx - ux * half, cy - uy * half),
                QPointF(cx + ux * half, cy + uy * half),
            )

    def _right_angle(
        self, painter: QPainter, viewport: Viewport, first: str, second: str
    ) -> None:
        one = self._line_coeffs(first)
        two = self._line_coeffs(second)
        if one is None or two is None:
            return
        a1, b1, c1 = one
        a2, b2, c2 = two
        determinant = a1 * b2 - a2 * b1
        if abs(determinant) < 1e-12:
            return
        x = (b1 * c2 - b2 * c1) / determinant
        y = (c1 * a2 - c2 * a1) / determinant
        px, py = viewport.to_screen(x, y)
        u = self._screen_direction(viewport, one)
        v = self._screen_direction(viewport, two)
        if u is None or v is None:
            return
        size = 12.0
        ux, uy = u
        vx, vy = v
        painter.drawLine(
            QPointF(px, py), QPointF(px + ux * size, py + uy * size)
        )
        painter.drawLine(
            QPointF(px + ux * size, py + uy * size),
            QPointF(px + (ux + vx) * size, py + (uy + vy) * size),
        )
        painter.drawLine(
            QPointF(px, py), QPointF(px + vx * size, py + vy * size)
        )

    def _angle_mark(
        self,
        painter: QPainter,
        viewport: Viewport,
        vertex: str,
        first: str,
        second: str,
        count: int,
    ) -> None:
        """A small arc at the vertex, with a tick for which equality it is."""
        centre = self._point_xy(vertex)
        one = self._point_xy(first)
        two = self._point_xy(second)
        if centre is None or one is None or two is None:
            return
        vx, vy = viewport.to_screen(*centre)
        ax, ay = viewport.to_screen(*one)
        bx, by = viewport.to_screen(*two)
        start = math.atan2(ay - vy, ax - vx)
        end = math.atan2(by - vy, bx - vx)
        sweep = (end - start) % (2 * math.pi)
        if sweep > math.pi:
            sweep -= 2 * math.pi
        radius = 17.0 + 3.0 * (count - 1)
        points = []
        steps = 14
        for index in range(steps + 1):
            angle = start + sweep * index / steps
            points.append(
                QPointF(
                    vx + radius * math.cos(angle),
                    vy + radius * math.sin(angle),
                )
            )
        for index in range(steps):
            painter.drawLine(points[index], points[index + 1])
        # The tick sits on the arc, so two equal angles can be paired by
        # counting marks the way a paper does it.
        middle = start + sweep / 2
        for offset in range(count):
            shift = (offset - (count - 1) / 2) * 0.10
            angle = middle + shift
            inner = radius - 3.5
            outer = radius + 3.5
            painter.drawLine(
                QPointF(
                    vx + inner * math.cos(angle),
                    vy + inner * math.sin(angle),
                ),
                QPointF(
                    vx + outer * math.cos(angle),
                    vy + outer * math.sin(angle),
                ),
            )

    def _screen_direction(
        self, viewport: Viewport, line: tuple[float, float, float]
    ) -> tuple[float, float] | None:
        a, b, c = line
        if abs(b) > abs(a):
            p1 = (0.0, -c / b)
            p2 = (1.0, -(a + c) / b)
        elif a != 0:
            p1 = (-c / a, 0.0)
            p2 = (-(b + c) / a, 1.0)
        else:
            return None
        x1, y1 = viewport.to_screen(*p1)
        x2, y2 = viewport.to_screen(*p2)
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length == 0:
            return None
        return dx / length, dy / length

    def _draw_grid(self, painter: QPainter, viewport: Viewport) -> None:
        """A grid, faint enough to be a guide rather than a subject.

        It is on the screen only: the exported figure is black on white,
        the way a competition paper is.
        """
        if not self.show_axes:
            # The grid goes with the axes: both are worksheet aids, and a
            # blank sheet is what a competition problem is drawn on.
            return
        step = 1.0
        pixels = step * viewport.scale
        view = viewport.view
        if pixels >= 14.0:
            # Too close together and it is a grey wash; the axes keep
            # their numbers even when the grid gives up.
            first_x = math.floor(view.x_min / step) * step
            first_y = math.floor(view.y_min / step) * step
            painter.setPen(QPen(QColor(PALETTE.grid), 1.0))
            x = first_x
            while x <= view.x_max:
                sx, _ = viewport.to_screen(x, 0)
                painter.drawLine(QPointF(sx, 0), QPointF(sx, self.height()))
                x += step
            y = first_y
            while y <= view.y_max:
                _, sy = viewport.to_screen(0, y)
                painter.drawLine(QPointF(0, sy), QPointF(self.width(), sy))
                y += step
        if self.show_axes:
            self._draw_axes(painter, viewport)

    def _draw_axes(self, painter: QPainter, viewport: Viewport) -> None:
        """The axes and their numbers, so a coordinate can be read.

        Screen only: a competition paper does not print its coordinate
        grid, and neither does the export.  The axes are drawn only when
        they are inside the view; a figure far from the origin is not
        crossed by a line it never reaches.
        """
        view = viewport.view
        scale = viewport.scale
        if scale <= 0:
            return
        step = _tick_step(scale)
        font = QFont()
        # The ticks belong to the interface, not to the figure: they
        # follow the chosen interface size.
        font.setPointSizeF(max(6.0, QApplication.font().pointSizeF() * 0.72))
        painter.setFont(font)
        axis_pen = QPen(QColor(PALETTE.grid_axis), 1.0)
        label_colour = QColor(PALETTE.text_muted)

        if view.y_min <= 0 <= view.y_max:
            _, sy = viewport.to_screen(0.0, 0.0)
            painter.setPen(axis_pen)
            painter.drawLine(QPointF(0, sy), QPointF(self.width(), sy))
            painter.setPen(label_colour)
            value = math.ceil(view.x_min / step) * step
            while value <= view.x_max:
                if abs(value) > 1e-9:
                    sx, _ = viewport.to_screen(value, 0.0)
                    painter.drawLine(QPointF(sx, sy - 3), QPointF(sx, sy + 3))
                    painter.drawText(
                        QPointF(sx + 3, min(sy + 14, self.height() - 2)),
                        _tick_text(value),
                    )
                value += step

        if view.x_min <= 0 <= view.x_max:
            sx, _ = viewport.to_screen(0.0, 0.0)
            painter.setPen(axis_pen)
            painter.drawLine(QPointF(sx, 0), QPointF(sx, self.height()))
            painter.setPen(label_colour)
            value = math.ceil(view.y_min / step) * step
            while value <= view.y_max:
                if abs(value) > 1e-9:
                    _, sy = viewport.to_screen(0.0, value)
                    painter.drawLine(QPointF(sx - 3, sy), QPointF(sx + 3, sy))
                    painter.drawText(
                        QPointF(max(2.0, sx - 32), sy - 3), _tick_text(value)
                    )
                value += step

        if view.x_min <= 0 <= view.x_max and view.y_min <= 0 <= view.y_max:
            sx, sy = viewport.to_screen(0.0, 0.0)
            painter.setPen(label_colour)
            painter.drawText(QPointF(sx + 4, sy + 14), "0")

    def _draw_selection(
        self, painter: QPainter, viewport: Viewport, style: FigureStyle
    ) -> None:
        """The selected object, drawn again in the accent colour.

        Drawing it twice is simpler than drawing it once in two
        colours, and it means the selection looks the same whatever the
        object is.
        """
        if not self._selected:
            return
        marked = replace(style, stroke=PALETTE.accent)
        for primitive in self.controller.primitives():
            if getattr(primitive, "id", "") not in self._selected:
                continue
            # The accent colour wins over the object's own colour: a
            # red line that is selected has to look selected.
            primitive = replace(
                primitive, ink=replace(primitive.ink, color=PALETTE.accent)
            )
            if isinstance(primitive, LinePrimitive):
                self._draw_line(painter, viewport, primitive, marked)
            elif isinstance(primitive, SegmentPrimitive):
                self._draw_segment(painter, viewport, primitive, marked)
            elif isinstance(primitive, RayPrimitive):
                self._draw_ray(painter, viewport, primitive, marked)
            elif isinstance(primitive, CirclePrimitive):
                self._draw_circle(painter, viewport, primitive, marked)
            elif isinstance(primitive, ArcPrimitive):
                self._draw_arc(painter, viewport, primitive, marked)
            elif isinstance(primitive, PolygonPrimitive):
                self._draw_polygon(painter, viewport, primitive, marked)
            elif isinstance(primitive, PointPrimitive):
                self._draw_point(painter, viewport, primitive, marked)

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
        metrics = painter.fontMetrics()
        width = metrics.horizontalAdvance(hint) + 20.0
        height = float(metrics.height()) + 12.0
        box = QRectF(10.0, 10.0, width, height)
        # A note in the corner of the sheet, not text floating over the
        # figure: the note has a ground of its own so it can be read
        # whatever is underneath it.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(PALETTE.accent_soft))
        painter.drawRoundedRect(box, 8.0, 8.0)
        painter.setPen(QColor(PALETTE.accent))
        painter.drawText(
            QPointF(box.left() + 10.0, box.top() + height / 2.0 + metrics.ascent() / 2.0 - 1.0),
            hint,
        )

    def _pen(
        self, auxiliary: bool, style: FigureStyle, ink: Ink | None = None
    ) -> QPen:
        """The pen of a stroke on the screen.

        The paper draws a competition figure in 0.4pt, because that is
        what a printed figure looks like. The screen is not paper: a
        hairline that thin is almost invisible while you are working,
        so the screen draws a little heavier and the export stays true
        to the paper.

        An object's own colour and width win over the figure's, when it
        has them (T050).
        """
        width = style.auxiliary_stroke_width if auxiliary else style.stroke_width
        if ink is not None and ink.width is not None:
            width = ink.width
        width = max(width, SCREEN_MIN_STROKE if not auxiliary else SCREEN_MIN_AUX_STROKE)
        color = ink.color if ink is not None and ink.color else style.stroke
        pen = QPen(QColor(color), width)
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
        painter.setPen(self._pen(primitive.auxiliary, style, primitive.ink))
        painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def _draw_segment(
        self, painter: QPainter, viewport: Viewport, primitive: SegmentPrimitive, style: FigureStyle
    ) -> None:
        x1, y1 = viewport.to_screen(primitive.x1, primitive.y1)
        x2, y2 = viewport.to_screen(primitive.x2, primitive.y2)
        painter.setPen(self._pen(primitive.auxiliary, style, primitive.ink))
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
        painter.setPen(self._pen(primitive.auxiliary, style, primitive.ink))
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
        painter.setPen(self._pen(primitive.auxiliary, style, primitive.ink))
        painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def _draw_circle(
        self, painter: QPainter, viewport: Viewport, primitive: CirclePrimitive, style: FigureStyle
    ) -> None:
        cx, cy = viewport.to_screen(primitive.cx, primitive.cy)
        radius = primitive.radius * viewport.scale
        painter.setPen(self._pen(primitive.auxiliary, style, primitive.ink))
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

    def _draw_arc(
        self, painter: QPainter, viewport: Viewport, primitive: ArcPrimitive, style: FigureStyle
    ) -> None:
        """One arc or sector.

        Qt measures arc angles counter-clockwise from 3 o'clock, which is
        the same convention the primitives use (they are worked out in
        figure coordinates, where y points up).  Negating them here -- as
        this used to -- mirrors every arc about the horizontal axis, so
        an angle mark appeared in the wrong quadrant.
        """
        cx, cy = viewport.to_screen(primitive.cx, primitive.cy)
        radius = primitive.radius * viewport.scale
        rect = QRectF(cx - radius, cy - radius, 2 * radius, 2 * radius)
        start = round(primitive.start_angle * 16)
        span = round(primitive.span_angle * 16)
        painter.setPen(self._pen(primitive.auxiliary, style, primitive.ink))
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
        ink = primitive.ink
        radius = (
            ink.point_size
            if ink.point_size is not None
            else (style.point_radius if primitive.free else style.derived_point_radius)
        )
        color = QColor(ink.color or style.stroke)
        if primitive.undefined:
            # An object with no value at this placement: hollow, so the
            # user can see that something is missing (GeoGebra's "undefined").
            painter.setPen(QPen(color, 0.6))
            painter.setBrush(Qt.BrushStyle.NoBrush)
        else:
            painter.setPen(QPen(color, 0.4))
            painter.setBrush(color)
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
        painter.setPen(QColor(primitive.ink.color or style.stroke))
        painter.drawText(
            QPointF(x + primitive.offset_x * offset, y - primitive.offset_y * offset),
            primitive.text,
        )

    def _draw_text(
        self,
        painter: QPainter,
        viewport: Viewport,
        primitive: TextPrimitive,
        style: FigureStyle,
    ) -> None:
        """A note on the paper, left-aligned at its anchor."""
        x, y = viewport.to_screen(primitive.x, primitive.y)
        font = QFont()
        font.setFamily(style.font_family.split(",")[0].strip())
        font.setPointSizeF(primitive.font_size)
        painter.setFont(font)
        painter.setPen(QColor(primitive.ink.color or style.stroke))
        line_height = painter.fontMetrics().height()
        for index, line in enumerate(primitive.text.splitlines() or [""]):
            painter.drawText(
                QPointF(x, y + index * line_height),
                line,
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
        # Every tool uses the same small pointer: the cursor is the hand,
        # and the armed tool is already named on the toolbar.
        self.setCursor(precision_cursor())
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
        """What the canvas is waiting for.

        The point tool is armed from the start, and its hint teaches
        the first action -- but once there is a figure, a hint that
        covers the paper is noise, so it goes away.
        """
        tool = self._tool
        if tool is None:
            return ""
        if tool.op == "point.free" and self.controller.figure().nodes:
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

    def select(self, node_id: str | None, additive: bool = False) -> None:
        """Select an object, add one to the selection, or clear it.

        A claim is often about more than one object -- three points are
        collinear, two lines are parallel -- so selection is a list, in
        the order the teacher picked.  Shift-click adds (or removes);
        a plain click starts again.
        """
        if node_id is None:
            if not self._selected:
                return
            self._selected = []
        elif additive:
            if node_id in self._selected:
                self._selected = [item for item in self._selected if item != node_id]
            else:
                self._selected = [*self._selected, node_id]
        elif self._selected == [node_id]:
            self._selected = []
        else:
            self._selected = [node_id]
        self.selectionChanged.emit(list(self._selected))
        self.update()

    def selected(self) -> list[str]:
        """The selected objects, in the order they were picked."""
        return list(self._selected)

    def prune_selection(self) -> None:
        """Forget selected objects that no longer exist.

        Deleting a point deletes what depends on it; a selection that
        still names the deleted objects would make the next question be
        about something that is not on the paper.
        """
        figure = self.controller.figure()
        keep = [node_id for node_id in self._selected if node_id in figure.nodes]
        if keep != self._selected:
            self._selected = keep
            self.selectionChanged.emit(list(keep))
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
            self._pan_from_select = False
            self._pan_moved = False
            return
        additive = bool(
            QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier
        )
        if additive and (self._tool is None or self._tool.op == "select"):
            # Shift-click builds a selection, even on a draggable point:
            # picking three points to ask "are they collinear" must not
            # require dragging them one by one.
            picked = self._hit_object(px, py, SELECTABLE_KINDS)
            if picked is not None:
                self.select(picked, additive=True)
                return
        node_id = self._hit_point(px, py)
        if (
            node_id is not None
            and self.controller.draggable(node_id)
            and (
                self._tool is None
                or self._tool.op in ("point.free", "select")
            )
        ):
            # Grab it. The point tool and the pointer are the two tools
            # whose clicks on a point mean "move it" rather than "use it
            # as an argument".
            self.select(node_id)
            self.controller.push_undo()
            self._dragging = node_id
            self._drag_moved = False
            viewport = self._viewport()
            fx, fy = viewport.to_figure(px, py)
            current = self.controller.point_positions()[node_id]
            self._drag_offset = (fx - current[0], fy - current[1])
            return
        if (
            self._tool is None or self._tool.op == "select"
        ) and self._hit_object(px, py, SELECTABLE_KINDS) is None:
            # Empty paper with the pointer: drag it to move the sheet.
            # A click without movement still clears the selection.
            self._dragging = "__pan__"
            self._drag_offset = (px, py)
            self._pan_from_select = True
            self._pan_moved = False
            return
        if self._tool is not None:
            self._tool_click(px, py)
            return

    def mouseDoubleClickEvent(self, event: object) -> None:
        """A double click on a point: type its exact position.

        Dragging puts a point near where the mouse was. A competition
        figure wants it at exactly (3/2, 7/4), and the way to say that
        is to type it.
        """
        position = event.position()  # type: ignore[attr-defined]
        node_id = self._hit_point(position.x(), position.y())
        if node_id is None:
            return
        self.pointEditRequested.emit(node_id)

    def mouseMoveEvent(self, event: object) -> None:
        position = event.position()  # type: ignore[attr-defined]
        px, py = position.x(), position.y()
        if self._dragging is None:
            # Hovering must not swap the small pointer for a large system
            # hand.  The pointer is the same from the first click on.
            return
        if self._dragging == "__pan__":
            self._pan = (
                self._pan[0] - (px - self._drag_offset[0]) / self._viewport().scale,
                self._pan[1] + (py - self._drag_offset[1]) / self._viewport().scale,
            )
            self._drag_offset = (px, py)
            self._pan_moved = True
            self.update()
            return
        viewport = self._viewport()
        fx, fy = viewport.to_figure(px, py)
        self._drag_moved = True
        self._drag_target = (
            fx - self._drag_offset[0],
            fy - self._drag_offset[1],
        )
        if not self._drag_timer.isActive():
            self._drag_timer.start()

    def _apply_drag(self) -> None:
        """Move the point to the latest cursor position, once per tick."""
        target = self._drag_target
        self._drag_target = None
        if target is None or self._dragging in (None, "__pan__"):
            return
        self.controller.move_point(self._dragging, target[0], target[1])

    def mouseReleaseEvent(self, _event: object) -> None:
        moved = self._drag_moved
        if self._dragging == "__pan__":
            if self._pan_from_select and not self._pan_moved:
                self.select(None)
        elif self._dragging is not None and moved:
            # Apply the last position before the figure settles. The
            # timer may have a frame queued, and the release is where
            # the final pixel has to land.
            self._drag_timer.stop()
            self._apply_drag()
            # The drag is over: the figure settles and the verdicts are
            # recomputed. A click that only picked something is not a
            # change, and changes nothing.
            self.controller.finish_move()
        self._dragging = None
        self._drag_moved = False
        self._pan_from_select = False
        self._pan_moved = False
        self._drag_target = None

    def _moved(self, _node_id: str) -> None:
        """A point moved: the picture has to be redrawn. That is all."""
        self.update()

    def contextMenuEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        """Right-click on an object: what to do with it.

        GeoGebra's object menu, with the three things a teacher needs
        for a competition figure: delete it, hide it, or draw it dashed
        because it is only there to support the figure.
        """
        position = event.pos()
        node_id = self._hit_object(position.x(), position.y(), SELECTABLE_KINDS)
        if node_id is None:
            return
        menu = self._object_menu(node_id)
        # The menu's own actions do the work; a dismissed menu does
        # nothing at all.
        menu.exec(event.globalPos())

    def _object_menu(self, node_id: str) -> QMenu:
        """The menu for one object.

        It is built here, apart from the part that shows it, so that it
        can be looked at without a modal menu in the way.
        """
        node = self.controller.figure().nodes.get(node_id)
        menu = QMenu(self)
        if node is None:
            return menu
        hidden = not node.style.visible
        appearance_action = menu.addAction("\u5c5e\u6027\u2026")
        appearance_action.triggered.connect(lambda: self._edit_appearance(node_id))
        menu.addSeparator()
        show_action = menu.addAction("\u663e\u793a" if hidden else "\u9690\u85cf")
        dashed = node.style.line_style == "dashed"
        line_action = menu.addAction("\u5b9e\u7ebf" if dashed else "\u865a\u7ebf")
        label_action = menu.addAction("\u6539\u6807\u7b7e\u2026")
        menu.addSeparator()
        self._appearance_menu(menu, node_id, node)
        menu.addSeparator()
        delete_action = menu.addAction("\u5220\u9664")
        show_action.triggered.connect(
            lambda: self.controller.set_hidden(node_id, hidden)
        )
        line_action.triggered.connect(
            lambda: self.controller.set_auxiliary(node_id, not dashed)
        )
        # The name in the construction and the name on the paper are two
        # things: a midpoint built as M may be D in the problem.
        label_action.triggered.connect(lambda: self._edit_label(node_id))
        delete_action.triggered.connect(lambda: self.deleteRequested.emit(node_id))
        return menu

    def _appearance_menu(self, menu: QMenu, node_id: str, node: Node) -> None:
        """How the object looks: colour, width, and (for a point) size and label.

        These are appearance, not construction: the menu changes what is
        drawn and nothing about what is true.  Every action goes through
        the controller, so it is one undo step like any other edit.
        """
        color_menu = menu.addMenu("\u989c\u8272")
        for name, code in COLOR_CHOICES:
            action = color_menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(node.style.color == code)
            action.triggered.connect(
                lambda _checked=False, code=code: self.controller.set_color(
                    node_id, code
                )
            )
        color_menu.addSeparator()
        default_color = color_menu.addAction("\u9ed8\u8ba4")
        default_color.setCheckable(True)
        default_color.setChecked(node.style.color in ("", "#000000"))
        default_color.triggered.connect(
            lambda: self.controller.set_color(node_id, None)
        )

        width_menu = menu.addMenu("\u7ebf\u5bbd")
        for name, width in LINE_WIDTHS.items():
            action = width_menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(node.style.line_width == width)
            action.triggered.connect(
                lambda _checked=False, width=width: self.controller.set_line_width(
                    node_id, width
                )
            )
        width_menu.addSeparator()
        default_width = width_menu.addAction("\u9ed8\u8ba4")
        default_width.setCheckable(True)
        default_width.setChecked(node.style.line_width is None)
        default_width.triggered.connect(
            lambda: self.controller.set_line_width(node_id, None)
        )

        if node.kind != "point":
            return

        size_menu = menu.addMenu("\u70b9\u5927\u5c0f")
        for name, size in POINT_SIZES.items():
            action = size_menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(node.style.point_size == size)
            action.triggered.connect(
                lambda _checked=False, size=size: self.controller.set_point_size(
                    node_id, size
                )
            )
        size_menu.addSeparator()
        default_size = size_menu.addAction("\u9ed8\u8ba4")
        default_size.setCheckable(True)
        default_size.setChecked(node.style.point_size is None)
        default_size.triggered.connect(
            lambda: self.controller.set_point_size(node_id, None)
        )

        position_menu = menu.addMenu("\u6807\u7b7e\u4f4d\u7f6e")
        auto = position_menu.addAction("\u81ea\u52a8")
        auto.setCheckable(True)
        auto.setChecked(node.style.label_pos is None)
        auto.triggered.connect(lambda: self.controller.set_label_pos(node_id, None))
        for direction in LABEL_DIRECTIONS:
            action = position_menu.addAction(direction)
            action.setCheckable(True)
            action.setChecked(node.style.label_pos == direction)
            action.triggered.connect(
                lambda _checked=False, direction=direction: self.controller.set_label_pos(
                    node_id, direction
                )
            )

    def _edit_appearance(self, node_id: str) -> None:
        """One dialog for colour, width, size, label and label position."""
        node = self.controller.figure().nodes.get(node_id)
        if node is None:
            return
        dialog = AppearanceDialog(self, node)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.controller.set_appearance(node_id, **dialog.values())
        except GeobenchError as exc:
            QMessageBox.warning(self, "改不了", str(exc))

    def _edit_label(self, node_id: str) -> None:
        """Ask for the label this object should show, and set it."""
        node = self.controller.figure().nodes.get(node_id)
        if node is None:
            return
        current = node.style.label or node.label or node_id
        text, accepted = QInputDialog.getText(
            self,
            "\u6539\u6807\u7b7e",
            f"{node_id} \u5728\u56fe\u4e0a\u53eb\u4ec0\u4e48\uff1f\uff08\u7a7a\u7740\u5c31\u7528\u540d\u5b57\uff09",
            text=current,
        )
        if not accepted:
            return
        self.controller.set_label(node_id, text)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """The return key finishes a variable tool; Delete removes what is selected."""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._finish_variable_tool()
            return
        if event.key() == Qt.Key.Key_Delete and self._selected:
            if len(self._selected) == 1:
                self.deleteRequested.emit(self._selected[0])
            else:
                self.deleteManyRequested.emit(list(self._selected))
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
        if tool.op == "select":
            # The pointer picks whatever is under the click, of any kind.
            # Shift adds to the selection: a claim needs several objects.
            node_id = self._hit_object(px, py, SELECTABLE_KINDS)
            additive = bool(
                QApplication.keyboardModifiers()
                & Qt.KeyboardModifier.ShiftModifier
            )
            self.select(node_id, additive=additive)
            return
        if tool.op == "point.free":
            fx, fy = viewport.to_figure(px, py)
            # Where two objects cross, the crossing itself: a point with
            # no freedom of its own, not a free point that happens to
            # be in the same place.  A crossing wins over "on the
            # circle" or "on the line" when the click is at it -- that
            # is what pointing at a crossing means -- but a click along
            # an object, away from the crossing, still attaches to the
            # object.
            tolerance = GRAB_RADIUS_PX / viewport.scale
            crossing = self.controller.crossing_near(fx, fy, tolerance)
            attach = self._nearest_attachable(px, py)
            magnet = CROSSING_MAGNET_PX / viewport.scale
            if crossing is not None and (
                attach is None or crossing.distance <= attach[2] + magnet
            ):
                op, args = crossing.operation()
                self.constructRequested.emit(op, args)
                return
            if attach is not None:
                node_id, kind, _distance = attach
                if kind == "circle":
                    where = self.controller.parameter_on_circle(node_id, fx, fy)
                    self.constructRequested.emit("point.on_circle", [node_id, where])
                else:
                    where = self.controller.parameter_on_line(node_id, fx, fy)
                    self.constructRequested.emit("point.on_line", [node_id, where])
                return
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

    def _nearest_attachable(
        self, px: float, py: float
    ) -> tuple[str, str, float] | None:
        """The nearest line, segment or circle under the click.

        One distance for all three: a click between a circle and a line
        attaches to whichever it is actually nearer, instead of always
        preferring the circle because circles are checked first.
        """
        viewport = self._viewport()
        x, y = viewport.to_figure(px, py)
        tolerance = GRAB_RADIUS_PX / viewport.scale
        figure = self.controller.figure()
        best: tuple[str, str, float] | None = None
        for primitive in self.controller.primitives():
            node = figure.nodes.get(getattr(primitive, "id", ""))
            if node is None or node.kind not in ("line", "segment", "circle"):
                continue
            distance = distance_to(primitive, x, y)
            if distance is None or distance > tolerance:
                continue
            if best is None or distance < best[2]:
                best = (node.id, node.kind, distance)
        return best


#: The kinds the pointer can pick: anything that can be seen.
SELECTABLE_KINDS: tuple[str, ...] = ("point", "line", "segment", "ray", "circle", "polygon")

#: The node kinds that answer to each argument kind. A construction that
#: wants a line is happy with a segment: "the foot on BC" means the same
#: thing whether BC is drawn as a segment or as a line.
_KIND_KINDS: dict[str, tuple[str, ...]] = {
    "point": ("point",),
    "line": ("line", "segment"),
    "segment": ("segment",),
    "circle": ("circle",),
    "polygon": ("polygon",),
}


def _tick_step(scale: float) -> float:
    """A round number of figure units that is at least 64 pixels apart.

    Integers when the figure is fitted (the usual case), halves and
    fifths only when zoomed in far enough that an integer would be a
    long way apart.  A dozen labels across the canvas is a ruler; fifty
    is a grey wash.
    """
    target = 64.0
    if scale <= 0:
        return 1.0
    exponent = math.floor(math.log10(max(1e-12, target / scale)))
    base = 10.0 ** exponent
    for factor in (1.0, 2.0, 5.0, 10.0):
        step = base * factor
        if step * scale >= target:
            return step
    return base * 10.0


def _tick_text(value: float) -> str:
    """A tick number as short as it can be: 2, 0.5, -1.25."""
    if abs(value - round(value)) < 1e-9:
        return str(round(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


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
