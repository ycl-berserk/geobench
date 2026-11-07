"""The desktop studio: the window, the canvas and the controller behind them.

The application is one Python process: the kernel runs inside it, so
clicking a point is a function call rather than a network request
(decision D16).
"""

from __future__ import annotations

__all__ = ["build_window", "main"]


def __getattr__(name: str) -> object:
    """Import the Qt parts lazily, so the package can be imported headless."""
    if name == "build_window":
        from geobench.app.main import build_window

        return build_window
    if name == "main":
        from geobench.app.main import main

        return main
    raise AttributeError(name)
