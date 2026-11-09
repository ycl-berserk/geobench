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
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QPoint, QSize, Qt
from PySide6.QtGui import QAction, QColor, QKeySequence, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
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

from geobench.app.canvas import FigureCanvas
from geobench.app.controller import StudioController
from geobench.app.icons import group_icon, tool_icon
from geobench.app.theme import PALETTE, mono_font
from geobench.app.tools import POINT_TOOL, ToolGroup, ToolSpec, build_toolbar
from geobench.commands import by_id
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
    on_points: bool = True


#: The relations the window offers. The command table knows how many
#: objects each one takes; this list only says which ones to put on the
#: toolbar.
RELATION_IDS: tuple[str, ...] = (
    "collinear",
    "concyclic",
    "equal_length",
    "perpendicular",
    "parallel",
    "circumcenter_of",
    "orthocenter_of",
)

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
    """The relation buttons, built from the command table."""
    specs: list[RelationSpec] = []
    for kind in RELATION_IDS:
        command = by_id(kind)
        if command is None:
            continue
        on_points = command.arg_kinds[0] == "point" if command.arg_kinds else True
        specs.append(
            RelationSpec(
                kind=kind,
                label=command.name_zh,
                arg_count=command.arity,
                hint=f"选 {command.arity} 个对象，检查{command.summary}",
                on_points=on_points,
            )
        )
    return tuple(specs)

#: The relations the window can check.
RELATIONS: tuple[RelationSpec, ...] = (
    RelationSpec("collinear", "共线", 3, "选三个点，检查它们是否共线"),
    RelationSpec("concyclic", "共圆", 4, "选四个点，检查它们是否共圆"),
    RelationSpec("equal_length", "等长", 4, "选四个点，检查两条线段是否等长"),
    RelationSpec("perpendicular", "垂直", 2, "选两条线，检查它们是否垂直", False),
)

#: The two scopes a judgement can have.
SCOPE_LABELS = {
    IDENTITY: "作用域：identity（对任意摆放成立）",
    INSTANCE: "作用域：instance（只对当前这张图成立）",
}


class ObjectPicker(QDialog):
    """Choose the objects a relation is about.

    The user picks the objects; the window never guesses. Picking "the
    first three points" would silently check a claim nobody made, which
    is the one thing this product must not do.
    """

    def __init__(
        self, parent: QWidget, candidates: list[str], count: int, title: str
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(240)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"选 {count} 个对象（按住 Ctrl 多选）"))
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        for candidate in candidates:
            self.list.addItem(candidate)
        layout.addWidget(self.list)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def chosen(self) -> list[str]:
        return [item.text() for item in self.list.selectedItems()]


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
        self.canvas.valueRequested.connect(self._on_value_requested)

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
        splitter.addWidget(self._panel("构造", self.steps, "这张图是怎么造出来的"))
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

        edit_menu = menu.addMenu("编辑")
        undo_action = QAction("撤销", self)
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        undo_action.triggered.connect(self._undo)
        edit_menu.addAction(undo_action)
        redo_action = QAction("重做", self)
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        redo_action.triggered.connect(self._redo)
        edit_menu.addAction(redo_action)

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

    # -- interaction -------------------------------------------------------

    def _arm(self, tool: ToolSpec, group: ToolGroup | None = None) -> None:
        """Arm a tool, and make the group's button show it."""
        self.canvas.set_tool(tool)
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

    def _add_relation(self, spec: RelationSpec) -> None:
        """Let the user choose the objects the relation is about."""
        figure = self.controller.figure()
        if spec.on_points:
            candidates = [
                node.id for node in figure.nodes.values() if node.kind == "point"
            ]
        else:
            candidates = [
                node.id
                for node in figure.nodes.values()
                if node.kind in {"line", "segment"}
            ]
        if len(candidates) < spec.arg_count:
            self.status.showMessage(
                f"图里还没有足够的对象来检查这个关系（需要 {spec.arg_count} 个）"
            )
            return
        picker = ObjectPicker(self, candidates, spec.arg_count, f"检查{spec.label}")
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
            if item is not None and node is not None and node.role == "free":
                placement = node.placement or ("?", "?")
                tail = f"({_short(placement[0])}, {_short(placement[1])})"
                item.setText(f"{item.data(HEAD_ROLE)}{tail}")
                item.setData(TAIL_ROLE, tail)
        self.status.showMessage("拖动中——判定会在松手后更新")

    def _refresh_steps(self) -> None:
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

    def _refresh_judgements(self) -> None:
        verdicts = self.controller.judge(self._scope)
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
    "RELATIONS",
    "ObjectPicker",
    "RelationSpec",
    "StudioWindow",
    "ToolSpec",
]
