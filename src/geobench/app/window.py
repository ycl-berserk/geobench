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

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from geobench.app.canvas import FigureCanvas
from geobench.app.controller import StudioController
from geobench.errors import GeobenchError
from geobench.judges import IDENTITY, INSTANCE, Verdict


@dataclass(frozen=True)
class ToolSpec:
    """One construction tool."""

    key: str
    label: str
    op: str
    arg_count: int
    hint: str


@dataclass(frozen=True)
class RelationSpec:
    """A relation the window can check."""

    kind: str
    label: str
    arg_count: int
    hint: str
    on_points: bool = True


#: The tools of the first version. Each one is an operator that already
#: exists and has been cross-checked against an independent
#: implementation; adding an operator adds a tool without touching the
#: window.
TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec("point", "点", "point.free", 0, "在空白处点击，放一个自由点"),
    ToolSpec("midpoint", "中点", "point.midpoint", 2, "依次点两个点"),
    ToolSpec("centroid", "重心", "point.centroid", 3, "依次点三个点"),
    ToolSpec("circumcenter", "外心", "point.circumcenter", 3, "依次点三个点"),
    ToolSpec("incenter", "内心", "point.incenter", 3, "依次点三个点"),
    ToolSpec("orthocenter", "垂心", "point.orthocenter", 3, "依次点三个点"),
    ToolSpec("circumcircle", "外接圆", "circle.through", 3, "依次点三个点"),
)

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


