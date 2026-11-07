"""The GeoGebra command table: one source of truth for names.

A teacher who already uses GeoGebra types ``中点(A,B)`` -- or, in a
GeoGebra whose interface is English, ``Midpoint(A,B)``. Both must work
here, and both must mean the same thing as they do there. So this table
records, for every geometry command GeoGebra has:

- the **Chinese** command name (the canonical one, decision D17);
- the **English** command name (GeoGebra's own, always also accepted);
- the **operator** or **judge** we implement it with;
- whether it is implemented yet.

Three things read this table, which is why it is worth having exactly
one:

- the **DSL** resolves a command name to an operator through it;
- the **toolbar** is generated from it;
- the **coverage table** in ``docs/plan.md`` is checked against it, so
  the document cannot quietly fall behind the code.

The command list is taken from GeoGebra's *Geometry Commands* section
(plus the conic, transformation and measurement commands that belong to
plane geometry). GeoGebra is not used as an oracle -- its kernel is
numeric -- but it *is* the reference for what a command means and what
it is called.

The English name is always accepted as well, even where the Chinese one
is the headline. That is not hedging: GeoGebra's own input bar accepts
English in every language, so a teacher may type either. Supporting
both costs nothing and removes a whole class of "the tool does not
recognise my command" complaints.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The families the commands are grouped into, in the order the coverage
#: table uses.
FAMILIES: tuple[str, ...] = (
    "点",
    "线",
    "圆",
    "多边形",
    "变换",
    "轨迹与曲线",
    "测量",
    "判定",
    "圆锥曲线",
)

#: The selectors a construction may take, where GeoGebra asks which of
#: several answers is wanted. ``另一交点`` is the second intersection,
#: not "any other one": it is the one that is not already known.
#:
#: The value written into the construction graph is the canonical one
#: (``other``), not the Chinese word: the Chinese is how a person writes
#: it, the canonical one is what the operator sees.
SELECTORS: dict[str, str] = {
    "第一交点": "0",
    "另一交点": "other",
    "第一切点": "0",
    "另一切点": "other",
}

#: What a command *does*, as opposed to what family it belongs to.
CONSTRUCTION = "构造"
JUDGEMENT = "判定"
MEASUREMENT = "测量"


@dataclass(frozen=True)
class CommandSpec:
    """One GeoGebra command, and what we make of it."""

    id: str
    """Our operator id (for a construction) or our judge id (for a relation)."""

    name_zh: str
    """GeoGebra's Chinese command name. The canonical name here."""

    name_en: str
    """GeoGebra's English command name. Always accepted too."""

    family: str
    kind: str
    arity: int
    summary: str
    implemented: bool = False
    alias_of: str | None = None
    """Another command's id, when this command is a synonym of that one."""

    arg_kinds: tuple[str, ...] = ()
    """What the arguments must be, for a relation.

    A construction's contract lives in the operator registry, which
    already declares it. A relation's does not, and without it two
    relations sharing a name could not be told apart: ``垂直`` is both
    "these two lines are perpendicular" and "this point's perpendicular
    falls on this line", and the arguments are what say which was meant.
    """

    @property
    def names(self) -> tuple[str, ...]:
        return (self.name_zh, self.name_en)


def _c(
    id: str,
    name_zh: str,
    name_en: str,
    family: str,
    kind: str,
    arity: int,
    summary: str,
    implemented: bool = False,
    alias_of: str | None = None,
    arg_kinds: tuple[str, ...] = (),
) -> CommandSpec:
    return CommandSpec(
        id=id,
        name_zh=name_zh,
        name_en=name_en,
        family=family,
        kind=kind,
        arity=arity,
        summary=summary,
        implemented=implemented,
        alias_of=alias_of,
        arg_kinds=arg_kinds,
    )


