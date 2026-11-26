"""Reading a GeoGebra file: `.ggb` in, the DSL out.

A `.ggb` is a ZIP with ``geogebra.xml`` inside it.  The XML lists the
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
- **names.**  GeoGebra writes ``H_{1}``, ``f_1`` and ``H'``; the DSL
  wants identifiers.  The import renames them, keeps a map from the old
  name to the new, and says so.

Anything the DSL cannot express is **reported**, not approximated: an
import that quietly drops a construction produces a figure that is not
the one the teacher has.  A command that depends on an object we did not
import is skipped too -- never emitted as a line that would fail to
parse.
"""

from __future__ import annotations

import contextlib
import math
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import sympy as sp

from geobench.commands import COMMANDS, JUDGEMENT, CommandSpec
from geobench.dsl import parse_dsl
from geobench.dsl.parser import _KIND_BY_COMMAND
from geobench.errors import GeobenchError
from geobench.evaluate import evaluate_numeric_direct
from geobench.model import Figure, Node
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry
from geobench.style import COLORS

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
    "Excenter": "旁心",
    "OrthogonalLine": "垂直",
    "PerpendicularLine": "垂直",
    "ParallelLine": "平行",
    "PerpendicularBisector": "中垂线",
    "LineBisector": "中垂线",
    "AngleBisector": "角平分线",
    "AngularBisector": "角平分线",
    "PerpendicularSegment": "垂线段",
    "Rotate": "旋转",
    "Translate": "平移",
    "Dilate": "位似",
    "Mirror": "镜像",
    "Reflect": "镜像",
    "Angle": "角度",
    "Distance": "距离",
    "Length": "长度",
    "Area": "面积",
    "Perimeter": "周长",
    "Radius": "半径",
    "Slope": "斜率",
    "Direction": "方向",
}

#: Our command table, by both names.  A construction whose name is not in
#: here is reported instead of emitted: the parser would only refuse it.
#:
#: Several names are shared by a construction and a judgement -- ``外心``
#: is both "the circumcentre of these three points" and "is this point
#: the circumcentre?".  An import always wants the construction, so a
#: judgement never replaces an entry that is already there.
_KNOWN: dict[str, CommandSpec] = {}
# Constructions first, so that a shared name always resolves to the one
# that builds something.
for _command in COMMANDS:
    if _command.kind != JUDGEMENT:
        _KNOWN[_command.name_zh] = _command
        _KNOWN[_command.name_en] = _command
for _command in COMMANDS:
    _KNOWN.setdefault(_command.name_zh, _command)
    _KNOWN.setdefault(_command.name_en, _command)

#: The kinds a label can have, as far as the import cares.
_LINE_LIKE = frozenset({"line", "segment"})

#: The DSL spells colours by name (a ``#`` would start a comment), so a
#: GeoGebra colour is mapped to the nearest one the studio can write.
_NAMED_COLORS = {
    name: code
    for name, code in COLORS.items()
    if name.isascii()
}
_NAMED_RGB = {
    name: tuple(int(code[i : i + 2], 16) for i in (1, 3, 5))
    for name, code in _NAMED_COLORS.items()
}


