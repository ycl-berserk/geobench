"""The cases a figure has to pass.

A skill that nobody measures is a skill nobody can improve.  These are
the requests a teacher actually types, and what each answer has to
contain for it to be a *usable* competition figure.

The expectations are deliberately about the **figure**, not about the
text: a model may write the same figure in a different order, and that
is fine.  What is not fine is a missing object, a claim the drawn
figure does not satisfy, or an object that cannot exist.

The requests are written the way a **problem statement** is written --
naming the points, as problems do (``M``, ``N``, ``H``) -- because
that is both what a teacher types and what makes the expectations
checkable: the names in the expectation are the names in the request.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Case:
    """One request, and what a good answer looks like."""

    name: str
    request: str
    must_include: tuple[str, ...] = ()
    """Objects the figure has to have (by id)."""

    must_not: tuple[str, ...] = ()
    """Objects the figure must not have."""

    must_relate: tuple[tuple[str, tuple[str, ...]], ...] = ()
    """Claims the drawn figure has to satisfy, as (relation, arguments).

    The relation is written the way a paper writes it -- ``("相等",
    ("AB", "AC"))`` -- and it is judged **in the drawn configuration**:
    that is the question "is this picture consistent with what it
    claims", and it is answered in milliseconds.
    """

    must_not_relate: tuple[tuple[str, tuple[str, ...]], ...] = ()
    """Claims the drawn figure must **not** satisfy.

    This is how a *silent substitution* is caught: a model that could
    not draw what was asked for and drew something else instead --
    without saying so -- is caught here.
    """

    acute: tuple[str, str, str] = ()
    """The three vertices of a triangle that has to be acute."""

    right_at: tuple[str, str, str] = ()
    """A triangle whose angle at the **second** vertex has to be right."""

    min_segments: int = 0
    """The figure has to have at least this many segments.

    A competition figure *draws* the sides: a triangle whose sides are
    not on the paper is not a figure of a triangle.
    """

    expect_wall: bool = False
    """The request cannot be done, and the point is that the kernel
    **catches it**.  The figure is supposed to have problems -- the
    model hits the wall and the wall holds."""

    tags: tuple[str, ...] = field(default=())
    """What this case is about, for the report."""


CASES: tuple[Case, ...] = (
    Case(
        name="锐角三角形 + 三个心",
        request="画一个锐角三角形ABC，标出它的外心O、垂心H和重心G",
        must_include=("A", "B", "C", "O", "H", "G"),
        must_relate=(
            ("外心", ("O", "A", "B", "C")),
            ("垂心", ("H", "A", "B", "C")),
            ("重心", ("G", "A", "B", "C")),
        ),
        acute=("A", "B", "C"),
        min_segments=3,
        tags=("心", "锐角"),
    ),
    Case(
        name="外接圆 + 圆上的点",
        request="作三角形ABC的外接圆c，在圆c上取一点P，连接PA、PB、PC",
        must_include=("A", "B", "C", "P", "c"),
        must_relate=(("点在", ("P", "c")),),
        min_segments=3,
        tags=("圆", "圆上的点"),
    ),
    Case(
        name="九点圆",
        request="在△ABC中作A到BC的垂线，垂足为H，取BC的中点D、AB的中点M、"
        "AC的中点N，证明D、M、N、H共圆",
        must_include=("A", "B", "C", "D", "M", "N", "H"),
        must_relate=(
            ("中点", ("D", "B", "C")),
            ("中点", ("M", "A", "B")),
            ("中点", ("N", "A", "C")),
            ("共圆", ("D", "M", "N", "H")),
        ),
        min_segments=3,
        tags=("垂足", "中点", "共圆", "九点圆"),
    ),
    Case(
        name="等腰三角形的顶角平分线",
        request="画一个等腰三角形ABC，AB=AC，作顶角A的平分线与BC交于D",
        must_include=("A", "B", "C", "D"),
        must_relate=(
            ("相等", ("AB", "AC")),
            ("中点", ("D", "B", "C")),
        ),
        min_segments=3,
        tags=("角平分线", "等腰"),
    ),
    Case(
        name="三条中线与重心",
        request="作三角形ABC的三条中线AD、BE、CF，并求重心G",
        must_include=("A", "B", "C", "D", "E", "F", "G"),
        must_relate=(
            ("中点", ("D", "B", "C")),
            ("中点", ("E", "A", "C")),
            ("中点", ("F", "A", "B")),
            ("重心", ("G", "A", "B", "C")),
        ),
        min_segments=3,
        tags=("中线", "重心"),
    ),
    Case(
        name="圆上一点的切线",
        request="画一个圆c，在圆c上取一点P，作圆c在P点的切线t",
        must_include=("P", "c", "t"),
        must_relate=(("相切", ("t", "c")),),
        tags=("切线",),
    ),
    Case(
        name="圆外一点的切线",
        request="画一个圆c，圆外取一点P，过P作圆c的切线t",
        must_include=("P", "c", "t"),
        must_relate=(("相切", ("t", "c")),),
        tags=("切线",),
    ),
    Case(
        name="做不到的切线（圆内点）",
        request="画一个圆c，在圆c内取一点P，过P作圆c的切线t",
        must_include=("P", "c", "t"),
        must_not_relate=(("点在", ("P", "c")),),
        expect_wall=True,
        tags=("退化", "切线", "拒绝"),
        # A tangent from a point inside the circle does not exist.  The
        # model may well try; the kernel catches it, and the loop asks
        # for another try.  What is being measured here is not the
        # figure -- it is that **the wall holds**: the software does not
        # quietly hand out a figure that is not what was asked for.
        # A model that puts P *on* the circle instead (and says
        # nothing) has substituted silently, and that fails too.
    ),
    Case(
        name="直角三角形的斜边中点",
        request="画一个直角三角形ABC，∠A=90°，作斜边BC的中点M",
        must_include=("A", "B", "C", "M"),
        must_relate=(("中点", ("M", "B", "C")),),
        right_at=("B", "A", "C"),
        min_segments=3,
        tags=("直角", "中点"),
    ),
)
