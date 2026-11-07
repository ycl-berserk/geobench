"""The studio application.

    geobench-app

opens the window. The kernel runs in the same process, so clicking a
point is a function call, not a network request (decision D16).
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from geobench import __version__
from geobench.app.controller import StudioController
from geobench.app.theme import apply_theme
from geobench.app.window import StudioWindow


def build_window(controller: StudioController | None = None) -> StudioWindow:
    """The studio window, with a controller of its own if none is given."""
    return StudioWindow(controller or StudioController())


def main() -> int:
    """Entry point of the ``geobench-app`` command."""
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication(sys.argv)
    app.setApplicationName("geobench")
    app.setApplicationVersion(__version__)
    apply_theme(app)
    window = build_window()
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