def _nearest_color(rgb: tuple[int, int, int]) -> str:
    return min(
        _NAMED_RGB,
        key=lambda name: sum(
            (rgb[index] - _NAMED_RGB[name][index]) ** 2 for index in range(3)
        ),
    )



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

    ``H_{1}`` becomes ``H1``, ``f_1`` becomes ``f1``, ``H'`` becomes
    ``H1``: the DSL wants identifiers, and GeoGebra's subscripts and
    primes are the places the two disagree.  Greek letters are names a
    geometry figure actually uses, so they are kept.
    """
    text = label.replace("_{", "").replace("}", "")
    text = text.replace("'", "1").replace("′", "1")
    text = "".join(ch for ch in text if ch.isalnum())
    if not text:
        return "X"
    # The lexer reads a Chinese run and a Latin run as two tokens, so a
    # GeoGebra label like 距离IC cannot be written as one identifier.
    # Keep the readable Latin part and prefix it rather than breaking
    # the line into two names.
    has_cjk = any("\u4e00" <= char <= "\u9fff" for char in text)
    has_ascii = any(char.isascii() and char.isalnum() for char in text)
    if has_cjk and has_ascii:
        ascii_part = "".join(
            char for char in text if char.isascii() and char.isalnum()
        )
        text = "m" + (ascii_part or "name")
    if text[0].isdigit():
        return "n" + text
    return text


def _unique(name: str, used: set[str]) -> str:
    """A name not already in the figure; suffixes 2, 3, ... when needed."""
    if name not in used:
        used.add(name)
        return name
    index = 2
    while f"{name}{index}" in used:
        index += 1
    name = f"{name}{index}"
    used.add(name)
    return name


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


def _circumcircle(
    first: tuple[float, float],
    second: tuple[float, float],
    third: tuple[float, float],
) -> tuple[float, float, float] | None:
    """The centre and radius of a circle through three saved points."""
    ax, ay = first
    bx, by = second
    cx, cy = third
    determinant = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if determinant == 0:
        return None
    s1, s2, s3 = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
    ux = (s1 * (by - cy) + s2 * (cy - ay) + s3 * (ay - by)) / determinant
    uy = (s1 * (cx - bx) + s2 * (ax - cx) + s3 * (bx - ax)) / determinant
    return ux, uy, math.hypot(ax - ux, ay - uy)


@dataclass
class _RawCommand:
    """One GeoGebra command, before translation."""

    name: str
    inputs: list[str]
    outputs: list[str]


@dataclass
class _Macro:
    """A custom tool defined in the file itself (``geogebra_macro.xml``)."""

    name: str
    inputs: list[str]
    outputs: list[str]
    commands: list[_RawCommand]


def _read_macros(archive: zipfile.ZipFile) -> dict[str, _Macro]:
    """The custom tools a file carries, by command name.

    A teacher's figure often uses tools they built themselves, and those
    tools shadow the built-in command of the same name.  The macro body,
    not the name, is what the figure means, so an import expands them.
    """
    try:
        xml = archive.read("geogebra_macro.xml")
    except KeyError:
        return {}
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return {}
    macros: dict[str, _Macro] = {}
    for node in root.findall("macro"):
        name = node.get("cmdName")
        construction = node.find("construction")
        if not name or construction is None:
            continue
        commands: list[_RawCommand] = []
        for command in construction.findall("command"):
            commands.append(
                _RawCommand(
                    command.get("name") or "",
                    _attributes(command.findall("input")),
                    _attributes(command.findall("output")),
                )
            )
        macros[name] = _Macro(
            name,
            _attributes(node.findall("macroInput")),
            _attributes(node.findall("macroOutput")),
            commands,
        )
    return macros


def _expand_macros(
    construction: ET.Element,
    macros: dict[str, _Macro],
    result: ImportResult,
    hidden: set[str],
) -> list[_RawCommand]:
    """Flatten every macro call into the primitive commands it stands for."""
    expanded: list[_RawCommand] = []
    counter = 0
    used_macros: set[str] = set()

    def fresh(label: str) -> str:
        nonlocal counter
        counter += 1
        name = f"m{counter}_{_sanitize(label)}"
        # A macro's internal construction is how GeoGebra computes the
        # tool's output; the teacher sees the output, not the scaffolding.
        hidden.add(name)
        return name

    def emit(
        name: str,
        inputs: list[str],
        outputs: list[str],
        stack: tuple[str, ...],
    ) -> None:
        macro = macros.get(name)
        if macro is None or name in stack:
            expanded.append(_RawCommand(name, inputs, outputs))
            return
        used_macros.add(name)
        # The macro's own labels are renamed, except its inputs (which are
        # the caller's objects) and its outputs (which are the caller's
        # results).  Without the renaming, two applications of the same
        # tool would collide.
        mapping = dict(zip(macro.inputs, inputs, strict=False))
        inner_labels: set[str] = set()
        for command in macro.commands:
            inner_labels.update(command.inputs)
            inner_labels.update(command.outputs)
        for label in inner_labels:
            if label not in mapping:
                mapping[label] = fresh(label)
        mapping.update(zip(macro.outputs, outputs, strict=False))
        for command in macro.commands:
            emit(
                command.name,
                [mapping.get(value, value) for value in command.inputs],
                [mapping.get(value, value) for value in command.outputs],
                (*stack, name),
            )

    for command in construction.findall("command"):
        emit(
            command.get("name") or "",
            _attributes(command.findall("input")),
            _attributes(command.findall("output")),
            (),
        )
    for name in sorted(used_macros):
        result.warnings.append(f"自定义工具「{name}」已按文件里的定义展开")
    return expanded


class _Kinds:
    """What each label is, and everything the translator remembers."""

    def __init__(self) -> None:
        self.kind: dict[str, str] = {}
        self.endpoints: dict[str, tuple[str, str]] = {}
        self.used: set[str] = set()
        self.names: dict[str, str] = {}
        """GeoGebra label -> the name it got in the DSL."""
        self.coords: dict[str, tuple[float, float]] = {}
        """Every point's saved position, including produced points."""
        self.circles: dict[str, tuple[float, float, float]] = {}
        """Circles we can place a ``Point`` on: centre and radius."""
        self.missing: set[str] = set()
        """Labels that were not imported; dependants are skipped."""

        self.hidden: set[str] = set()
        """Labels the source file does not draw (``show object="false"``)."""

        self.colors: dict[str, str] = {}
        """Object colours, as a DSL colour name, when the source set one."""

        self.dashed: set[str] = set()
        """Objects the source draws with a non-solid line style."""

        self.labels_hidden: set[str] = set()
        """Objects whose name the source does not print."""

        self.intersections: list[tuple[str, str]] = []
        """Imported intersections, so their selector can be matched later."""

    def set(
        self,
        label: str,
        kind: str,
        endpoints: tuple[str, str] | None = None,
    ) -> None:
        self.kind[label] = kind
        if endpoints is not None:
            self.endpoints[label] = endpoints

    def name(self, label: str) -> str:
        return self.names.get(label, _sanitize(label))

    def allocate(self, label: str) -> str:
        name = _unique(_sanitize(label), self.used)
        self.names[label] = name
        return name


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
        macros = _read_macros(archive)

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
    texts: list[tuple[str, str, str, str]] = []
    expressions = {
        element.get("label", ""): element.get("exp", "")
        for element in construction.findall("expression")
    }

    # Every point's saved position, free or produced: a ``Point(c)`` on
    # a circle needs it to recover the parameter the teacher had.
    for element in construction.findall("element"):
        kind = element.get("type")
        label = element.get("label") or ""
        show = element.find("show")
        if show is not None and show.get("object") == "false":
            kinds.hidden.add(label)
        if show is not None and show.get("label") == "false":
            kinds.labels_hidden.add(label)
        color = element.find("objColor")
        if color is not None:
            try:
                rgb = (
                    int(color.get("r", "0")),
                    int(color.get("g", "0")),
                    int(color.get("b", "0")),
                )
            except (TypeError, ValueError):
                rgb = (0, 0, 0)
            if rgb != (0, 0, 0) and kind != "point":
                # Points follow the studio's own convention: blue for
                # free points, black for derived ones.  A source file's
                # grey helper dots would only blur that distinction.
                kinds.colors[label] = _nearest_color(rgb)
        line_style = element.find("lineStyle")
        if line_style is not None and line_style.get("type", "0") not in (
            "0",
            "",
        ):
            kinds.dashed.add(label)
        if kind == "point":
            coords = element.find("coords")
            if coords is not None:
                with contextlib.suppress(TypeError, ValueError, ZeroDivisionError):
                    # GeoGebra stores homogeneous coordinates; a computed
                    # point may have z != 1, and x/z is where it really is.
                    z = float(coords.get("z", "1") or 1)
                    kinds.coords[label] = (
                        float(coords.get("x", "0")) / z,
                        float(coords.get("y", "0")) / z,
                    )
        elif kind == "text":
            start = element.find("startPoint")
            content = expressions.get(label, "")
            # GeoGebra stores the expression with the quotes around it.
            if len(content) >= 2 and content.startswith('"') and content.endswith('"'):
                content = content[1:-1]
            content = content.replace('\\"', '"')
            if start is None or not content:
                result.skipped.append(f"文本 {label}: 没有内容或位置，未导入")
                continue
            try:
                raw_x = float(start.get("x", "0"))
                raw_y = float(start.get("y", "0"))
            except (TypeError, ValueError):
                raw_x = raw_y = math.nan
            if not (math.isfinite(raw_x) and math.isfinite(raw_y)):
                result.skipped.append(f"文本 {label}: 位置是 nan/∞，未导入")
                continue
            x = format(raw_x, ".6g")
            y = format(raw_y, ".6g")
            texts.append((label, content, x, y))

    # -- the free points ---------------------------------------------------
    produced: set[str] = set()
    for command in construction.findall("command"):
        for output in command.findall("output"):
            produced.update(output.attrib.values())

    free: list[tuple[str, str, str]] = []
    hidden_free: list[str] = []
    free_style: list[str] = []
    for element in construction.findall("element"):
        if element.get("type") != "point":
            continue
        label = element.get("label") or ""
        if label in produced:
            continue
        coords = element.find("coords")
        if coords is None:
            kinds.missing.add(label)
            result.skipped.append(f"点 {label}: 没有坐标，未导入")
            continue
        try:
            raw_x = float(coords.get("x", "0"))
            raw_y = float(coords.get("y", "0"))
        except (TypeError, ValueError):
            raw_x = raw_y = math.nan
        if not (math.isfinite(raw_x) and math.isfinite(raw_y)):
            kinds.missing.add(label)
            result.skipped.append(f"点 {label}: 坐标是 nan/∞，未导入")
            continue
        x_text, moved_x = _exact(coords.get("x", "0"))
        y_text, moved_y = _exact(coords.get("y", "0"))
        name = kinds.allocate(label)
        if name != label:
            result.renames[label] = name
        if moved_x or moved_y:
            result.warnings.append(
                f"点 {label} 的坐标是浮点数，按 1e-6 取成了有理数 ({x_text}, {y_text})"
            )
        free.append((name, x_text, y_text))
        kinds.set(name, "point")
        if label in kinds.hidden:
            hidden_free.append(name)
        if label in kinds.colors:
            free_style.append(f"颜色 {name} {kinds.colors[label]}")
        if label in kinds.dashed:
            free_style.append(f"辅助 {name}")
        if label in kinds.labels_hidden:
            free_style.append(f"隐藏标签 {name}")

    if free:
        points = " ".join(f"{name}({x}, {y})" for name, x, y in free)
        lines.append(f"点 {points}")
        lines.extend(f"隐藏 {name}" for name in hidden_free)
        lines.extend(free_style)

    # -- the commands, in construction order -------------------------------
    for raw in _expand_macros(construction, macros, result, kinds.hidden):
        line, skipped = _translate(
            raw.name, raw.inputs, raw.outputs, kinds, result
        )
        if line is not None:
            # One GeoGebra command may need two DSL lines (a perpendicular
            # segment is also the foot it ends at); a newline separates them.
            lines.extend(line.splitlines())
            # An object the source file does not draw stays in the figure
            # -- later constructions depend on it -- but is not drawn.
            for output_label in raw.outputs:
                if output_label in kinds.names:
                    name = kinds.name(output_label)
                    if output_label in kinds.hidden:
                        lines.append(f"隐藏 {name}")
                    if output_label in kinds.colors:
                        lines.append(
                            f"颜色 {name} {kinds.colors[output_label]}"
                        )
                    if output_label in kinds.dashed:
                        lines.append(f"辅助 {name}")
                    if output_label in kinds.labels_hidden:
                        lines.append(f"隐藏标签 {name}")
        if skipped:
            result.skipped.append(skipped)

    for label, content, x, y in texts:
        name = kinds.allocate(label)
        escaped = (
            content.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
        )
        lines.append(f'文本 {name}("{escaped}", {x}, {y})')

    _choose_intersections(lines, kinds)

    result.dsl = "\n".join(lines) + "\n"
    return result