#: Every geometry command we know about. This is the coverage table.
COMMANDS: tuple[CommandSpec, ...] = (
    # -- 点 ---------------------------------------------------------------
    _c("point.free", "点", "Point", "点", CONSTRUCTION, 2, "自由点", True),
    _c("point.midpoint", "中点", "Midpoint", "点", CONSTRUCTION, 2, "线段的中点", True),
    _c("point.centroid", "重心", "Barycenter", "点", CONSTRUCTION, 3, "三角形的重心", True),
    _c(
        "point.circumcenter",
        "外心",
        "Circumcenter",
        "点",
        CONSTRUCTION,
        3,
        "三角形的外心",
        True,
    ),
    _c("point.incenter", "内心", "Incenter", "点", CONSTRUCTION, 3, "三角形的内心", True),
    _c(
        "point.orthocenter",
        "垂心",
        "Orthocenter",
        "点",
        CONSTRUCTION,
        3,
        "三角形的垂心",
        True,
    ),
    _c(
        "point.foot",
        "垂足",
        "OrthogonalProjection",
        "点",
        CONSTRUCTION,
        2,
        "点到直线的垂足",
        True,
    ),
    _c(
        "point.intersect_lines",
        "交点",
        "Intersect",
        "点",
        CONSTRUCTION,
        2,
        "两条直线的交点",
        True,
    ),
    _c(
        "point.intersect_line_circle",
        "交点",
        "Intersect",
        "点",
        CONSTRUCTION,
        3,
        "直线与圆的交点",
        True,
    ),
    _c(
        "point.intersect_circles",
        "交点",
        "Intersect",
        "点",
        CONSTRUCTION,
        3,
        "两圆的交点",
    ),
    _c("point.on_object", "点在", "PointIn", "点", CONSTRUCTION, 2, "点是否在对象上"),
    _c(
        "point.nearest_on_object",
        "最近点",
        "NearestPoint",
        "点",
        CONSTRUCTION,
        2,
        "对象上离给定点最近的点",
    ),
    _c(
        "point.polygon_vertex",
        "顶点",
        "Vertex",
        "点",
        CONSTRUCTION,
        2,
        "多边形的顶点",
    ),
    _c(
        "point.affine_ratio",
        "仿射比",
        "AffineRatio",
        "点",
        CONSTRUCTION,
        4,
        "按比例分割线段",
    ),
    _c(
        "point.in_region",
        "区域内点",
        "PointInRegion",
        "点",
        CONSTRUCTION,
        2,
        "区域内的点",
    ),
    # -- 线 ---------------------------------------------------------------
    _c("line.free", "直线", "Line", "线", CONSTRUCTION, 2, "过两点的直线", True),
    _c(
        "line.perpendicular_through",
        "垂直",
        "Perpendicular",
        "线",
        CONSTRUCTION,
        2,
        "过一点作垂线",
        True,
    ),
    _c(
        "line.parallel_through",
        "平行",
        "Parallel",
        "线",
        CONSTRUCTION,
        2,
        "过一点作平行线",
        True,
    ),
    _c(
        "line.perpendicular_bisector",
        "中垂线",
        "PerpendicularBisector",
        "线",
        CONSTRUCTION,
        2,
        "线段的中垂线",
    ),
    _c(
        "line.angle_bisector",
        "角平分线",
        "AngleBisector",
        "线",
        CONSTRUCTION,
        3,
        "角的平分线",
    ),
    _c("line.tangent", "切线", "Tangent", "线", CONSTRUCTION, 2, "圆的切线"),
    _c("line.polar", "极线", "Polar", "线", CONSTRUCTION, 2, "点的极线"),
    _c("ray.free", "射线", "Ray", "线", CONSTRUCTION, 2, "射线"),
    _c("segment.free", "线段", "Segment", "线", CONSTRUCTION, 2, "线段", True),
    _c("polyline.free", "折线", "PolyLine", "线", CONSTRUCTION, 2, "折线"),
    # -- 圆 ---------------------------------------------------------------
    _c("circle.free", "圆", "Circle", "圆", CONSTRUCTION, 2, "以一点为圆心的圆", True),
    _c(
        "circle.center_point",
        "圆",
        "Circle",
        "圆",
        CONSTRUCTION,
        2,
        "以一点为圆心、过另一点的圆",
        alias_of="circle.free",
    ),
    _c("circle.through", "外接圆", "Circumcircle", "圆", CONSTRUCTION, 3, "过三点的圆", True),
    _c("circle.incircle", "内切圆", "Incircle", "圆", CONSTRUCTION, 3, "三角形的内切圆"),
    _c("arc.free", "弧", "Arc", "圆", CONSTRUCTION, 3, "圆弧"),
    _c("arc.three_points", "圆弧", "CircularArc", "圆", CONSTRUCTION, 3, "三点确定的弧"),
    _c("sector.circular", "圆扇形", "CircularSector", "圆", CONSTRUCTION, 3, "圆扇形"),
    _c("sector.free", "扇形", "Sector", "圆", CONSTRUCTION, 3, "扇形"),
    _c("sector.three_points", "三点扇形", "SectorThreePoints", "圆", CONSTRUCTION, 3, "三点扇形"),
    _c("circle.osculating", "密切圆", "OsculatingCircle", "圆", CONSTRUCTION, 2, "密切圆"),
    # -- 多边形 ------------------------------------------------------------
    _c("polygon.free", "多边形", "Polygon", "多边形", CONSTRUCTION, 3, "多边形"),
    _c("polygon.regular", "正多边形", "RegularPolygon", "多边形", CONSTRUCTION, 3, "正多边形"),
    _c("polygon.rigid", "刚性多边形", "RigidPolygon", "多边形", CONSTRUCTION, 3, "刚性多边形"),
    # -- 变换 --------------------------------------------------------------
    _c("transform.translate", "平移", "Translate", "变换", CONSTRUCTION, 2, "平移"),
    _c("transform.rotate", "旋转", "Rotate", "变换", CONSTRUCTION, 3, "旋转"),
    _c("transform.dilate", "位似", "Dilate", "变换", CONSTRUCTION, 3, "位似"),
    _c("transform.mirror", "镜像", "Mirror", "变换", CONSTRUCTION, 2, "镜像"),
    _c("transform.reflect", "反射", "Reflect", "变换", CONSTRUCTION, 2, "关于直线反射"),
    # -- 轨迹与曲线 --------------------------------------------------------
    _c("locus.free", "轨迹", "Locus", "轨迹与曲线", CONSTRUCTION, 2, "轨迹"),
    _c("locus.envelope", "包络", "Envelope", "轨迹与曲线", CONSTRUCTION, 1, "包络"),
    _c("curve.parametric", "曲线", "Curve", "轨迹与曲线", CONSTRUCTION, 3, "参数曲线"),
    # -- 测量 --------------------------------------------------------------
    _c("measure.distance", "距离", "Distance", "测量", MEASUREMENT, 2, "两点距离"),
    _c("measure.length", "长度", "Length", "测量", MEASUREMENT, 1, "线段长度"),
    _c("measure.area", "面积", "Area", "测量", MEASUREMENT, 1, "多边形面积"),
    _c("measure.perimeter", "周长", "Perimeter", "测量", MEASUREMENT, 1, "多边形周长"),
    _c("measure.angle", "角度", "Angle", "测量", MEASUREMENT, 3, "三点角"),
    _c("measure.radius", "半径", "Radius", "测量", MEASUREMENT, 1, "圆的半径"),
    _c("measure.slope", "斜率", "Slope", "测量", MEASUREMENT, 1, "直线的斜率"),
    _c("measure.direction", "方向", "Direction", "测量", MEASUREMENT, 1, "直线的方向"),
    # -- 判定 --------------------------------------------------------------
    _c("collinear", "共线", "AreCollinear", "判定", JUDGEMENT, 3, "三点共线", True,
       arg_kinds=("point", "point", "point")),
    _c("concyclic", "共圆", "AreConcyclic", "判定", JUDGEMENT, 4, "四点共圆", True,
       arg_kinds=("point", "point", "point", "point")),
    _c("concurrency", "共点", "AreConcurrent", "判定", JUDGEMENT, 3, "三线共点", True,
       arg_kinds=("line", "line", "line")),
    _c("equal_length", "相等", "AreEqual", "判定", JUDGEMENT, 4, "两线段等长", True,
       arg_kinds=("point", "point", "point", "point")),
    _c("congruent", "全等", "AreCongruent", "判定", JUDGEMENT, 4, "两线段全等",
       arg_kinds=("point", "point", "point", "point")),
    _c("parallel", "平行", "AreParallel", "判定", JUDGEMENT, 2, "两线平行",
       arg_kinds=("line", "line")),
    _c("perpendicular", "垂直", "ArePerpendicular", "判定", JUDGEMENT, 2, "两线垂直", True,
       arg_kinds=("line", "line")),
    _c("tangent_to", "相切", "IsTangent", "判定", JUDGEMENT, 2, "直线与圆相切", True,
       arg_kinds=("line", "circle")),
    _c("point_in", "点在", "PointIn", "判定", JUDGEMENT, 2, "点在对象上",
       arg_kinds=("point", "any")),
    _c("ratio_equal", "比例相等", "SimpleRatio", "判定", JUDGEMENT, 6, "两组线段成比例",
       arg_kinds=("point",) * 6),
    # The three relations below have no GeoGebra equivalent: GeoGebra
    # cannot judge anything, which is the whole reason this product
    # exists. The Chinese names are the ones a teacher would use.
    _c("midpoint_of", "中点", "IsMidpoint", "判定", JUDGEMENT, 3, "M 是 AB 的中点", True,
       arg_kinds=("point", "point", "point")),
    _c(
        "point_perpendicular",
        "垂直",
        "IsPerpendicularPoint",
        "判定",
        JUDGEMENT,
        2,
        "点到直线的连线垂直于该直线",
        True,
        arg_kinds=("point", "line"),
    ),
    _c(
        "angle_bisector",
        "角平分线",
        "IsAngleBisector",
        "判定",
        JUDGEMENT,
        4,
        "AP 平分 ∠BAC",
        True,
        arg_kinds=("point", "point", "point", "point"),
    ),
    # -- 圆锥曲线 ----------------------------------------------------------
    _c("conic.ellipse", "椭圆", "Ellipse", "圆锥曲线", CONSTRUCTION, 3, "椭圆"),
    _c("conic.parabola", "抛物线", "Parabola", "圆锥曲线", CONSTRUCTION, 2, "抛物线"),
    _c("conic.hyperbola", "双曲线", "Hyperbola", "圆锥曲线", CONSTRUCTION, 3, "双曲线"),
    _c("conic.five_points", "二次曲线", "Conic", "圆锥曲线", CONSTRUCTION, 5, "五点二次曲线"),
    _c("conic.directrix", "准线", "Directrix", "圆锥曲线", CONSTRUCTION, 1, "准线"),
    _c("conic.focus", "焦点", "Focus", "圆锥曲线", CONSTRUCTION, 1, "焦点"),
    _c("conic.axes", "轴", "Axes", "圆锥曲线", CONSTRUCTION, 1, "轴"),
    _c(
        "conic.eccentricity",
        "离心率",
        "Eccentricity",
        "圆锥曲线",
        CONSTRUCTION,
        1,
        "离心率",
    ),
)


