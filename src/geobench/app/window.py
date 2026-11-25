"""The studio window: construction steps, canvas, judgements.

Three panes, because a problem is three things:

- **how the figure was built** (the left pane) -- a construction is a
  sequence of steps, and a figure you cannot explain is not a problem you
  can state;
- **the figure** (the middle) -- where you drag things;
- **what is true about it** (the right pane) -- which claims hold for
  every placement, which hold only here, and which are false.

The layout is borrowed from GeoGebra's Construction Protocol, whose
insight is that a dynamic figure is a *list of steps*, not a pile of
objects (decision D19).
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from fractions import Fraction
from itertools import permutations
from pathlib import Path

from PySide6.QtCore import (
    QModelIndex,
    QPersistentModelIndex,
    QPoint,
    QRect,
    QSettings,
    QSize,
    QStandardPaths,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QKeySequence,
    QPainter,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from geobench import __version__
from geobench.ai_settings import resolve_provider
from geobench.app.ai_panel import AIPanel
from geobench.app.canvas import FigureCanvas
from geobench.app.controller import StudioController
from geobench.app.export import copy_image, copy_svg_source, write_png, write_svg
from geobench.app.export_html import write_html
from geobench.app.icons import group_icon, tool_icon
from geobench.app.settings_dialog import SettingsDialog
from geobench.app.theme import (
    PALETTE,
    PARAMETER_LIMIT,
    PARAMETER_MAX,
    PARAMETER_MIN,
    PARAMETER_SLIDER_STEP,
    PARAMETER_SPIN_STEP,
    PARAMETER_ZERO,
    UI_SIZES,
    apply_theme,
    button_words,
    current_ui_size,
    mono_font,
    set_ui_size,
)
from geobench.app.tools import (
    POINT_TOOL,
    SELECT_TOOL,
    ToolGroup,
    ToolSpec,
    build_toolbar,
)
from geobench.commands import COMMANDS, JUDGEMENT, by_id
from geobench.errors import GeobenchError
from geobench.ggb import import_ggb
from geobench.ggb_export import export_ggb
from geobench.judges import IDENTITY, INSTANCE, Verdict
from geobench.model import Figure, Node

#: The figure the "打开一个示例" button opens: a triangle with its
#: midpoint, circumcentre and circumcircle, and two claims that are
#: proved rather than drawn.  It is the product in one screen -- a
#: picture, and the reason to trust it.
_EXAMPLE = """
点 A(0,0) B(6,0) C(2,4)
AB = 线段(A,B)
BC = 线段(B,C)
CA = 线段(C,A)
M = 中点(A,B)
O = 外心(A,B,C)
w = 外接圆(A,B,C)
断言 共线(A,M,B)
断言 相等(A,M,M,B)
"""


@dataclass(frozen=True)
class RelationSpec:
    """A relation the window can check.

    The name and the number of objects come from the command table, so
    the buttons cannot drift away from what the judges actually take.
    """

    kind: str
    label: str
    arg_count: int
    hint: str
    arg_kinds: tuple[str, ...] = ()
    """What each argument must be: point, line, circle, any."""


#: The relations the window offers. The command table knows how many
#: objects each one takes; this list only says which ones to put on the
#: toolbar.
_KIND_CANDIDATES: dict[str, tuple[str, ...]] = {
    "point": ("point",),
    "line": ("line", "segment"),
    "circle": ("circle",),
    "any": ("line", "segment", "ray", "circle"),
}

_KIND_LABELS: dict[str, str] = {
    "point": "\u70b9",
    "line": "\u7ebf",
    "circle": "\u5706",
    "any": "\u5bf9\u8c61",
}

def _short(value: str) -> str:
    """A coordinate as short as it can be and still be exact enough to read.

    The coordinate itself is a rational ("29/20"); a person wants to see
    a decimal ("1.45").
    """
    try:
        number = float(Fraction(value))
    except (TypeError, ValueError, ZeroDivisionError):
        return value
    if number == int(number):
        return str(int(number))
    return f"{number:.4f}".rstrip("0").rstrip(".")


def _relations() -> tuple[RelationSpec, ...]:
    """The relation buttons, built from the command table.

    Every relation the judges know is on the panel. The kernel can
    check seventeen of them; the panel used to offer seven, and the
    ones missing were the ones a competition problem leans on.
    """
    specs: list[RelationSpec] = []
    commands = [
        command
        for command in COMMANDS
        if command.kind == JUDGEMENT and command.implemented
    ]
    # Two relations may share a name: 垂直 is both "these two lines are
    # perpendicular" and "this point is perpendicular to this line".
    # Two buttons with the same word on them are no help, so the ones
    # that would collide say what they take.
    names: dict[str, int] = {}
    for command in commands:
        names[command.name_zh] = names.get(command.name_zh, 0) + 1
    for command in commands:
        kinds = command.arg_kinds or ("point",) * command.arity
        label = command.name_zh
        if names[label] > 1:
            label += "\uff08" + "\u00b7".join(
                _KIND_LABELS.get(kind, kind) for kind in kinds
            ) + "\uff09"
        specs.append(
            RelationSpec(
                kind=command.id,
                label=label,
                arg_count=command.arity,
                hint=(
                    f"\u9009 {command.arity} \u4e2a\u5bf9\u8c61\uff08"
                    + "\u3001".join(_KIND_LABELS.get(kind, kind) for kind in kinds)
                    + f"\uff09\uff0c\u68c0\u67e5{command.summary}"
                ),
                arg_kinds=kinds,
            )
        )
    return tuple(specs)


def _fitting_order(spec: RelationSpec, kinds: list[str]) -> tuple[int, ...] | None:
    """An order of the selected objects that fills this relation's slots.

    ``None`` when no order fits: a relation about two lines is not
    offered for three points.  Trying the orders (there are at most
    four objects) keeps the teacher from having to click them in the
    kernel's order -- the claim is the same either way.
    """
    if len(kinds) != spec.arg_count:
        return None
    if spec.arg_count > 4:
        # Eight points have forty thousand orders; the teacher's click
        # order is the only one worth trying for claims that large.
        orders: list[tuple[int, ...]] = [tuple(range(len(kinds)))]
    else:
        orders = list(permutations(range(len(kinds))))
    for order in orders:
        if all(
            kinds[index] in _KIND_CANDIDATES.get(slot, (slot,))
            for index, slot in zip(order, spec.arg_kinds, strict=True)
        ):
            return order
    return None


#: The two scopes a judgement can have, in the words a classroom uses.
SCOPE_LABELS = {
    IDENTITY: "证明：无论怎么拖动，这句话都成立（对任意图形）",
    INSTANCE: "检验：只看你现在摆的这张图",
}


class ObjectPicker(QDialog):
    """Choose the objects a relation is about, one slot per argument.

    The user picks the objects; the window never guesses. Picking "the
    first three points" would silently check a claim nobody made, which
    is the one thing this product must not do.

    A relation is not a list of objects of one kind: the point-in-one
    relation wants a point and then an object, the tangent relation
    wants a line and then a circle. So every slot says what kind of
    object it wants.
    """

    def __init__(
        self, parent: QWidget, slots: list[tuple[str, list[str]]], title: str
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(280)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.combos: list[QComboBox] = []
        for index, (kind_label, candidates) in enumerate(slots, 1):
            combo = QComboBox()
            combo.addItems(candidates)
            form.addRow(f"{index}. {kind_label}", combo)
            self.combos.append(combo)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_words(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def chosen(self) -> list[str]:
        return [combo.currentText() for combo in self.combos]


class PointEditor(QDialog):
    """Type the exact position of a point.

    Two boxes, and what is typed is taken as the number it is: "1/2"
    is one half, and "0.5" is the same one half.
    """

    def __init__(self, parent: QWidget, node_id: str, x: str, y: str) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"\u70b9 {node_id} \u7684\u4f4d\u7f6e")
        self.setMinimumWidth(260)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.x_edit = QLineEdit(x)
        self.y_edit = QLineEdit(y)
        form.addRow("x", self.x_edit)
        form.addRow("y", self.y_edit)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_words(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def position(self) -> tuple[str, str]:
        return (self.x_edit.text(), self.y_edit.text())


#: The roles the step delegate reads. The item's own text stays plain
#: -- it is what the rest of the program and the tests read -- and the
#: delegate draws the two parts in two tones.
HEAD_ROLE = int(Qt.ItemDataRole.UserRole) + 1
TAIL_ROLE = int(Qt.ItemDataRole.UserRole) + 2
#: The colour of a verdict, as the text of a colour. A QColor comes
#: back from the model as a QVariant, and a QVariant in a delegate is
#: a thing to be unpacked rather than guessed at.
VERDICT_ROLE = int(Qt.ItemDataRole.UserRole) + 3
#: The step's position in the construction: 1, 2, 3...
NUMBER_ROLE = int(Qt.ItemDataRole.UserRole) + 4
#: A colour for a claim in the steps pane, once its verdict is known.
TINT_ROLE = int(Qt.ItemDataRole.UserRole) + 5


class StepDelegate(QStyledItemDelegate):
    """Draws a construction step as a sentence, not as a string.

    The name is the subject and the call is the explanation, so they
    should not look the same size of thing: the name is bold and dark,
    the call is quiet.
    """

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Draw one step."""
        state = option.state
        selected = bool(state & QStyle.StateFlag.State_Selected)
        hovered = bool(state & QStyle.StateFlag.State_MouseOver)
        rect = option.rect
        if selected or hovered:
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(
                QColor(PALETTE.accent_soft if selected else PALETTE.surface_alt)
            )
            painter.drawRoundedRect(rect.adjusted(2, 1, -2, -1), 6, 6)
            painter.restore()

        head = index.data(HEAD_ROLE) or ""
        tail = index.data(TAIL_ROLE) or ""
        number = index.data(NUMBER_ROLE)
        tint = index.data(TINT_ROLE)
        metrics = option.fontMetrics
        painter.save()
        font = option.font
        number_width = 0
        if number is not None:
            number_width = 24
            font.setBold(False)
            painter.setFont(font)
            painter.setPen(QColor(PALETTE.text_muted))
            painter.drawText(
                QRect(
                    rect.left() + 6,
                    rect.top(),
                    number_width,
                    rect.height(),
                ),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                str(number),
            )
        text_rect = rect.adjusted(10 + number_width, 0, -6, 0)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(PALETTE.text))
        painter.drawText(
            text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, head
        )
        if tail:
            head_width = metrics.horizontalAdvance(head)
            font.setBold(False)
            painter.setFont(font)
            painter.setPen(QColor(tint) if tint else QColor(PALETTE.text_muted))
            painter.drawText(
                text_rect.adjusted(head_width, 0, 0, 0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                tail,
            )
        painter.restore()


class VerdictDelegate(QStyledItemDelegate):
    """Draws a judgement row, and keeps the verdict's colour.

    A selected row takes its text colour from the palette, which would
    throw away the one thing the reader wants to see: whether the claim
    is proved or refuted. So the text is drawn here, in the colour the
    row was given.
    """

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Draw one cell."""
        colour = index.data(VERDICT_ROLE)
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        painter.save()
        painter.setPen(QColor(colour) if isinstance(colour, str) else QColor(PALETTE.text))
        painter.drawText(
            option.rect.adjusted(10, 0, -6, 0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            str(text),
        )
        painter.restore()


#: How long after the last change the figure is written to the recovery
#: file.  Long enough not to write on every dragged pixel, short enough
#: that a crash loses at most a few seconds of work.
AUTOSAVE_MS = 4000


def data_dir() -> Path:
    """Where the program keeps its own files (recovery, log)."""
    override = os.environ.get("GEOBENCH_DATA_DIR")
    if override:
        root = Path(override)
    else:
        base = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppDataLocation
        )
        root = Path(base) if base else Path.home() / ".geobench"
    root.mkdir(parents=True, exist_ok=True)
    return root


def recovery_paths() -> tuple[Path, Path]:
    """The autosaved figure and the note saying which file it belongs to."""
    root = data_dir()
    return root / "recovery.geobench", root / "recovery.json"


class StudioWindow(QMainWindow):
    """The main window of the studio."""

    #: The verdicts have arrived. The number tells which request they
    #: answer, so that a slow proof for an old figure can be dropped.
    verdictsReady = Signal(int, list)
    #: The exact evaluation finished: the request, the figure it ran on,
    #: and what it found out about itself.
    exactReady = Signal(int, object, dict, int)

    def __init__(self, controller: StudioController | None = None) -> None:
        super().__init__()
        self.controller = controller or StudioController()
        self.setWindowTitle("geobench — 竞赛几何命题工作台")
        self.resize(1180, 720)
        self._scope = IDENTITY
        self._verdicts: list[Verdict] = []
        #: The objects each verdict is about, aligned with _verdicts.  A
        #: Verdict says what it found, not what it was asked about; the
        #: table needs both to read as a sentence.
        self._verdict_args: list[list[str]] = []
        self._witness: dict[str, object] | None = None
        self._path: Path | None = None
        #: Has the figure changed since it was last opened or saved?
        self._dirty = False
        self._recovery_text, self._recovery_note = recovery_paths()
        self.setAcceptDrops(True)
        self._autosave = QTimer(self)
        self._autosave.setSingleShot(True)
        self._autosave.setInterval(AUTOSAVE_MS)
        self._autosave.timeout.connect(self._write_recovery)

        self.canvas = FigureCanvas(self.controller)
        self.canvas.constructRequested.connect(self._on_construct)
        self.canvas.deleteRequested.connect(self._delete_node)
        self.canvas.deleteManyRequested.connect(self._delete_nodes)
        self.canvas.pointEditRequested.connect(self._edit_point)
        self.canvas.valueRequested.connect(self._on_value_requested)
        self.canvas.selectionChanged.connect(self._on_selection)

        # A blank canvas is a dead end.  The first thing a teacher sees
        # is a way in -- an example, a sentence, or a file -- and it
        # gets out of the way as soon as there is something on the
        # paper.  It is an overlay, not a separate page: clicking the
        # blank part of the canvas still places a point.
        self._empty_state = self._build_empty_state()
        overlay = QVBoxLayout(self.canvas)
        overlay.setContentsMargins(24, 24, 24, 24)
        overlay.addStretch(1)
        overlay.addWidget(
            self._empty_state, 0, Qt.AlignmentFlag.AlignHCenter
        )
        overlay.addStretch(1)

        self._playback_timer = QTimer(self)
        self._playback_timer.setInterval(450)
        self._playback_timer.timeout.connect(self._playback_tick)
        self._playback_limit: int | None = None

        self.steps = QListWidget()
        self.steps.setToolTip("构造步骤：这张图是怎么一步步造出来的（右键删除）")
        self.steps.setItemDelegate(StepDelegate(self.steps))
        # A selection on the canvas can name several objects; the steps
        # pane should show the same selection, not just the last one.
        self.steps.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.steps.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.steps.customContextMenuRequested.connect(self._steps_menu)
        # The delete key works on the selected step, which is what a
        # list of objects invites.
        delete_key = QAction("删除", self)
        delete_key.setShortcut(QKeySequence.StandardKey.Delete)
        delete_key.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        delete_key.triggered.connect(self._delete_selected_step)
        self.steps.addAction(delete_key)

        self.judgements = QTableWidget(0, 3)
        self.judgements.setHorizontalHeaderLabels(["说法", "结论", "为什么"])
        self.judgements.setItemDelegate(VerdictDelegate(self.judgements))
        self.judgements.verticalHeader().setVisible(False)
        self.judgements.setShowGrid(False)
        self.judgements.setAlternatingRowColors(True)
        self.judgements.setWordWrap(False)
        self.judgements.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.judgements.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.judgements.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.judgements.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.judgements.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.judgements.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )

        # The table gives the verdict at a glance; the pane built by
        # _judgement_panel below says why, in a sentence, with the
        # symbolic derivation folded away. A verdict without its
        # evidence is a claim, and this product exists to avoid those.

        self.status = self.statusBar()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        steps_box = QWidget()
        steps_layout = QVBoxLayout(steps_box)
        steps_layout.setContentsMargins(0, 0, 0, 0)
        steps_layout.setSpacing(6)
        # The free numbers are knobs: they belong above the steps, where
        # a hand can reach them while watching the figure.
        self._parameters = QWidget()
        self._parameter_layout = QVBoxLayout(self._parameters)
        self._parameter_layout.setContentsMargins(0, 0, 0, 0)
        self._parameter_layout.setSpacing(4)
        self._parameter_rows: dict[str, tuple[QSlider, QDoubleSpinBox]] = {}
        self._parameter_ids: tuple[str, ...] = ()
        self._parameter_dragging: str | None = None
        self._number_timer = QTimer(self)
        self._number_timer.setSingleShot(True)
        self._number_timer.setInterval(300)
        self._number_timer.timeout.connect(self._settle_number)
        steps_layout.addWidget(self._parameters)
        steps_layout.addWidget(self._playback_buttons())
        self._steps_hint = QLabel("作图的每一步会列在这里")
        self._steps_hint.setObjectName("panelNote")
        self._steps_hint.setContentsMargins(8, 4, 8, 4)
        steps_layout.addWidget(self._steps_hint)
        steps_layout.addWidget(self.steps)
        splitter.addWidget(
            self._panel(
                "\u6784\u9020",
                steps_box,
                "\u8fd9\u5f20\u56fe\u662f\u600e\u4e48\u9020\u51fa\u6765\u7684",
            )
        )
        splitter.addWidget(
            self._panel("画板", self.canvas, "拖动自由点")
        )
        splitter.addWidget(self._panel("判定", self._judgement_panel(), "哪些说法成立"))
        splitter.setSizes([260, 760, 400])
        splitter.setStretchFactor(1, 1)
        # A wide, quiet handle: the panes are separated by a gap, not by
        # a bar that reads as a hole in the window.
        splitter.setHandleWidth(12)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        self.setCentralWidget(central)

        self._build_menu()
        self._build_toolbar()
        self.controller.on_change(self._figure_changed)
        self.controller.on_change(self.refresh)
        self.controller.on_move(self._point_moved)
        self._dragging = False
        self._judge_request = 0
        self._judge_pending = False
        self._exact_request = 0
        self._exact_running = False
        self.verdictsReady.connect(self._on_verdicts)
        self.exactReady.connect(self._on_exact)
        self.refresh()
        # A tool is armed from the start. An empty toolbar and an idle
        # canvas look like a program that is not working: a click with
        # no tool armed does nothing, and nothing says so.
        point_group = next(
            (
                group
                for group in self._groups
                if any(tool.op == "point.free" for tool in group.tools)
            ),
            None,
        )
        self._arm(POINT_TOOL, point_group)

    # -- layout ------------------------------------------------------------

    def _set_judgement_note(self, text: str) -> None:
        """The note in the judgement pane's heading."""
        label = getattr(self, "_judgement_note", None)
        if label is not None:
            label.setText(text)

    def _panel(self, title: str, widget: QWidget, note: str = "") -> QWidget:
        """One pane: a card with a heading that says what it is for."""
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("panelHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 9, 12, 9)
        header_layout.setSpacing(8)

        # A short rule of the accent colour: the one piece of colour in
        # the interface, and it marks where a section begins.
        rule = QFrame()
        rule.setObjectName("accentRule")
        rule.setFixedWidth(3)
        rule.setFixedHeight(14)
        header_layout.addWidget(rule)

        heading = QLabel(title)
        heading.setObjectName("panelTitle")
        # The heading must not stretch: without this the layout gives it
        # half the panel and the canvas is squeezed into the bottom.
        heading.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        header_layout.addWidget(heading)
        header_layout.addStretch(1)
        if note:
            note_label = QLabel(note)
            note_label.setObjectName("panelNote")
            header_layout.addWidget(note_label)
            if title == "判定":
                self._judgement_note = note_label
        layout.addWidget(header)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(8, 8, 8, 8)
        body_layout.addWidget(widget)
        layout.addWidget(body, 1)
        return card

    def _judgement_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        # What a teacher asks is almost never "show me all seventeen
        # relations": it is "these three points -- are they collinear?".
        # The panel follows the selection, and the full list stays one
        # click away for the times when there is no selection yet.
        self._context_hint = QLabel(
            "在图上点选对象（按住 Shift 可多选），这里会出现能问的问题。"
        )
        self._context_hint.setObjectName("panelNote")
        self._context_hint.setWordWrap(True)
        layout.addWidget(self._context_hint)

        self._context_box = QWidget()
        self._context_layout = QGridLayout(self._context_box)
        self._context_layout.setContentsMargins(0, 0, 0, 0)
        self._context_layout.setHorizontalSpacing(6)
        self._context_layout.setVerticalSpacing(6)
        layout.addWidget(self._context_box)

        self._all_toggle = QToolButton()
        self._all_toggle.setText("全部关系")
        self._all_toggle.setCheckable(True)
        self._all_toggle.setChecked(False)
        self._all_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._all_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self._all_toggle.setToolTip("没有选中对象时，也可以直接挑一种关系")
        self._all_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._all_toggle.toggled.connect(self._toggle_all_relations)
        layout.addWidget(self._all_toggle)

        self._all_relations = QWidget()
        chips = QGridLayout(self._all_relations)
        chips.setContentsMargins(0, 0, 0, 0)
        chips.setHorizontalSpacing(6)
        chips.setVerticalSpacing(6)
        for index, spec in enumerate(_relations()):
            button = QPushButton(spec.label)
            button.setToolTip(spec.hint)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, relation=spec: self._add_relation(relation)
            )
            chips.addWidget(button, index // 4, index % 4)
        self._all_relations.setVisible(False)
        layout.addWidget(self._all_relations)

        scope_row = QWidget()
        scope_layout = QHBoxLayout(scope_row)
        scope_layout.setContentsMargins(0, 0, 0, 0)
        scope_layout.setSpacing(6)
        scope_layout.addWidget(QLabel("问法"))
        # Two buttons, one of them down: the scope is a choice between
        # two things, and a button that says "toggle" does not say which
        # one is in force.  The words are the teacher's, not the
        # kernel's: "证明" is what "identity" means in a classroom, and
        # "检验" is what "instance" means.
        self.scope_group = QButtonGroup(self)
        self.scope_group.setExclusive(True)
        self.scope_buttons: dict[str, QPushButton] = {}
        for scope, label in ((IDENTITY, "证明"), (INSTANCE, "检验")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setToolTip(SCOPE_LABELS[scope])
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, chosen=scope: self.set_scope(chosen)
            )
            self.scope_group.addButton(button)
            self.scope_buttons[scope] = button
            scope_layout.addWidget(button)
        self.scope_buttons[IDENTITY].setChecked(True)
        scope_layout.addStretch(1)
        layout.addWidget(scope_row)

        layout.addWidget(self.judgements)

        # The human sentence first: what the claim says and why it is
        # true or false.  The symbolic derivation is there for the
        # teacher who wants it, behind a fold, because the expression is
        # evidence for the kernel and clutter for the classroom.
        self.evidence_summary = QLabel(
            "选中一行，这里用一句话说明它为什么成立（或不成立）。"
        )
        self.evidence_summary.setWordWrap(True)
        self.evidence_summary.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.evidence_summary.setMinimumHeight(64)
        self.evidence_summary.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )

        self.witness_button = QPushButton("在图上看看这个反例")
        self.witness_button.setToolTip(
            "把自由点摆成反例的位置；看一眼再 Ctrl+Z 回来"
        )
        self.witness_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.witness_button.setVisible(False)
        self.witness_button.clicked.connect(self._preview_witness)

        self.derivation_toggle = QToolButton()
        self.derivation_toggle.setText("推导")
        self.derivation_toggle.setCheckable(True)
        self.derivation_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.derivation_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.derivation_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.derivation_toggle.toggled.connect(self._toggle_derivation)

        self.evidence = QPlainTextEdit()
        self.evidence.setReadOnly(True)
        # The evidence is read symbol by symbol; a proportional font
        # makes the minus sign and the hyphen the same width.
        self.evidence.setFont(mono_font())
        self.evidence.setMinimumHeight(90)
        self.evidence.setPlaceholderText("推导会显示在这里")
        self.evidence.setVisible(False)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(6)
        detail_layout.addWidget(self.evidence_summary)
        detail_layout.addWidget(self.witness_button)
        detail_layout.addWidget(self.derivation_toggle)
        detail_layout.addWidget(self.evidence)
        layout.addWidget(detail, 1)
        self.judgements.itemSelectionChanged.connect(self._show_evidence)
        return panel

    def _toggle_all_relations(self, open_: bool) -> None:
        self._all_relations.setVisible(open_)
        self._all_toggle.setArrowType(
            Qt.ArrowType.DownArrow if open_ else Qt.ArrowType.RightArrow
        )

    def _toggle_derivation(self, open_: bool) -> None:
        self.evidence.setVisible(open_)
        self.derivation_toggle.setArrowType(
            Qt.ArrowType.DownArrow if open_ else Qt.ArrowType.RightArrow
        )

    def _refresh_relation_choices(self, node_ids: list[str]) -> None:
        """Offer the relations that fit what is selected, and nothing else.

        The selection is an order: "a point, on this circle" is not the
        same claim as "this circle, on a point".  A relation is offered
        when the selected kinds match its slots in some order, and the
        order that matched is the one the claim is built with.
        """
        while self._context_layout.count():
            item = self._context_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not node_ids:
            self._context_hint.setText(
                "在图上点选对象（按住 Shift 可多选），这里会出现能问的问题。"
            )
            return

        figure = self.controller.figure()
        kinds = [
            figure.nodes[node_id].kind
            for node_id in node_ids
            if node_id in figure.nodes
        ]
        chosen = "、".join(node_ids)
        self._context_hint.setText(f"选中了 {chosen}，可以问：")

        matches: list[tuple[RelationSpec, list[str]]] = []
        for spec in _relations():
            order = _fitting_order(spec, kinds)
            if order is None:
                continue
            matches.append((spec, [node_ids[index] for index in order]))

        if not matches:
            self._context_hint.setText(
                f"选中了 {chosen}：这几个对象之间没有能直接问的问题。"
                "换几个对象，或者展开下面的“全部关系”。"
            )
            return

        for index, (spec, args) in enumerate(matches[:9]):
            button = QPushButton(spec.label)
            button.setToolTip(spec.hint)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, relation=spec, chosen_args=args: (
                    self._ask_about(relation, chosen_args)
                )
            )
            self._context_layout.addWidget(button, index // 3, index % 3)

    def _ask_about(self, spec: RelationSpec, args: list[str]) -> None:
        """Add the claim about the objects the teacher selected."""
        try:
            self.controller.add_relation(spec.kind, args)
        except GeobenchError as exc:
            self.status.showMessage(f"加不了这个关系：{exc}")
            return
        self.status.showMessage(f"要检查：{_claim_text(spec.kind, args)}")

    def _build_menu(self) -> None:
        """The file menu.

        A figure that cannot be saved is a figure that does not exist,
        as far as the teacher is concerned: they close the window and
        the work is gone. The file is the DSL, so the figure is written
        in the same language a person would write it.
        """
        menu = self.menuBar()
        file_menu = menu.addMenu("文件")
        new_action = QAction("新建", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.setToolTip("新建一张空白图（Ctrl+N）")
        new_action.triggered.connect(self._new_file)
        file_menu.addAction(new_action)
        open_action = QAction("打开…", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._open_file)
        file_menu.addAction(open_action)
        example_action = QAction("打开示例", self)
        example_action.triggered.connect(self._open_example)
        file_menu.addAction(example_action)
        self._recent_menu = file_menu.addMenu("最近打开")
        self._fill_recent_menu()
        save_action = QAction("保存", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self._save_file)
        file_menu.addAction(save_action)
        save_as_action = QAction("另存为…", self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(self._save_file_as)
        file_menu.addAction(save_as_action)

        export_menu = file_menu.addMenu("导出")
        export_svg_action = QAction("导出 SVG…", self)
        export_svg_action.triggered.connect(self._export_svg)
        export_menu.addAction(export_svg_action)
        export_png_action = QAction("导出 PNG…", self)
        export_png_action.triggered.connect(self._export_png)
        export_menu.addAction(export_png_action)
        export_html_action = QAction("导出 HTML（可以拖动）…", self)
        export_html_action.triggered.connect(self._export_html)
        export_menu.addAction(export_html_action)
        export_ggb_action = QAction("导出 GeoGebra 文件（.ggb）…", self)
        export_ggb_action.setToolTip("写回 GeoGebra；不能写回的构造会列出来")
        export_ggb_action.triggered.connect(self._export_ggb)
        export_menu.addAction(export_ggb_action)
        export_menu.addSeparator()
        copy_picture_action = QAction("复制图形到剪贴板", self)
        copy_picture_action.triggered.connect(self._copy_picture)
        export_menu.addAction(copy_picture_action)
        copy_svg_action = QAction("复制 SVG 源码", self)
        copy_svg_action.triggered.connect(self._copy_svg)
        export_menu.addAction(copy_svg_action)

        edit_menu = menu.addMenu("编辑")
        self._undo_action = QAction("撤销", self)
        self._undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self._undo_action.setToolTip("撤销一步（Ctrl+Z）")
        self._undo_action.triggered.connect(self._undo)
        edit_menu.addAction(self._undo_action)
        self._redo_action = QAction("重做", self)
        self._redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self._redo_action.setToolTip("重做一步（Ctrl+Y）")
        self._redo_action.triggered.connect(self._redo)
        edit_menu.addAction(self._redo_action)

        view_menu = menu.addMenu("视图")
        self._axes_action = QAction("坐标轴", self)
        self._axes_action.setCheckable(True)
        self._axes_action.setChecked(self.canvas.show_axes)
        self._axes_action.setToolTip("在画布上显示坐标轴与刻度（导出时不画）")
        self._axes_action.toggled.connect(self._set_axes)
        view_menu.addAction(self._axes_action)
        view_menu.addSeparator()
        view_fit = QAction("适应窗口", self)
        view_fit.triggered.connect(self.canvas.fit)
        view_menu.addAction(view_fit)
        view_zoom_in = QAction("放大", self)
        view_zoom_in.triggered.connect(self.canvas.zoom_in)
        view_menu.addAction(view_zoom_in)
        view_zoom_out = QAction("缩小", self)
        view_zoom_out.triggered.connect(self.canvas.zoom_out)
        view_menu.addAction(view_zoom_out)

        settings_menu = menu.addMenu("设置")
        service_action = QAction("模型服务…", self)
        service_action.setToolTip("选择模型服务，并告诉它钥匙在哪")
        service_action.triggered.connect(self._open_settings)
        settings_menu.addAction(service_action)

        size_menu = settings_menu.addMenu("界面字号")
        self._size_actions: dict[str, QAction] = {}
        for name in UI_SIZES:
            action = QAction(name, self)
            action.setCheckable(True)
            action.setChecked(name == current_ui_size())
            action.triggered.connect(
                lambda _checked=False, chosen=name: self._set_ui_size(chosen)
            )
            size_menu.addAction(action)
            self._size_actions[name] = action

        help_menu = menu.addMenu("帮助")
        shortcuts_action = QAction("快捷键…", self)
        shortcuts_action.triggered.connect(self._show_shortcuts)
        help_menu.addAction(shortcuts_action)
        guide_action = QAction("30 秒上手", self)
        guide_action.setToolTip("打开一个示例，看一次“选中对象 → 提问 → 反例”")
        guide_action.triggered.connect(self._quick_start)
        help_menu.addAction(guide_action)
        help_menu.addSeparator()
        about_action = QAction("关于 geobench", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _export_svg(self) -> None:
        """Write the figure to a file, as a vector picture.

        A vector file is what a document wants: it stays sharp at any
        size, and it can be opened and edited again.
        """
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 SVG", "图形.svg", "SVG 图片 (*.svg)"
        )
        if not path:
            return
        try:
            write_svg(self.controller.figure(), self.controller.style, Path(path))
        except OSError as exc:
            self.status.showMessage(f"导出失败：{exc}")
            return
        self.status.showMessage("已导出 SVG")

    def _export_html(self) -> None:
        """Write the figure as a page a student can drag.

        A picture in a document is a claim that something is true; a
        picture a student can move is the argument for it.
        """
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 HTML", "图形.html", "网页 (*.html)"
        )
        if not path:
            return
        try:
            write_html(
                self.controller.figure(),
                self.controller.style,
                Path(path),
                title=Path(path).stem,
            )
        except GeobenchError as exc:
            self.status.showMessage(f"导出失败：{exc}")
            return
        except OSError as exc:
            self.status.showMessage(f"导出失败：{exc}")
            return
        self.status.showMessage("已导出 HTML（在学生那边可以直接拖动）")

    def _export_ggb(self) -> None:
        """Write the figure back out as a GeoGebra file."""
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 GeoGebra 文件", "图形.ggb", "GeoGebra 文件 (*.ggb)"
        )
        if not path:
            return
        target = Path(path)
        if target.suffix.lower() != ".ggb":
            target = target.with_suffix(".ggb")
        try:
            skipped = export_ggb(self.controller.figure(), target)
        except GeobenchError as exc:
            self.status.showMessage(f"导出失败：{exc}")
            return
        if skipped:
            QMessageBox.information(
                self,
                "导出 GeoGebra 文件",
                f"已导出 {target.name}，但有 {len(skipped)} 个对象写不回去：\n\n"
                + "\n".join(f"· {item}" for item in skipped[:12])
                + ("\n…" if len(skipped) > 12 else ""),
            )
        self.status.showMessage(
            f"已导出 {target.name}"
            + (f"（{len(skipped)} 处没有写回）" if skipped else "")
        )

    def _export_png(self) -> None:
        """Write the figure to a file, as a picture."""
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 PNG", "图形.png", "PNG 图片 (*.png)"
        )
        if not path:
            return
        try:
            write_png(self.controller.figure(), self.controller.style, Path(path))
        except OSError as exc:
            self.status.showMessage(f"导出失败：{exc}")
            return
        self.status.showMessage("已导出 PNG")

    def _copy_picture(self) -> None:
        """Put the figure on the clipboard, as a picture.

        This is the ordinary way a figure reaches a Word document: paste.
        """
        try:
            copy_image(self.controller.figure(), self.controller.style)
        except OSError as exc:
            self.status.showMessage(f"复制失败：{exc}")
            return
        self.status.showMessage("图形已复制到剪贴板，可以直接粘贴到 Word 里")

    def _copy_svg(self) -> None:
        """Put the SVG source on the clipboard, for a document that wants it."""
        try:
            copy_svg_source(self.controller.figure(), self.controller.style)
        except OSError as exc:
            self.status.showMessage(f"复制失败：{exc}")
            return
        self.status.showMessage("SVG 源码已复制到剪贴板")

    # -- the construction protocol, played ---------------------------------

    def _playback_buttons(self) -> QWidget:
        """The buttons that play the construction.

        The construction protocol is the list of steps a teacher
        already has on the left. These buttons play it back, so a
        student can watch a figure being built.
        """
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        play = QPushButton("\u64ad\u653e")
        play.setToolTip("\u4e00\u6b65\u4e00\u6b65\u770b\u8fd9\u5f20\u56fe\u662f\u600e\u4e48\u9020\u51fa\u6765\u7684")
        play.clicked.connect(self._play_construction)
        step = QPushButton("\u5355\u6b65")
        step.setToolTip("\u5f80\u4e0b\u8d70\u4e00\u6b65")
        step.clicked.connect(self._step_forward)
        stop = QPushButton("\u505c\u6b62")
        stop.setToolTip("\u56de\u5230\u5b8c\u6574\u7684\u56fe")
        stop.clicked.connect(self._stop_playback)
        for button in (play, step, stop):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            layout.addWidget(button)
        layout.addStretch(1)
        return row

    def _construction_steps(self) -> list[str]:
        """The construction steps, in the order they were made."""
        return list(self.controller.figure().nodes)

    def _play_construction(self) -> None:
        """Watch the figure being built, one step at a time.

        The steps are the ones already listed on the left; the picture
        grows as they are reached. Nothing is rebuilt and nothing is
        lost -- when the playback ends, the whole figure is there
        again.
        """
        self._playback_limit = 0
        self.canvas.set_playback_limit(0)
        self._playback_timer.start()
        self.status.showMessage("\u4e00\u6b65\u4e00\u6b65\u770b\u8fd9\u5f20\u56fe\u662f\u600e\u4e48\u9020\u51fa\u6765\u7684")

    def _step_forward(self) -> None:
        """One more step, on its own."""
        self._playback_timer.stop()
        steps = self._construction_steps()
        limit = 0 if self._playback_limit is None else self._playback_limit
        limit = min(limit + 1, len(steps))
        self._playback_limit = limit
        self.canvas.set_playback_limit(limit)
        self._highlight_step(limit - 1)

    def _stop_playback(self) -> None:
        """The whole figure, again."""
        self._playback_timer.stop()
        self._playback_limit = None
        self.canvas.set_playback_limit(None)
        self.steps.clearSelection()

    def _playback_tick(self) -> None:
        """One more step of the construction."""
        steps = self._construction_steps()
        limit = 0 if self._playback_limit is None else self._playback_limit
        if limit >= len(steps):
            self._stop_playback()
            self.status.showMessage("\u9020\u5b8c\u4e86")
            return
        limit += 1
        self._playback_limit = limit
        self.canvas.set_playback_limit(limit)
        self._highlight_step(limit - 1)

    def _highlight_step(self, index: int) -> None:
        """Show which step the construction is at."""
        steps = self._construction_steps()
        if index < 0 or index >= len(steps):
            return
        row = self._step_rows.get(steps[index])
        if row is not None:
            self.steps.setCurrentRow(row)

    def _undo(self) -> None:
        if self.controller.undo():
            self.canvas.reset_pending()
            self.status.showMessage("撤销了一步")
        else:
            self.status.showMessage("没有可撤销的了")

    def _redo(self) -> None:
        if self.controller.redo():
            self.canvas.reset_pending()
            self.status.showMessage("重做了一步")
        else:
            self.status.showMessage("没有可重做的了")

    def _set_axes(self, shown: bool) -> None:
        """Show or hide the axes; the export never draws them."""
        self.canvas.set_show_axes(shown)
        self.status.showMessage("坐标轴：" + ("显示" if shown else "隐藏"))

    def _set_ui_size(self, name: str) -> None:
        """Change the interface size, now and next time."""
        set_ui_size(name)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app)
        # The evidence pane has its own font, chosen when it was built.
        self.evidence.setFont(mono_font())
        QSettings("geobench", "studio").setValue("ui/size", name)
        for key, action in self._size_actions.items():
            action.setChecked(key == name)
        self.status.showMessage(f"界面字号：{name}（已记住）")

    def _show_shortcuts(self) -> None:
        QMessageBox.information(self, "快捷键", _shortcuts_text())

    def _quick_start(self) -> None:
        self._open_example()
        self.status.showMessage(
            "示例已打开：拖动 A 试试；右侧两条断言会说为什么成立"
        )

    def _show_about(self) -> None:
        QMessageBox.about(self, "关于 geobench", _about_text())

    # -- recent files and drops ---------------------------------------------

    def _recent_paths(self) -> list[Path]:
        stored = QSettings("geobench", "studio").value("file/recent", [])
        if isinstance(stored, str):
            stored = [stored]
        if not isinstance(stored, (list, tuple)):
            stored = []
        paths = [Path(item) for item in stored if isinstance(item, str)]
        return [path for path in paths if path.exists()][:8]

    def _remember_recent(self, path: Path) -> None:
        paths = [path, *(item for item in self._recent_paths() if item != path)]
        QSettings("geobench", "studio").setValue(
            "file/recent", [str(item) for item in paths[:8]]
        )
        self._fill_recent_menu()

    def _fill_recent_menu(self) -> None:
        menu = getattr(self, "_recent_menu", None)
        if menu is None:
            return
        menu.clear()
        paths = self._recent_paths()
        if not paths:
            empty = menu.addAction("（还没有打开过文件）")
            empty.setEnabled(False)
            return
        for path in paths:
            action = menu.addAction(path.name)
            action.setToolTip(str(path))
            action.triggered.connect(
                lambda _checked=False, target=path: self._load_path(target)
            )

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        if any(
            url.isLocalFile()
            and Path(url.toLocalFile()).suffix.lower() in {".geobench", ".ggb"}
            for url in urls
        ):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.suffix.lower() in {".geobench", ".ggb"}:
                event.acceptProposedAction()
                self._load_path(path)
                return

    def _open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "打开图形",
            "",
            "Geobench 图形 (*.geobench);;GeoGebra 文件 (*.ggb);;所有文件 (*)",
        )
        if not path:
            return
        self._load_path(Path(path))

    def _load_path(self, path: Path) -> None:
        if not self._confirm_discard():
            return
        if path.suffix.lower() == ".ggb":
            self._load_ggb(path)
            return
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            self.status.showMessage(f"打不开这个文件：{exc}")
            return
        try:
            self.controller.load_text(source)
        except GeobenchError as exc:
            self.status.showMessage(f"这个文件读不了：{exc}")
            return
        self._path = path
        self._dirty = False
        self._clear_recovery()
        self._remember_recent(path)
        self._update_title()
        # A file opens fitted: the teacher wants to see the figure, not
        # a corner of it at the default zoom.
        self.canvas.fit()
        self.refresh()
        self.status.showMessage(f"打开了 {path.name}")

    def _load_ggb(self, path: Path) -> None:
        """Open a GeoGebra file: translated to the DSL, then opened.

        The translation reports what it could not carry (a tangent that
        became one line, a subscript that had to be renamed).  Saying so
        is the difference between an import and a guess.
        """
        try:
            result = import_ggb(path)
        except GeobenchError as exc:
            self.status.showMessage(f"读不了这个 .ggb：{exc}")
            return
        if not result.ok:
            self.status.showMessage("这个 .ggb 里没有能搬过来的构造")
            return
        try:
            self.controller.load_text(result.dsl)
        except GeobenchError as exc:
            self.status.showMessage(f"搬过来以后读不了：{exc}")
            return
        # A .ggb stays a GeoGebra file: saving writes our own format,
        # and the teacher keeps the original untouched.
        self._path = None
        self._dirty = False
        self._clear_recovery()
        self._update_title()
        self.canvas.fit()
        self.refresh()
        notes = [*result.warnings, *result.skipped]
        if notes:
            QMessageBox.information(
                self,
                "从 GeoGebra 读入",
                f"读入了 {path.name}。\n\n有 {len(notes)} 处需要你看一眼：\n\n"
                + "\n".join(f"· {note}" for note in notes[:12]),
            )
        self.status.showMessage(
            f"读入了 {path.name}" + (f"（{len(notes)} 处调整）" if notes else "")
        )

    def _build_empty_state(self) -> QWidget:
        """The first screen: three ways into a figure, and a quiet hint.

        A teacher opening the program has a problem in mind, not a
        command name.  So the blank page offers the three things that
        actually start a lesson: an example that works, a sentence, and
        a file from GeoGebra.
        """
        card = QFrame()
        card.setObjectName("card")
        card.setFixedWidth(420)
        # A click on the card is a click on the card, not a point behind it.
        card.setAttribute(Qt.WidgetAttribute.WA_NoMousePropagation, True)
        inner = QVBoxLayout(card)
        inner.setContentsMargins(28, 26, 28, 26)
        inner.setSpacing(10)
        inner.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize)

        title = QLabel("从哪儿开始？")
        title.setObjectName("emptyTitle")
        inner.addWidget(title)

        note = QLabel(
            "打开一个做好的例子，用一句话描述图形，"
            "或者打开 GeoGebra 文件。也可以直接点一下画布，放一个点。"
        )
        note.setObjectName("panelNote")
        note.setWordWrap(True)
        note.setMinimumHeight(72)
        inner.addWidget(note)

        starters = (
            ("打开一个示例", self._open_example),
            ("用一句话作图", self._open_ai_panel),
            ("打开文件…", self._open_file),
        )
        for text, slot in starters:
            button = QPushButton(text)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(slot)
            inner.addWidget(button)
        return card

    def _open_example(self) -> None:
        """A figure that shows the product: a proof, not a drawing."""
        if not self._confirm_discard():
            return
        try:
            self.controller.load_text(_EXAMPLE)
        except GeobenchError as exc:
            self.status.showMessage(f"示例打不开：{exc}")
            return
        self._path = None
        self._dirty = False
        self._clear_recovery()
        self._update_title()
        self.canvas.fit()
        self.refresh()
        self.status.showMessage(
            "示例：三角形、中点、外心、外接圆；右侧两条断言会说为什么成立"
        )

    def _save_file(self) -> None:
        if self._path is None:
            self._save_file_as()
            return
        self._write_path(self._path)

    def _save_file_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "另存为", "", "Geobench 图形 (*.geobench);;所有文件 (*)"
        )
        if not path:
            return
        target = Path(path)
        if target.suffix == "":
            target = target.with_suffix(".geobench")
        self._write_path(target)

    def _write_path(self, path: Path) -> None:
        try:
            path.write_text(self.controller.to_text(), encoding="utf-8")
        except OSError as exc:
            self.status.showMessage(f"存不进去：{exc}")
            return
        self._path = path
        self._dirty = False
        self._clear_recovery()
        self._remember_recent(path)
        self._update_title()
        self.status.showMessage(f"存好了 {path.name}")

    def _update_title(self) -> None:
        name = self._path.name if self._path is not None else "未命名"
        mark = "*" if self._dirty else ""
        self.setWindowTitle(f"geobench — 竞赛几何命题工作台（{name}{mark}）")

    # -- data safety --------------------------------------------------------

    def _figure_changed(self) -> None:
        """A change means the figure is no longer what the file holds."""
        self._dirty = True
        self._update_title()
        self._autosave.start()

    def _write_recovery(self) -> None:
        """Write the figure where a crash cannot take it away."""
        if not self._dirty:
            return
        text = self.controller.to_text()
        if not text.strip():
            return
        note = {
            "path": str(self._path) if self._path is not None else None,
            "saved_at": time.time(),
        }
        try:
            temporary = self._recovery_text.with_suffix(".tmp")
            temporary.write_text(text, encoding="utf-8")
            temporary.replace(self._recovery_text)
            self._recovery_note.write_text(
                json.dumps(note, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            # Autosave is a safety net, not a feature; a full disk should
            # not interrupt the lesson.
            pass

    def has_recovery(self) -> bool:
        try:
            return bool(self._recovery_text.read_text(encoding="utf-8").strip())
        except OSError:
            return False

    def restore_recovery(self) -> None:
        """Open the autosaved figure after an unclean exit."""
        try:
            source = self._recovery_text.read_text(encoding="utf-8")
        except OSError as exc:
            self.status.showMessage(f"恢复文件读不了：{exc}")
            return
        try:
            self.controller.load_text(source)
        except GeobenchError as exc:
            self.status.showMessage(f"自动保存的图损坏了：{exc}")
            self.discard_recovery()
            return
        try:
            note = json.loads(self._recovery_note.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            note = {}
        original = note.get("path")
        if isinstance(original, str) and original.endswith(".geobench"):
            self._path = Path(original)
        self._dirty = True
        self._update_title()
        self.canvas.fit()
        self.refresh()
        self.status.showMessage("已恢复上次自动保存的图形")

    def discard_recovery(self) -> None:
        self._clear_recovery()

    def _clear_recovery(self) -> None:
        self._autosave.stop()
        for path in (self._recovery_text, self._recovery_note):
            with contextlib.suppress(OSError):
                path.unlink()

    def _confirm_discard(self) -> bool:
        """Ask before work is replaced.  True means it is safe to go on."""
        if not self._dirty:
            return True
        name = self._path.name if self._path is not None else "未命名"
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("还有没保存的改动")
        box.setText(f"「{name}」还没有保存。")
        box.setInformativeText("要先保存吗？")
        box.setStandardButtons(
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel
        )
        box.setDefaultButton(QMessageBox.StandardButton.Save)
        choice = box.exec()
        if choice == QMessageBox.StandardButton.Save:
            self._save_file()
            return not self._dirty
        return choice == QMessageBox.StandardButton.Discard

    def _new_file(self) -> None:
        if not self._confirm_discard():
            return
        self.controller.clear()
        self._path = None
        self._dirty = False
        self._clear_recovery()
        self._update_title()
        self.canvas.fit()
        self.refresh()
        self.status.showMessage("新建了一张空白图")

    def closeEvent(self, event: QCloseEvent) -> None:
        # There is nobody to ask in a headless test run; a close there is
        # a discard by definition.
        if (
            self._dirty
            and QApplication.platformName() != "offscreen"
            and not self._confirm_discard()
        ):
            event.ignore()
            return
        self._clear_recovery()
        event.accept()

    def _build_toolbar(self) -> None:
        """One button per group, one menu under it -- the way GeoGebra
        does it.

        The groups are generated from the command table, so a command
        that is implemented is a tool: nothing can be finished and then
        left with no way to reach it.
        """
        toolbar = QToolBar("构造")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(22, 22))
        self.addToolBar(toolbar)

        # The pointer comes first, the way it does in every drawing
        # program: picking an object is the first thing a person does.
        pointer = QToolButton()
        pointer.setText(SELECT_TOOL.label)
        pointer.setIcon(tool_icon("__select__"))
        pointer.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        pointer.setToolTip("选择：点一下选中某个对象（Delete 键删掉它）")
        pointer.setCheckable(True)
        pointer.setCursor(Qt.CursorShape.PointingHandCursor)
        pointer.clicked.connect(lambda _checked=False: self._arm(SELECT_TOOL))
        toolbar.addWidget(pointer)
        self._pointer_button = pointer
        toolbar.addSeparator()

        # Undo and redo are the two buttons a drawing program is judged
        # by when something goes wrong, so they are on the toolbar, not
        # only behind Ctrl+Z.
        toolbar.addAction(self._undo_action)
        toolbar.addAction(self._redo_action)
        toolbar.addSeparator()

        self._tool_buttons = {}
        self._group_labels: dict[str, str] = {}
        self._group_first: dict[str, str] = {}
        self._groups = build_toolbar(self.controller.registry)
        for group in self._groups:
            button = QToolButton()
            # The button shows the *group*: the icon says what kind of
            # thing it makes, the word says which family it belongs to.
            button.setText(group.label)
            button.setIcon(group_icon(group.label))
            button.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            )
            button.setToolTip(f"{group.label}：{group.tools[0].label}")
            button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            menu = QMenu(button)
            button.setMenu(menu)
            for tool in group.tools:
                action = menu.addAction(tool_icon(tool.op), tool.label)
                action.setToolTip(tool.hint)
                action.triggered.connect(
                    lambda _checked=False, spec=tool, grp=group: self._arm(spec, grp)
                )
            button.clicked.connect(
                lambda _checked=False, grp=group: self._arm(grp.tools[0], grp)
            )
            toolbar.addWidget(button)
            self._tool_buttons[group.key] = button
            self._group_labels[group.key] = group.label
            self._group_first[group.key] = group.tools[0].label
        toolbar.addSeparator()
        fit_action = QAction(tool_icon("__fit__"), "适应窗口", self)
        fit_action.setShortcut(QKeySequence.StandardKey.ZoomIn)
        fit_action.triggered.connect(self.canvas.fit)
        toolbar.addAction(fit_action)

        for text, slot, hint in (
            ("\u2212", self.canvas.zoom_out, "缩小"),
            ("+", self.canvas.zoom_in, "放大"),
        ):
            zoom_button = QToolButton()
            zoom_button.setText(text)
            zoom_button.setToolTip(hint)
            zoom_button.setCursor(Qt.CursorShape.PointingHandCursor)
            zoom_button.setFixedWidth(30)
            zoom_button.clicked.connect(
                lambda _checked=False, step=slot: step()
            )
            toolbar.addWidget(zoom_button)

        ai_action = QAction("AI 作图", self)
        ai_action.setToolTip("用一句话说你要什么图")
        ai_action.triggered.connect(self._open_ai_panel)
        toolbar.addAction(ai_action)

    # -- interaction -------------------------------------------------------

    def _arm(self, tool: ToolSpec, group: ToolGroup | None = None) -> None:
        """Arm a tool, and make the group's button show it."""
        self.canvas.set_tool(tool)
        self._pointer_button.setChecked(tool.op == "select")
        for key, button in self._tool_buttons.items():
            label = self._group_labels.get(key, key)
            armed = group is not None and key == group.key
            button.setChecked(armed)
            if armed:
                # The armed group shows the icon of the armed tool, in
                # the accent colour: what is in force is visible.
                button.setIcon(tool_icon(tool.op, "active"))
                button.setToolTip(f"{label}：{tool.label}（已选中）")
            else:
                button.setIcon(group_icon(label))
                button.setToolTip(f"{label}：{self._group_first.get(key, '')}")
        self.status.showMessage(f"{tool.label}：{tool.hint}")

    def _on_selection(self, node_ids: list[str]) -> None:
        """An object was picked: say which, and offer what can be asked.

        Selection is the teacher's way of pointing at a claim.  The
        panel follows it, so the next click is on the claim itself, not
        on a relation button followed by a dialog.
        """
        if not node_ids:
            self.status.showMessage("没有选中任何对象")
            self._refresh_relation_choices([])
            return
        names = "、".join(node_ids)
        if len(node_ids) == 1:
            self.status.showMessage(
                f"选中了 {names}；按住 Shift 再点可以多选，右侧会出现能问的问题"
            )
        else:
            self.status.showMessage(f"选中了 {names}；右侧是能问的问题")
        row = self._step_rows.get(node_ids[-1])
        if row is not None:
            self.steps.setCurrentRow(row)
        # setCurrentRow clears the others; add them back, so the steps
        # pane shows the same three objects the canvas does.
        for node_id in node_ids[:-1]:
            other = self._step_rows.get(node_id)
            if other is not None:
                item = self.steps.item(other)
                if item is not None:
                    item.setSelected(True)
        self._refresh_relation_choices(node_ids)

    def _on_value_requested(self, kind: str) -> None:
        """The tool needs a number, or a choice of intersection."""
        value = self._value_for(kind)
        if value is None:
            self.canvas.reset_pending()
            return
        self.canvas.supply_value(value)

    def _value_for(self, kind: str) -> str | None:
        """Ask the user for a value. Returns None if they changed their mind.

        A method of its own so that a test can answer without a dialog:
        everything else about the tool flow is exercised the way the
        user drives it.
        """
        if kind == "selector":
            labels = ["第一个交点", "第二个交点"]
            values = ["0", "1"]
            choice, accepted = QInputDialog.getItem(
                self, "交点选择", "要哪一个交点：", labels, 0, False
            )
            if not accepted:
                return None
            return values[labels.index(choice)]
        text, accepted = QInputDialog.getText(self, "输入", "请输入数字：")
        if not accepted or not text.strip():
            return None
        return text.strip()

    def _on_construct(self, op: str, args: list[str]) -> None:
        try:
            node_id = self.controller.construct(op, args)
        except GeobenchError as exc:
            self.status.showMessage(f"构造失败：{exc}")
            return
        missing = self._missing_reason(node_id)
        if missing is not None:
            # The construction went through, but what it built has no
            # value: the two lines are parallel, the circle has no
            # radius, the point is not on the circle.  The teacher needs
            # to hear that now, not discover an empty corner of the
            # drawing later.
            self.status.showMessage(
                _NO_VALUE_ZH.format(name=node_id, reason=_undefined_text(missing))
            )
            return
        self.status.showMessage(f"{op}({', '.join(args)})")

    def _missing_reason(self, node_id: str) -> str | None:
        """Why this object has no value, if it has none."""
        for name, reason in self.controller.undefined():
            if name == node_id:
                return reason
        return None

    def _open_ai_panel(self) -> None:
        """Ask the model for a figure.

        The model writes the DSL; the parser decides whether it is a
        figure. Nothing the model says can put wrong geometry on the
        canvas: either the parser accepts the text, or the panel shows
        why it refused.
        """
        resolution = resolve_provider()
        panel = AIPanel(
            self,
            resolution.provider,
            self.controller.registry,
            self.controller.to_text(),
            resolution,
        )
        panel.configure_requested.connect(lambda: self._configure_service(panel))
        if panel.exec() != QDialog.DialogCode.Accepted:
            return
        text = panel.accepted_figure()
        if not text.strip():
            return
        try:
            self.controller.load_text(text)
        except Exception as exc:
            self.status.showMessage(f"这张图画不出来：{exc}")
            return
        missing = [
            f"{name}（{_undefined_text(reason)}）"
            for name, reason in self.controller.undefined()
        ]
        if missing:
            # The figure is on the screen, but part of it could not be
            # built.  Saying so is the difference between a figure the
            # teacher can trust and one they have to check themselves.
            self.status.showMessage(
                "图已经放到画板上了，但有对象没有值：" + "；".join(missing)
            )
            return
        self.status.showMessage("AI 画的图已经放到画板上了")

    def _open_settings(self) -> None:
        """Say which model service to talk to, and where the key is."""
        dialog = SettingsDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.status.showMessage("模型服务设置已保存")

    def _configure_service(self, panel: AIPanel) -> None:
        """Set the model service up, from inside the AI panel.

        The panel asks for it because that is where the user finds out
        that there is no service to talk to -- so the way out of that
        has to be right there.
        """
        dialog = SettingsDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        resolution = resolve_provider()
        panel.set_provider(resolution.provider, resolution)

    def _edit_point(self, node_id: str) -> None:
        """Let the user type the exact position of a point."""
        node = self.controller.figure().nodes.get(node_id)
        if node is None:
            return
        placement = node.placement or ("0", "0")
        dialog = PointEditor(self, node_id, placement[0], placement[1])
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        text_x, text_y = dialog.position()
        try:
            self.controller.set_point_position(node_id, text_x, text_y)
        except GeobenchError as exc:
            self.status.showMessage(f"\u8fd9\u4e2a\u4f4d\u7f6e\u4e0d\u884c\uff1a{exc}")
            return
        self.status.showMessage(f"{node_id} \u632a\u5230\u4e86 ({text_x}, {text_y})")

    def _add_relation(self, spec: RelationSpec) -> None:
        """Let the user choose the objects the relation is about."""
        figure = self.controller.figure()
        slots: list[tuple[str, list[str]]] = []
        for kind in spec.arg_kinds:
            accepted = _KIND_CANDIDATES.get(kind, (kind,))
            candidates = [
                node.id for node in figure.nodes.values() if node.kind in accepted
            ]
            slots.append((_KIND_LABELS.get(kind, kind), candidates))
        if any(not candidates for _label, candidates in slots):
            self.status.showMessage(
                f"图里还没有足够的对象来检查这个关系（需要 {spec.arg_count} 个）"
            )
            return
        picker = ObjectPicker(self, slots, f"\u68c0\u67e5{spec.label}")
        if picker.exec() != QDialog.DialogCode.Accepted:
            self.status.showMessage("没选对象，关系没加上")
            return
        args = picker.chosen()
        if len(args) != spec.arg_count:
            self.status.showMessage(
                f"要选 {spec.arg_count} 个对象，关系没加上"
            )
            return
        try:
            self.controller.add_relation(spec.kind, args)
        except GeobenchError as exc:
            self.status.showMessage(f"加不了这个关系：{exc}")
            return
        self.status.showMessage(f"关系 {spec.kind}({', '.join(args)})")

    # -- refreshing --------------------------------------------------------

    def refresh(self) -> None:
        """Redraw the steps, and send the exact evaluation to a worker.

        The picture is already on the screen (the controller draws it
        numerically); what is missing is the ability to *judge* it, and
        that is the slow part.  So it runs the way a proof runs: on a
        copy, in another thread, and the table is filled when it
        arrives.
        """
        self._refresh_steps()
        self._refresh_parameters()
        self.canvas.prune_selection()
        self._refresh_relation_choices(self.canvas.selected())
        empty = not self.controller.figure().nodes
        self._empty_state.setVisible(empty)
        self._refresh_exact()
        if self._dragging:
            # The drag is over; the verdicts have been settled.
            self._dragging = False
            self.status.showMessage("松手了：判定已按新的位置算过")

    def _refresh_exact(self) -> None:
        """Evaluate exactly, behind the picture.

        At most one worker runs at a time.  A figure is built one
        construction at a time, and starting a whole exact evaluation per
        keystroke would put a dozen of them on the CPU at once, all but
        one of them already out of date.  Instead the request is bumped,
        and when the running worker finishes it notices that its answer
        is stale and starts again on the figure as it is now.
        """
        self._exact_request += 1
        request = self._exact_request
        if self._exact_running:
            return
        self._exact_running = True
        version = self.controller.exact_version()
        figure = self.controller.snapshot_figure()

        def work() -> None:
            state: dict[str, str]
            try:
                state = self.controller.evaluate_exact_figure(figure)
            except GeobenchError as exc:  # pragma: no cover - worker safety
                state = {"status": "failed", "reason": str(exc)}
            self.exactReady.emit(request, figure, state, version)

        threading.Thread(target=work, daemon=True).start()

    def _on_exact(
        self, request: int, figure: object, state: dict[str, str], version: int
    ) -> None:
        """The exact evaluation arrived: absorb it and judge if we can."""
        self._exact_running = False
        if request != self._exact_request:
            # The figure changed while this was being evaluated: the
            # answer is about a figure that no longer exists.  Ask again,
            # about the one that does.
            self._refresh_exact()
            return
        if version != self.controller.exact_version():
            # The construction changed while the worker was thinking --
            # a slider moved.  Its answer is about a different figure.
            return
        if not isinstance(figure, Figure):  # pragma: no cover - defensive
            return
        if not self.controller.absorb_exact(figure, dict(state)):
            return
        self._refresh_steps()
        inexact = self.controller.inexact()
        if inexact:
            self._verdicts = []
            self.judgements.setRowCount(0)
            self._set_judgement_note("这张图太大，判定不回答")
            self.status.showMessage(
                f"这张图画得出来，也可以拖；但它太大，精确求值超出预算，判定不回答（{inexact}）"
            )
            return
        self._refresh_judgements()

    def _point_moved(self, node_id: str) -> None:
        """A point moved: one row of the steps pane changed, and that is all.

        The verdicts are not recomputed while the mouse is moving: a
        verdict is about a claim, and a claim is not made at a particular
        pixel. The status bar says so, so the reader knows why the table
        has not changed yet.
        """
        self._dragging = True
        row = self._step_rows.get(node_id)
        if row is not None:
            item = self.steps.item(row)
            node = self.controller.figure().nodes.get(node_id)
            if item is not None and node is not None:
                tail = ""
                if node.kind == "number":
                    tail = f"= {_short(node.args[0])}"
                elif node.role == "free":
                    placement = node.placement or ("?", "?")
                    tail = f"({_short(placement[0])}, {_short(placement[1])})"
                elif node.role == "attached" and node.op:
                    command = by_id(node.op)
                    call = command.name_zh if command is not None else node.op
                    tail = f"= {call}({', '.join(node.args)})"
                if tail:
                    number = item.data(NUMBER_ROLE)
                    prefix = f"{number}. " if number is not None else ""
                    item.setText(f"{prefix}{item.data(HEAD_ROLE)}{tail}")
                    item.setData(TAIL_ROLE, tail)
        self.status.showMessage("拖动中——判定会在松手后更新")

    def _refresh_steps(self) -> None:
        # The pane is rebuilt from scratch, so it has to remember where
        # it was: a rebuild that throws away the selection is a rebuild
        # that loses the reader's place.
        current = self.steps.currentItem()
        keep: str | None = None
        if current is not None:
            payload = current.data(Qt.ItemDataRole.UserRole)
            if payload:
                keep = str(payload[1])
        self.steps.clear()
        self._step_rows: dict[str, int] = {}
        self._relation_rows: dict[str, int] = {}
        figure = self.controller.figure()
        self._steps_hint.setVisible(not figure.nodes)
        undefined = dict(self.controller.undefined())
        number = 0
        for node_id, node in figure.nodes.items():
            number += 1
            name = node.label or node_id
            if node.role == "free":
                if node.kind == "number":
                    head = f"{name} "
                    tail = f"= {_short(node.args[0])}"
                else:
                    placement = node.placement or ("?", "?")
                    head = f"{name} "
                    tail = f"({_short(placement[0])}, {_short(placement[1])})"
            else:
                command = by_id(node.op) if node.op else None
                call = command.name_zh if command is not None else (node.op or "?")
                head = f"{name} "
                tail = f"= {call}({', '.join(node.args)})"
            item = QListWidgetItem(f"{number}. {head}{tail}")
            item.setData(Qt.ItemDataRole.UserRole, ("node", node_id))
            item.setData(NUMBER_ROLE, number)
            item.setData(HEAD_ROLE, head)
            item.setData(TAIL_ROLE, tail)
            self._step_rows[node_id] = self.steps.count()
            if node_id in undefined:
                item.setToolTip(f"在这个摆放下没有值：{_undefined_text(undefined[node_id])}")
                item.setData(TAIL_ROLE, f"{tail}  （这个摆放下没有值）")
            self.steps.addItem(item)
        for relation in figure.relations:
            number += 1
            head = "断言 "
            tail = _claim_text(relation.kind, relation.args)
            item = QListWidgetItem(f"{number}. {head}{tail}")
            item.setData(Qt.ItemDataRole.UserRole, ("relation", relation.id))
            item.setData(NUMBER_ROLE, number)
            item.setData(HEAD_ROLE, head)
            item.setData(TAIL_ROLE, tail)
            self._relation_rows[relation.id] = self.steps.count()
            self.steps.addItem(item)
        if keep is not None:
            row = self._step_rows.get(keep)
            if row is not None:
                self.steps.setCurrentRow(row)

    def _free_numbers(self) -> list[Node]:
        return [
            node
            for node in self.controller.figure().nodes.values()
            if node.kind == "number" and node.op == "number.free"
        ]

    @staticmethod
    def _number_value(node: Node) -> float:
        try:
            return float(Fraction(node.args[0]))
        except (TypeError, ValueError, ZeroDivisionError):
            return PARAMETER_ZERO

    def _refresh_parameters(self) -> None:
        """Show a slider for every free number in the figure."""
        numbers = self._free_numbers()
        ids = tuple(node.id for node in numbers)
        if ids != self._parameter_ids:
            self._build_parameter_rows(numbers)
        self._parameters.setVisible(bool(numbers))
        if ids == self._parameter_ids:
            for node in numbers:
                self._set_row_value(node.id, self._number_value(node))

    def _build_parameter_rows(self, numbers: list[Node]) -> None:
        while self._parameter_layout.count():
            item = self._parameter_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._parameter_rows.clear()
        self._parameter_ids = tuple(node.id for node in numbers)
        for node in numbers:
            self._parameter_layout.addWidget(self._parameter_row(node))

    def _parameter_row(self, node: Node) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(6)
        name = QLabel(node.id)
        name.setToolTip("自由数：拖动滑块，整张图跟着变")
        name.setMinimumWidth(20)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(-1000, 1000)
        slider.setValue(
            round(
                max(PARAMETER_MIN, min(PARAMETER_MAX, self._number_value(node)))
                / PARAMETER_SLIDER_STEP
            )
        )
        slider.setToolTip("范围 −10 到 10；更远的数在右边直接输入")
        spin = QDoubleSpinBox()
        spin.setRange(-PARAMETER_LIMIT, PARAMETER_LIMIT)
        spin.setDecimals(3)
        spin.setSingleStep(PARAMETER_SPIN_STEP)
        spin.setValue(self._number_value(node))
        spin.setFixedWidth(84)
        layout.addWidget(name)
        layout.addWidget(slider, 1)
        layout.addWidget(spin)
        node_id = node.id
        slider.valueChanged.connect(
            lambda raw, nid=node_id: self._slider_moved(nid, raw)
        )
        slider.sliderPressed.connect(
            lambda nid=node_id: self._number_pressed(nid)
        )
        slider.sliderReleased.connect(self._number_released)
        spin.valueChanged.connect(
            lambda value, nid=node_id: self._spin_changed(nid, value)
        )
        self._parameter_rows[node_id] = (slider, spin)
        return row

    def _number_pressed(self, node_id: str) -> None:
        self.controller.push_undo()
        self._parameter_dragging = node_id
        self._number_timer.stop()

    def _slider_moved(self, node_id: str, raw: int) -> None:
        value = raw * PARAMETER_SLIDER_STEP
        row = self._parameter_rows.get(node_id)
        if row is not None:
            _slider, spin = row
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        if self._parameter_dragging != node_id:
            # Keyboard arrows arrive without a press: they are a drag too.
            self.controller.push_undo()
            self._parameter_dragging = node_id
        self.controller.set_number(node_id, value, final=False, record=False)
        self._number_timer.start()

    def _spin_changed(self, node_id: str, value: float) -> None:
        self._number_timer.stop()
        self._parameter_dragging = None
        self.controller.push_undo()
        self.controller.set_number(node_id, value, final=True, record=False)
        row = self._parameter_rows.get(node_id)
        if row is not None:
            slider, _spin = row
            slider.blockSignals(True)
            slider.setValue(
                round(max(PARAMETER_MIN, min(PARAMETER_MAX, value)) / PARAMETER_SLIDER_STEP)
            )
            slider.blockSignals(False)

    def _number_released(self) -> None:
        self._settle_number()

    def _settle_number(self) -> None:
        self._number_timer.stop()
        if self._parameter_dragging is None:
            return
        self._parameter_dragging = None
        self.controller.finish_move()

    def _set_row_value(self, node_id: str, value: float) -> None:
        row = self._parameter_rows.get(node_id)
        if row is None or self._parameter_dragging == node_id:
            return
        slider, spin = row
        slider.blockSignals(True)
        spin.blockSignals(True)
        slider.setValue(
                round(max(PARAMETER_MIN, min(PARAMETER_MAX, value)) / PARAMETER_SLIDER_STEP)
            )
        spin.setValue(value)
        slider.blockSignals(False)
        spin.blockSignals(False)

    def _refresh_judgements(self) -> None:
        """Ask for the verdicts, and carry on without them.

        A proof can take seconds. The screen must not wait for it, so
        the work happens on a copy of the figure, in another thread, and
        the table is filled when the answer arrives.

        Nothing is judged while the exact evaluation is still on its
        way: a verdict about a figure that has only been drawn
        numerically would be a verdict about the wrong thing.  The exact
        pass calls this again when it arrives.
        """
        if self.controller.exact_pending():
            self._set_judgement_note("精确求值中……判定随后就来")
            return
        if self.controller.inexact():
            self._set_judgement_note("这张图太大，判定不回答")
            return
        self._judge_request += 1
        request = self._judge_request
        figure = self.controller.snapshot_figure()
        scope = self._scope
        self._judge_pending = True
        self._set_judgement_note("判定中……")

        def work() -> None:
            try:
                verdicts = self.controller.judge_figure(figure, scope)
            except Exception:  # pragma: no cover - the worker must not die
                verdicts = []
            else:
                self.controller.absorb_verdicts(figure)
            self.verdictsReady.emit(request, verdicts)

        threading.Thread(target=work, daemon=True).start()

    def _on_verdicts(self, request: int, verdicts: list[Verdict]) -> None:
        """The verdicts have arrived."""
        if request != self._judge_request:
            # The figure has moved on since this proof started; its
            # answer is about a figure that no longer exists.
            return
        self._judge_pending = False
        self._set_judgement_note("哪些说法成立")
        verdicts = list(verdicts)
        self._verdicts = verdicts
        # The verdicts are in the order of the figure's relations; the
        # arguments are not in the verdict, so they are read off the
        # figure the same sequence.
        self._verdict_args = [
            list(relation.args) for relation in self.controller.figure().relations
        ]
        self.judgements.blockSignals(True)
        self.judgements.setRowCount(len(verdicts))
        for row, verdict in enumerate(verdicts):
            args = (
                self._verdict_args[row] if row < len(self._verdict_args) else []
            )
            self.judgements.setItem(
                row, 0, QTableWidgetItem(_claim_text(verdict.kind, args))
            )
            self.judgements.setItem(
                row, 1, QTableWidgetItem(_verdict_text(verdict.verdict))
            )
            self.judgements.setItem(
                row, 2, QTableWidgetItem(_evidence_summary(verdict))
            )
            # A verdict is coloured by what it says: green for proved,
            # red for refuted, quiet for "we do not know". A teacher
            # reads the table before reading the words.
            cell = self.judgements.item(row, 1)
            if cell is not None:
                colour = {
                    "proved": PALETTE.ok,
                    "refuted": PALETTE.danger,
                }.get(verdict.verdict, PALETTE.text_muted)
                cell.setData(VERDICT_ROLE, colour)
                cell.setForeground(QColor(colour))
        self.judgements.blockSignals(False)
        # A proved equality or right angle belongs on the figure, not
        # only in a table: that is how a geometry lesson points at it.
        marks: list[tuple[str, tuple[str, ...]]] = []
        for relation, verdict in zip(
            self.controller.figure().relations, verdicts, strict=False
        ):
            if verdict.verdict == "proved" and relation.kind in {
                "equal_length",
                "perpendicular",
            }:
                marks.append((relation.kind, tuple(relation.args)))
        self.canvas.set_proof_marks(marks)
        self._tint_step_verdicts()
        if verdicts:
            self.judgements.selectRow(0)
        else:
            self.evidence.clear()
            self.evidence_summary.setText(
                "选中一行，这里用一句话说明它为什么成立（或不成立）。"
            )
            self.witness_button.setVisible(False)
            self._witness = None

    def _tint_step_verdicts(self) -> None:
        """Colour each claim in the steps pane by what was decided."""
        for row in self._relation_rows.values():
            item = self.steps.item(row)
            if item is not None:
                item.setData(TINT_ROLE, None)
        relations = self.controller.figure().relations
        for relation, verdict in zip(relations, self._verdicts, strict=False):
            relation_row = self._relation_rows.get(relation.id)
            if relation_row is None:
                continue
            item = self.steps.item(relation_row)
            colour = {
                "proved": PALETTE.ok,
                "refuted": PALETTE.danger,
            }.get(verdict.verdict, PALETTE.text_muted)
            item.setData(TINT_ROLE, colour)
            item.setToolTip(
                f"{_claim_text(relation.kind, relation.args)}："
                f"{_verdict_text(verdict.verdict)}\n"
                f"{_evidence_summary(verdict)}"
            )
        self.steps.viewport().update()

    def _delete_node(self, node_id: str) -> None:
        """Delete one object, with everything that depends on it."""
        try:
            self.controller.remove_node(node_id)
        except GeobenchError as exc:
            self.status.showMessage(f"删不掉：{exc}")
            return
        self.canvas.reset_pending()
        self.status.showMessage(f"删掉了 {node_id}")

    def _delete_nodes(self, node_ids: list[str]) -> None:
        """Delete every selected object, in one undo step."""
        try:
            removed = self.controller.remove_nodes(node_ids)
        except GeobenchError as exc:
            self.status.showMessage(f"删不掉：{exc}")
            return
        self.canvas.select(None)
        self.canvas.reset_pending()
        self.status.showMessage(f"删掉了 {removed} 个对象（一次撤销可以全部找回）")

    def _steps_menu(self, position: QPoint) -> None:
        """Right-click on a step: delete it."""
        item = self.steps.itemAt(position)
        if item is None:
            return
        self.steps.setCurrentItem(item)
        menu = QMenu(self)
        delete_action = menu.addAction("删除")
        chosen = menu.exec(self.steps.mapToGlobal(position))
        if chosen is delete_action:
            self._delete_selected_step()

    def _delete_selected_step(self) -> None:
        """Delete whatever the steps pane has selected.

        Deleting a point deletes what depends on it and the claims
        about it: an object and everything that only exists because of
        it go together, and leaving half of it behind is worse than
        leaving all of it.
        """
        selected = self.steps.selectedItems()
        if not selected:
            return
        payload = selected[0].data(Qt.ItemDataRole.UserRole)
        if not payload:
            return
        kind, identifier = payload
        try:
            if kind == "relation":
                self.controller.remove_relation(identifier)
            else:
                self.controller.remove_node(identifier)
        except GeobenchError as exc:
            self.status.showMessage(f"删不掉：{exc}")
            return
        self.canvas.reset_pending()
        self.status.showMessage(f"删掉了 {identifier}")

    def _show_evidence(self) -> None:
        """Say, in a sentence, why the selected claim holds or does not.

        The kernel's evidence is a symbolic reduction: it is the proof,
        and it is also unreadable in a classroom.  The sentence comes
        first; the derivation is one click away for the teacher who
        wants to see the algebra.
        """
        self._witness = None
        self.witness_button.setVisible(False)
        rows = self.judgements.selectionModel().selectedRows()
        if not rows:
            self.evidence_summary.setText(
                "选中一行，这里用一句话说明它为什么成立（或不成立）。"
            )
            self.evidence.clear()
            return
        index = rows[0].row()
        if index < 0 or index >= len(self._verdicts):
            return
        verdict = self._verdicts[index]
        args = self._verdict_args[index] if index < len(self._verdict_args) else []
        lines = [_claim_text(verdict.kind, args), _verdict_text(verdict.verdict)]
        if verdict.verdict == "proved":
            lines.append(
                "对所有摆放都成立：这是图形的性质，不是这一张图的巧合。"
                if verdict.scope == IDENTITY
                else "只在你现在摆的这张图里成立。"
            )
        elif verdict.verdict == "refuted":
            lines.append("这句话不是恒等式：有一个合法的摆放让它不成立。")
            if verdict.witness:
                self._witness = dict(verdict.witness)
                self.witness_button.setVisible(True)
                lines.append("反例：" + _witness_text(verdict.witness))
        elif verdict.verdict == "supported":
            lines.append("找不到反例，但也还没能证明；换个问法或换个范围再试。")
        else:
            lines.append(_evidence_text(verdict.evidence))
        self.evidence_summary.setText("\n".join(lines))
        self.evidence.setPlainText(_evidence_text(verdict.evidence))

    def _preview_witness(self) -> None:
        """Put the figure at the counterexample's placement, so it can be seen."""
        if self._witness is None:
            return
        if not self.controller.apply_witness(self._witness):
            self.status.showMessage("这个反例里有拖不动的点，摆不出来")
            return
        self.status.showMessage(
            "已经把图摆到反例的位置；按 Ctrl+Z 回到原来的样子"
        )

    def set_scope(self, scope: str) -> None:
        """Choose the scope the judgements are made in."""
        self._scope = scope
        button = self.scope_buttons.get(scope)
        if button is not None:
            button.setChecked(True)
        self._refresh_judgements()

    def toggle_scope(self) -> None:
        """Switch between the identity and the instance scope."""
        self.set_scope(INSTANCE if self._scope == IDENTITY else IDENTITY)


def _relation_name(kind: str) -> str:
    """The Chinese name of a relation, as the command table has it."""
    command = by_id(kind)
    if command is not None:
        return command.name_zh
    return kind


#: The evidence the kernel writes, in the language the kernel writes it
#: in -- the kernel is a library, and its messages are its own. The
#: window shows them in the teacher's language. The expressions inside
#: are symbolic and need no translation.
_EVIDENCE_ZH: tuple[tuple[str, str], ...] = (
    (
        "the relation holds for the given configuration:",
        "在这张图的摆放下成立：",
    ),
    (
        "the relation fails for the given configuration:",
        "在这张图的摆放下不成立：",
    ),
    (
        "the relation does not hold identically; counterexample:",
        "不是恒等式；反例：",
    ),
    (
        "the expression reduces to 0 identically:",
        "表达式恒等于 0：",
    ),
    (
        "the configuration is degenerate:",
        "这张图的摆下图退化：",
    ),
    (
        "every sampled placement was degenerate:",
        "所有采样的摆下图都是退化的：",
    ),
    ("substitution failed:", "代入失败："),
)

#: Why an object has no value, in the teacher's language.  The kernel
#: names the condition that failed; the classroom needs the reason.
_UNDEFINED_ZH: dict[str, str] = {
    "parallel_lines": "两条直线平行，没有交点",
    "lines are parallel or coincident; no unique intersection": "两条直线平行，没有交点",
    "discriminant": "判别式为零（退化）",
    "determinant": "行列式为零（退化）",
    "point_on_circle": "这个点不在圆上",
    "b": "分母为零（退化）",
    "no value at this placement": "在这个摆放下没有值",
    "the two lines are parallel; there is no intersection": "两条直线平行，没有交点",
    "the construction divides by something that vanishes identically": "构造里出现恒为零的除数",
}

#: The kernel says why an object is missing in its own words; the window
#: says it in the language of the classroom.
_NO_VALUE_ZH = "对象 {name} 没有值：{reason}"


def _undefined_text(reason: str) -> str:
    """Why an object has no value, in Chinese."""
    return _UNDEFINED_ZH.get(reason, reason)

_SAMPLES_ZH = re.compile(
    r"the relation holds in all (\d+) samples but the expression did not reduce "
    r"to 0 identically(?: \(([^)]*)\))? \(size (\d+) ops\): (.*)"
)

#: "the expansion would have up to N terms, over the budget of M" -- the
#: reason the kernel gave up on a proof.
_BUDGET_ZH = re.compile(
    r"^the expansion would have up to (\d+) terms, over the budget of (\d+)$"
)

#: "node 'P' has no value: ..." -- an object the construction could not
#: make at all.
_NO_VALUE_EVIDENCE = re.compile(r"^node '(?P<name>[^']+)' has no value: (?P<reason>.*)$")

#: "the configuration is degenerate: P has no value here (parallel_lines)"
#: -- an object the configuration could not make *here*.
_DEGENERATE_EVIDENCE = re.compile(
    r"^the configuration is degenerate: (?P<name>\S+) has no value here "
    r"\((?P<reason>[^)]*)\)$"
)


def _evidence_text(evidence: str) -> str:
    """The evidence, in Chinese."""
    match = _SAMPLES_ZH.match(evidence)
    if match is not None:
        count, note, size, expression = match.groups()
        reason = ""
        if note:
            budget = _BUDGET_ZH.match(note)
            if budget is not None:
                terms, limit = budget.groups()
                reason = f"（展开后可能有 {terms} 项，超出预算 {limit}）"
            else:
                reason = f"（{note}）"
        return (
            f"在全部 {count} 个样本里都成立，但表达式没能化简成恒等于 0"
            f"{reason}（{size} 个运算）：{expression}"
        )
    match = _NO_VALUE_EVIDENCE.match(evidence)
    if match is not None:
        return f"对象 {match.group('name')} 没有值：{_undefined_text(match.group('reason'))}"
    match = _DEGENERATE_EVIDENCE.match(evidence)
    if match is not None:
        name = match.group("name")
        return f"这张图的摆下图退化：{name} 没有值（{_undefined_text(match.group('reason'))}）"
    for english, chinese in _EVIDENCE_ZH:
        if evidence.startswith(english):
            return chinese + evidence[len(english) :].strip()
    return evidence


def _shortcuts_text() -> str:
    """The keyboard, in the order a lesson uses it."""
    return (
        "Ctrl+Z / Ctrl+Y    撤销 / 重做\n"
        "Delete             删除选中的对象\n"
        "Shift + 点击        多选（右侧面板会列出能问的问题）\n"
        "中键拖动            平移画布\n"
        "滚轮                缩放\n"
        "双击一个点          输入精确坐标（1/2 和 0.5 是同一个数）\n"
        "Ctrl+N              新建一张空白图\n"
        "Ctrl+O / Ctrl+S     打开 / 保存（改动会自动留一份恢复文件）\n"
        "Ctrl+Shift+S        另存为\n"
        "把 .geobench 或 .ggb 文件拖进窗口即可打开"
    )


def _about_text() -> str:
    return (
        f"geobench {__version__}\n\n"
        "面向竞赛级平面几何命题的确定性几何内核与工作台。\n"
        "判定回答的是“对任意摆放是否成立”，不是“这张图看起来对不对”。\n\n"
        "MIT License"
    )


def _verdict_text(verdict: str) -> str:
    return {
        "proved": "成立",
        "refuted": "不成立",
        "supported": "未证明",
        "undecided": "不能判定",
    }.get(verdict, verdict)


def _claim_text(kind: str, args: list[str]) -> str:
    """The claim as a sentence in the language of a geometry paper.

    "AB = CD" is what the teacher said; "相等" with four object names
    is what the kernel takes.  The table shows the first, the DSL the
    second.
    """
    if kind == "collinear":
        return f"{'、'.join(args)} 共线"
    if kind == "concyclic" and len(args) >= 3:
        return f"{'、'.join(args)} 共圆"
    if kind == "parallel" and len(args) == 2:
        return f"{args[0]} ∥ {args[1]}"
    if kind == "perpendicular" and len(args) == 2:
        return f"{args[0]} ⊥ {args[1]}"
    if kind == "equal_length" and len(args) == 4:
        return f"{args[0]}{args[1]} = {args[2]}{args[3]}"
    if kind == "point_in" and len(args) == 2:
        return f"{args[0]} 在 {args[1]} 上"
    if kind == "midpoint_of" and len(args) == 3:
        return f"{args[0]} 是 {args[1]}{args[2]} 的中点"
    if kind == "centroid_of" and len(args) == 4:
        return f"{args[0]} 是 △{args[1]}{args[2]}{args[3]} 的重心"
    if kind == "tangent_to" and len(args) == 2:
        return f"{args[0]} 与 {args[1]} 相切"
    if kind == "concurrency" and len(args) == 3:
        return f"{'、'.join(args)} 三线共点"
    if kind == "angle_equal" and len(args) == 6:
        return (
            f"∠{args[0]}{args[1]}{args[2]} = ∠{args[3]}{args[4]}{args[5]}"
        )
    return f"{_relation_name(kind)}（{'、'.join(args)}）"


def _witness_text(witness: dict[str, object]) -> str:
    """The counterexample written the way a teacher would write it."""
    parts: list[str] = []
    for name, value in sorted(witness.items()):
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            parts.append(
                f"{name}（{_short(str(value[0]))}, {_short(str(value[1]))}）"
            )
        else:
            parts.append(f"{name} = {value}")
    return "、".join(parts)


def _evidence_summary(verdict: Verdict) -> str:
    """One short phrase for the table's third column.

    The full sentence lives in the pane below.  A table cell is a
    glance, not a proof.
    """
    if verdict.verdict == "proved":
        return (
            "对任意图形都成立"
            if verdict.scope == IDENTITY
            else "只在这张图上成立"
        )
    if verdict.verdict == "refuted":
        return "有一个反例，选中可以看"
    text = _evidence_text(verdict.evidence)
    for stop in ("：", "。"):
        if stop in text:
            text = text.split(stop, 1)[0]
    return text[:48] or "不能判定"


__all__ = [
    "ObjectPicker",
    "RelationSpec",
    "StudioWindow",
    "ToolSpec",
]