def _choose_intersections(lines: list[str], kinds: _Kinds) -> None:
    """Pick the intersection the source actually meant.

    GeoGebra numbers the two answers of ``Intersect`` differently from
    the kernel: its "second" can be the kernel's first.  The selector
    alone therefore cannot be copied.  The source file does record the
    **saved position** of the point, so after a quick numeric pass we
    take whichever of the two answers is the one at that position.
    """
    if not kinds.intersections:
        return
    try:
        registry = OperatorRegistry()
        register_builtins(registry)
    except Exception:
        return

    # An intersection may depend on another intersection that is also
    # being corrected (N on the circle through H, say).  One pass would
    # read the old H; repeat until nothing moves, so the corrections
    # travel down the construction in order.
    for _ in range(6):
        try:
            figure = parse_dsl("\n".join(lines))
            evaluate_numeric_direct(figure, registry)
        except Exception:
            return
        changed = False
        for original, kind in kinds.intersections:
            name = kinds.name(original)
            node = figure.nodes.get(name)
            saved = kinds.coords.get(original)
            if node is None or saved is None:
                continue
            candidates = _candidates(figure, node, kind)
            if candidates is None:
                continue
            index = 0
            if _distance(candidates[1], saved) < _distance(candidates[0], saved):
                index = 1
            if len(node.args) >= 3 and node.args[2] == str(index):
                continue
            for position, line in enumerate(lines):
                if line.startswith(f"{name} = 交点(") and line.endswith(")"):
                    lines[position] = (
                        f"{name} = 交点({node.args[0]}, {node.args[1]}, {index})"
                    )
                    changed = True
                    break
        if not changed:
            return


