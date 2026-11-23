"""The parameter shelf: drag a number, the figure follows.

The arithmetic lives in the kernel (tests/unit/test_parameters.py); this
is the thing a hand touches.  While the slider moves, only the picture
is recomputed; on release the exact layer is rebuilt, because the
constant is part of what the construction *is*.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
except ImportError as exc:  # pragma: no cover - depends on the machine
    pytest.skip(f"Qt is not usable on this machine: {exc}", allow_module_level=True)

from geobench.app.controller import StudioController
from geobench.app.window import StudioWindow

SOURCE = "数 a = 2.5\n点 P(0,0)\nw = 圆(P, a)\n"


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _window(app: QApplication) -> StudioWindow:
    controller = StudioController()
    controller.load_text(SOURCE)
    window = StudioWindow(controller)
    window.show()
    app.processEvents()
    return window


def _radius_sq(controller: StudioController) -> float:
    return float(controller.figure().nodes["w"].cache["numeric"]["circle"][2])


def test_a_free_number_gets_a_slider(app: QApplication) -> None:
    window = _window(app)
    assert "a" in window._parameter_rows
    slider, spin = window._parameter_rows["a"]
    assert slider.value() == 250
    assert spin.value() == pytest.approx(2.5)
    assert not window._parameters.isHidden()
    window.close()


def test_dragging_the_slider_redraws_the_picture(app: QApplication) -> None:
    window = _window(app)
    slider, spin = window._parameter_rows["a"]
    slider.setValue(400)
    app.processEvents()

    assert window.controller.figure().nodes["a"].args == ["4"]
    assert spin.value() == pytest.approx(4.0)
    assert _radius_sq(window.controller) == pytest.approx(16.0)
    window.close()


def test_the_exact_layer_arrives_after_the_drag(app: QApplication) -> None:
    window = _window(app)
    slider, _spin = window._parameter_rows["a"]
    slider.setValue(300)
    app.processEvents()
    window._settle_number()
    window.controller.evaluate_exact()
    circle = window.controller.figure().nodes["w"]
    assert str(circle.cache["circle"][2]) == "9"
    window.close()


def test_typing_a_number_is_one_step(app: QApplication) -> None:
    window = _window(app)
    _slider, spin = window._parameter_rows["a"]
    spin.setValue(3.5)
    app.processEvents()

    assert window.controller.figure().nodes["a"].args == ["7/2"]
    assert _radius_sq(window.controller) == pytest.approx(12.25)

    assert window.controller.undo()
    app.processEvents()
    assert window.controller.figure().nodes["a"].args == ["5/2"]
    assert _radius_sq(window.controller) == pytest.approx(6.25)
    window.close()


def test_a_slider_drag_is_one_undo(app: QApplication) -> None:
    window = _window(app)
    slider, _spin = window._parameter_rows["a"]
    slider.setValue(400)
    app.processEvents()
    window._settle_number()
    app.processEvents()

    assert window.controller.undo()
    app.processEvents()
    assert window.controller.figure().nodes["a"].args == ["5/2"]
    window.close()


def test_the_shelf_is_hidden_when_there_is_no_number(app: QApplication) -> None:
    controller = StudioController()
    controller.load_text("点 A(0,0) B(4,0)\nAB = 线段(A, B)\n")
    window = StudioWindow(controller)
    window.show()
    app.processEvents()
    assert window._parameters.isHidden()
    window.close()


def test_the_step_says_the_value(app: QApplication) -> None:
    window = _window(app)
    texts = [window.steps.item(row).text() for row in range(window.steps.count())]
    assert any("a = 2.5" in text for text in texts), texts
    window.close()
