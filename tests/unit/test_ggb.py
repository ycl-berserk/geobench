"""Reading a `.ggb`: the translation, and the things it cannot carry.

The test builds its own tiny `.ggb` rather than shipping a teacher's
file: a `.ggb` is a ZIP with `geogebra.xml` inside, so a test can make
one in a few lines, and the fixture stays readable in the diff.

What is checked is the *translation*: every construction becomes the DSL
line for the same construction, and the three places where the two
languages disagree are handled rather than approximated.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
import zipfile
from fractions import Fraction
from pathlib import Path

import pytest

from geobench.dsl import parse_dsl
from geobench.evaluate import (
    evaluate_figure,
    evaluate_numeric,
    evaluate_numeric_direct,
)
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


MACRO_XML = """<?xml version="1.0" encoding="utf-8"?>
<geogebra format="5.0">
  <macro cmdName="外心">
    <macroInput a0="A" a1="B" a2="C"/>
    <macroOutput a0="E"/>
    <construction>
      <command name="Segment"><input a0="A" a1="B"/><output a0="f"/></command>
      <command name="Midpoint"><input a0="A" a1="B"/><output a0="E"/></command>
    </construction>
  </macro>
</geogebra>
"""

MACRO_FIGURE = """<?xml version="1.0" encoding="utf-8"?>
<geogebra format="5.0">
  <construction>
    <element type="point" label="A"><coords x="0" y="0" z="1"/></element>
    <element type="point" label="B"><coords x="4" y="0" z="1"/></element>
    <element type="point" label="C"><coords x="1" y="3" z="1"/></element>
    <command name="外心"><input a0="A" a1="B" a2="C"/><output a0="O"/></command>
    <command name="Segment"><input a0="A" a1="O"/><output a0="s"/></command>
  </construction>
</geogebra>
"""

#: The teacher's own files, used as a smoke test where they are present.
CORPUS = Path(
    os.environ.get(
        "GEOBENCH_CORPUS", str(Path.home() / "Desktop" / "竞赛图形ggb示例")
    )
)


def _write_ggb(path: Path, xml: str = XML, macro: str | None = None) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("geogebra.xml", xml)
        if macro is not None:
            archive.writestr("geogebra_macro.xml", macro)
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


FORMS = """<?xml version="1.0" encoding="utf-8"?>
<geogebra format="5.0">
  <construction>
    <element type="point" label="A"><coords x="0" y="0" z="1"/></element>
    <element type="point" label="B"><coords x="4" y="0" z="1"/></element>
    <element type="point" label="C"><coords x="1" y="3" z="1"/></element>
    <command name="Segment"><input a0="A" a1="B"/><output a0="f"/></command>
    <command name="Midpoint"><input a0="f"/><output a0="M"/></command>
    <command name="Line"><input a0="A" a1="f"/><output a0="p"/></command>
    <command name="PerpendicularSegment">
      <input a0="C" a1="f"/><output a0="h"/><output a1="D"/>
    </command>
    <command name="Mirror"><input a0="C" a1="M"/><output a0="C_1"/></command>
  </construction>
</geogebra>
"""


def test_geogebra_forms_the_dsl_does_not_share_are_translated(tmp_path: Path) -> None:
    """Midpoint(segment), Line(point, line), a perpendicular segment, a half-turn."""
    result = import_ggb(_write_ggb(tmp_path / "forms.ggb", FORMS))
    lines = result.dsl.splitlines()
    assert "M = 中点(A, B)" in lines
    assert "p = 平行(A, f)" in lines
    assert "D = 垂足(C, f)" in lines
    assert "h = 线段(C, D)" in lines
    assert "C1 = 点对称(C, M)" in lines


def test_a_custom_tool_is_expanded_not_matched_by_name(tmp_path: Path) -> None:
    """A teacher's 外心 tool shadows the built-in: its body is the truth."""
    result = import_ggb(
        _write_ggb(tmp_path / "macro.ggb", MACRO_FIGURE, MACRO_XML)
    )
    lines = result.dsl.splitlines()
    assert "O = 中点(A, B)" in lines
    assert not any("外心(" in line for line in lines)
    assert any("自定义工具" in item for item in result.warnings)
    # The macro's own segment is scaffolding; it must not appear in the
    # drawing even though it stays in the construction.
    assert any(line.startswith("隐藏 m") for line in lines)


def test_the_intersection_selector_matches_the_saved_point(
    tmp_path: Path, registry: OperatorRegistry
) -> None:
    """GeoGebra's "second" answer is not necessarily the kernel's.

    The source records where the selected point really is; the import
    must use that to number the two answers, or the point jumps to the
    other end of the chord.
    """
    xml = """<?xml version="1.0" encoding="utf-8"?>
    <geogebra format="5.0"><construction>
      <element type="point" label="A"><coords x="-10" y="0" z="1"/></element>
      <element type="point" label="B"><coords x="10" y="0" z="1"/></element>
      <element type="point" label="O"><coords x="0" y="0" z="1"/></element>
      <element type="point" label="R"><coords x="5" y="0" z="1"/></element>
      <command name="Line"><input a0="A" a1="B"/><output a0="l"/></command>
      <command name="Circle"><input a0="O" a1="R"/><output a0="c"/></command>
      <command name="Intersect"><input a0="l" a1="c" a2="2"/>
        <output a0="P"/></command>
      <element type="point" label="P"><coords x="5" y="0" z="1"/></element>
    </construction></geogebra>"""
    result = import_ggb(_write_ggb(tmp_path / "selector.ggb", xml))
    figure = parse_dsl(result.dsl)
    evaluate_figure(figure, registry)
    evaluate_numeric(figure)
    x, y = figure.nodes["P"].cache["numeric"]["coords"]
    assert x == pytest.approx(5.0)
    assert y == pytest.approx(0.0)


