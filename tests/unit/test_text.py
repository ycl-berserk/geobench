"""Notes on the paper, and labels that are turned off.

A figure is not only strokes: a competition statement often has a line
of prose beside it.  These tests cover the text object, its round trip,
and the separate question of whether an object's *name* is drawn.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from geobench.dsl import parse_dsl, to_dsl
from geobench.evaluate import evaluate_figure
from geobench.ggb import import_ggb
from geobench.operators import register_builtins
from geobench.primitives import PointPrimitive, TextPrimitive, figure_primitives
from geobench.registry import OperatorRegistry
from geobench.style import COMPETITION


@pytest.fixture()
def registry() -> OperatorRegistry:
    reg = OperatorRegistry()
    register_builtins(reg)
    return reg


def test_a_text_note_keeps_its_lines_and_position(
    registry: OperatorRegistry,
) -> None:
    figure = parse_dsl(
        '点 A(0,0)\n文本 note("第一行\\n第二行", -1.5, 2.5)'
    )
    evaluate_figure(figure, registry)
    primitives = figure_primitives(figure, COMPETITION)
    note = next(p for p in primitives if isinstance(p, TextPrimitive))
    assert note.text == "第一行\n第二行"
    assert (note.x, note.y) == (-1.5, 2.5)

    again = parse_dsl(to_dsl(figure))
    evaluate_figure(again, registry)
    assert again.nodes["note"].args[0] == "第一行\n第二行"


def test_a_label_can_be_hidden_without_hiding_the_point(
    registry: OperatorRegistry,
) -> None:
    figure = parse_dsl("点 A(0,0)\n隐藏标签 A")
    evaluate_figure(figure, registry)
    primitives = figure_primitives(figure, COMPETITION)
    point = next(p for p in primitives if isinstance(p, PointPrimitive))
    assert point.label == ""


def test_a_geogebra_note_is_imported(tmp_path: Path) -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
    <geogebra format="5.0"><construction>
      <element type="point" label="A"><coords x="0" y="0" z="1"/></element>
      <expression label="text1" exp="&quot;first line&#xa;second line&quot;"/>
      <element type="text" label="text1">
        <show object="true" label="false"/>
        <startPoint x="-3" y="-4" z="1"/>
      </element>
    </construction></geogebra>"""
    path = tmp_path / "note.ggb"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("geogebra.xml", xml)
    result = import_ggb(path)
    lines = result.dsl.splitlines()
    assert any(line.startswith('文本 text1("first line\\nsecond line"') for line in lines)
    figure = parse_dsl(result.dsl)
    assert figure.nodes["text1"].args[0] == "first line\nsecond line"
    assert figure.nodes["text1"].placement == ("-3", "-4")
