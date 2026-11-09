"""The look of the studio.

The figure is the product. A competition figure is black on white, and
this program exists to make one -- so the interface around it stays
quiet: one accent colour, a lot of white, and a clear hierarchy. All the
colour on the screen belongs to the figure.

Everything about the look lives here: the palette, the spacing, the
type scale, the corner radii. The widgets only say *what* they are ("this
is a panel heading"); this module says what that looks like. One place to
change, and the window cannot drift out of style.

The Chinese font matters more than the colours: Qt's default font on a
bare system may not have the glyphs, and then every label comes out as
an empty box.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
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

#: The families to try for the evidence pane, where the expressions are
#: read one symbol at a time and a proportional font makes them lie.
MONO_CANDIDATES: tuple[str, ...] = (
    "Cascadia Mono",
    "Consolas",
    "Sarasa Mono SC",
    "Noto Sans Mono CJK SC",
    "DejaVu Sans Mono",
    "Courier New",
)

#: The point size of the interface font.
FONT_POINT_SIZE = 9.5

#: The point size of the evidence pane.
MONO_POINT_SIZE = 9.0


#: The spacing scale. Every margin, padding and gap in the studio is one
#: of these, so the rhythm of the window is the same everywhere.
SPACE_XS: int = 4
SPACE_SM: int = 8
SPACE_MD: int = 12
SPACE_LG: int = 16

#: The corner radii.
RADIUS: int = 6
RADIUS_LG: int = 10


@dataclass(frozen=True)
class Palette:
    """The colours of the studio.

    One accent, and a lot of near-white. A figure is worth looking at;
    the furniture around it is not.
    """

    #: The window behind everything.
    window: str = "#eef1f5"
    #: A panel: white, so the figure's paper and the panels read as one.
    surface: str = "#ffffff"
    #: The strip at the top of a panel.
    surface_alt: str = "#f6f8fa"
    #: The inside of a text area -- a little sunken, so it reads as a well.
    surface_sunken: str = "#fbfcfd"
    #: The hairline that separates things.
    border: str = "#dde3ea"
    #: A hairline that has to be seen: the edge of the paper.
    border_strong: str = "#c9d2dc"
    #: The text.
    text: str = "#1c2833"
    #: The text that is not the point.
    text_muted: str = "#6c7b8b"
    #: The colour of a drawn icon: quiet enough to sit next to a word,
    #: dark enough to be seen.
    icon: str = "#56687c"
    #: The one accent colour.
    accent: str = "#2f6fb5"
    accent_hover: str = "#3d84cd"
    #: The accent, barely there -- a selected row, an armed tool.
    accent_soft: str = "#e6f0fa"
    accent_border: str = "#b5d2ef"
    #: The three answers a judgement can have.
    ok: str = "#1a7f57"
    danger: str = "#bf3b2e"
    warn: str = "#9c6b16"
    #: The grid on the paper.
    grid: str = "#f0f3f7"
    grid_axis: str = "#dfe4ea"

    def stylesheet(self) -> str:
        """The whole studio, as one stylesheet.

        Widgets are named rather than restyled one by one: a panel
        heading is a heading everywhere, and says so here.
        """
        return f"""
        QMainWindow, QDialog {{
            background: {self.window};
            color: {self.text};
        }}

        /* -- the frame around a panel ---------------------------------- */
        QFrame#card {{
            background: {self.surface};
            border: 1px solid {self.border};
            border-radius: {RADIUS_LG}px;
        }}
        QFrame#panelHeader {{
            background: {self.surface_alt};
            border: none;
            border-bottom: 1px solid {self.border};
            border-top-left-radius: {RADIUS_LG - 1}px;
            border-top-right-radius: {RADIUS_LG - 1}px;
        }}
        QFrame#accentRule {{
            background: {self.accent};
            border: none;
            border-radius: 1px;
        }}
        QLabel#panelTitle {{
            color: {self.text};
            font-weight: 600;
            font-size: 10pt;
        }}
        QLabel#panelNote {{
            color: {self.text_muted};
        }}
        QLabel {{
            color: {self.text};
        }}

        /* -- the toolbar ------------------------------------------------ */
        QToolBar {{
            background: {self.surface};
            border: none;
            border-bottom: 1px solid {self.border};
            padding: {SPACE_SM}px {SPACE_MD}px;
            spacing: {SPACE_XS}px;
        }}
        QToolBar::separator {{
            background: {self.border};
            width: 1px;
            margin: 4px {SPACE_SM}px;
        }}
        QToolButton {{
            padding: {SPACE_SM - 2}px {SPACE_MD}px;
            border: 1px solid transparent;
            border-radius: {RADIUS}px;
            color: {self.text};
            background: transparent;
        }}
        QToolButton:hover {{
            background: {self.surface_alt};
            border-color: {self.border};
        }}
        QToolButton:pressed {{
            background: {self.accent_soft};
        }}
        QToolButton:checked {{
            background: {self.accent_soft};
            border-color: {self.accent_border};
            color: {self.accent};
            font-weight: 600;
        }}
        QToolButton::menu-indicator {{
            subcontrol-position: right center;
            right: 2px;
            width: 14px;
        }}

        /* -- buttons ---------------------------------------------------- */
        QPushButton {{
            padding: {SPACE_SM - 2}px {SPACE_MD}px;
            border: 1px solid {self.border};
            border-radius: {RADIUS}px;
            background: {self.surface};
            color: {self.text};
        }}
        QPushButton:hover {{
            border-color: {self.border_strong};
            background: {self.surface_alt};
        }}
        QPushButton:pressed {{
            background: {self.accent_soft};
            border-color: {self.accent_border};
        }}
        QPushButton:checked {{
            background: {self.accent_soft};
            border-color: {self.accent_border};
            color: {self.accent};
            font-weight: 600;
        }}

        /* -- the list of construction steps ------------------------------ */
        QListWidget {{
            background: {self.surface};
            border: none;
            outline: none;
            padding: {SPACE_XS}px;
        }}
        QListWidget::item {{
            padding: 5px {SPACE_SM}px;
            border-radius: {RADIUS}px;
            color: {self.text};
        }}
        QListWidget::item:hover {{
            background: {self.surface_alt};
        }}
        QListWidget::item:selected {{
            background: {self.accent_soft};
            color: {self.text};
        }}

        /* -- the table of judgements ------------------------------------- */
        QTableWidget {{
            background: {self.surface};
            border: none;
            gridline-color: transparent;
            alternate-background-color: {self.surface_sunken};
            outline: none;
        }}
        QTableWidget::item {{
            padding: 5px {SPACE_SM}px;
            border-bottom: 1px solid {self.border};
        }}
        QTableWidget::item:selected {{
            background: {self.accent_soft};
        }}
        QHeaderView::section {{
            background: {self.surface_alt};
            color: {self.text_muted};
            padding: 6px {SPACE_SM}px;
            border: none;
            border-bottom: 1px solid {self.border};
            font-weight: 600;
        }}

        /* -- the evidence well ------------------------------------------- */
        QPlainTextEdit {{
            background: {self.surface_sunken};
            border: 1px solid {self.border};
            border-radius: {RADIUS}px;
            padding: {SPACE_SM}px;
            color: {self.text};
            selection-background-color: {self.accent_soft};
            selection-color: {self.text};
        }}

        QLineEdit, QComboBox, QSpinBox {{
            padding: {SPACE_SM - 2}px {SPACE_SM}px;
            border: 1px solid {self.border};
            border-radius: {RADIUS}px;
            background: {self.surface};
            color: {self.text};
        }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
            border-color: {self.accent_border};
        }}

        /* -- the chrome around it ---------------------------------------- */
        QMenuBar {{
            background: {self.surface};
            border-bottom: 1px solid {self.border};
            padding: 2px {SPACE_SM}px;
        }}
        QMenuBar::item {{
            padding: 5px {SPACE_MD}px;
            border-radius: {RADIUS}px;
            background: transparent;
            color: {self.text};
        }}
        QMenuBar::item:selected {{
            background: {self.accent_soft};
            color: {self.accent};
        }}
        QMenu {{
            background: {self.surface};
            border: 1px solid {self.border};
            border-radius: {RADIUS}px;
            padding: {SPACE_XS}px;
        }}
        QMenu::item {{
            padding: 6px 28px 6px {SPACE_MD}px;
            border-radius: {RADIUS}px;
            color: {self.text};
        }}
        QMenu::item:selected {{
            background: {self.accent_soft};
            color: {self.accent};
        }}
        QMenu::separator {{
            height: 1px;
            background: {self.border};
            margin: {SPACE_XS}px {SPACE_SM}px;
        }}
        QStatusBar {{
            background: {self.surface};
            border-top: 1px solid {self.border};
            color: {self.text_muted};
        }}
        QStatusBar::item {{
            border: none;
        }}
        QSplitter::handle {{
            background: transparent;
        }}
        QSplitter::handle:hover {{
            background: {self.accent_border};
        }}

        /* -- the scrollbars ---------------------------------------------- */
        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            margin: 0;
            border: none;
        }}
        QScrollBar::handle:vertical {{
            background: {self.border_strong};
            border-radius: 5px;
            min-height: 32px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {self.text_muted};
        }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 10px;
            margin: 0;
            border: none;
        }}
        QScrollBar::handle:horizontal {{
            background: {self.border_strong};
            border-radius: 5px;
            min-width: 32px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {self.text_muted};
        }}
        QScrollBar::add-line, QScrollBar::sub-line {{
            width: 0;
            height: 0;
        }}
        QScrollBar::add-page, QScrollBar::sub-page {{
            background: transparent;
        }}
        """


#: The palette of the studio.
PALETTE = Palette()


def pick_font(candidates: tuple[str, ...] = FONT_CANDIDATES, size: float = FONT_POINT_SIZE) -> QFont:
    """A font that can draw Chinese, if the system has one."""
    available = set(QFontDatabase.families())
    for family in candidates:
        if family in available:
            font = QFont(family)
            font.setPointSizeF(size)
            return font
    font = QFont()
    font.setPointSizeF(size)
    return font


def ui_font() -> QFont:
    """The font of the interface."""
    return pick_font()


def mono_font() -> QFont:
    """The font of the evidence pane.

    The evidence is read symbol by symbol -- a polynomial, a
    substitution -- and in a proportional font the minus sign and the
    hyphen are the same width and the reader stops trusting the layout.
    """
    return pick_font(MONO_CANDIDATES, MONO_POINT_SIZE)


def palette() -> QPalette:
    """The palette of the studio.

    The stylesheet paints most of the window, but not everything: a
    table cell that is coloured by what it says (a verdict) needs the
    palette to stay out of the way.
    """
    colours = QPalette()
    colours.setColor(QPalette.ColorRole.Window, QColor(PALETTE.window))
    colours.setColor(QPalette.ColorRole.WindowText, QColor(PALETTE.text))
    colours.setColor(QPalette.ColorRole.Base, QColor(PALETTE.surface))
    colours.setColor(QPalette.ColorRole.AlternateBase, QColor(PALETTE.surface_sunken))
    colours.setColor(QPalette.ColorRole.Text, QColor(PALETTE.text))
    colours.setColor(QPalette.ColorRole.Button, QColor(PALETTE.surface))
    colours.setColor(QPalette.ColorRole.ButtonText, QColor(PALETTE.text))
    colours.setColor(QPalette.ColorRole.ToolTipBase, QColor(PALETTE.surface))
    colours.setColor(QPalette.ColorRole.ToolTipText, QColor(PALETTE.text))
    colours.setColor(QPalette.ColorRole.Highlight, QColor(PALETTE.accent_soft))
    colours.setColor(QPalette.ColorRole.HighlightedText, QColor(PALETTE.text))
    colours.setColor(QPalette.ColorRole.PlaceholderText, QColor(PALETTE.text_muted))
    return colours


def apply_theme(app: QApplication) -> None:
    """Give the application its font and its colours."""
    app.setFont(ui_font())
    app.setPalette(palette())
    app.setStyleSheet(PALETTE.stylesheet())