def test_colour_and_line_style_come_across(tmp_path: Path) -> None:
    """A red dotted auxiliary circle stays red and dotted."""
    xml = """<?xml version="1.0" encoding="utf-8"?>
    <geogebra format="5.0"><construction>
      <element type="point" label="A"><coords x="0" y="0" z="1"/></element>
      <element type="point" label="B"><coords x="4" y="0" z="1"/></element>
      <command name="Circle"><input a0="A" a1="B"/><output a0="c"/></command>
      <element type="conic" label="c"><objColor r="211" g="47" b="47"/>
        <lineStyle thickness="5" type="10" typeHidden="1"/></element>
    </construction></geogebra>"""
    result = import_ggb(_write_ggb(tmp_path / "style.ggb", xml))
    lines = result.dsl.splitlines()
    assert "颜色 c red" in lines
    assert "辅助 c" in lines
    figure = parse_dsl(result.dsl)
    assert figure.nodes["c"].style.color != "#000000"
    assert figure.nodes["c"].style.line_style == "dashed"


def test_an_object_the_source_hides_is_not_drawn(tmp_path: Path) -> None:
    """GeoGebra's show=false is a decision, not a detail to lose."""
    xml = """<?xml version="1.0" encoding="utf-8"?>
    <geogebra format="5.0"><construction>
      <element type="point" label="A"><coords x="0" y="0" z="1"/></element>
      <element type="point" label="B"><coords x="4" y="0" z="1"/></element>
      <element type="point" label="C"><coords x="2" y="3" z="1"/></element>
      <command name="Line"><input a0="A" a1="B"/><output a0="l"/></command>
      <element type="line" label="l"><show object="false" label="false"/></element>
      <command name="Midpoint"><input a0="A" a1="B"/><output a0="M"/></command>
      <element type="point" label="M"><show object="false" label="false"/>
        <coords x="2" y="0" z="1"/></element>
    </construction></geogebra>"""
    result = import_ggb(_write_ggb(tmp_path / "hidden.ggb", xml))
    lines = result.dsl.splitlines()
    assert "l = 直线(A, B)" in lines
    assert "隐藏 l" in lines
    assert "隐藏 M" in lines
    figure = parse_dsl(result.dsl)
    assert figure.nodes["l"].style.visible is False
    assert figure.nodes["M"].style.visible is False


def test_the_points_stay_inside_the_circle(tmp_path: Path) -> None:
    """``Point(c)`` keeps the parameter the teacher had, not a free point."""
    xml = """<?xml version="1.0" encoding="utf-8"?>
    <geogebra format="5.0"><construction>
      <element type="point" label="O"><coords x="0" y="0" z="1"/></element>
      <element type="point" label="A"><coords x="2" y="0" z="1"/></element>
      <element type="point" label="B"><coords x="0" y="2" z="1"/></element>
      <command name="Circle"><input a0="O" a1="A"/><output a0="c"/></command>
      <command name="Point"><input a0="c"/><output a0="B"/></command>
    </construction></geogebra>"""
    result = import_ggb(_write_ggb(tmp_path / "on-circle.ggb", xml))
    line = next(
        line for line in result.dsl.splitlines() if line.startswith("B = 圆上的点")
    )
    parameter = line.split(", ")[-1].rstrip(")")
    assert 0 <= Fraction(parameter) < 1
    figure = parse_dsl(result.dsl)
    evaluate_numeric(figure)
    assert figure.nodes["B"].op == "point.on_circle"


CORPUS_FILES = sorted(CORPUS.glob("*.ggb")) if CORPUS.is_dir() else []


@pytest.mark.skipif(not CORPUS_FILES, reason="the teacher's corpus is not here")
@pytest.mark.parametrize("path", CORPUS_FILES, ids=lambda path: path.name)
def test_the_real_corpus_imports_and_builds(
    path: Path, registry: OperatorRegistry
) -> None:
    """Every real file goes through the importer and the kernel."""
    result = import_ggb(path)
    assert result.dsl.strip()
    figure = parse_dsl(result.dsl)
    evaluate_figure(figure, registry)
    evaluate_numeric(figure)


@pytest.mark.skipif(not CORPUS_FILES, reason="the teacher's corpus is not here")
@pytest.mark.parametrize("path", CORPUS_FILES, ids=lambda path: path.name)
def test_imported_intersections_sit_where_the_source_saved_them(
    path: Path, registry: OperatorRegistry
) -> None:
    """GeoGebra's intersection numbering is not the kernel's.

    Every imported intersection point must land on the position the
    source file recorded for it -- otherwise a point jumps to the other
    end of the chord without any error being reported.
    """
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("geogebra.xml"))
    saved: dict[str, tuple[float, float]] = {}
    for element in root.find("construction").findall("element"):
        if element.get("type") != "point":
            continue
        coords = element.find("coords")
        if coords is None:
            continue
        z = float(coords.get("z", "1") or 1)
        saved[element.get("label", "")] = (
            float(coords.get("x", "0")) / z,
            float(coords.get("y", "0")) / z,
        )

    result = import_ggb(path)
    figure = parse_dsl(result.dsl)
    evaluate_numeric_direct(figure, registry)
    checked = 0
    for node_id, node in figure.nodes.items():
        if not (node.op or "").startswith("point.intersect"):
            continue
        wanted = saved.get(node_id)
        values = node.cache.get("numeric") or {}
        actual = values.get("coords")
        if wanted is None or actual is None:
            continue
        checked += 1
        assert actual[0] == pytest.approx(wanted[0], abs=0.02), node_id
        assert actual[1] == pytest.approx(wanted[1], abs=0.02), node_id
    assert checked
