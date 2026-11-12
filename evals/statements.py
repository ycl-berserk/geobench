"""The real problem statements -- the ones a teacher actually types.

The cases in :mod:`evals.cases` measure the **contract**: does the
model know our language?  Those cases were written by us, with one
phrasing each, and the skill even hands the model a table of good
coordinates to reuse.  That is not the same question as "type a
problem, get a figure that satisfies it".

These are the other half.  Each statement is a real competition or
textbook problem, phrased the way a teacher would type it into the
panel, and each carries the **conditions** the problem states -- a
length, an angle, a perpendicularity, a tangency.  A figure is an
answer only if it satisfies them.

Every statement also carries a **reference**: a hand-written figure
that satisfies the conditions.  The reference does two jobs:

- it checks the checks (a condition that the reference fails is a
  condition that is wrong, and the test suite says so);
- it is the figure the model is trying to produce, so the difference
  between the two is what "the model got it wrong" means.

The statements are grouped by what they lean on, so a report says
*where* the channel is weak rather than just how weak it is.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from evals.conditions import (
    Condition,
    angle_is,
    circle_through,
    concyclic,
    distances_to_sides_equal,
    equal_angles,
    equal_length,
    equilateral,
    exists,
    incircle_exists,
    length_is,
    midpoint_is,
    on_circle,
    on_segment,
    parallel,
    perpendicular,
    tangent_to,
    triangle_is_acute,
)


@dataclass(frozen=True)
class Statement:
    """One problem statement, and what a correct answer has to satisfy."""

    name: str
    request: str
    """The statement, as a teacher types it into the panel."""

    conditions: tuple[Condition, ...] = ()
    """What the figure has to satisfy."""

    must_include: tuple[str, ...] = ()
    """The objects the statement names."""

    reference: str = ""
    """A hand-written figure that satisfies the conditions."""

    tags: tuple[str, ...] = field(default=())
    """What the statement leans on.

    The **first** tag is the group the report sorts by: 数值条件 (the
    numbers in the statement), 关系构造 (the relations the model has to
    build), 定理型 (a figure that shows a theorem), 改述 (the same
    problem asked another way).
    """


STATEMENTS: tuple[Statement, ...] = (
    # -- lengths and angles: the model has to *compute* ---------------------
    Statement(
        name="直角三角形（3-4-5）+ 垂足",
        request="画一个直角三角形ABC，∠A=90°，AB=3，AC=4，作A到BC的垂线，垂足为H",
        conditions=(
            angle_is(90.0, "A", "B", "C"),
            length_is(3.0, "A", "B"),
            length_is(4.0, "A", "C"),
            on_segment("H", "B", "C"),
            perpendicular("A", "H", "B", "C"),
        ),
        must_include=("A", "B", "C", "H"),
        reference="""
点 A(0,0) B(0,3) C(4,0)
AB = 线段(A, B)
AC = 线段(A, C)
BC = 线段(B, C)
bc = 直线(B, C)
H = 垂足(A, bc)
AH = 线段(A, H)
""",
        tags=("数值条件", "数值长度", "垂足"),
    ),
    Statement(
        name="平行四边形（边长 + 角）",
        request="画一个平行四边形ABCD，AB=5，AD=3，∠DAB=60°",
        conditions=(
            length_is(5.0, "A", "B"),
            length_is(3.0, "A", "D"),
            angle_is(60.0, "A", "D", "B"),
            parallel("A", "B", "D", "C"),
            parallel("A", "D", "B", "C"),
            equal_length("A", "B", "D", "C"),
        ),
        must_include=("A", "B", "C", "D"),
        reference="""
点 A(0,0) B(5,0)
E = 旋转(B, 60, A)
D = 位似(E, 3/5, A)
C = 平移(B, D)
AB = 线段(A, B)
BC = 线段(B, C)
CD = 线段(C, D)
DA = 线段(D, A)
""",
        tags=("数值条件", "数值长度", "数值角度", "平行四边形"),
    ),
    Statement(
        name="矩形（边长）",
        request="画一个矩形ABCD，AB=3，BC=4",
        conditions=(
            length_is(3.0, "A", "B"),
            length_is(4.0, "B", "C"),
            angle_is(90.0, "A", "B", "D"),
            angle_is(90.0, "B", "A", "C"),
            parallel("A", "B", "D", "C"),
            parallel("A", "D", "B", "C"),
        ),
        must_include=("A", "B", "C", "D"),
        reference="""