class StudioWindow(QMainWindow):
    """The main window of the studio."""

    def __init__(self, controller: StudioController | None = None) -> None:
        super().__init__()
        self.controller = controller or StudioController()
        self.setWindowTitle("geobench — 竞赛几何命题工作台")
        self.resize(1180, 720)
        self._scope = IDENTITY
        self._verdicts: list[Verdict] = []

        self.canvas = FigureCanvas(self.controller)
        self.canvas.constructRequested.connect(self._on_construct)

        self.steps = QListWidget()
        self.steps.setToolTip("构造步骤：这张图是怎么一步步造出来的")

        self.judgements = QTableWidget(0, 3)
        self.judgements.setHorizontalHeaderLabels(["关系", "结论", "证据"])
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
        self.evidence.setMinimumHeight(110)
        self.evidence.setPlaceholderText("选中一行，这里显示它的证据")
        self.judgements.itemSelectionChanged.connect(self._show_evidence)

        self.scope_label = QLabel(SCOPE_LABELS[IDENTITY])
        self.status = self.statusBar()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._panel("构造", self.steps))
        splitter.addWidget(self._panel("画板", self.canvas))
        splitter.addWidget(self._panel("判定", self._judgement_panel()))
        splitter.setSizes([250, 540, 390])

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        self.setCentralWidget(central)

        self._build_toolbar()
        self.controller.on_change(self.refresh)
        self.refresh()

    # -- layout ------------------------------------------------------------

    def _panel(self, title: str, widget: QWidget) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        heading = QLabel(title)
        heading.setStyleSheet("font-weight: 600; padding: 2px;")
        # The heading must not stretch: without this the layout gives it
        # half the panel and the canvas is squeezed into the bottom.
        heading.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(heading)
        layout.addWidget(widget, 1)
        return panel

    def _judgement_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        for spec in RELATIONS:
            button = QPushButton(spec.label)
            button.setToolTip(spec.hint)
            button.clicked.connect(
                lambda _checked=False, relation=spec: self._add_relation(relation)
            )
            row_layout.addWidget(button)
        row_layout.addStretch(1)
        layout.addWidget(row)

        scope_row = QWidget()
        scope_layout = QHBoxLayout(scope_row)
        scope_layout.setContentsMargins(0, 0, 0, 0)
        scope_layout.addWidget(self.scope_label)
        scope_layout.addStretch(1)
        switch = QPushButton("切换作用域")
        switch.setToolTip("identity：对一切合法摆放成立；instance：只对当前这张图成立")
        switch.clicked.connect(self.toggle_scope)
        scope_layout.addWidget(switch)
        layout.addWidget(scope_row)

        layout.addWidget(self.judgements)
        layout.addWidget(self.evidence, 1)
        return panel

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("构造")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        for tool in TOOLS:
            action = QAction(tool.label, self)
            action.setToolTip(tool.hint)
            action.triggered.connect(
                lambda _checked=False, spec=tool: self._arm(spec)
            )
            toolbar.addAction(action)
        toolbar.addSeparator()
        fit_action = QAction("适应窗口", self)
        fit_action.setShortcut(QKeySequence.StandardKey.ZoomIn)
        fit_action.triggered.connect(self.canvas.fit)
        toolbar.addAction(fit_action)

    # -- interaction -------------------------------------------------------

    def _arm(self, tool: ToolSpec) -> None:
        self.canvas.set_tool(tool.op, tool.arg_count)
        self.status.showMessage(f"{tool.label}：{tool.hint}")

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

    def _refresh_steps(self) -> None:
        self.steps.clear()
        figure = self.controller.figure()
        undefined = dict(self.controller.undefined())
        for node_id, node in figure.nodes.items():
            if node.role == "free":
                placement = node.placement or ("?", "?")
                text = f"{node_id}  ({placement[0]}, {placement[1]})"
            else:
                text = f"{node_id} = {node.op}({', '.join(node.args)})"
            item = QListWidgetItem(text)
            if node_id in undefined:
                item.setForeground(Qt.GlobalColor.darkGray)
                item.setToolTip(f"在这个摆放下没有值：{undefined[node_id]}")
            self.steps.addItem(item)
        for relation in figure.relations:
            item = QListWidgetItem(f"断言 {relation.kind}({', '.join(relation.args)})")
            item.setForeground(Qt.GlobalColor.darkBlue)
            self.steps.addItem(item)

    def _refresh_judgements(self) -> None:
        verdicts = self.controller.judge(self._scope)
        self._verdicts = verdicts
        self.judgements.blockSignals(True)
        self.judgements.setRowCount(len(verdicts))
        for row, verdict in enumerate(verdicts):
            self.judgements.setItem(row, 0, QTableWidgetItem(verdict.kind))
            self.judgements.setItem(row, 1, QTableWidgetItem(_verdict_text(verdict.verdict)))
            self.judgements.setItem(row, 2, QTableWidgetItem(verdict.evidence[:120]))
        self.judgements.blockSignals(False)
        if verdicts:
            self.judgements.selectRow(0)
        else:
            self.evidence.clear()

    def _show_evidence(self) -> None:
        """Show the full evidence of the selected relation."""
        rows = self.judgements.selectionModel().selectedRows()
        if not rows:
            return
        index = rows[0].row()
        if index < 0 or index >= len(self._verdicts):
            return
        verdict = self._verdicts[index]
        text = f"{verdict.kind} — {verdict.verdict}\n\n{verdict.evidence}"
        if verdict.witness:
            text += "\n\n反例（一个不满足的摆放）：\n" + "\n".join(
                f"  {key}: {value}" for key, value in sorted(verdict.witness.items())
            )
        self.evidence.setPlainText(text)

    def toggle_scope(self) -> None:
        """Switch between the identity and the instance scope."""
        self._scope = INSTANCE if self._scope == IDENTITY else IDENTITY
        self.scope_label.setText(SCOPE_LABELS[self._scope])
        self._refresh_judgements()


def _verdict_text(verdict: str) -> str:
    return {
        "proved": "成立（proved）",
        "refuted": "不成立（refuted）",
        "supported": "未证（supported）",
        "undecided": "无法判定（undecided）",
    }.get(verdict, verdict)


__all__ = [
    "RELATIONS",
    "TOOLS",
    "ObjectPicker",
    "RelationSpec",
    "StudioWindow",
    "ToolSpec",
]
