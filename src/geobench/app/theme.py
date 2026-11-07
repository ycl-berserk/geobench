"""The look of the studio.

Small on purpose: a competition figure is black on white and the window
should not compete with it. What matters here is the **font** -- the
interface is in Chinese, and Qt's default font on a bare system may not
have the glyphs, in which case every label comes out as an empty box.
"""

from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

#: The families to try, in order. The first one the system has wins.
FONT_CANDIDATES: tuple[str, ...] = (
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "PingFang SC",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "SimHei",
    "SimSun",
    "WenQuanYi Micro Hei",
)

#: The point size of the interface font.
FONT_POINT_SIZE = 9


def pick_font() -> QFont:
    """A font that can draw Chinese, if the system has one."""
    available = set(QFontDatabase.families())
    for family in FONT_CANDIDATES:
        if family in available:
            font = QFont(family)
            font.setPointSize(FONT_POINT_SIZE)
            return font
    return QFont()


def apply_theme(app: QApplication) -> None:
    """Give the application its font and its colours."""
    app.setFont(pick_font())
    app.setStyleSheet(
        """
        QMainWindow { background: #fbfbfa; color: #1f2933; }
        QToolBar { border: 0; padding: 4px; spacing: 2px; }
        QToolButton { padding: 4px 10px; border-radius: 3px; color: #1f2933; }
        QToolButton:hover { background: #ececeb; }
        QToolButton:checked { background: #dfe6ee; }
        QTableWidget { background: white; gridline-color: #e6e6e4; color: #1f2933; }
        QHeaderView::section { background: #f2f2f0; padding: 4px; border: 0; color: #1f2933; }
        QListWidget { background: white; border: 1px solid #e2e2e0; color: #1f2933; }
        QPlainTextEdit { background: white; color: #1f2933; border: 1px solid #e2e2e0; }
        QPushButton { padding: 4px 10px; color: #1f2933; }
        QLabel { color: #1f2933; }
        """
    )