点 A(0,0) B(3,0) C(3,4) D(0,4)
AB = 线段(A, B)
BC = 线段(B, C)
CD = 线段(C, D)
DA = 线段(D, A)
""",
        tags=("数值条件", "数值长度", "矩形"),
    ),
    Statement(
        name="菱形（对角线）",
        request="画一个菱形ABCD，对角线AC=6，BD=8",
        conditions=(
            equal_length("A", "B", "B", "C"),
            equal_length("A", "B", "C", "D"),
            equal_length("A", "B", "D", "A"),
            length_is(6.0, "A", "C"),
            length_is(8.0, "B", "D"),
            perpendicular("A", "C", "B", "D"),
        ),
        must_include=("A", "B", "C", "D"),
        reference="""
点 A(-3,0) C(3,0) B(0,-4) D(0,4)
AB = 线段(A, B)
BC = 线段(B, C)
CD = 线段(C, D)
DA = 线段(D, A)
""",
        tags=("数值条件", "数值长度", "菱形"),
    ),
    Statement(
        name="等边三角形 + 外接圆 + 内切圆",
        request="画一个等边三角形ABC，边长4，作它的外接圆和内切圆",
        conditions=(
            equilateral("A", "B", "C"),
            length_is(4.0, "A", "B"),
            circle_through("A", "B", "C"),
            incircle_exists("A", "B", "C"),
        ),
        must_include=("A", "B", "C"),
        reference="""
点 A(0,0) B(4,0)
C = 旋转(B, 60, A)
AB = 线段(A, B)
BC = 线段(B, C)
CA = 线段(C, A)
O = 外心(A, B, C)
w = 外接圆(A, B, C)
I = 内心(A, B, C)
n = 内切圆(A, B, C)
""",
        tags=("数值条件", "等边", "圆"),
    ),
    Statement(
        name="圆外一点的切线（带长度）",
        request="画一个圆c，圆心为O，半径2，在圆外取一点P，使OP=5，过P作圆c的切线t",
        conditions=(
            length_is(5.0, "O", "P"),
            tangent_to("t", "c"),
            exists("O", "c", "P", "t"),
        ),
        must_include=("O", "c", "P", "t"),
        reference="""
点 O(0,0) A(2,0) P(5,0)
c = 圆(O, A)
t = 切线(P, c)
OP = 线段(O, P)
""",
        tags=("数值条件", "切线", "数值长度"),
    ),
    # -- relations: the model has to construct them -------------------------
    Statement(
        name="等腰三角形 + 中点 + 高",
        request="画一个等腰三角形ABC，AB=AC，D是BC的中点，作AD",
        conditions=(
            equal_length("A", "B", "A", "C"),
            midpoint_is("D", "B", "C"),
            perpendicular("A", "D", "B", "C"),
        ),
        must_include=("A", "B", "C", "D"),
        reference="""
点 A(0,3) B(-2,0) C(2,0)
AB = 线段(A, B)
AC = 线段(A, C)
BC = 线段(B, C)
D = 中点(B, C)
AD = 线段(A, D)
""",
        tags=("关系构造", "等腰", "中点"),
    ),
    Statement(
        name="等腰三角形的顶角平分线",
        request="画一个等腰三角形ABC，AB=AC，作顶角A的平分线与BC交于D",
        conditions=(
            equal_length("A", "B", "A", "C"),
            equal_angles("A", "B", "D", "A", "D", "C"),
            on_segment("D", "B", "C"),
        ),
        must_include=("A", "B", "C", "D"),
        reference="""
点 A(0,3) B(-2,0) C(2,0)
AB = 线段(A, B)
AC = 线段(A, C)
BC = 线段(B, C)
m = 角平分线(B, A, C)
D = 交点(BC, m)
""",
        tags=("关系构造", "等腰", "角平分线"),
    ),
    Statement(
        name="三条中线与重心",
        request="作三角形ABC的三条中线AD、BE、CF，并求重心G",
        conditions=(
            midpoint_is("D", "B", "C"),
            midpoint_is("E", "A", "C"),
            midpoint_is("F", "A", "B"),
            on_segment("G", "A", "D"),
            on_segment("G", "B", "E"),
            on_segment("G", "C", "F"),
        ),
        must_include=("A", "B", "C", "D", "E", "F", "G"),
        reference="""
点 A(2,3) B(0,0) C(5,0)
D = 中点(B, C)
E = 中点(A, C)
F = 中点(A, B)
AD = 线段(A, D)
BE = 线段(B, E)
CF = 线段(C, F)
G = 重心(A, B, C)
""",
        tags=("关系构造", "中线", "重心"),
    ),
    Statement(
        name="锐角三角形 + 三个心",
        request="画一个锐角三角形ABC，标出它的外心O、垂心H和重心G",
        conditions=(
            triangle_is_acute("A", "B", "C"),
            exists("O", "H", "G"),
            equal_length("O", "A", "O", "B"),
            equal_length("O", "B", "O", "C"),
            perpendicular("A", "H", "B", "C"),
        ),
        must_include=("A", "B", "C", "O", "H", "G"),
        reference="""
