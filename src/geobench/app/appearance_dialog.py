"""One dialog for everything about how one object looks.

The context menu has quick actions (a colour, a width), and those are
right for a single change.  But "make this the key point -- red, bigger,
label on the right" is *one* intention, and it should be one dialog and
one undo step, not three menu visits.

The dialog edits appearance only.  It never touches the construction.
"""

from __future__ import annotations

from typing import NotRequired, TypedDict

from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from geobench.app.theme import button_words
from geobench.model import Node
from geobench.style import (
    COLOR_CHOICES,
    LABEL_DIRECTIONS,
    LINE_WIDTHS,
    POINT_SIZES,
)


class AppearanceValues(TypedDict):
    """What the dialog hands to the controller."""

    color: str
    line_width: float | None
    label: str
    point_size: NotRequired[float | None]
    label_pos: NotRequired[str | None]


class AppearanceDialog(QDialog):
    """Colour, width, size, label text and label position, in one place."""

    def __init__(self, parent: QWidget, node: Node) -> None:
        super().__init__(parent)
        self._node = node
        self._color = node.style.color or "#000000"
        self._width = node.style.line_width
        self._size = node.style.point_size
        self._position = node.style.label_pos

        self.setWindowTitle(f"{node.id} 的属性")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        form = QFormLayout()
        form.setSpacing(10)

        self.label_edit = QLineEdit(node.style.label or node.label or node.id)
        self.label_edit.setToolTip("图上显示的名字；留空就用构造里的名字")
        form.addRow("标签", self.label_edit)

        form.addRow("颜色", self._color_row())

        self.width_box = QComboBox()
        self.width_box.addItem("默认", None)
        for name, value in LINE_WIDTHS.items():
            self.width_box.addItem(f"{name}（{value:g}）", value)
        if self._width is not None and self._width not in LINE_WIDTHS.values():
            self.width_box.addItem(f"{self._width:g}", self._width)
        self._select(self.width_box, self._width)
        form.addRow("线宽", self.width_box)

        if node.kind == "point":
            self.size_box = QComboBox()
            self.size_box.addItem("默认", None)
            for name, value in POINT_SIZES.items():
                self.size_box.addItem(name, value)
            if self._size is not None and self._size not in POINT_SIZES.values():
                self.size_box.addItem(f"{self._size:g}", self._size)
            self._select(self.size_box, self._size)
            form.addRow("点大小", self.size_box)

            self.position_box = QComboBox()
            self.position_box.addItem("自动", None)
            for direction in LABEL_DIRECTIONS:
                self.position_box.addItem(direction, direction)
            self._select(self.position_box, self._position)
            form.addRow("标签位置", self.position_box)

        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        button_words(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _color_row(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        group = QButtonGroup(self)
        group.setExclusive(True)

        default = QPushButton("默认")
        default.setCheckable(True)
        default.setToolTip("跟整张图的颜色走")
        default.setChecked(self._color in ("", "#000000"))
        default.clicked.connect(lambda: self._pick("#000000"))
        group.addButton(default)
        layout.addWidget(default)

        for name, code in COLOR_CHOICES:
            swatch = QPushButton()
            swatch.setFixedSize(24, 24)
            swatch.setCheckable(True)
            swatch.setToolTip(name)
            swatch.setStyleSheet(
                f"QPushButton {{ background: {code}; border: 1px solid #b9c3cd;"
                " border-radius: 4px; }"
                " QPushButton:checked { border: 2px solid #2f6fb5; }"
            )
            swatch.setChecked(self._color == code)
            swatch.clicked.connect(lambda _checked=False, code=code: self._pick(code))
            group.addButton(swatch)
            layout.addWidget(swatch)
        layout.addStretch(1)
        return row

    def _pick(self, code: str) -> None:
        self._color = code

    @staticmethod
    def _select(box: QComboBox, value: object) -> None:
        index = box.findData(value)
        if index >= 0:
            box.setCurrentIndex(index)

    def values(self) -> AppearanceValues:
        """What the dialog settled on, ready for the controller."""
        result: AppearanceValues = {
            "color": self._color,
            "line_width": self.width_box.currentData(),
            "label": self.label_edit.text().strip(),
        }
        if self._node.kind == "point":
            result["point_size"] = self.size_box.currentData()
            result["label_pos"] = self.position_box.currentData()
        return result
