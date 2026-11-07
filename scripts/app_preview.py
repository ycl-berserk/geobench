"""Open the studio window, build a figure in it, and take a picture.

    python scripts/app_preview.py

The picture goes to examples/studio-window.png. It is how the window is
reviewed without a human sitting in front of it.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from geobench.app.controller import StudioController  # noqa: E402
from geobench.app.theme import apply_theme  # noqa: E402
from geobench.app.window import StudioWindow  # noqa: E402


def build_figure(controller: StudioController) -> None:
    """The same problem the demo scripts use."""
    controller.add_free_point(0, 0, "A")
    controller.add_free_point(6, 0, "B")
    controller.add_free_point(2, 4, "C")
    controller.construct("segment.free", ["B", "C"], "BC")
    controller.construct("point.midpoint", ["A", "B"], "M")
    controller.construct("point.foot", ["A", "BC"], "D")
    controller.construct("point.circumcenter", ["A", "B", "C"], "O")
    controller.construct("circle.through", ["A", "B", "C"], "c1")
    controller.add_relation("collinear", ["A", "M", "B"])
    controller.add_relation("equal_length", ["O", "A", "O", "B"])
    controller.add_relation("collinear", ["A", "D", "C"])


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    apply_theme(app)
    controller = StudioController()
    window = StudioWindow(controller)
    window.resize(1180, 720)
    window.show()
    app.processEvents()

    build_figure(controller)
    for _ in range(5):
        app.processEvents()
    window.refresh()
    window.steps.scrollToTop()
    for _ in range(5):
        app.processEvents()

    out = ROOT / "examples" / "studio-window.png"
    out.parent.mkdir(exist_ok=True)
    window.grab().save(str(out))
    print(f"window picture: {out.relative_to(ROOT)}")

    print("\n== 判定 ==")
    for verdict in controller.judge():
        print(f"  {verdict.kind:<14} -> {verdict.verdict}")
    print("\n== 步骤 ==")
    for node_id, node in controller.figure().nodes.items():
        print(f"  {node_id:<4} {node.op or 'free':<22} {node.args}")


if __name__ == "__main__":
    main()