点 A(2,3) B(0,0) C(5,0)
AB = 线段(A, B)
BC = 线段(B, C)
CA = 线段(C, A)
O = 外心(A, B, C)
H = 垂心(A, B, C)
G = 重心(A, B, C)
""",
        tags=("关系构造", "心", "锐角"),
    ),
    Statement(
        name="三条高交于垂心",
        request="画一个锐角三角形ABC，作它的高AD、BE、CF，交于H",
        conditions=(
            triangle_is_acute("A", "B", "C"),
            perpendicular("A", "D", "B", "C"),
            perpendicular("B", "E", "A", "C"),
            perpendicular("C", "F", "A", "B"),
            on_segment("H", "A", "D"),
            on_segment("H", "B", "E"),
        ),
        must_include=("A", "B", "C", "D", "E", "F", "H"),
        reference="""
点 A(2,3) B(0,0) C(5,0)
bc = 直线(B, C)
ac = 直线(A, C)
ab = 直线(A, B)
D = 垂足(A, bc)
E = 垂足(B, ac)
F = 垂足(C, ab)
AD = 线段(A, D)
BE = 线段(B, E)
CF = 线段(C, F)
H = 交点(AD, BE)
""",
        tags=("关系构造", "高", "垂心"),
    ),
    Statement(
        name="内心与角平分线",
        request="作三角形ABC的内心I和角平分线BD",
        conditions=(
            distances_to_sides_equal("I", "A", "B", "C"),
            equal_angles("B", "A", "D", "B", "D", "C"),
            on_segment("D", "A", "C"),
        ),
        must_include=("A", "B", "C", "I", "D"),
        reference="""
点 A(0,3) B(-2,0) C(2,0)
AB = 线段(A, B)
AC = 线段(A, C)
BC = 线段(B, C)
I = 内心(A, B, C)
m = 角平分线(A, B, C)
D = 交点(AC, m)
""",
        tags=("关系构造", "内心", "角平分线"),
    ),
    Statement(
        name="九点圆（用户的那道题）",
        request="在△ABC中作A到BC的垂线，垂足为H，取BC的中点D、AB的中点M、AC的中点N，证明D、M、N、H共圆",
        conditions=(
            on_segment("H", "B", "C"),
            perpendicular("A", "H", "B", "C"),
            midpoint_is("D", "B", "C"),
            midpoint_is("M", "A", "B"),
            midpoint_is("N", "A", "C"),
            concyclic("D", "M", "N", "H"),
        ),
        must_include=("A", "B", "C", "D", "M", "N", "H"),
        reference="""
点 A(2,3) B(0,0) C(5,0)
AB = 线段(A, B)
BC = 线段(B, C)
CA = 线段(C, A)
bc = 直线(B, C)
ah = 垂直(A, bc)
H = 交点(ah, bc)
D = 中点(B, C)
M = 中点(A, B)
N = 中点(A, C)
""",
        tags=("定理型", "九点圆", "共圆", "垂足"),
    ),
    Statement(
        name="圆上的点与三条连线",
        request="作三角形ABC的外接圆c，在圆c上取一点P，连接PA、PB、PC",
        conditions=(
            on_circle("P", "c"),
            exists("P", "c", "PA", "PB", "PC"),
        ),
        must_include=("A", "B", "C", "P", "c", "PA", "PB", "PC"),
        reference="""
点 A(0,0) B(4,0) C(1,3)
AB = 线段(A, B)
BC = 线段(B, C)
CA = 线段(C, A)
c = 外接圆(A, B, C)
P = 圆上的点(c, 1/4)
PA = 线段(P, A)
PB = 线段(P, B)
PC = 线段(P, C)
""",
        tags=("定理型", "圆上的点",),
    ),
    Statement(
        name="圆上一点的切线",
        request="画一个圆c，在圆c上取一点P，作圆c在P点的切线t，连结OP",
        conditions=(
            on_circle("P", "c"),
            tangent_to("t", "c"),
            exists("t", "OP"),
        ),
        must_include=("O", "c", "P", "t"),
        reference="""
点 O(0,0) A(2,0)
c = 圆(O, A)
P = 圆上的点(c, 1/4)
t = 切线(P, c)
OP = 线段(O, P)
""",
        tags=("定理型", "切线",),
    ),
    Statement(
        name="平行四边形的对角线互相平分",
        request="画一个平行四边形ABCD，连接对角线AC、BD，交于O",
        conditions=(
            parallel("A", "B", "D", "C"),
            parallel("A", "D", "B", "C"),
            midpoint_is("O", "A", "C"),
            midpoint_is("O", "B", "D"),
        ),
        must_include=("A", "B", "C", "D", "O"),
        reference="""
