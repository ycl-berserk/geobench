"""A proved claim is drawn where the teacher looks, not only listed.

The table says equal lengths and right angles; the figure gets the tick
marks and the little square.  These tests check the wiring: a proved
verdict becomes a mark, a refuted one does not, and the canvas can draw
the marks without falling over.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
except ImportError as exc:  # pragma: no cover - depends on the machine
    pytest.skip(f"Qt is not usable on this machine: {exc}", allow_module_level=True)

from geobench.app.controller import StudioController
from geobench.app.window import StudioWindow
from geobench.judges import IDENTITY, Verdict

SOURCE = """点 A(0, 0) B(4, 0) C(1, 3)
M = 中点(A, B)
f = 直线(A, B)
p = 垂直(C, f)
断言 相等(A, M, M, B)
断言 垂直(f, p)
"""


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def window(app: QApplication, tmp_path, monkeypatch) -> StudioWindow:
    monkeypatch.setenv("GEOBENCH_DATA_DIR", str(tmp_path / "data"))
    controller = StudioController()
    controller.load_text(SOURCE)
    return StudioWindow(controller)


def test_a_proved_claim_becomes_a_mark(window: StudioWindow) -> None:
    verdicts = [
        Verdict(kind="equal_length", verdict="proved", scope=IDENTITY),
        Verdict(kind="perpendicular", verdict="proved", scope=IDENTITY),
    ]
    window._on_verdicts(0, verdicts)
    assert window.canvas._proof_marks == [
        ("equal_length", ("A", "M", "M", "B")),
        ("perpendicular", ("f", "p")),
    ]


def test_a_refuted_claim_is_not_drawn(window: StudioWindow) -> None:
    verdicts = [
        Verdict(kind="equal_length", verdict="refuted", scope=IDENTITY),
        Verdict(kind="perpendicular", verdict="refuted", scope=IDENTITY),
    ]
    window._on_verdicts(0, verdicts)
    assert window.canvas._proof_marks == []


def test_the_canvas_draws_the_marks(window: StudioWindow) -> None:
    window._on_verdicts(
        0,
        [
            Verdict(kind="equal_length", verdict="proved", scope=IDENTITY),
            Verdict(kind="perpendicular", verdict="proved", scope=IDENTITY),
        ],
    )
    image = QImage(640, 480, QImage.Format.Format_ARGB32)
    image.fill(0xFFFFFFFF)
    window.canvas.render(image)
    assert not image.isNull()
