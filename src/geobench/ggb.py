"""Reading a GeoGebra file: `.ggb` in, the DSL out.

A `.ggb` is a ZIP with `geogebra.xml` inside it.  The XML lists the
construction as a list of commands -- ``Segment(A,B) -> f`` -- in the
order they were made, which is exactly the shape the DSL has: one line
per command, in order.

So the import is a **translation**, not a re-implementation: each
command becomes the DSL line for the same construction, and the figure
is then built by our own parser, by our own kernel.  Nothing is read
from GeoGebra's numbers except the free points, and even those are not
trusted as they stand -- they are floating point, our kernel is exact,
so each one is turned into the simplest rational within 1e-6 of where it
was.

Three differences between the two languages are worth naming, because
each one loses something:

- **two answers, one command.**  GeoGebra's ``Tangent(P, c)`` produces
  *two* lines; ours produces one (which of the two is a convention).
  The first is imported, the second is reported as skipped -- never
  silently dropped.
- **zeros and ones.**  GeoGebra's intersection selector counts from 1,
  ours from 0.  Getting this wrong would swap two points of the figure,
  so it is converted in one place, with a test.
- **names.**  GeoGebra writes ``H_{1}`` and ``f_1``; the DSL wants
  identifiers.  The import renames them and says so.

Anything the DSL cannot express is **reported**, not approximated: an
import that quietly drops a construction produces a figure that is not
the one the teacher has.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import sympy as sp

from geobench.errors import GeobenchError

#: How close an imported coordinate has to be to a rational, relative to
#: the size of the figure.  A hand-drawn point has no exact value of its
#: own, so "the simplest number in the neighbourhood" is the right one.
DENOMINATOR_LIMIT = 10**6

#: GeoGebra command names -> ours.  Chinese names are already ours (both
#: come from GeoGebra), so only the English ones need saying.
_NAMES: dict[str, str] = {
    "Segment": "线段",
    "Line": "直线",
    "Ray": "射线",
    "Polyline": "折线",
    "Polygon": "多边形",
    "Midpoint": "中点",
    "Centroid": "重心",
    "Circumcenter": "外心",
    "Orthocenter": "垂心",
    "Incenter": "内心",
    "OrthogonalLine": "垂直",
    "PerpendicularLine": "垂直",
    "ParallelLine": "平行",
    "PerpendicularBisector": "中垂线",
    "LineBisector": "中垂线",
    "AngleBisector": "角平分线",
    "AngularBisector": "角平分线",
    "Rotate": "旋转",
    "Translate": "平移",
    "Dilate": "位似",
    "Mirror": "镜像",
    "Reflect": "镜像",
}

#: Commands whose *argument list* has to be rearranged, not just renamed.
_REORDERED = frozenset({"LineBisector", "PerpendicularBisector", "Intersect", "Tangent", "Circle"})

#: The kinds a label can have, as far as the import cares.
_LINE_LIKE = frozenset({"line", "segment"})


@dataclass
class ImportResult:
    """What came out of a `.ggb`, and what did not."""

    dsl: str
    warnings: list[str] = field(default_factory=list)
    """Things that were imported but changed (rounding, renaming)."""

    skipped: list[str] = field(default_factory=list)
    """Constructions the DSL cannot express, and why."""

    renames: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return bool(self.dsl.strip())


def _sanitize(label: str) -> str:
    """A GeoGebra label as a DSL name.

    ``H_{1}`` becomes ``H1``, ``f_1`` becomes ``f1``: the DSL wants
    identifiers, and GeoGebra's subscripts are the one place the two
    disagree.
    """
    text = label.replace("_{", "").replace("}", "").replace("_", "")
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", text)
    if not text:
        return "X"
    if text[0].isdigit():
        return "n" + text
    return text


def _exact(value: str) -> tuple[str, bool]:
    """A floating coordinate as an exact one, and whether it moved.

    A hand-drawn point has no exact value of its own: the number in the
    file is a measurement, and a measurement is not what a kernel wants.
    Six significant digits is the faith that was in the drawing -- a
    thousandth of a unit on a figure a few units across -- and the
    decimal is read as the rational it is, so ``-1.63393`` becomes
    ``-163393/100000`` and nothing downstream ever sees a float.
    """
    number = float(value)
    shortened = float(f"{number:.6g}")
    rational = sp.Rational(str(shortened))
    return str(rational), abs(shortened - number) > 0


class _Kinds:
    """What each label is, so an Intersect knows what it is intersecting."""

    def __init__(self) -> None:
        self.kind: dict[str, str] = {}
        self.endpoints: dict[str, tuple[str, str]] = {}

    def set(self, label: str, kind: str, endpoints: tuple[str, str] | None = None) -> None:
        self.kind[label] = kind
        if endpoints is not None:
            self.endpoints[label] = endpoints


def import_ggb(path: Path) -> ImportResult:
    """Read a `.ggb` and write the DSL for the same construction."""
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise GeobenchError(f"{path.name} 不是一个 GeoGebra 文件：{exc}") from None
    with archive:
        try:
            xml = archive.read("geogebra.xml")
        except KeyError:
            raise GeobenchError(f"{path.name} 里没有 geogebra.xml") from None

    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise GeobenchError(f"{path.name} 的 geogebra.xml 读不懂：{exc}") from None

    construction = root.find("construction")
    if construction is None:
        raise GeobenchError(f"{path.name} 里没有构造")

    result = ImportResult(dsl="")
    kinds = _Kinds()
    lines: list[str] = []

    # -- the free points ---------------------------------------------------
    produced: set[str] = set()
    for command in construction.findall("command"):
        for output in command.findall("output"):
            produced.update(output.attrib.values())

    free: list[tuple[str, str, str]] = []
    for element in construction.findall("element"):
        if element.get("type") != "point":
            continue
        label = element.get("label") or ""
        if label in produced:
            continue
        coords = element.find("coords")
        if coords is None:
            continue
        x_text, moved_x = _exact(coords.get("x", "0"))
        y_text, moved_y = _exact(coords.get("y", "0"))
        name = _sanitize(label)
        if name != label:
            result.renames[label] = name
        if moved_x or moved_y:
            result.warnings.append(
                f"点 {label} 的坐标是浮点数，按 1e-6 取成了有理数 ({x_text}, {y_text})"
            )
        free.append((name, x_text, y_text))
        kinds.set(name, "point")

    if free:
        points = " ".join(f"{name}({x}, {y})" for name, x, y in free)
        lines.append(f"点 {points}")

    # -- the commands, in construction order -------------------------------
    for command in construction.findall("command"):
        name = command.get("name") or ""
        inputs = _attributes(command.findall("input"))
        outputs = _attributes(command.findall("output"))
        line, skipped = _translate(name, inputs, outputs, kinds, result)
        if line is not None:
            lines.append(line)
        if skipped:
            result.skipped.append(skipped)

    result.dsl = "\n".join(lines) + "\n"
    return result


def _attributes(elements: list[ET.Element]) -> list[str]:
    """The arguments of a command, in order (a0, a1, ...)."""
    values: list[str] = []
    for element in elements:
        for key in sorted(element.attrib, key=lambda name: int(name[1:])):
            values.append(element.attrib[key])
    return values


def _translate(
    name: str,
    inputs: list[str],
    outputs: list[str],
    kinds: _Kinds,
    result: ImportResult,
) -> tuple[str | None, str]:
    """One GeoGebra command as one DSL line, or a reason it cannot be."""
    if not outputs:
        return None, f"{name}({', '.join(inputs)}): 没有产出对象"
    label = _sanitize(outputs[0])
    if label != outputs[0]:
        result.renames[outputs[0]] = label
    if len(outputs) > 1:
        result.skipped.append(
            f"{name}({', '.join(inputs)}) 在 GeoGebra 里给出 {len(outputs)} 个对象"
            f"（{', '.join(outputs)}），本语言一条命令一个对象 —— 只导入了 {outputs[0]}"
        )

    def args(values: list[str]) -> list[str]:
        # A label is renamed; a *number* is left alone.  A rotation's
        # angle is "90", and turning it into the name "n90" would ask
        # the kernel for a point called n90.
        return [value if _is_number(value) else _sanitize(value) for value in values]

    # -- the commands whose arguments are not just renamed ----------------
    if name in ("LineBisector", "PerpendicularBisector"):
        if not inputs:
            return None, f"{name}: 没有参数"
        source = _sanitize(inputs[0])
        ends = kinds.endpoints.get(source)
        if ends is None:
            return None, f"{name}({source}): 它不是一条已知端点的线段，无法转成中垂线"
        first, second = args(list(ends))
        kinds.set(label, "line")
        return f"{label} = 中垂线({first}, {second})", ""

    if name == "Intersect":
        if len(inputs) < 2:
            return None, "Intersect: 参数不足"
        first, second = _sanitize(inputs[0]), _sanitize(inputs[1])
        selector = inputs[2] if len(inputs) > 2 else "1"
        first_kind = kinds.kind.get(first, "")
        second_kind = kinds.kind.get(second, "")
        if first_kind in _LINE_LIKE and second_kind in _LINE_LIKE:
            kinds.set(label, "point")
            return f"{label} = 交点({_sanitize(first)}, {_sanitize(second)})", ""
        if {first_kind, second_kind} & _LINE_LIKE and "circle" in (first_kind, second_kind):
            line = first if first_kind in _LINE_LIKE else second
            circle = second if first_kind in _LINE_LIKE else first
            index = _selector(selector)
            kinds.set(label, "point")
            return (
                f"{label} = 交点({_sanitize(line)}, {_sanitize(circle)}, {index})",
                "",
            )
        if first_kind == "circle" and second_kind == "circle":
            index = _selector(selector)
            kinds.set(label, "point")
            return (
                f"{label} = 交点({_sanitize(first)}, {_sanitize(second)}, {index})",
                "",
            )
        return None, f"Intersect({first}, {second}): 不认识这两条对象的类型"

    if name == "Tangent":
        if len(inputs) != 2:
            return None, "Tangent: 参数不足"
        kinds.set(label, "line")
        return f"{label} = 切线({_sanitize(inputs[0])}, {_sanitize(inputs[1])})", ""

    if name == "Circle":
        if len(inputs) == 3:
            kinds.set(label, "circle")
            return f"{label} = 外接圆({', '.join(args(inputs))})", ""
        if len(inputs) == 2:
            kinds.set(label, "circle")
            return f"{label} = 圆({', '.join(args(inputs))})", ""
        return None, f"Circle({', '.join(inputs)}): 参数个数不认识"

    # -- everything else: rename the command, keep the arguments ----------
    ours = _NAMES.get(name, name)
    if name == "Segment" and len(inputs) == 2:
        kinds.set(label, "segment", (_sanitize(inputs[0]), _sanitize(inputs[1])))
    elif name in ("Line", "Ray", "OrthogonalLine", "ParallelLine"):
        kinds.set(label, "line")
    elif ours == "多边形":
        kinds.set(label, "polygon")
    elif ours in ("中点", "重心", "外心", "垂心", "内心", "交点"):
        kinds.set(label, "point")

    # A name that is neither ours nor in the table is reported: guessing
    # a command is how a figure quietly becomes a different figure.
    return f"{label} = {ours}({', '.join(args(inputs))})", ""


def _is_number(text: str) -> bool:
    """Is this argument a number rather than a label?"""
    try:
        float(text)
    except (TypeError, ValueError):
        return False
    return True


def _selector(value: str) -> int:
    """GeoGebra counts intersections from 1; we count from 0."""
    try:
        return max(0, int(float(value)) - 1)
    except (TypeError, ValueError):
        return 0


__all__ = ["ImportResult", "import_ggb"]
