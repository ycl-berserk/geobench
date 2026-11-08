"""Saving and loading a figure.

A figure that cannot be saved is a figure that does not exist, as far
as the teacher is concerned: they close the window and the work is
gone. The file is the DSL, so what is written is something a person
can read and edit.
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
from geobench.dsl.errors import DSLParseError


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def controller() -> StudioController:
    return StudioController()


def _figure(controller: StudioController) -> None:
    controller.add_free_point(0, 0, "A")
    controller.add_free_point(6, 0, "B")
    controller.add_free_point(2, 4, "C")
    controller.construct("point.midpoint", ["A", "B"])
    controller.construct("point.circumcenter", ["A", "B", "C"])
    controller.add_relation("collinear", ["A", "M", "B"])


def test_a_figure_is_written_as_text_a_person_can_read(controller: StudioController) -> None:
    _figure(controller)
    text = controller.to_text()
    assert "点 A(0,0)" in text
    assert "中点(A, B)" in text
    assert "断言 共线(A, M, B)" in text


def test_a_figure_survives_being_written_and_read_back(
    controller: StudioController, tmp_path
) -> None:
    _figure(controller)
    path = tmp_path / "figure.geobench"
    path.write_text(controller.to_text(), encoding="utf-8")

    other = StudioController()
    other.load_text(path.read_text(encoding="utf-8"))

    before = controller.figure()
    after = other.figure()
    assert list(after.nodes) == list(before.nodes)
    assert [relation.kind for relation in after.relations] == [
        relation.kind for relation in before.relations
    ]
    # The names survive: the midpoint is still called M.
    assert "M" in after.nodes
    assert "O" in after.nodes
    # And the positions are the same.
    assert other.point_positions()["A"] == pytest.approx((0.0, 0.0))
    assert other.point_positions()["B"] == pytest.approx((6.0, 0.0))


def test_a_file_that_makes_no_sense_is_refused_and_changes_nothing(
    controller: StudioController, tmp_path
) -> None:
    _figure(controller)
    before = list(controller.figure().nodes)

    path = tmp_path / "broken.geobench"
    path.write_text("点 A(0, 0)\nX = 不存在的命令(A)\n", encoding="utf-8")
    with pytest.raises(DSLParseError):
        controller.load_text(path.read_text(encoding="utf-8"))

    assert list(controller.figure().nodes) == before
