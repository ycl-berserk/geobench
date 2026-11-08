"""Judges: decide geometric relations.

A judge computes a symbolic expression over the free points' symbols and then
answers one of four verdicts (docs/spec.md section 6.1):

``proved``     the expression is identically zero -- the relation holds for
               *every* admissible placement of the free points;
``refuted``    a concrete admissible placement makes the expression nonzero;
``supported``  the expression vanished in every sample taken, but is not an
               identity;
``undecided``  the kernel cannot decide (unsupported kind, ambiguity).

The distinction between ``proved`` and ``supported`` is the whole point of the
project, so ``supported`` is never silently upgraded.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

import sympy as sp
from sympy import Expr

from geobench.errors import StateError
from geobench.evaluate import free_symbols, symbolic_coords
from geobench.field import FIELD
from geobench.model import Figure
from geobench.operators import OpContext

PROVED = "proved"
REFUTED = "refuted"
SUPPORTED = "supported"
UNDECIDED = "undecided"


@dataclass
class Verdict:
    """The outcome of a judgement, with the evidence the spec requires."""

    kind: str
    verdict: str
    scope: str = "identity"
    evidence: str = ""
    witness: dict[str, object] | None = None
    samples: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "verdict": self.verdict,
            "scope": self.scope,
            "evidence": self.evidence,
            "witness": self.witness,
            "samples": self.samples,
        }


#: The relation is decided for *every* admissible placement of the free points.
IDENTITY = "identity"
#: The relation is decided for the configuration as drawn.
INSTANCE = "instance"

#: The runtime key holding the cached verdicts.
CACHE_VERDICTS = "verdicts"


def _verdict_key(
    figure: Figure, judge_id: str, args: list[str], scope: str
) -> tuple[object, ...]:
    """What a verdict depends on.

    An **identity** verdict does not depend on the placement -- that is
    what "identity" means -- so the key holds only the *versions* of the
    nodes involved, which change exactly when an expression changes.

    An **instance** verdict does depend on the placement, so the free
    points' positions are part of its key.
    """
    versions = figure.runtime.get("versions", {})
    key: list[object] = [
        judge_id,
        tuple(args),
        scope,
        tuple(versions.get(arg, 0) for arg in args),
    ]
    if scope == INSTANCE:
        placements = []
        for node_id, node in figure.nodes.items():
            if node.role == "free" and node.placement is not None:
                placements.append((node_id, tuple(node.placement)))
        key.append(tuple(placements))
    return tuple(key)


@dataclass
class JudgeSpec:
    id: str
    args: tuple[str, ...]
    summary: str
    impl: Callable[[JudgeContext, list[str]], Expr]
    degree: int = 1


@dataclass
class JudgeContext:
    figure: Figure
    ctx: OpContext


# -- expressions -----------------------------------------------------------


def _det3(m: list[list[Expr]]) -> Expr:
    """3x3 determinant, written out so sympy never expands it eagerly."""
    return (
        m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
        - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
        + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
    )


def _det4(m: list[list[Expr]]) -> Expr:
    """4x4 determinant, expanded along the last column.

    Written by hand rather than via ``Matrix.det()``: sympy's generic
    determinant expands eagerly, and on symbolic rational entries that is
    where the time goes. This keeps the expression factored, so the caller
    can cancel it once at the end.
    """
    total: Expr = sp.Integer(0)
    for i in range(4):
        minor = [[m[r][c] for c in range(3)] for r in range(4) if r != i]
        sign = 1 if (i + 3) % 2 == 0 else -1
        total = total + sign * m[i][3] * _det3(minor)
    return total


def _det_collinear(ctx: JudgeContext, args: list[str]) -> Expr:
    x1, y1 = symbolic_coords(ctx.figure, args[0])
    x2, y2 = symbolic_coords(ctx.figure, args[1])
    x3, y3 = symbolic_coords(ctx.figure, args[2])
    return (x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1)


def _dot_perpendicular(ctx: JudgeContext, args: list[str]) -> Expr:
    a1, b1, _ = ctx.ctx.line(args[0])
    a2, b2, _ = ctx.ctx.line(args[1])
    return a1 * a2 + b1 * b2


def _point_line_perpendicular(ctx: JudgeContext, args: list[str]) -> Expr:
    px, py = symbolic_coords(ctx.figure, args[0])
    a, b, c = ctx.ctx.line(args[1])
    return a * px + b * py + c


def _det_concyclic(ctx: JudgeContext, args: list[str]) -> Expr:
    """Four points are concyclic iff this 4x4 determinant vanishes."""
    rows: list[list[Expr]] = []
    for node_id in args[:4]:
        x, y = symbolic_coords(ctx.figure, node_id)
        rows.append([x * x + y * y, x, y, sp.Integer(1)])
    return _det4(rows)


def _equal_length(ctx: JudgeContext, args: list[str]) -> Expr:
    ax, ay = symbolic_coords(ctx.figure, args[0])
    bx, by = symbolic_coords(ctx.figure, args[1])
    cx, cy = symbolic_coords(ctx.figure, args[2])
    dx, dy = symbolic_coords(ctx.figure, args[3])
    return (ax - bx) ** 2 + (ay - by) ** 2 - ((cx - dx) ** 2 + (cy - dy) ** 2)


def _midpoint_of(ctx: JudgeContext, args: list[str]) -> Expr:
    mx, my = symbolic_coords(ctx.figure, args[0])
    ax, ay = symbolic_coords(ctx.figure, args[1])
    bx, by = symbolic_coords(ctx.figure, args[2])
    return (2 * mx - ax - bx) ** 2 + (2 * my - ay - by) ** 2


def _angle_bisector(ctx: JudgeContext, args: list[str]) -> Expr:
    """p lies on the bisector of angle abc iff its distances to ab and bc agree."""
    px, py = symbolic_coords(ctx.figure, args[0])
    ax, ay = symbolic_coords(ctx.figure, args[1])
    bx, by = symbolic_coords(ctx.figure, args[2])
    cx, cy = symbolic_coords(ctx.figure, args[3])
    a1, b1, c1 = (by - cy, cx - bx, bx * cy - cx * by)
    a2, b2, c2 = (ay - by, bx - ax, ax * by - bx * ay)
    d1 = (a1 * px + b1 * py + c1) ** 2 / (a1 * a1 + b1 * b1)
    d2 = (a2 * px + b2 * py + c2) ** 2 / (a2 * a2 + b2 * b2)
    return d1 - d2


def _tangent_to(ctx: JudgeContext, args: list[str]) -> Expr:
    a, b, c = ctx.ctx.line(args[0])
    cx, cy, r2 = ctx.ctx.circle(args[1])
    return (a * cx + b * cy + c) ** 2 - (a * a + b * b) * r2


def _concurrent(ctx: JudgeContext, args: list[str]) -> Expr:
    rows = [list(ctx.ctx.line(node_id)) for node_id in args[:3]]
    return sp.Matrix(rows).det()


def _squared_length(ctx: JudgeContext, first: str, second: str) -> Expr:
    ax, ay = symbolic_coords(ctx.figure, first)
    bx, by = symbolic_coords(ctx.figure, second)
    return (ax - bx) ** 2 + (ay - by) ** 2


def _dot_between(
    ctx: JudgeContext,
    p1: str,
    p2: str,
    q1: str,
    q2: str,
) -> Expr:
    """The dot product of the vector p1p2 with the vector q1q2."""
    x1, y1 = symbolic_coords(ctx.figure, p1)
    x2, y2 = symbolic_coords(ctx.figure, p2)
    x3, y3 = symbolic_coords(ctx.figure, q1)
    x4, y4 = symbolic_coords(ctx.figure, q2)
    return (x2 - x1) * (x4 - x3) + (y2 - y1) * (y4 - y3)


def _parallel(ctx: JudgeContext, args: list[str]) -> Expr:
    """Two lines are parallel iff their normals are proportional."""
    a1, b1, _ = ctx.ctx.line(args[0])
    a2, b2, _ = ctx.ctx.line(args[1])
    return a1 * b2 - b1 * a2


def _point_in(ctx: JudgeContext, args: list[str]) -> Expr:
    """A point lies on a line, a segment or a circle."""
    px, py = symbolic_coords(ctx.figure, args[0])
    node = ctx.figure.node(args[1])
    if node.kind == "circle":
        cx, cy, r2 = ctx.ctx.circle(args[1])
        return (px - cx) ** 2 + (py - cy) ** 2 - r2
    a, b, c = ctx.ctx.as_line(args[1])
    return a * px + b * py + c


def _ratio_equal(ctx: JudgeContext, args: list[str]) -> Expr:
    """Two ratios of segments are equal: AB/CD = EF/GH.

    The lengths are squared, so the equation stays a polynomial: the
    ratio of the squares is the square of the ratio.
    """
    ab = _squared_length(ctx, args[0], args[1])
    cd = _squared_length(ctx, args[2], args[3])
    ef = _squared_length(ctx, args[4], args[5])
    gh = _squared_length(ctx, args[6], args[7])
    return ab * gh - cd * ef


def _circumcenter_of(ctx: JudgeContext, args: list[str]) -> Expr:
    """O is the circumcentre of ABC: the three radii are equal.

    Two equalities at once, written as the **sum of their squares** --
    over the reals, a sum of squares vanishes only when every term does.
    """
    oa = _squared_length(ctx, args[0], args[1])
    ob = _squared_length(ctx, args[0], args[2])
    oc = _squared_length(ctx, args[0], args[3])
    return (oa - ob) ** 2 + (ob - oc) ** 2


def _orthocenter_of(ctx: JudgeContext, args: list[str]) -> Expr:
    """H is the orthocentre of ABC: each altitude is perpendicular.

    Three equalities at once, again as a sum of squares.
    """
    first = _dot_between(ctx, args[0], args[1], args[2], args[3])
    second = _dot_between(ctx, args[0], args[2], args[1], args[3])
    third = _dot_between(ctx, args[0], args[3], args[1], args[2])
    return first**2 + second**2 + third**2


def _centroid_of(ctx: JudgeContext, args: list[str]) -> Expr:
    """G is the centroid of ABC: it is the average of the three vertices."""
    gx, gy = symbolic_coords(ctx.figure, args[0])
    ax, ay = symbolic_coords(ctx.figure, args[1])
    bx, by = symbolic_coords(ctx.figure, args[2])
    cx, cy = symbolic_coords(ctx.figure, args[3])
    return (3 * gx - ax - bx - cx) ** 2 + (3 * gy - ay - by - cy) ** 2


def _angle_equal(ctx: JudgeContext, args: list[str]) -> Expr:
    """The angles ABC and DEF have the same measure.

    The **cosine** is used, because it is injective on [0, 180] -- the
    unsigned angle. The lengths enter through their square roots, which
    is the price of keeping the sign: squaring the cosine would also
    accept a pair of supplementary angles, and that would be a false
    "proved".
    """
    first = _angle_parts(ctx, args[0], args[1], args[2])
    second = _angle_parts(ctx, args[3], args[4], args[5])
    return first[0] * sp.sqrt(second[2]) - second[0] * sp.sqrt(first[2])


def _angle_parts(
    ctx: JudgeContext, vertex: str, first: str, second: str
) -> tuple[Expr, Expr, Expr]:
    """The cosine numerator, the sine numerator and the length product.

    For the angle at B between BA and BC: the dot product and the cross
    product of the two rays, and |BA|^2 |BC|^2 -- the square of the
    product of the two lengths.
    """
    bx, by = symbolic_coords(ctx.figure, vertex)
    ax, ay = symbolic_coords(ctx.figure, first)
    cx, cy = symbolic_coords(ctx.figure, second)
    ux, uy = ax - bx, ay - by
    vx, vy = cx - bx, cy - by
    dot = ux * vx + uy * vy
    cross = ux * vy - uy * vx
    lengths = (ux * ux + uy * uy) * (vx * vx + vy * vy)
    return dot, cross, lengths


_JUDGES: list[JudgeSpec] = [
    JudgeSpec(
        id="collinear",
        args=("p1", "p2", "p3"),
        summary="three points lie on one line",
        impl=_det_collinear,
    ),
    JudgeSpec(
        id="perpendicular",
        args=("l1", "l2"),
        summary="two lines meet at a right angle",
        impl=_dot_perpendicular,
    ),
    JudgeSpec(
        id="point_perpendicular",
        args=("p", "line"),
        summary="a point lies on a line's perpendicular through the origin",
        impl=_point_line_perpendicular,
    ),
    JudgeSpec(
        id="concyclic",
        args=("p1", "p2", "p3", "p4"),
        summary="four points lie on one circle",
        impl=_det_concyclic,
    ),
    JudgeSpec(
        id="equal_length",
        args=("a", "b", "c", "d"),
        summary="two segments have the same length",
        impl=_equal_length,
    ),
    JudgeSpec(
        id="midpoint_of",
        args=("m", "a", "b"),
        summary="m is the midpoint of ab",
        impl=_midpoint_of,
    ),
    JudgeSpec(
        id="angle_bisector",
        args=("p", "a", "b", "c"),
        summary="p lies on the bisector of angle abc",
        impl=_angle_bisector,
    ),
    JudgeSpec(
        id="tangent_to",
        args=("line", "circle"),
        summary="a line is tangent to a circle",
        impl=_tangent_to,
    ),
    JudgeSpec(
        id="concurrency",
        args=("l1", "l2", "l3"),
        summary="three lines meet in one point",
        impl=_concurrent,
    ),
    JudgeSpec(
        id="parallel",
        args=("l1", "l2"),
        summary="two lines are parallel",
        impl=_parallel,
    ),
    JudgeSpec(
        id="point_in",
        args=("p", "object"),
        summary="a point lies on a line, a segment or a circle",
        impl=_point_in,
    ),
    JudgeSpec(
        id="ratio_equal",
        args=("a", "b", "c", "d", "e", "f", "g", "h"),
        summary="two ratios of segments are equal: AB/CD = EF/GH",
        impl=_ratio_equal,
    ),
    JudgeSpec(
        id="circumcenter_of",
        args=("o", "a", "b", "c"),
        summary="o is the circumcentre of abc",
        impl=_circumcenter_of,
    ),
    JudgeSpec(
        id="orthocenter_of",
        args=("h", "a", "b", "c"),
        summary="h is the orthocentre of abc",
        impl=_orthocenter_of,
    ),
    JudgeSpec(
        id="centroid_of",
        args=("g", "a", "b", "c"),
        summary="g is the centroid of abc",
        impl=_centroid_of,
    ),
    JudgeSpec(
        id="angle_equal",
        args=("a", "b", "c", "d", "e", "f"),
        summary="the angles abc and def have the same measure",
        impl=_angle_equal,
    ),
]


class JudgeRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, JudgeSpec] = {}
        for spec in _JUDGES:
            self._specs[spec.id] = spec

    def ids(self) -> list[str]:
        return list(self._specs)

    def has(self, judge_id: str) -> bool:
        return judge_id in self._specs

    def spec(self, judge_id: str) -> JudgeSpec:
        try:
            return self._specs[judge_id]
        except KeyError:
            raise StateError(
                f"unknown judge {judge_id!r}; known judges: {', '.join(self.ids())}"
            ) from None

    def describe(self, judge_id: str) -> dict[str, object]:
        spec = self.spec(judge_id)
        return {
            "id": spec.id,
            "args": list(spec.args),
            "summary": spec.summary,
            "verdicts": [PROVED, REFUTED, SUPPORTED, UNDECIDED],
        }


# -- sampling --------------------------------------------------------------


def _sample(
    figure: Figure, count: int, seed: int
) -> list[dict[sp.Symbol, Expr]]:
    """Random admissible placements of the free points."""
    rng = random.Random(seed)
    samples: list[dict[sp.Symbol, Expr]] = []
    free = [n for n in figure.nodes.values() if n.role == "free" and n.kind == "point"]
    for _ in range(count):
        mapping: dict[sp.Symbol, Expr] = {}
        for node in free:
            if node.coords is None:
                continue
            mapping[FIELD.coerce(node.coords[0])] = sp.Integer(rng.randint(-9, 9))
            mapping[FIELD.coerce(node.coords[1])] = sp.Integer(rng.randint(-9, 9))
        samples.append(mapping)
    return samples


def _witness(
    figure: Figure, mapping: dict[sp.Symbol, Expr]
) -> dict[str, object]:
    """A human-readable counterexample configuration."""
    out: dict[str, object] = {}
    for node in figure.nodes.values():
        if node.role != "free" or node.kind != "point" or node.coords is None:
            continue
        x = FIELD.coerce(node.coords[0]).subs(mapping)
        y = FIELD.coerce(node.coords[1]).subs(mapping)
        out[node.id] = [str(x), str(y)]
    return out


def judge_relation(
    figure: Figure,
    judge_id: str,
    args: list[str],
    registry: JudgeRegistry,
    sample_count: int = 32,
    seed: int = 20261105,
    scope: str = IDENTITY,
) -> Verdict:
    """Decide a relation about a figure, reusing a verdict already reached.

    ``scope`` selects what the verdict means:

    ``IDENTITY``  the relation must hold for *every* admissible placement of
                  the free points. This is the scope that matters for
                  problem authoring: a relation that merely happens to hold in
                  the drawn configuration is not a theorem.
    ``INSTANCE``  the relation is checked for the configuration as drawn, with
                  the free points fixed at their placement. This is the scope
                  for "is the figure I just drew consistent with the claim".

    The verdict is cached on the figure. An identity verdict does not
    change when a free point is dragged -- that is what "identity" means
    -- so the screen can keep showing it without re-running the proof on
    every frame.
    """
    cache = figure.runtime.setdefault(CACHE_VERDICTS, {})
    key = _verdict_key(figure, judge_id, list(args), scope)
    cached = cache.get(key)
    if isinstance(cached, Verdict):
        return cached
    verdict = _judge_uncached(
        figure, judge_id, args, registry, sample_count, seed, scope
    )
    cache[key] = verdict
    return verdict


def _judge_uncached(
    figure: Figure,
    judge_id: str,
    args: list[str],
    registry: JudgeRegistry,
    sample_count: int,
    seed: int,
    scope: str,
) -> Verdict:
    """Decide a relation, without consulting the cache."""
    spec = registry.spec(judge_id)
    if len(args) != len(spec.args):
        raise StateError(
            f"judge {spec.id!r} takes {len(spec.args)} arguments, got {len(args)}"
        )

    # A verdict that has already been reached is reused: an identity
    # verdict does not change when a free point is dragged, so the
    # screen can show it without re-running the proof every frame.
    ctx = JudgeContext(figure=figure, ctx=OpContext(figure))
    try:
        expression = spec.impl(ctx, list(args))
    except StateError as exc:
        return Verdict(kind=spec.id, verdict=UNDECIDED, scope=scope, evidence=str(exc))

    if scope == INSTANCE:
        placement = free_symbols(figure)
        try:
            value = expression.subs(placement)
        except Exception as exc:  # pragma: no cover - defensive
            return Verdict(
                kind=spec.id, verdict=UNDECIDED, scope=scope, evidence=f"substitution failed: {exc}"
            )
        if FIELD.simplify_to_zero(value):
            return Verdict(
                kind=spec.id,
                verdict=PROVED,
                scope=scope,
                evidence=f"the relation holds for the given configuration: {sp.sstr(expression)} = 0",
            )
        return Verdict(
            kind=spec.id,
            verdict=REFUTED,
            scope=scope,
            evidence=(
                f"the relation fails for the given configuration: "
                f"{sp.sstr(expression)} = {sp.sstr(value)}"
            ),
            witness=_witness(figure, placement),
        )

    # Sampling comes *before* the symbolic reduction, and the order is not
    # cosmetic: a counterexample is a proof of falsity and costs milliseconds,
    # while reducing a rational function to zero can take seconds. Refuting
    # first keeps the common case fast; only a relation that survives every
    # sample pays for the symbolic proof.
    samples = _sample(figure, sample_count, seed)
    nonzero: dict[sp.Symbol, Expr] | None = None
    for mapping in samples:
        try:
            value = expression.subs(mapping)
        except Exception:  # pragma: no cover - a bad substitution is not a counterexample
            continue
        if value != 0:
            nonzero = mapping
            break
    if nonzero is not None:
        return Verdict(
            kind=spec.id,
            verdict=REFUTED,
            scope=scope,
            evidence=(
                f"the relation does not hold identically; "
                f"counterexample: {sp.sstr(expression)[:200]} != 0"
            ),
            witness=_witness(figure, nonzero),
            samples=sample_count,
        )

    if FIELD.simplify_to_zero(expression):
        return Verdict(
            kind=spec.id,
            verdict=PROVED,
            scope=scope,
            evidence=f"the expression reduces to 0 identically: {sp.sstr(expression)[:200]}",
        )
    return Verdict(
        kind=spec.id,
        verdict=SUPPORTED,
        scope=scope,
        evidence=(
            f"the relation holds in all {sample_count} samples but the expression "
            f"did not reduce to 0 identically (size {sp.count_ops(expression)} ops): "
            f"{sp.sstr(expression)[:200]}"
        ),
        samples=sample_count,
    )
