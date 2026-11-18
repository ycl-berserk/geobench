"""Reading a `.ggb`: the translation, and the things it cannot carry.

The test builds its own tiny `.ggb` rather than shipping a teacher's
file: a `.ggb` is a ZIP with `geogebra.xml` inside, so a test can make
one in a few lines, and the fixture stays readable in the diff.

What is checked is the *translation*: every construction becomes the DSL
line for the same construction, and the three places where the two
languages disagree are handled rather than approximated.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from geobench.dsl import parse_dsl
from geobench.evaluate import evaluate_figure, evaluate_numeric
from geobench.ggb import import_ggb
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry

XML = """<?xml version="1.0" encoding="utf-8"?>
<geogebra format="5.0">
  <construction>
    <element type="point" label="A"><coords x="0" y="0" z="1"/></element>
    <element type="point" label="B"><coords x="4" y="0" z="1"/></element>
    <element type="point" label="C"><coords x="1" y="3" z="1"/></element>
    <command name="Segment"><input a0="A" a1="B"/><output a0="f"/></command>
    <command name="Midpoint"><input a0="A" a1="B"/><output a0="M"/></command>
    <command name="外心"><input a0="A" a1="B" a2="C"/><output a0="O"/></command>
    <command name="Circle"><input a0="A" a1="B" a2="C"/><output a0="c"/></command>
    <command name="Intersect"><input a0="c" a1="f" a2="1"/><output a0="P"/></command>
    <command name="Tangent"><input a0="B" a1="c"/><output a0="k"/><output a1="n"/></command>
    <command name="LineBisector"><input a0="f"/><output a0="i"/></command>
    <command name="OrthogonalLine"><input a0="A" a1="f"/><output a0="p"/></command>
    <command name="Rotate"><input a0="A" a1="90" a2="B"/><output a0="A_1"/></command>
  </construction>
</geogebra>
"""


def _write_ggb(path: Path, xml: str = XML) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("geogebra.xml", xml)
    return path


@pytest.fixture(scope="module")
def registry() -> OperatorRegistry:
    reg = OperatorRegistry()
    register_builtins(reg)
    return reg


def test_the_free_points_come_first(tmp_path: Path) -> None:
    result = import_ggb(_write_ggb(tmp_path / "figure.ggb"))
    first = result.dsl.splitlines()[0]
    assert first.startswith("点 ")
    assert "A(0, 0)" in first


def test_a_command_becomes_the_line_for_the_same_construction(tmp_path: Path) -> None:
    result = import_ggb(_write_ggb(tmp_path / "figure.ggb"))
    lines = result.dsl.splitlines()
    assert "f = 线段(A, B)" in lines
    assert "M = 中点(A, B)" in lines
    assert "O = 外心(A, B, C)" in lines
    assert "c = 外接圆(A, B, C)" in lines
    assert "p = 垂直(A, f)" in lines


def test_geogebra_counts_intersections_from_one(tmp_path: Path) -> None:
    """``Intersect(c, f, 1)`` is ``交点(c, f, 0)``: the first one."""
    result = import_ggb(_write_ggb(tmp_path / "figure.ggb"))
    assert "P = 交点(f, c, 0)" in result.dsl.splitlines()


def test_a_line_bisector_is_written_with_its_two_ends(tmp_path: Path) -> None:
    """GeoGebra takes the segment; the DSL takes the two points."""
    result = import_ggb(_write_ggb(tmp_path / "figure.ggb"))
    assert "i = 中垂线(A, B)" in result.dsl.splitlines()


def test_two_answers_are_reported_not_dropped(tmp_path: Path) -> None:
    """GeoGebra's tangent gives two lines; the DSL gives one."""
    result = import_ggb(_write_ggb(tmp_path / "figure.ggb"))
    assert "k = 切线(B, c)" in result.dsl.splitlines()
    assert "n = 切线(B, c)" not in result.dsl.splitlines()
    assert any("Tangent" in item and "2" in item for item in result.skipped)


def test_a_subscript_is_renamed_and_said_so(tmp_path: Path) -> None:
    result = import_ggb(_write_ggb(tmp_path / "figure.ggb"))
    assert "A1 = 旋转(A, 90, B)" in result.dsl.splitlines()
    assert result.renames["A_1"] == "A1"


def test_the_imported_figure_is_a_figure(tmp_path: Path, registry: OperatorRegistry) -> None:
    """The point of the exercise: the kernel accepts what comes out."""
    result = import_ggb(_write_ggb(tmp_path / "figure.ggb"))
    figure = parse_dsl(result.dsl)
    evaluate_figure(figure, registry)
    evaluate_numeric(figure)
    assert "P" in figure.nodes
    assert figure.nodes["M"].kind == "point"


def test_a_file_that_is_not_a_geogebra_file_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "not-a-figure.ggb"
    path.write_text("hello", encoding="utf-8")
    with pytest.raises(Exception) as failure:
        import_ggb(path)
    assert "GeoGebra" in str(failure.value)


def test_a_zip_without_the_xml_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "empty.ggb"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("something.txt", "x")
    with pytest.raises(Exception) as failure:
        import_ggb(path)
    assert "geogebra.xml" in str(failure.value)


def test_a_coordinate_is_taken_as_an_exact_number(tmp_path: Path) -> None:
    """A hand-drawn point has no exact value: six digits is the faith."""
    xml = XML.replace('x="0" y="0" z="1"', 'x="-1.6339331842054619" y="4.686114575962919" z="1"')
    result = import_ggb(_write_ggb(tmp_path / "figure.ggb", xml))
    first = result.dsl.splitlines()[0]
    assert "-163393/100000" in first
    assert "468611/100000" in first
    assert any("浮点" in item for item in result.warnings)