def by_id(command_id: str) -> CommandSpec | None:
    """The command with this id, if we know it."""
    for command in COMMANDS:
        if command.id == command_id:
            return command
    return None


def lookup(name: str) -> CommandSpec | None:
    """The command with this name -- Chinese or English.

    A teacher may type either, and GeoGebra itself accepts English in
    every language, so both must land on the same command.
    """
    found = lookup_all(name)
    return found[0] if found else None


def lookup_all(name: str) -> list[CommandSpec]:
    """Every command with this name.

    GeoGebra overloads some names: ``交点`` is line-line, line-circle or
    circle-circle, and ``圆`` is centre-radius or centre-through-point.
    Which one is meant depends on the *arguments*, so the whole set is
    returned and the caller picks by fitting the arguments.
    """
    return [
        command
        for command in COMMANDS
        if name == command.name_zh or name == command.name_en
    ]


def by_family(family: str) -> list[CommandSpec]:
    """The commands of one family, in table order."""
    return [command for command in COMMANDS if command.family == family]


def implemented() -> list[CommandSpec]:
    """The commands that are done."""
    return [command for command in COMMANDS if command.implemented]


def coverage_rows() -> list[tuple[str, str, str, bool]]:
    """The coverage table, ready to be written into the plan document."""
    rows: list[tuple[str, str, str, bool]] = []
    for family in FAMILIES:
        for command in by_family(family):
            rows.append((command.name_en, command.name_zh, command.id, command.implemented))
    return rows


__all__ = [
    "COMMANDS",
    "CONSTRUCTION",
    "FAMILIES",
    "JUDGEMENT",
    "MEASUREMENT",
    "SELECTORS",
    "CommandSpec",
    "by_family",
    "by_id",
    "coverage_rows",
    "implemented",
    "lookup",
    "lookup_all",
]
