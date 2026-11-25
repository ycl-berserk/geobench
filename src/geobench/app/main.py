"""The studio application.

    geobench-app

opens the window. The kernel runs in the same process, so clicking a
point is a function call, not a network request (decision D16).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from geobench import __version__
from geobench.app.controller import StudioController
from geobench.app.theme import (
    DEFAULT_UI_SIZE,
    UI_SIZES,
    apply_theme,
    set_ui_size,
)
from geobench.app.window import StudioWindow


def _icon_path() -> Path:
    """The window icon, in a checkout and in a frozen build."""
    base = Path(
        getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3] / "packaging")
    )
    return base / "icon.png"


def build_window(controller: StudioController | None = None) -> StudioWindow:
    """The studio window, with a controller of its own if none is given."""
    return StudioWindow(controller or StudioController())


def main() -> int:
    """Entry point of the ``geobench-app`` command."""
    smoke = "--smoke-test" in sys.argv[1:]
    if smoke:
        # The packaging job runs on a machine with no interactive desktop.
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication(sys.argv)
    app.setApplicationName("geobench")
    app.setApplicationVersion(__version__)
    icon = _icon_path()
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    chosen = QSettings("geobench", "studio").value("ui/size", DEFAULT_UI_SIZE)
    if isinstance(chosen, str) and chosen in UI_SIZES:
        set_ui_size(chosen)
    apply_theme(app)
    window = build_window()
    if smoke:
        # The AI skill is read from data files; a packaged build that
        # forgot them must fail here, not when a teacher clicks AI.
        from geobench.ai import EXAMPLES_PATH, PROMPT_PATH, STANDARDS_PATH

        if not all(
            path.exists()
            for path in (PROMPT_PATH, STANDARDS_PATH, EXAMPLES_PATH)
        ):
            return 2
        window.show()
        app.processEvents()
        window.close()
        return 0
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