点 A(0,0) B(5,0) D(2,3)
C = 平移(B, D)
AB = 线段(A, B)
BC = 线段(B, C)
CD = 线段(C, D)
DA = 线段(D, A)
ac = 直线(A, C)
bd = 直线(B, D)
O = 交点(ac, bd)
""",
        tags=("定理型", "平行四边形", "对角线"),
    ),
    Statement(
        name="直角三角形的外接圆（斜边中点）",
        request="画一个直角三角形ABC，∠A=90°，作它的外接圆c，取斜边BC的中点M",
        conditions=(
            angle_is(90.0, "A", "B", "C"),
            midpoint_is("M", "B", "C"),
            equal_length("M", "A", "M", "B"),
            equal_length("M", "B", "M", "C"),
            on_circle("B", "c"),
            on_circle("C", "c"),
        ),
        must_include=("A", "B", "C", "c", "M"),
        reference="""
点 A(0,0) B(0,3) C(4,0)
AB = 线段(A, B)
AC = 线段(A, C)
BC = 线段(B, C)
O = 外心(A, B, C)
c = 外接圆(A, B, C)
M = 中点(B, C)
""",
        tags=("定理型", "直角", "外接圆", "中点"),
    ),
    Statement(
        name="三角形的外接圆与内切圆",
        request="作三角形ABC的外接圆c和内切圆n",
        conditions=(
            on_circle("A", "c"),
            on_circle("B", "c"),
            on_circle("C", "c"),
            exists("c", "n"),
        ),
        must_include=("A", "B", "C", "c", "n"),
        reference="""
点 A(0,0) B(4,0) C(1,3)
AB = 线段(A, B)
BC = 线段(B, C)
CA = 线段(C, A)
O = 外心(A, B, C)
c = 外接圆(A, B, C)
n = 内切圆(A, B, C)
""",
        tags=("定理型", "圆",),
    ),
    Statement(
        name="两条中线的交点是重心",
        request="作三角形ABC的中线AD、BE，交于G",
        conditions=(
            midpoint_is("D", "B", "C"),
            midpoint_is("E", "A", "C"),
            on_segment("G", "A", "D"),
            on_segment("G", "B", "E"),
        ),
        must_include=("A", "B", "C", "D", "E", "G"),
        reference="""
点 A(2,3) B(0,0) C(5,0)
D = 中点(B, C)
E = 中点(A, C)
AD = 线段(A, D)
BE = 线段(B, E)
G = 交点(AD, BE)
""",
        tags=("定理型", "中线", "重心"),
    ),
    Statement(
        name="四点在同一圆上",
        request="画一个圆c，在圆c上依次取四点A、B、C、D，作四边形ABCD",
        conditions=(
            on_circle("A", "c"),
            on_circle("B", "c"),
            on_circle("C", "c"),
            on_circle("D", "c"),
        ),
        must_include=("A", "B", "C", "D", "c"),
        reference="""
点 O(0,0) A(2,0)
c = 圆(O, A)
B = 圆上的点(c, 1/4)
C = 圆上的点(c, 1/2)
D = 圆上的点(c, 3/4)
AB = 线段(A, B)
BC = 线段(B, C)
CD = 线段(C, D)
DA = 线段(D, A)
""",
        tags=("定理型", "圆上的点", "圆内接四边形"),
    ),
    # -- the same problem, asked differently -------------------------------
    Statement(
        name="等腰三角形（另一种说法）",
        request="作一个顶角为40°的等腰三角形ABC，AB=AC",
        conditions=(
            equal_length("A", "B", "A", "C"),
            angle_is(40.0, "A", "B", "C"),
        ),
        must_include=("A", "B", "C"),
        reference="""
点 A(0,0) B(5,0)
C = 旋转(B, 40, A)
AB = 线段(A, B)
AC = 线段(A, C)
BC = 线段(B, C)
""",
        tags=("改述", "等腰", "数值角度", "改述"),
    ),
    Statement(
        name="中点（另一种说法）",
        request="在三角形ABC中，D是边BC的中点，把AD画出来",
        conditions=(midpoint_is("D", "B", "C"),),
        must_include=("A", "B", "C", "D"),
        reference="""
点 A(2,3) B(0,0) C(5,0)
AB = 线段(A, B)
BC = 线段(B, C)
CA = 线段(C, A)
D = 中点(B, C)
AD = 线段(A, D)
""",
        tags=("改述", "中点", "改述"),
    ),
)


__all__ = ["STATEMENTS", "Statement"]
