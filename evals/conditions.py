"""The conditions a problem statement carries, and how they are checked.

A real problem statement does not say "draw a triangle"; it says
"AB=AC", "∠A=90°", "AC=4", "P is outside the circle".  Those are
**conditions on the figure**, and a figure is only an answer if it
satisfies them.

This module is that vocabulary: a condition is a name, a sentence the
teacher would recognise, and a check that says whether the drawn
figure satisfies it.  The checks run on the **drawn** figure -- the
coordinates the teacher sees -- because that is what "does this
picture match the problem" means.

Every check answers three ways:

- ``True``  -- the figure satisfies it;
- ``False`` -- the figure does not;
- ``None``  -- it could not be asked (an object the figure lacks).

``None`` is not ``False``: a figure that does not have point ``H`` has
not *contradicted* the statement, it has not answered it.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from geobench.model import Figure

#: How close two lengths have to be to count as equal.
LENGTH_TOLERANCE = 1e-6

#: How close an angle has to be to count as the wanted one.
ANGLE_TOLERANCE = 1e-6

#: How close a point has to be to a line, relative to the line's size.
LINE_TOLERANCE = 1e-6


@dataclass(frozen=True)
class Condition:
    """One condition, named the way the problem names it."""

    name: str
    check: Callable[[Figure], bool | None]


# -- the geometry the checks need ------------------------------------------


def coordinates(figure: Figure, name: str) -> tuple[float, float] | None:
    """Where a point is on the drawing, or ``None`` when it has no place."""
    node = figure.nodes.get(name)
    if node is None or node.kind != "point" or node.placement is None:
        return None
    try:
        x, y = node.placement
        return (float(x), float(y))
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return None


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _angle_at(
    first: tuple[float, float], at: tuple[float, float], third: tuple[float, float]
) -> float | None:
    u = (first[0] - at[0], first[1] - at[1])
    v = (third[0] - at[0], third[1] - at[1])
    nu, nv = math.hypot(*u), math.hypot(*v)
    if nu == 0 or nv == 0:
        return None
    cos = max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / (nu * nv)))
    return math.degrees(math.acos(cos))


def _close(got: float, want: float, tolerance: float) -> bool:
    return abs(got - want) <= tolerance * max(1.0, abs(got), abs(want))


def _points(figure: Figure, *names: str) -> list[tuple[float, float]] | None:
    """The places of the named points, or ``None`` when one is missing."""
    places: list[tuple[float, float]] = []
    for name in names:
        place = coordinates(figure, name)
        if place is None:
            return None
        places.append(place)
    return places


def _line_of(figure: Figure, name: str) -> tuple[float, float, float] | None:
    """The drawn line of a node, whatever shape it has.

    A segment and a line are both lines for the purpose of "is this
    perpendicular to that"; the segment's supporting line is used.
    """
    node = figure.nodes.get(name)
    if node is None or node.kind not in ("line", "segment"):
        return None
    drawn = node.cache.get("numeric", {}).get("line")
    if drawn is None:
        return None
    a, b, c = drawn
    return (float(a), float(b), float(c))


def _circle_of(figure: Figure, name: str) -> tuple[float, float, float] | None:
    """The drawn circle: centre and squared radius."""
    node = figure.nodes.get(name)
    if node is None or node.kind != "circle":
        return None
    drawn = node.cache.get("numeric", {}).get("circle")
    if drawn is None:
        return None
    cx, cy, r2 = drawn
    return (float(cx), float(cy), float(r2))


# -- the checks -------------------------------------------------------------


def equal_length(first: str, second: str, third: str, fourth: str) -> Condition:
    """``AB = CD``."""

    def check(figure: Figure) -> bool | None:
        places = _points(figure, first, second, third, fourth)
        if places is None:
            return None
        a, b, c, d = places
        return _close(_distance(a, b), _distance(c, d), LENGTH_TOLERANCE)

    return Condition(f"{first}{second} = {third}{fourth}", check)


def length_is(want: float, first: str, second: str) -> Condition:
    """``AB = 4``."""

    def check(figure: Figure) -> bool | None:
        places = _points(figure, first, second)
        if places is None:
            return None
        return _close(_distance(*places), want, LENGTH_TOLERANCE)

    return Condition(f"{first}{second} = {want}", check)


def angle_is(want: float, at: str, first: str, third: str) -> Condition:
    """``∠at = 90°`` -- the angle at ``at`` between ``first`` and ``third``."""

    def check(figure: Figure) -> bool | None:
        places = _points(figure, at, first, third)
        if places is None:
            return None
        vertex, one, other = places
        got = _angle_at(one, vertex, other)
        return None if got is None else _close(got, want, ANGLE_TOLERANCE)

    return Condition(f"∠{at} = {want:g}°", check)


def perpendicular(p: str, q: str, r: str, s: str) -> Condition:
    """``PQ ⊥ RS`` -- between the lines through the named points."""

    def check(figure: Figure) -> bool | None:
        places = _points(figure, p, q, r, s)
        if places is None:
            return None
        a, b, c, d = places
        u = (a[0] - b[0], a[1] - b[1])
        v = (c[0] - d[0], c[1] - d[1])
        nu, nv = math.hypot(*u), math.hypot(*v)
        if nu == 0 or nv == 0:
            return None
        dot = u[0] * v[0] + u[1] * v[1]
        return abs(dot) <= LINE_TOLERANCE * nu * nv

    return Condition(f"{p}{q} ⊥ {r}{s}", check)


def parallel(p: str, q: str, r: str, s: str) -> Condition:
    """``PQ ∥ RS``."""

    def check(figure: Figure) -> bool | None:
        places = _points(figure, p, q, r, s)
        if places is None:
            return None
        a, b, c, d = places
        u = (a[0] - b[0], a[1] - b[1])
        v = (c[0] - d[0], c[1] - d[1])
        nu, nv = math.hypot(*u), math.hypot(*v)
        if nu == 0 or nv == 0:
            return None
        cross = u[0] * v[1] - u[1] * v[0]
        return abs(cross) <= LINE_TOLERANCE * nu * nv

    return Condition(f"{p}{q} ∥ {r}{s}", check)


def collinear(p: str, q: str, r: str) -> Condition:
    """``P, Q, R`` on one line."""

    def check(figure: Figure) -> bool | None:
        places = _points(figure, p, q, r)
        if places is None:
            return None
        a, b, c = places
        u = (b[0] - a[0], b[1] - a[1])
        v = (c[0] - a[0], c[1] - a[1])
        nu, nv = math.hypot(*u), math.hypot(*v)
        if nu == 0 or nv == 0:
            return None
        cross = u[0] * v[1] - u[1] * v[0]
        return abs(cross) <= LINE_TOLERANCE * nu * nv

    return Condition(f"{p}{q}{r} 共线", check)


def midpoint_is(mid: str, first: str, second: str) -> Condition:
    """``M`` is the midpoint of ``PQ``."""

    def check(figure: Figure) -> bool | None:
        places = _points(figure, mid, first, second)
        if places is None:
            return None
        m, a, b = places
        centre = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        return _distance(m, centre) <= LENGTH_TOLERANCE * max(1.0, _distance(a, b))

    return Condition(f"{mid} 是 {first}{second} 的中点", check)


def on_line(point: str, p: str, q: str) -> Condition:
    """``P`` lies on the line through ``Q`` and ``R``."""

    def check(figure: Figure) -> bool | None:
        places = _points(figure, point, p, q)
        if places is None:
            return None
        a, b, c = places
        u = (c[0] - b[0], c[1] - b[1])
        v = (a[0] - b[0], a[1] - b[1])
        nu = math.hypot(*u)
        if nu == 0:
            return None
        cross = u[0] * v[1] - u[1] * v[0]
        return abs(cross) <= LINE_TOLERANCE * nu * math.hypot(*v)

    return Condition(f"{point} 在 {p}{q} 上", check)


def on_segment(point: str, p: str, q: str) -> Condition:
    """``P`` lies on the segment ``QR`` -- between the ends, not beyond."""

    def check(figure: Figure) -> bool | None:
        places = _points(figure, point, p, q)
        if places is None:
            return None
        a, b, c = places
        u = (c[0] - b[0], c[1] - b[1])
        v = (a[0] - b[0], a[1] - b[1])
        nu, nv = math.hypot(*u), math.hypot(*v)
        if nu == 0 or nv == 0:
            return None
        cross = u[0] * v[1] - u[1] * v[0]
        if abs(cross) > LINE_TOLERANCE * nu * nv:
            return False
        dot = (a[0] - b[0]) * (c[0] - b[0]) + (a[1] - b[1]) * (c[1] - b[1])
        return -LINE_TOLERANCE <= dot <= nu * nu + LINE_TOLERANCE

    return Condition(f"{point} 在线段 {p}{q} 上", check)


def on_circle(point: str, circle: str) -> Condition:
    """``P`` lies on the circle.

    The circle knows its own centre, so the check does not need one
    named separately -- which matters, because a statement that says
    "the circle c" has not named its centre.
    """

    def check(figure: Figure) -> bool | None:
        data = _circle_of(figure, circle)
        place = coordinates(figure, point)
        if data is None or place is None:
            return None
        cx, cy, r2 = data
        return _close((place[0] - cx) ** 2 + (place[1] - cy) ** 2, r2, LENGTH_TOLERANCE)

    return Condition(f"{point} 在圆 {circle} 上", check)


def tangent_to(line: str, circle: str) -> Condition:
    """The line touches the circle."""

    def check(figure: Figure) -> bool | None:
        data = _circle_of(figure, circle)
        drawn = _line_of(figure, line)
        if data is None or drawn is None:
            return None
        cx, cy, r2 = data
        a, b, c = drawn
        norm = math.hypot(a, b)
        if norm == 0:
            return None
        distance = abs(a * cx + b * cy + c) / norm
        return _close(distance * distance, r2, LENGTH_TOLERANCE)

    return Condition(f"{line} 与圆 {circle} 相切", check)


def concyclic(first: str, second: str, third: str, fourth: str) -> Condition:
    """Four points on one circle.

    The circle through the first three points is computed, and the
    fourth is asked whether it lies on it.  Three collinear points have
    no circle, and four collinear points are not on one either -- so
    that case answers "no", not "maybe".
    """

    def check(figure: Figure) -> bool | None:
        places = _points(figure, first, second, third, fourth)
        if places is None:
            return None
        (x1, y1), (x2, y2), (x3, y3), (x4, y4) = places
        # The centre of the circle through the first three points: the
        # perpendicular bisectors meet there.
        denominator = 2.0 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
        if abs(denominator) <= 1e-12:
            return False  # collinear: no circle through them
        square1 = x1 * x1 + y1 * y1
        square2 = x2 * x2 + y2 * y2
        square3 = x3 * x3 + y3 * y3
        cx = (
            square1 * (y2 - y3) + square2 * (y3 - y1) + square3 * (y1 - y2)
        ) / denominator
        cy = (
            square1 * (x3 - x2) + square2 * (x1 - x3) + square3 * (x2 - x1)
        ) / denominator
        radius2 = (x1 - cx) ** 2 + (y1 - cy) ** 2
        distance2 = (x4 - cx) ** 2 + (y4 - cy) ** 2
        scale = max(1.0, radius2)
        return abs(distance2 - radius2) <= LENGTH_TOLERANCE * scale

    return Condition(f"{first}{second}{third}{fourth} 共圆", check)


def triangle_is_acute(a: str, b: str, c: str) -> Condition:
    """Every angle of the triangle is smaller than a right angle."""

    def check(figure: Figure) -> bool | None:
        places = _points(figure, a, b, c)
        if places is None:
            return None
        first, second, third = places
        for x, y, z in ((first, second, third), (second, third, first), (third, first, second)):
            angle = _angle_at(y, x, z)
            if angle is None:
                return None
            if angle >= 90.0:
                return False
        return True

    return Condition(f"{a}{b}{c} 是锐角三角形", check)


def triangle_is_right(a: str, b: str, c: str) -> Condition:
    """The triangle has a right angle."""

    def check(figure: Figure) -> bool | None:
        places = _points(figure, a, b, c)
        if places is None:
            return None
        first, second, third = places
        for x, y, z in ((first, second, third), (second, third, first), (third, first, second)):
            angle = _angle_at(y, x, z)
            if angle is None:
                return None
            if abs(angle - 90.0) <= ANGLE_TOLERANCE * 90.0:
                return True
        return False

    return Condition(f"{a}{b}{c} 是直角三角形", check)


def equilateral(a: str, b: str, c: str) -> Condition:
    """All three sides are the same length."""

    def check(figure: Figure) -> bool | None:
        places = _points(figure, a, b, c)
        if places is None:
            return None
        first, second, third = places
        sides = (
            _distance(first, second),
            _distance(second, third),
            _distance(third, first),
        )
        return all(
            _close(side, sides[0], LENGTH_TOLERANCE) for side in sides
        ) and sides[0] > 0

    return Condition(f"{a}{b}{c} 是等边三角形", check)


def equal_angles(
    at: str, first: str, third: str, other_at: str, other_first: str, other_third: str
) -> Condition:
    """Two angles are equal."""

    def check(figure: Figure) -> bool | None:
        places = _points(figure, at, first, third, other_at, other_first, other_third)
        if places is None:
            return None
        vertex, one, other = places[0], places[1], places[2]
        other_vertex, other_one, other_other = places[3], places[4], places[5]
        left = _angle_at(one, vertex, other)
        right = _angle_at(other_one, other_vertex, other_other)
        if left is None or right is None:
            return None
        return _close(left, right, ANGLE_TOLERANCE)

    return Condition(
        f"∠{first}{at}{third} = ∠{other_first}{other_at}{other_third}", check
    )


def distances_to_sides_equal(
    point: str, a: str, b: str, c: str
) -> Condition:
    """The point is as far from the three sides as each other -- an incenter."""

    def check(figure: Figure) -> bool | None:
        places = _points(figure, point, a, b, c)
        if places is None:
            return None
        p = places[0]
        sides = [(places[1], places[2]), (places[2], places[3]), (places[3], places[1])]
        distances: list[float] = []
        for (u, v) in sides:
            edge = (v[0] - u[0], v[1] - u[1])
            length = math.hypot(*edge)
            if length == 0:
                return None
            distance = abs(edge[0] * (p[1] - u[1]) - edge[1] * (p[0] - u[0])) / length
            distances.append(distance)
        return all(
            _close(distance, distances[0], 1e-4) for distance in distances
        ) and distances[0] > 0

    return Condition(f"{point} 是 {a}{b}{c} 的内心", check)


def exists(*names: str) -> Condition:
    """The objects are there."""

    def check(figure: Figure) -> bool | None:
        for name in names:
            node = figure.nodes.get(name)
            if node is None:
                return False
            if node.kind == "point" and coordinates(figure, name) is None:
                return False
        return True

    return Condition("、".join(names) + " 都在", check)


def _circles(figure: Figure) -> list[tuple[str, float, float, float]]:
    """Every circle in the figure: its name, centre and squared radius."""
    found: list[tuple[str, float, float, float]] = []
    for node_id, node in figure.nodes.items():
        if node.kind != "circle":
            continue
        data = _circle_of(figure, node_id)
        if data is None:
            continue
        found.append((node_id, data[0], data[1], data[2]))
    return found


def circle_through(*names: str) -> Condition:
    """There is a circle through all the named points.

    The statement may not have named the circle -- "作它的外接圆" does
    not say what to call it -- so the check looks for the *circle*, not
    for a name.
    """

    def check(figure: Figure) -> bool | None:
        places = _points(figure, *names)
        if places is None:
            return None
        for _name, cx, cy, r2 in _circles(figure):
            if all(
                _close((x - cx) ** 2 + (y - cy) ** 2, r2, LENGTH_TOLERANCE)
                for x, y in places
            ):
                return True
        return False

    return Condition("有圆过 " + "、".join(names), check)


def incircle_exists(a: str, b: str, c: str) -> Condition:
    """There is a circle tangent to all three sides of the triangle."""

    def check(figure: Figure) -> bool | None:
        places = _points(figure, a, b, c)
        if places is None:
            return None
        first, second, third = places
        sides = [(first, second), (second, third), (third, first)]
        for _name, cx, cy, r2 in _circles(figure):
            radius = math.sqrt(r2)
            if radius == 0:
                continue
            touches = True
            for u, v in sides:
                edge = (v[0] - u[0], v[1] - u[1])
                length = math.hypot(*edge)
                if length == 0:
                    touches = False
                    break
                distance = abs(edge[0] * (cy - u[1]) - edge[1] * (cx - u[0])) / length
                if not _close(distance, radius, 1e-4):
                    touches = False
                    break
            if touches:
                return True
        return False

    return Condition(f"有圆与 {a}{b}{c} 的三边都相切", check)


__all__ = [
    "Condition",
    "angle_is",
    "circle_through",
    "collinear",
    "concyclic",
    "coordinates",
    "distances_to_sides_equal",
    "equal_angles",
    "equal_length",
    "equilateral",
    "exists",
    "incircle_exists",
    "length_is",
    "midpoint_is",
    "on_circle",
    "on_line",
    "on_segment",
    "parallel",
    "perpendicular",
    "tangent_to",
    "triangle_is_acute",
    "triangle_is_right",
]