def _distance(first: tuple[float, float], second: tuple[float, float]) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


def _line_payload(
    figure: Figure, name: str
) -> tuple[float, float, float] | None:
    node = figure.nodes.get(name)
    if node is None:
        return None
    values = node.cache.get("numeric") or {}
    line = values.get("line")
    if line:
        return float(line[0]), float(line[1]), float(line[2])
    segment = values.get("segment")
    if segment and len(segment) == 4:
        x1, y1, x2, y2 = (float(value) for value in segment)
        return y1 - y2, x2 - x1, x1 * y2 - x2 * y1
    return None


def _circle_payload(
    figure: Figure, name: str
) -> tuple[float, float, float] | None:
    node = figure.nodes.get(name)
    if node is None:
        return None
    values = node.cache.get("numeric") or {}
    circle = values.get("circle")
    if circle and len(circle) == 3:
        return float(circle[0]), float(circle[1]), float(circle[2])
    return None


def _candidates(
    figure: Figure, node: Node, kind: str
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    if kind == "line_circle":
        line = _line_payload(figure, node.args[0])
        circle = _circle_payload(figure, node.args[1])
        if line is None or circle is None:
            return None
        a, b, c = line
        cx, cy, r2 = circle
        norm_sq = a * a + b * b
        if norm_sq == 0:
            return None
        p0x, p0y = -a * c / norm_sq, -b * c / norm_sq
        dx, dy = b, -a
        fx, fy = p0x - cx, p0y - cy
        quad_a = dx * dx + dy * dy
        quad_b = 2 * (fx * dx + fy * dy)
        quad_c = fx * fx + fy * fy - r2
        disc = quad_b * quad_b - 4 * quad_a * quad_c
        if disc < 0 or quad_a == 0:
            return None
        root = math.sqrt(disc)
        t_plus = (-quad_b + root) / (2 * quad_a)
        t_minus = (-quad_b - root) / (2 * quad_a)
        return (
            (p0x + t_plus * dx, p0y + t_plus * dy),
            (p0x + t_minus * dx, p0y + t_minus * dy),
        )

    first = _circle_payload(figure, node.args[0])
    second = _circle_payload(figure, node.args[1])
    if first is None or second is None:
        return None
    x1, y1, r1 = first
    x2, y2, r2 = second
    dx, dy = x2 - x1, y2 - y1
    d2 = dx * dx + dy * dy
    if d2 == 0:
        return None
    k = r1 - r2 + d2
    n = 4 * r1 * d2 - k * k
    if n < 0:
        return None
    t = k / (2 * d2)
    bx, by = x1 + dx * t, y1 + dy * t
    s = math.sqrt(n) / (2 * d2)
    return ((bx - dy * s, by + dx * s), (bx + dy * s, by - dx * s))


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

    # A construction that depends on something we did not import cannot
    # be imported either.  Saying so here keeps a dangling reference out
    # of the DSL, where it would fail to parse.
    missing_input = next(
        (value for value in inputs if not _is_number(value) and value in kinds.missing),
        None,
    )
    if missing_input is not None:
        kinds.missing.update(outputs)
        return None, (
            f"{name}({', '.join(inputs)}): 依赖的 {missing_input} 没有导入，跳过"
        )

    # A macro may define a point or number of its own; when its body refers
    # to one we could not carry over, the line is reported rather than
    # emitted with a name the parser would not know.
    unknown_input = next(
        (
            value
            for value in inputs
            if not _is_number(value) and value not in kinds.names
        ),
        None,
    )
    if unknown_input is not None:
        kinds.missing.update(outputs)
        return None, (
            f"{name}({', '.join(inputs)}): {unknown_input} 没有定义，跳过"
        )

    def args(values: list[str]) -> list[str]:
        # A label is renamed; a *number* is left alone.  A rotation's
        # angle is "90", and turning it into the name "n90" would ask
        # the kernel for a point called n90.
        return [value if _is_number(value) else kinds.name(value) for value in values]

    # -- Point(c): a point on an object, not a free point -----------------
    if name == "Point":
        if len(inputs) != 1:
            kinds.missing.update(outputs)
            return None, f"Point({', '.join(inputs)}): 参数个数不认识"
        source = kinds.name(inputs[0])
        label = kinds.allocate(outputs[0])
        if label != outputs[0]:
            result.renames[outputs[0]] = label
        saved = kinds.coords.get(outputs[0])
        circle = kinds.circles.get(source)
        if circle is not None and saved is not None:
            cx, cy, _radius = circle
            angle = math.atan2(saved[1] - cy, saved[0] - cx) / (2 * math.pi)
            parameter = sp.Rational(angle - math.floor(angle)).limit_denominator(720)
            kinds.set(label, "point")
            result.warnings.append(
                f"点 {outputs[0]} 是 {inputs[0]} 上的点，按保存位置取参数 {parameter}"
            )
            return f"{label} = 圆上的点({source}, {parameter})", ""
        if saved is not None:
            x_text, _ = _exact(str(saved[0]))
            y_text, _ = _exact(str(saved[1]))
            kinds.set(label, "point")
            result.warnings.append(
                f"点 {outputs[0]} 依附于 {inputs[0]}，无法还原约束，导入为自由点"
            )
            return f"点 {label}({x_text}, {y_text})", ""
        kinds.missing.update(outputs)
        return None, f"Point({inputs[0]}): 无法定位这个点"

    # -- Arc(<circle>, M, N): no command of ours takes a circle yet --------
    if name == "Arc" and len(inputs) == 3:
        kinds.missing.update(outputs)
        return None, (
            f"Arc({', '.join(inputs)}): GeoGebra 的 Arc 取圆上的两点，"
            "本语言还没有这个写法（圆弧请用圆心加两点）"
        )

    # -- Midpoint(<segment>): GeoGebra takes the segment, we take its ends -
    if name == "Midpoint" and len(inputs) == 1:
        source = kinds.name(inputs[0])
        label = kinds.allocate(outputs[0])
        if label != outputs[0]:
            result.renames[outputs[0]] = label
        ends = kinds.endpoints.get(source)
        if ends is not None:
            kinds.set(label, "point")
            return f"{label} = 中点({ends[0]}, {ends[1]})", ""
        kinds.missing.update(outputs)
        return None, f"{name}({source}): 这不是一条知道端点的线段，取不到中点"

    # -- Line(<point>, <line>): the line through the point, parallel -------
    if name in ("Line", "直线") and len(inputs) == 2:
        second = kinds.name(inputs[1])
        if kinds.kind.get(second) in _LINE_LIKE:
            label = kinds.allocate(outputs[0])
            if label != outputs[0]:
                result.renames[outputs[0]] = label
            first = kinds.name(inputs[0])
            kinds.set(label, "line")
            return f"{label} = 平行({first}, {second})", ""

    # -- PerpendicularSegment(P, l): a segment *and* its foot -------------
    if name in ("PerpendicularSegment", "垂线段") and len(inputs) == 2:
        point = kinds.name(inputs[0])
        line = kinds.name(inputs[1])
        segment_label = kinds.allocate(outputs[0])
        if segment_label != outputs[0]:
            result.renames[outputs[0]] = segment_label
        if len(outputs) > 1:
            foot_label = kinds.allocate(outputs[1])
            if foot_label != outputs[1]:
                result.renames[outputs[1]] = foot_label
            kinds.set(segment_label, "segment", (point, foot_label))
            kinds.set(foot_label, "point")
            # Two DSL lines: the foot is what the rest of the figure may
            # depend on, and the segment is what the teacher sees.
            return (
                f"{foot_label} = 垂足({point}, {line})\n"
                f"{segment_label} = 线段({point}, {foot_label})"
            ), ""
        kinds.set(segment_label, "segment")
        return f"{segment_label} = 垂线段({point}, {line})", ""

    # -- Mirror(P, Q): in GeoGebra the second argument may be a point ------
    if name in ("Mirror", "镜像") and len(inputs) == 2:
        second = kinds.name(inputs[1])
        if kinds.kind.get(second) == "point":
            label = kinds.allocate(outputs[0])
            if label != outputs[0]:
                result.renames[outputs[0]] = label
            first = kinds.name(inputs[0])
            kinds.set(label, "point")
            return f"{label} = 点对称({first}, {second})", ""

    # -- the commands whose arguments are not just renamed ----------------
    if name in ("LineBisector", "PerpendicularBisector"):
        label = kinds.allocate(outputs[0])
        if label != outputs[0]:
            result.renames[outputs[0]] = label
        if len(inputs) == 2:
            first, second = args(inputs)
            kinds.set(label, "line")
            return f"{label} = 中垂线({first}, {second})", ""
        if len(inputs) == 1:
            source = kinds.name(inputs[0])
            ends = kinds.endpoints.get(source)
            if ends is not None:
                first, second = args(list(ends))
                kinds.set(label, "line")
                return f"{label} = 中垂线({first}, {second})", ""
            kinds.missing.update(outputs)
            return None, (
                f"{name}({source}): 它不是一条已知端点的线段，无法转成中垂线"
            )
        kinds.missing.update(outputs)
        return None, f"{name}: 参数个数不认识"

    if name == "Intersect":
        label = kinds.allocate(outputs[0])
        if label != outputs[0]:
            result.renames[outputs[0]] = label
        if len(inputs) < 2:
            kinds.missing.update(outputs)
            return None, "Intersect: 参数不足"
        first, second = kinds.name(inputs[0]), kinds.name(inputs[1])
        selector = inputs[2] if len(inputs) > 2 else "1"
        first_kind = kinds.kind.get(first, "")
        second_kind = kinds.kind.get(second, "")
        if first_kind in _LINE_LIKE and second_kind in _LINE_LIKE:
            kinds.set(label, "point")
            return f"{label} = 交点({first}, {second})", ""
        if {first_kind, second_kind} & _LINE_LIKE and "circle" in (
            first_kind,
            second_kind,
        ):
            line = first if first_kind in _LINE_LIKE else second
            circle_name = second if first_kind in _LINE_LIKE else first
            index = _selector(selector)
            kinds.set(label, "point")
            kinds.intersections.append((outputs[0], "line_circle"))
            return f"{label} = 交点({line}, {circle_name}, {index})", ""
        if first_kind == "circle" and second_kind == "circle":
            index = _selector(selector)
            kinds.set(label, "point")
            kinds.intersections.append((outputs[0], "circles"))
            return f"{label} = 交点({first}, {second}, {index})", ""
        kinds.missing.update(outputs)
        return None, f"Intersect({first}, {second}): 不认识这两条对象的类型"

    if name == "Tangent":
        if len(inputs) != 2:
            kinds.missing.update(outputs)
            return None, "Tangent: 参数不足"
        labels = []
        for output in outputs:
            label = kinds.allocate(output)
            if label != output:
                result.renames[output] = label
            labels.append(label)
        first, second = args(inputs)
        kinds.set(labels[0], "line")
        if len(outputs) == 1:
            return f"{labels[0]} = 切线({first}, {second})", ""
        kinds.set(labels[1], "line")
        if len(outputs) > 2:
            kinds.missing.update(outputs[2:])
            result.skipped.append(
                f"Tangent({', '.join(inputs)}) 多出的 {len(outputs) - 2} 条切线没有导入"
            )
        return (
            f"{labels[0]} = 切线({first}, {second})\n"
            f"{labels[1]} = 另一切线({first}, {second})"
        ), ""

    if name == "Circle":
        label = kinds.allocate(outputs[0])
        if label != outputs[0]:
            result.renames[outputs[0]] = label
        if len(inputs) == 3:
            kinds.set(label, "circle")
            centres = [kinds.coords.get(value) for value in inputs]
            if all(point is not None for point in centres):
                circle = _circumcircle(*centres)  # type: ignore[arg-type]
                if circle is not None:
                    kinds.circles[label] = circle
            return f"{label} = 外接圆({', '.join(args(inputs))})", ""
        if len(inputs) == 2:
            kinds.set(label, "circle")
            centre = kinds.coords.get(inputs[0])
            through = kinds.coords.get(inputs[1])
            if centre is not None and through is not None:
                kinds.circles[label] = (
                    centre[0],
                    centre[1],
                    math.hypot(through[0] - centre[0], through[1] - centre[1]),
                )
            return f"{label} = 圆({', '.join(args(inputs))})", ""
        kinds.missing.update(outputs)
        return None, f"Circle({', '.join(inputs)}): 参数个数不认识"

    # -- Polygon: GeoGebra also returns each edge as an object ------------
    if name == "Polygon" and len(inputs) >= 3 and len(outputs) > 1:
        labels = []
        for output in outputs:
            label = kinds.allocate(output)
            if label != output:
                result.renames[output] = label
            labels.append(label)
        polygon = labels[0]
        kinds.set(polygon, "polygon")
        generated = [
            f"{polygon} = 多边形({', '.join(args(inputs))})"
        ]
        edges = min(len(outputs) - 1, len(inputs))
        for index in range(edges):
            edge = labels[index + 1]
            start = kinds.name(inputs[index])
            end = kinds.name(inputs[(index + 1) % len(inputs)])
            kinds.set(edge, "segment", (start, end))
            generated.append(f"{edge} = 线段({start}, {end})")
        if len(outputs) - 1 > edges:
            kinds.missing.update(outputs[edges + 1 :])
            result.skipped.append(
                f"{name}({', '.join(inputs)}) 多出的 {len(outputs) - 1 - edges} 个对象无法导入"
            )
        return "\n".join(generated), ""

    # -- two-line angle bisector: one of the two answers ----------------
    if name in ("AngularBisector", "AngleBisector") and len(inputs) == 2:
        first_kind = kinds.kind.get(kinds.name(inputs[0]), "")
        second_kind = kinds.kind.get(kinds.name(inputs[1]), "")
        if first_kind in _LINE_LIKE and second_kind in _LINE_LIKE:
            label = kinds.allocate(outputs[0])
            if label != outputs[0]:
                result.renames[outputs[0]] = label
            kinds.set(label, "line")
            if len(outputs) > 1:
                kinds.missing.update(outputs[1:])
                result.skipped.append(
                    f"{name}({', '.join(inputs)}) 给出两条角平分线，"
                    f"只导入了 {outputs[0]}"
                )
            return (
                f"{label} = 角平分线({kinds.name(inputs[0])}, "
                f"{kinds.name(inputs[1])})",
                "",
            )

    # -- Mirror(line/circle, line) ----------------------------------------
    if name in ("Mirror", "Reflect") and inputs:
        first_kind = kinds.kind.get(kinds.name(inputs[0]), "")
        if first_kind in {"line", "segment", "circle"}:
            label = kinds.allocate(outputs[0])
            if label != outputs[0]:
                result.renames[outputs[0]] = label
            kinds.set(label, first_kind if first_kind == "circle" else "line")
            return (
                f"{label} = 镜像({kinds.name(inputs[0])}, "
                f"{kinds.name(inputs[1])})",
                "",
            )

    # -- everything else: rename the command, keep the arguments ----------
    ours = _NAMES.get(name, name)
    command = _KNOWN.get(name) or _KNOWN.get(ours)
    if command is None or not command.implemented:
        kinds.missing.update(outputs)
        return None, (
            f"{name}({', '.join(inputs)}): 这个构造还没有实现，跳过"
        )
    if command.kind == JUDGEMENT:
        kinds.missing.update(outputs)
        return None, f"{name}({', '.join(inputs)}): 这是判定，不是构造"

    label = kinds.allocate(outputs[0])
    if label != outputs[0]:
        result.renames[outputs[0]] = label
    if len(outputs) > 1:
        # A polygon produces its edges as well; the DSL polygon draws
        # them, so the extra labels are not separate objects.
        kinds.missing.update(outputs[1:])
        result.skipped.append(
            f"{name}({', '.join(inputs)}) 在 GeoGebra 里给出 {len(outputs)} 个对象"
            f"（{', '.join(outputs)}），本语言一条命令一个对象 —— 只导入了 {outputs[0]}"
        )

    if name == "Segment" and len(inputs) == 2:
        kinds.set(
            label,
            "segment",
            (kinds.name(inputs[0]), kinds.name(inputs[1])),
        )
    else:
        output_kind = _KIND_BY_COMMAND.get(command.alias_of or command.id)
        if output_kind is not None:
            kinds.set(label, output_kind)

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
