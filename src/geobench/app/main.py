"""The studio application.

    geobench-app

opens the window. The kernel runs in the same process, so clicking a
point is a function call, not a network request (decision D16).
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from types import TracebackType

from PySide6.QtCore import QSettings
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from geobench import __version__
from geobench.app.controller import StudioController
from geobench.app.theme import (
    DEFAULT_UI_SIZE,
    UI_SIZES,
    apply_theme,
    set_ui_size,
)
from geobench.app.window import StudioWindow, data_dir


def _icon_path() -> Path:
    """The window icon, in a checkout and in a frozen build."""
    base = Path(
        getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3] / "packaging")
    )
    return base / "icon.png"


def build_window(controller: StudioController | None = None) -> StudioWindow:
    """The studio window, with a controller of its own if none is given."""
    return StudioWindow(controller or StudioController())


def _setup_logging() -> Path:
    """Keep a record of what went wrong, where the teacher can send it."""
    path = data_dir() / "geobench.log"
    logging.basicConfig(
        filename=path,
        level=logging.INFO,
        encoding="utf-8",
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    def hook(
        exc_type: type[BaseException],
        exc: BaseException,
        traceback: TracebackType | None,
    ) -> None:
        logging.critical(
            "uncaught exception", exc_info=(exc_type, exc, traceback)
        )
        sys.__excepthook__(exc_type, exc, traceback)

    sys.excepthook = hook
    return path


def _offer_recovery(window: StudioWindow) -> None:
    """After a crash, the autosaved figure is still there; ask about it."""
    if not window.has_recovery():
        return
    answer = QMessageBox.question(
        window,
        "恢复上次的图形",
        "上次没有正常退出，自动保存的图形还在。\n\n要恢复吗？",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
    )
    if answer == QMessageBox.StandardButton.Yes:
        window.restore_recovery()
    else:
        window.discard_recovery()


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
    if not smoke:
        _setup_logging()
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
    _offer_recovery(window)
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
