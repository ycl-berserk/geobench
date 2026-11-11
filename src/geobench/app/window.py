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

import re
import threading
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from PySide6.QtCore import (
    QModelIndex,
    QPersistentModelIndex,
    QPoint,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QAction, QColor, QKeySequence, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
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
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
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

from geobench.ai_settings import resolve_provider
from geobench.app.ai_panel import AIPanel
from geobench.app.canvas import FigureCanvas
from geobench.app.controller import StudioController
from geobench.app.export import copy_image, copy_svg_source, write_png, write_svg
from geobench.app.icons import group_icon, tool_icon
from geobench.app.settings_dialog import SettingsDialog
from geobench.app.theme import PALETTE, button_words, mono_font
from geobench.app.tools import (
    POINT_TOOL,
    SELECT_TOOL,
    ToolGroup,
    ToolSpec,
    build_toolbar,
)
from geobench.commands import COMMANDS, JUDGEMENT, by_id
from geobench.errors import GeobenchError
from geobench.judges import IDENTITY, INSTANCE, Verdict


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
    "any": ("point", "line", "segment", "circle", "polygon"),
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



#: The two scopes a judgement can have.
SCOPE_LABELS = {
    IDENTITY: "作用域：identity（对任意摆放成立）",
    INSTANCE: "作用域：instance（只对当前这张图成立）",
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
        metrics = option.fontMetrics
        text_rect = rect.adjusted(10, 0, -6, 0)
        painter.save()
        font = option.font
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
            painter.setPen(QColor(PALETTE.text_muted))
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


class StudioWindow(QMainWindow):
    """The main window of the studio."""

    #: The verdicts have arrived. The number tells which request they
    #: answer, so that a slow proof for an old figure can be dropped.
    verdictsReady = Signal(int, list)

    def __init__(self, controller: StudioController | None = None) -> None:
        super().__init__()
        self.controller = controller or StudioController()
        self.setWindowTitle("geobench — 竞赛几何命题工作台")
        self.resize(1180, 720)
        self._scope = IDENTITY
        self._verdicts: list[Verdict] = []
        self._path: Path | None = None

        self.canvas = FigureCanvas(self.controller)
        self.canvas.constructRequested.connect(self._on_construct)
        self.canvas.deleteRequested.connect(self._delete_node)
        self.canvas.pointEditRequested.connect(self._edit_point)
        self.canvas.valueRequested.connect(self._on_value_requested)
        self.canvas.selectionChanged.connect(self._on_selection)

        self._playback_timer = QTimer(self)
        self._playback_timer.setInterval(450)
        self._playback_timer.timeout.connect(self._playback_tick)
        self._playback_limit: int | None = None

        self.steps = QListWidget()
        self.steps.setToolTip("构造步骤：这张图是怎么一步步造出来的（右键删除）")
        self.steps.setItemDelegate(StepDelegate(self.steps))
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
        self.judgements.setHorizontalHeaderLabels(["关系", "结论", "证据"])
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

        # The table gives the verdict at a glance; the pane below gives
        # the proof (or the counterexample) in full. A verdict without its
        # evidence is a claim, and this product exists to avoid those.
        self.evidence = QPlainTextEdit()
        self.evidence.setReadOnly(True)
        # The evidence is read symbol by symbol; a proportional font
        # makes the minus sign and the hyphen the same width.
        self.evidence.setFont(mono_font())
        self.evidence.setMinimumHeight(110)
        self.evidence.setPlaceholderText("选中一行，这里显示它的证据")
        self.judgements.itemSelectionChanged.connect(self._show_evidence)

        self.status = self.statusBar()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        steps_box = QWidget()
        steps_layout = QVBoxLayout(steps_box)
        steps_layout.setContentsMargins(0, 0, 0, 0)
        steps_layout.setSpacing(6)
        steps_layout.addWidget(self._playback_buttons())
        steps_layout.addWidget(self.steps)
        splitter.addWidget(
            self._panel(
                "\u6784\u9020",
                steps_box,
                "\u8fd9\u5f20\u56fe\u662f\u600e\u4e48\u9020\u51fa\u6765\u7684",
            )
        )
        splitter.addWidget(self._panel("画板", self.canvas, "拖动自由点"))
        splitter.addWidget(self._panel("判定", self._judgement_panel(), "哪些说法成立"))
        splitter.setSizes([280, 560, 420])
        # A wide, quiet handle: the panes are separated by a gap, not by
        # a bar that reads as a hole in the window.
        splitter.setHandleWidth(12)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        self.setCentralWidget(central)

        self._build_toolbar()
        self._build_menu()
        self.controller.on_change(self.refresh)
        self.controller.on_move(self._point_moved)
        self._dragging = False
        self._judge_request = 0
        self._judge_pending = False
        self.verdictsReady.connect(self._on_verdicts)
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

        chips = QGridLayout()
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
        layout.addLayout(chips)

        scope_row = QWidget()
        scope_layout = QHBoxLayout(scope_row)
        scope_layout.setContentsMargins(0, 0, 0, 0)
        scope_layout.setSpacing(6)
        scope_layout.addWidget(QLabel("作用域"))
        # Two buttons, one of them down: the scope is a choice between
        # two things, and a button that says "toggle" does not say which
        # one is in force.
        self.scope_group = QButtonGroup(self)
        self.scope_group.setExclusive(True)
        self.scope_buttons: dict[str, QPushButton] = {}
        for scope, label in ((IDENTITY, "恒等"), (INSTANCE, "实例")):
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
        layout.addWidget(self.evidence, 1)
        return panel

    def _build_menu(self) -> None:
        """The file menu.

        A figure that cannot be saved is a figure that does not exist,
        as far as the teacher is concerned: they close the window and
        the work is gone. The file is the DSL, so the figure is written
        in the same language a person would write it.
        """
        menu = self.menuBar()
        file_menu = menu.addMenu("文件")
        open_action = QAction("打开…", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._open_file)
        file_menu.addAction(open_action)
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
        export_menu.addSeparator()
        copy_picture_action = QAction("复制图形到剪贴板", self)
        copy_picture_action.triggered.connect(self._copy_picture)
        export_menu.addAction(copy_picture_action)
        copy_svg_action = QAction("复制 SVG 源码", self)
        copy_svg_action.triggered.connect(self._copy_svg)
        export_menu.addAction(copy_svg_action)

        settings_menu = menu.addMenu("设置")
        service_action = QAction("模型服务…", self)
        service_action.setToolTip("选择模型服务，并告诉它钥匙在哪")
        service_action.triggered.connect(self._open_settings)
        settings_menu.addAction(service_action)

        edit_menu = menu.addMenu("编辑")
        undo_action = QAction("撤销", self)
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        undo_action.triggered.connect(self._undo)
        edit_menu.addAction(undo_action)
        redo_action = QAction("重做", self)
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        redo_action.triggered.connect(self._redo)
        edit_menu.addAction(redo_action)

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

    def _open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "打开图形", "", "Geobench 图形 (*.geobench);;所有文件 (*)"
        )
        if not path:
            return
        self._load_path(Path(path))

    def _load_path(self, path: Path) -> None:
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
        self._update_title()
        self.status.showMessage(f"打开了 {path.name}")

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
        self._update_title()
        self.status.showMessage(f"存好了 {path.name}")

    def _update_title(self) -> None:
        name = self._path.name if self._path is not None else "未命名"
        self.setWindowTitle(f"geobench — 竞赛几何命题工作台（{name}）")

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

    def _on_selection(self, node_id: str) -> None:
        """An object was picked: say which one, and show it in the steps."""
        if not node_id:
            self.status.showMessage("没有选中任何对象")
            return
        self.status.showMessage(f"选中了 {node_id}（Delete 键删掉它）")
        row = self._step_rows.get(node_id)
        if row is not None:
            self.steps.setCurrentRow(row)

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
            self.controller.construct(op, args)
        except GeobenchError as exc:
            self.status.showMessage(f"构造失败：{exc}")
            return
        self.status.showMessage(f"{op}({', '.join(args)})")

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
        """Redraw the steps and the judgements."""
        self._refresh_steps()
        self._refresh_judgements()
        if self._dragging:
            # The drag is over; the verdicts have been settled.
            self._dragging = False
            self.status.showMessage("松手了：判定已按新的位置算过")

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
                if node.role == "free":
                    placement = node.placement or ("?", "?")
                    tail = f"({_short(placement[0])}, {_short(placement[1])})"
                elif node.role == "attached" and node.op:
                    command = by_id(node.op)
                    call = command.name_zh if command is not None else node.op
                    tail = f"= {call}({', '.join(node.args)})"
                if tail:
                    item.setText(f"{item.data(HEAD_ROLE)}{tail}")
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
        figure = self.controller.figure()
        undefined = dict(self.controller.undefined())
        for node_id, node in figure.nodes.items():
            name = node.label or node_id
            if node.role == "free":
                placement = node.placement or ("?", "?")
                head = f"{name} "
                tail = f"({_short(placement[0])}, {_short(placement[1])})"
            else:
                command = by_id(node.op) if node.op else None
                call = command.name_zh if command is not None else (node.op or "?")
                head = f"{name} "
                tail = f"= {call}({', '.join(node.args)})"
            item = QListWidgetItem(f"{head} {tail}".strip())
            item.setData(Qt.ItemDataRole.UserRole, ("node", node_id))
            item.setData(HEAD_ROLE, head)
            item.setData(TAIL_ROLE, tail)
            self._step_rows[node_id] = self.steps.count()
            if node_id in undefined:
                item.setToolTip(f"在这个摆放下没有值：{undefined[node_id]}")
                item.setData(TAIL_ROLE, f"{tail}  （这个摆放下没有值）")
            self.steps.addItem(item)
        for relation in figure.relations:
            head = "断言 "
            tail = f"{_relation_name(relation.kind)}({', '.join(relation.args)})"
            item = QListWidgetItem(f"{head} {tail}")
            item.setData(Qt.ItemDataRole.UserRole, ("relation", relation.id))
            item.setData(HEAD_ROLE, head)
            item.setData(TAIL_ROLE, tail)
            self.steps.addItem(item)
        if keep is not None:
            row = self._step_rows.get(keep)
            if row is not None:
                self.steps.setCurrentRow(row)

    def _refresh_judgements(self) -> None:
        """Ask for the verdicts, and carry on without them.

        A proof can take seconds. The screen must not wait for it, so
        the work happens on a copy of the figure, in another thread, and
        the table is filled when the answer arrives.
        """
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
        self.judgements.blockSignals(True)
        self.judgements.setRowCount(len(verdicts))
        for row, verdict in enumerate(verdicts):
            self.judgements.setItem(row, 0, QTableWidgetItem(_relation_name(verdict.kind)))
            self.judgements.setItem(row, 1, QTableWidgetItem(_verdict_text(verdict.verdict)))
            self.judgements.setItem(row, 2, QTableWidgetItem(_evidence_text(verdict.evidence)[:120]))
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
        if verdicts:
            self.judgements.selectRow(0)
        else:
            self.evidence.clear()

    def _delete_node(self, node_id: str) -> None:
        """Delete one object, with everything that depends on it."""
        try:
            self.controller.remove_node(node_id)
        except GeobenchError as exc:
            self.status.showMessage(f"删不掉：{exc}")
            return
        self.canvas.reset_pending()
        self.status.showMessage(f"删掉了 {node_id}")

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
        """Show the full evidence of the selected relation."""
        rows = self.judgements.selectionModel().selectedRows()
        if not rows:
            return
        index = rows[0].row()
        if index < 0 or index >= len(self._verdicts):
            return
        verdict = self._verdicts[index]
        text = (
            f"{_relation_name(verdict.kind)} —— {_verdict_text(verdict.verdict)}"
            f"\n\n{_evidence_text(verdict.evidence)}"
        )
        if verdict.witness:
            text += "\n\n反例（一个不满足的摆放）：\n" + "\n".join(
                f"  {key}: {value}" for key, value in sorted(verdict.witness.items())
            )
        self.evidence.setPlainText(text)

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
    ("substitution failed:", "代入失败："),
)

_SAMPLES_ZH = re.compile(
    r"the relation holds in all (\d+) samples but the expression did not reduce "
    r"to 0 identically \(size (\d+) ops\): (.*)"
)


def _evidence_text(evidence: str) -> str:
    """The evidence, in Chinese."""
    match = _SAMPLES_ZH.match(evidence)
    if match is not None:
        count, size, expression = match.groups()
        return f"在全部 {count} 个样本里都成立，但表达式没能化简成恒等于 0（{size} 个运算）：{expression}"
    for english, chinese in _EVIDENCE_ZH:
        if evidence.startswith(english):
            return chinese + evidence[len(english) :].strip()
    return evidence


def _verdict_text(verdict: str) -> str:
    return {
        "proved": "成立（proved）",
        "refuted": "不成立（refuted）",
        "supported": "未证（supported）",
        "undecided": "无法判定（undecided）",
    }.get(verdict, verdict)


__all__ = [
    "ObjectPicker",
    "RelationSpec",
    "StudioWindow",
    "ToolSpec",
]
