"""Generate the oracle fixture batteries.

Fixtures are deterministic: the same script produces the same files, so the
battery is reproducible and reviewable in a diff. Every operator gets at least
20 configurations, of which at least 3 are degenerate (docs/spec.md 5.3).

Run with::

    python scripts/gen_fixtures.py
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "oracle"))

from harness import Fixture, save_fixtures  # noqa: E402

SEED = 20261105
TARGET = 24
DEGENERATE = 4


def _points(rng: random.Random, count: int, spread: int = 8) -> dict[str, tuple[str, str]]:
    names = ["A", "B", "C", "D", "E", "F"][:count]
    out: dict[str, tuple[str, str]] = {}
    for name in names:
        out[name] = (str(rng.randint(-spread, spread)), str(rng.randint(-spread, spread)))
    return out


def _non_degenerate_triangle(rng: random.Random) -> dict[str, tuple[str, str]]:
    """Three points that are certainly not collinear (a wide-ish triangle)."""
    while True:
        points = _points(rng, 3)
        ax, ay = (int(v) for v in points["A"])
        bx, by = (int(v) for v in points["B"])
        cx, cy = (int(v) for v in points["C"])
        area2 = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
        if area2 != 0:
            return points


def _distinct_pair(rng: random.Random) -> dict[str, tuple[str, str]]:
    while True:
        points = _points(rng, 2)
        if points["A"] != points["B"]:
            return points


def _slanted_pair(rng: random.Random) -> dict[str, tuple[str, str]]:
    """Two points whose line is neither vertical nor horizontal."""
    while True:
        points = _points(rng, 2)
        if points["A"][0] != points["B"][0] and points["A"][1] != points["B"][1]:
            return points


def _distinct_points(rng: random.Random, count: int) -> dict[str, tuple[str, str]]:
    """Points that are all different from each other."""
    names = ["A", "B", "C", "D", "E", "F"][:count]
    while True:
        points = _points(rng, count)
        if len({points[name] for name in names}) == count:
            return points


def _two_non_coincident_lines(rng: random.Random) -> dict[str, tuple[str, str]]:
    """Two lines that are not parallel and do not share every point."""
    while True:
        points = _points(rng, 4)
        a, b, c, d = points["A"], points["B"], points["C"], points["D"]
        det = (int(a[1]) - int(b[1])) * (int(c[0]) - int(d[0])) - (
            int(c[1]) - int(d[1])
        ) * (int(a[0]) - int(b[0]))
        if det != 0 and a != c:
            return points


def _parallel_lines(rng: random.Random) -> dict[str, tuple[str, str]]:
    """Two distinct lines with the same direction, so they never meet."""
    while True:
        points = _points(rng, 2)
        ax, ay = int(points["A"][0]), int(points["A"][1])
        bx, by = int(points["B"][0]), int(points["B"][1])
        if ax == bx and ay == by:
            continue
        # Translate the first line by a non-zero vector along its normal.
        dx, dy = bx - ax, by - ay
        length = (dx * dx + dy * dy) ** 0.5
        nx, ny = -dy / length, dx / length
        shift = rng.randint(1, 5)
        offset = (round(nx * shift), round(ny * shift))
        if offset == (0, 0):
            continue
        return {
            "A": points["A"],
            "B": points["B"],
            "C": (str(ax + offset[0]), str(ay + offset[1])),
            "D": (str(bx + offset[0]), str(by + offset[1])),
        }


def _collinear_triple(rng: random.Random) -> dict[str, tuple[str, str]]:
    """Three points on one line, spread out."""
    x0, y0 = rng.randint(-6, 6), rng.randint(-6, 6)
    dx, dy = rng.randint(1, 3), rng.randint(-3, 3)
    return {
        "A": (str(x0), str(y0)),
        "B": (str(x0 + dx), str(y0 + dy)),
        "C": (str(x0 + 2 * dx), str(y0 + 2 * dy)),
    }


def _centre_and_radius(
    points: dict[str, tuple[str, str]], names: tuple[str, str, str]
) -> tuple[float, float, float]:
    """The circumcentre and radius of three points, in floats."""
    ax, ay = (float(v) for v in points[names[0]])
    bx, by = (float(v) for v in points[names[1]])
    cx, cy = (float(v) for v in points[names[2]])
    determinant = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if determinant == 0:
        return 0.0, 0.0, 0.0
    s1 = ax * ax + ay * ay
    s2 = bx * bx + by * by
    s3 = cx * cx + cy * cy
    ux = (s1 * (by - cy) + s2 * (cy - ay) + s3 * (ay - by)) / determinant
    uy = (s1 * (cx - bx) + s2 * (ax - cx) + s3 * (bx - ax)) / determinant
    r2 = (ax - ux) ** 2 + (ay - uy) ** 2
    return ux, uy, r2**0.5


def _two_intersecting_circles(rng: random.Random) -> dict[str, tuple[str, str]]:
    """Six points whose two triples give circles that meet in two points."""
    while True:
        points = _points(rng, 6, spread=5)
        ux1, uy1, r1 = _centre_and_radius(points, ("A", "B", "C"))
        ux2, uy2, r2 = _centre_and_radius(points, ("D", "E", "F"))
        if r1 == 0 or r2 == 0:
            continue
        distance = ((ux1 - ux2) ** 2 + (uy1 - uy2) ** 2) ** 0.5
        # Two points of intersection when neither circle contains the
        # other and they are not too far apart.
        if abs(r1 - r2) < distance < r1 + r2:
            return points


def battery(op_id: str, rng: random.Random) -> list[Fixture]:
    fixtures: list[Fixture] = []

    def add(points: dict[str, tuple[str, str]], args: list[str], kind: str, expect: str, note: str) -> None:
        fixtures.append(Fixture(points=points, args=args, kind=kind, expect=expect, note=note))

    if op_id == "point.midpoint":
        for _ in range(TARGET):
            pts = _distinct_pair(rng)
            add(pts, ["A", "B"], "normal", "value", "distinct endpoints")
        for _ in range(DEGENERATE):
            pts = _distinct_pair(rng)
            same = {"A": pts["A"], "B": pts["A"]}
            add(same, ["A", "B"], "degenerate", "error", "zero-length segment")
    elif op_id == "point.centroid":
        # The centroid is defined for every triple, including collinear ones.
        for _ in range(TARGET):
            pts = _non_degenerate_triangle(rng)
            add(pts, ["A", "B", "C"], "normal", "value", "non-degenerate triangle")
        for _ in range(DEGENERATE):
            pts = _collinear_triple(rng)
            add(pts, ["A", "B", "C"], "edge", "value", "collinear triple still has a centroid")
    elif op_id == "point.foot":
        for _ in range(TARGET):
            pts = _distinct_pair(rng)
            add(pts, ["A", "line:B,A"], "normal", "value", "projection onto a line")
        for _ in range(DEGENERATE):
            pts = _distinct_pair(rng)
            add(pts, ["A", "line:A,A"], "degenerate", "error", "degenerate line")
    elif op_id in {"point.circumcenter", "point.incenter", "point.orthocenter"}:
        for _ in range(TARGET):
            pts = _non_degenerate_triangle(rng)
            add(pts, ["A", "B", "C"], "normal", "value", "non-degenerate triangle")
        for _ in range(DEGENERATE):
            pts = _collinear_triple(rng)
            add(pts, ["A", "B", "C"], "degenerate", "error", "collinear triple")
    elif op_id == "point.intersect_lines":
        for _ in range(TARGET):
            pts = _two_non_coincident_lines(rng)
            add(pts, ["line:A,B", "line:C,D"], "normal", "value", "crossing lines")
        for _ in range(DEGENERATE):
            pts = _points(rng, 2)
            add(pts, ["line:A,B", "line:A,B"], "degenerate", "error", "identical lines")
            pts2 = _parallel_lines(rng)
            add(pts2, ["line:A,B", "line:C,D"], "degenerate", "error", "parallel lines")
    elif op_id == "line.free":
        for _ in range(TARGET):
            pts = _distinct_pair(rng)
            add(pts, ["A", "B"], "normal", "value", "two distinct points")
        for _ in range(DEGENERATE):
            pts = _distinct_pair(rng)
            same = {"A": pts["A"], "B": pts["A"]}
            add(same, ["A", "B"], "degenerate", "error", "identical points")
    elif op_id in {"line.perpendicular_through", "line.parallel_through"}:
        for _ in range(TARGET):
            pts = _points(rng, 3)
            add(pts, ["C", "line:A,B"], "normal", "value", "through a point")
        for _ in range(DEGENERATE):
            pts = _points(rng, 3)
            add(pts, ["C", "line:A,A"], "degenerate", "error", "degenerate line")
    elif op_id == "point.intersect_line_circle":
        # The line AB is a chord of the circle through A, B, C, so it meets
        # the circle exactly in A and B -- two intersections, always.
        for _ in range(TARGET):
            pts = _non_degenerate_triangle(rng)
            add(pts, ["line:A,B", "circle:A,B,C", "0"], "normal", "value", "first root")
            add(pts, ["line:A,B", "circle:A,B,C", "1"], "normal", "value", "second root")
        # A line through one point of the circle and one point off it: the
        # 'other intersection' is then well defined.
        for _ in range(DEGENERATE):
            pts = _non_degenerate_triangle(rng)
            ax, ay = (int(v) for v in pts["A"])
            pts["E"] = (str(ax + 1), str(ay + 4))
            add(
                pts,
                ["line:A,E", "circle:A,B,C", "other"],
                "normal",
                "value",
                "the intersection other than A",
            )
        # Tangent and disjoint lines: the operator must refuse both.
        for offset in range(DEGENERATE):
            pts = {
                "A": ("0", "0"),
                "B": ("2", "0"),
                "C": ("1", "1"),
                "E": ("0", str(2 + offset)),
                "F": ("0", str(4 + offset)),
                "G": ("1", str(4 + offset)),
            }
            add(pts, ["line:A,E", "circle:A,B,C", "0"], "degenerate", "error", "tangent line")
            add(
                pts,
                ["line:F,G", "circle:A,B,C", "0"],
                "degenerate",
                "error",
                "line misses the circle",
            )
    elif op_id == "segment.free":
        for _ in range(TARGET):
            pts = _distinct_pair(rng)
            add(pts, ["A", "B"], "normal", "value", "two distinct endpoints")
        for _ in range(DEGENERATE):
            pts = _distinct_pair(rng)
            same = {"A": pts["A"], "B": pts["A"]}
            add(same, ["A", "B"], "degenerate", "error", "identical endpoints")
    elif op_id == "circle.through":
        for _ in range(TARGET):
            pts = _non_degenerate_triangle(rng)
            add(pts, ["A", "B", "C"], "normal", "value", "non-degenerate triangle")
        for _ in range(DEGENERATE):
            pts = _collinear_triple(rng)
            add(pts, ["A", "B", "C"], "degenerate", "error", "collinear triple")
    elif op_id == "circle.free":
        for _ in range(TARGET):
            pts = _points(rng, 1)
            r2 = str(rng.randint(1, 36))
            add(pts, ["A", r2], "normal", "value", "positive squared radius")
        for _ in range(DEGENERATE):
            pts = _points(rng, 1)
            add(pts, ["A", "0"], "degenerate", "error", "zero radius")
    elif op_id == "line.perpendicular_bisector":
        for _ in range(TARGET):
            pts = _distinct_pair(rng)
            add(pts, ["A", "B"], "normal", "value", "two distinct endpoints")
        # A vertical segment and a horizontal one: the bisector is then
        # horizontal or vertical, which the coefficients must still get
        # right (no slope anywhere).
        add({"A": ("0", "0"), "B": ("0", "5")}, ["A", "B"], "edge", "value", "vertical segment")
        add({"A": ("0", "0"), "B": ("5", "0")}, ["A", "B"], "edge", "value", "horizontal segment")
        for _ in range(DEGENERATE):
            pts = _distinct_pair(rng)
            same = {"A": pts["A"], "B": pts["A"]}
            add(same, ["A", "B"], "degenerate", "error", "zero-length segment")
    elif op_id == "line.angle_bisector":
        for _ in range(TARGET):
            pts = _non_degenerate_triangle(rng)
            add(pts, ["A", "B", "C"], "normal", "value", "non-degenerate triangle")
        # A right angle: the bisector is at 45 degrees, which is where a
        # sign error in the formula shows up first.
        add(
            {"A": ("0", "0"), "B": ("1", "1"), "C": ("0", "4")},
            ["A", "B", "C"],
            "edge",
            "value",
            "narrow angle",
        )
        add(
            {"A": ("0", "0"), "B": ("0", "0"), "C": ("4", "0")},
            ["A", "B", "C"],
            "degenerate",
            "error",
            "one side of the angle has zero length",
        )
        for _ in range(DEGENERATE):
            pts = _distinct_pair(rng)
            add(
                {"A": pts["A"], "B": pts["A"], "C": pts["B"]},
                ["A", "B", "C"],
                "degenerate",
                "error",
                "the vertex coincides with one side's endpoint",
            )
    elif op_id == "line.tangent":
        # The point of tangency is one of the three points the circle
        # passes through, so it is on the circle by construction.
        for _ in range(TARGET):
            pts = _non_degenerate_triangle(rng)
            add(pts, ["A", "circle:A,B,C"], "normal", "value", "tangent at a vertex")
        # A point **outside** the circle: there are two tangents from it,
        # and the kernel keeps one of them -- which one is a convention,
        # not a fact of the geometry, so the oracle returns both.
        for _ in range(TARGET):
            pts = {"A": ("0", "0"), "D": (str(rng.randint(3, 9)), str(rng.randint(-4, 4)))}
            add(
                pts,
                ["D", "circle:A,4"],
                "normal",
                "value",
                "tangent from a point outside the circle",
            )
        # A point **inside** the circle: there is no tangent from there,
        # and the centre is the sharpest case of it.  The circle has
        # centre A and squared radius 4, so a point is inside when its
        # distance from A is less than 2.
        for coords in (("0", "0"), ("1", "0"), ("0", "1"), ("1", "1"), ("-1", "-1")):
            pts = {"A": ("0", "0"), "D": coords}
            note = (
                "the point is the centre of the circle"
                if coords == ("0", "0")
                else "the point is inside the circle"
            )
            add(pts, ["D", "circle:A,4"], "degenerate", "error", note)
    elif op_id == "point.intersect_circles":
        for _ in range(TARGET):
            pts = _two_intersecting_circles(rng)
            add(pts, ["circle:A,B,C", "circle:D,E,F", "0"], "normal", "value", "first root")
            add(pts, ["circle:A,B,C", "circle:D,E,F", "1"], "normal", "value", "second root")
        # The same circle twice: concentric, so there is no pair of points.
        pts = _points(rng, 3)
        add(pts, ["circle:A,B,C", "circle:A,B,C", "0"], "degenerate", "error", "the same circle twice")
        # Two circles far apart: they never meet.
        far = {
            "A": ("0", "0"),
            "B": ("4", "0"),
            "C": ("2", "3"),
            "D": ("40", "0"),
            "E": ("44", "0"),
            "F": ("42", "3"),
        }
        add(far, ["circle:A,B,C", "circle:D,E,F", "0"], "degenerate", "error", "the circles do not meet")
        # One circle strictly inside the other: they never meet either.
        inside = {
            "A": ("0", "0"),
            "B": ("4", "0"),
            "C": ("2", "3"),
            "D": ("1", "1"),
            "E": ("3", "1"),
            "F": ("2", "2"),
        }
        add(
            inside,
            ["circle:A,B,C", "circle:D,E,F", "0"],
            "degenerate",
            "error",
            "one circle inside the other",
        )
    elif op_id == "point.nearest_on_object":
        for _ in range(TARGET):
            pts = _points(rng, 3)
            add(pts, ["A", "line:B,C"], "normal", "value", "nearest point on a line")
            add(pts, ["A", "segment:B,C"], "normal", "value", "nearest point on a segment")
        # The foot falls outside the segment: the nearest point is then
        # the nearer end, which is what a foot is not.
        add(
            {"A": ("10", "0"), "B": ("0", "0"), "C": ("2", "0")},
            ["A", "segment:B,C"],
            "edge",
            "value",
            "the foot is beyond the end of the segment",
        )
        for _ in range(DEGENERATE):
            pts = _points(rng, 3)
            add(pts, ["A", "segment:B,B"], "degenerate", "error", "zero-length segment")
    elif op_id == "circle.center_point":
        for _ in range(TARGET):
            pts = _distinct_pair(rng)
            add(pts, ["A", "B"], "normal", "value", "centre and a point on the circle")
        for _ in range(DEGENERATE):
            pts = _distinct_pair(rng)
            add(
                {"A": pts["A"], "B": pts["A"]},
                ["A", "B"],
                "degenerate",
                "error",
                "the point is the centre",
            )
    elif op_id == "circle.incircle":
        for _ in range(TARGET):
            pts = _non_degenerate_triangle(rng)
            add(pts, ["A", "B", "C"], "normal", "value", "non-degenerate triangle")
        for _ in range(DEGENERATE):
            pts = _collinear_triple(rng)
            add(pts, ["A", "B", "C"], "degenerate", "error", "collinear triple")
    elif op_id == "polygon.free":
        for _ in range(TARGET):
            pts = _distinct_points(rng, 4)
            add(pts, ["A", "B", "C"], "normal", "value", "a triangle")
            add(pts, ["A", "B", "C", "D"], "normal", "value", "a quadrilateral")
        # Three collinear vertices: still a polygon, just a flat corner.
        add(
            {"A": ("0", "0"), "B": ("2", "0"), "C": ("4", "0"), "D": ("2", "3")},
            ["A", "B", "C", "D"],
            "edge",
            "value",
            "three collinear vertices",
        )
        for _ in range(DEGENERATE):
            pts = _points(rng, 4)
            add(
                {"A": pts["A"], "B": pts["A"], "C": pts["C"], "D": pts["D"]},
                ["A", "B", "C", "D"],
                "degenerate",
                "error",
                "two vertices coincide",
            )
    elif op_id == "arc.three_points":
        for _ in range(TARGET):
            pts = _non_degenerate_triangle(rng)
            add(pts, ["A", "B", "C"], "normal", "value", "three points on a circle")
        for _ in range(DEGENERATE):
            pts = _collinear_triple(rng)
            add(pts, ["A", "B", "C"], "degenerate", "error", "collinear: no circle")
        add(
            {"A": ("2", "0"), "B": ("0", "2"), "C": ("-2", "0")},
            ["A", "B", "C"],
            "edge",
            "value",
            "a semicircle",
        )
    elif op_id == "sector.three_points":
        for _ in range(TARGET):
            # The three points must be different: the sector runs from the
            # centre to its two ends, and an end that sits on the centre
            # has no end at all.
            pts = _distinct_points(rng, 3)
            add(
                {"O": pts["A"], "A": pts["B"], "B": pts["C"]},
                ["O", "A", "B"],
                "normal",
                "value",
                "a centre and two ends",
            )
        for _ in range(DEGENERATE):
            pts = _points(rng, 3)
            add(
                {"O": pts["A"], "A": pts["A"], "B": pts["C"]},
                ["O", "A", "B"],
                "degenerate",
                "error",
                "the radius would be zero",
            )
        add(
            {"O": ("0", "0"), "A": ("3", "4"), "B": ("-4", "3")},
            ["O", "A", "B"],
            "edge",
            "value",
            "the ends are not on the same circle",
        )
    elif op_id == "ray.free":
        for _ in range(TARGET):
            pts = _distinct_pair(rng)
            add(pts, ["A", "B"], "normal", "value", "a ray through two points")
        add(
            {"A": ("0", "0"), "B": ("1", "0")},
            ["A", "B"],
            "edge",
            "value",
            "a horizontal ray",
        )
        add(
            {"A": ("0", "0"), "B": ("0", "1")},
            ["A", "B"],
            "edge",
            "value",
            "a vertical ray",
        )
        for _ in range(DEGENERATE):
            pts = _points(rng, 2)
            add(
                {"A": pts["A"], "B": pts["A"]},
                ["A", "B"],
                "degenerate",
                "error",
                "the two points coincide",
            )
    elif op_id == "polyline.free":
        for _ in range(TARGET):
            pts = _points(rng, 4)
            add(pts, ["A", "B", "C"], "normal", "value", "three points")
            add(pts, ["A", "B", "C", "D"], "normal", "value", "four points")
        add(
            {"A": ("0", "0"), "B": ("2", "0"), "C": ("4", "0")},
            ["A", "B", "C"],
            "edge",
            "value",
            "a straight polyline",
        )
        for _ in range(DEGENERATE):
            pts = _points(rng, 4)
            add(
                {"A": pts["A"], "B": pts["A"], "C": pts["C"]},
                ["A", "B", "C"],
                "degenerate",
                "error",
                "two neighbours coincide",
            )
    elif op_id == "polygon.regular":
        for _ in range(TARGET):
            pts = _distinct_pair(rng)
            add(pts, ["A", "B", "3"], "normal", "value", "a triangle")
            add(pts, ["A", "B", "4"], "normal", "value", "a square")
            add(pts, ["A", "B", "5"], "normal", "value", "a pentagon")
        add(
            {"A": ("0", "0"), "B": ("2", "0")},
            ["A", "B", "6"],
            "edge",
            "value",
            "a hexagon",
        )
        for _ in range(DEGENERATE):
            pts = _distinct_pair(rng)
            add(pts, ["A", "B", "2"], "degenerate", "error", "two vertices")
        add(
            {"A": ("1", "1"), "B": ("1", "1")},
            ["A", "B", "4"],
            "degenerate",
            "error",
            "the vertex is the centre",
        )
    elif op_id == "point.polygon_vertex":
        for _ in range(TARGET):
            pts = _points(rng, 4)
            add(pts, ["polygon:A,B,C,D", "1"], "normal", "value", "the first vertex")
            add(pts, ["polygon:A,B,C,D", "3"], "normal", "value", "the third vertex")
        add(
            {"A": ("0", "0"), "B": ("2", "0"), "C": ("2", "2"), "D": ("0", "2")},
            ["polygon:A,B,C,D", "4"],
            "edge",
            "value",
            "the last vertex",
        )
        add(
            {"A": ("0", "0"), "B": ("2", "0"), "C": ("2", "2"), "D": ("0", "2")},
            ["polygon:A,B,C,D", "5"],
            "degenerate",
            "error",
            "there is no fifth vertex",
        )
        add(
            {"A": ("0", "0"), "B": ("2", "0"), "C": ("2", "2"), "D": ("0", "2")},
            ["polygon:A,B,C,D", "0"],
            "degenerate",
            "error",
            "the vertices are counted from one",
        )
        add(
            {"A": ("0", "0"), "B": ("2", "0"), "C": ("2", "2"), "D": ("0", "2")},
            ["polygon:A,B,C,D", "-1"],
            "degenerate",
            "error",
            "a negative vertex number",
        )
    elif op_id == "point.affine_ratio":
        for _ in range(TARGET):
            pts = _distinct_pair(rng)
            add(pts, ["A", "B", "1", "1"], "normal", "value", "the midpoint")
            add(pts, ["A", "B", "2", "1"], "normal", "value", "twice as far along")
        add(
            {"A": ("0", "0"), "B": ("6", "0")},
            ["A", "B", "1", "2"],
            "edge",
            "value",
            "one part in three",
        )
        add(
            {"A": ("0", "0"), "B": ("6", "0")},
            ["A", "B", "0", "0"],
            "degenerate",
            "error",
            "the ratio 0 : 0 divides nothing",
        )
        add(
            {"A": ("0", "0"), "B": ("6", "0")},
            ["A", "B", "1", "-1"],
            "degenerate",
            "error",
            "the two parts of the ratio cancel out",
        )
        add(
            {"A": ("0", "0"), "B": ("6", "0")},
            ["A", "B", "2", "-2"],
            "degenerate",
            "error",
            "the two parts of the ratio cancel out again",
        )
        add(
            {"A": ("0", "0"), "B": ("6", "0")},
            ["A", "B", "0", "2"],
            "edge",
            "value",
            "the point is the first end itself",
        )
    elif op_id == "line.polar":
        for _ in range(TARGET):
            pts = _non_degenerate_triangle(rng)
            pts["P"] = _points(rng, 4)["D"]
            add(pts, ["P", "circle:A,B,C"], "normal", "value", "the polar of a point")
        add(
            {"A": ("0", "0"), "B": ("3", "0"), "C": ("0", "4")},
            ["A", "circle:A,B,C"],
            "edge",
            "value",
            "a point on the circle: its polar is the tangent",
        )
        add(
            {"O": ("0", "0")},
            ["O", "circle:O,25"],
            "degenerate",
            "error",
            "the centre of the circle has no polar",
        )
        add(
            {"O": ("0", "0")},
            ["O", "circle:O,0"],
            "degenerate",
            "error",
            "a circle of no radius has no polar",
        )
        add(
            {"O": ("3", "4")},
            ["O", "circle:O,25"],
            "degenerate",
            "error",
            "the centre of the circle has no polar",
        )
    elif op_id == "measure.distance":
        for _ in range(TARGET):
            pts = _distinct_pair(rng)
            add(pts, ["A", "B"], "normal", "value", "two points")
        add(
            {"A": ("2", "3"), "B": ("2", "3")},
            ["A", "B"],
            "edge",
            "value",
            "the distance from a point to itself",
        )
        add(
            {"A": ("0", "0"), "B": ("12", "0")},
            ["A", "B"],
            "edge",
            "value",
            "a horizontal pair",
        )
        add(
            {"A": ("0", "0"), "B": ("3", "4")},
            ["A", "B"],
            "edge",
            "value",
            "a three-four-five pair",
        )
    elif op_id == "measure.length":
        for _ in range(TARGET):
            pts = _distinct_pair(rng)
            add(pts, ["segment:A,B"], "normal", "value", "a segment")
        add(
            {"A": ("1", "1"), "B": ("1", "1")},
            ["segment:A,B"],
            "edge",
            "value",
            "a segment of no length",
        )
        add(
            {"A": ("0", "0"), "B": ("5", "0")},
            ["segment:A,B"],
            "edge",
            "value",
            "a horizontal segment",
        )
        add(
            {"A": ("0", "0"), "B": ("0", "7")},
            ["segment:A,B"],
            "edge",
            "value",
            "a vertical segment",
        )
    elif op_id in {"measure.area", "measure.perimeter"}:
        for _ in range(TARGET):
            pts = _distinct_points(rng, 4)
            add(pts, ["polygon:A,B,C,D"], "normal", "value", "a quadrilateral")
        add(
            {"A": ("0", "0"), "B": ("1", "0"), "C": ("2", "0"), "D": ("3", "0")},
            ["polygon:A,B,C,D"],
            "edge",
            "value",
            "a flat polygon",
        )
        add(
            {"A": ("0", "0"), "B": ("4", "0"), "C": ("2", "3")},
            ["polygon:A,B,C"],
            "edge",
            "value",
            "a triangle",
        )
        add(
            {"A": ("0", "0"), "B": ("2", "0"), "C": ("2", "2"), "D": ("0", "2")},
            ["polygon:A,B,C,D"],
            "edge",
            "value",
            "a square",
        )
    elif op_id == "measure.angle":
        for _ in range(TARGET):
            pts = _non_degenerate_triangle(rng)
            add(pts, ["A", "B", "C"], "normal", "value", "the angle of a triangle")
        add(
            {"A": ("0", "0"), "B": ("1", "0"), "C": ("1", "1")},
            ["A", "B", "C"],
            "edge",
            "value",
            "a right angle",
        )
        add(
            {"A": ("0", "0"), "B": ("1", "0"), "C": ("2", "1/1000")},
            ["A", "B", "C"],
            "edge",
            "value",
            "a very small angle",
        )
        add(
            {"A": ("0", "0"), "B": ("1", "1"), "C": ("-1", "1")},
            ["A", "B", "C"],
            "edge",
            "value",
            "a right angle at the vertex",
        )
        for _ in range(DEGENERATE):
            pts = _points(rng, 3)
            add(
                {"A": pts["A"], "B": pts["A"], "C": pts["C"]},
                ["A", "B", "C"],
                "degenerate",
                "error",
                "the vertex lies on one of the other points",
            )
    elif op_id == "measure.radius":
        for _ in range(TARGET):
            pts = _non_degenerate_triangle(rng)
            add(pts, ["circle:A,B,C"], "normal", "value", "the circle through three points")
        add(
            {"A": ("0", "0"), "B": ("1", "0"), "C": ("0", "1")},
            ["circle:A,B,C"],
            "edge",
            "value",
            "a circle of radius one",
        )
        add(
            {"A": ("0", "0"), "B": ("10", "0"), "C": ("0", "10")},
            ["circle:A,B,C"],
            "edge",
            "value",
            "a big circle",
        )
        add(
            {"O": ("0", "0")},
            ["circle:O,25"],
            "edge",
            "value",
            "a circle of radius five about a given centre",
        )
    elif op_id == "measure.slope":
        for _ in range(TARGET):
            pts = _slanted_pair(rng)
            add(pts, ["line:A,B"], "normal", "value", "a slanting line")
        add(
            {"A": ("0", "0"), "B": ("5", "0")},
            ["line:A,B"],
            "edge",
            "value",
            "a horizontal line",
        )
        add(
            {"A": ("0", "0"), "B": ("1", "1")},
            ["line:A,B"],
            "edge",
            "value",
            "a line at forty-five degrees",
        )
        for _ in range(DEGENERATE):
            pts = _points(rng, 2)
            add(
                {"A": pts["A"], "B": (pts["A"][0], "7")},
                ["line:A,B"],
                "degenerate",
                "error",
                "a vertical line has no finite slope",
            )
    elif op_id == "measure.direction":
        for _ in range(TARGET):
            pts = _distinct_pair(rng)
            add(pts, ["line:A,B"], "normal", "value", "a slanting line")
        add(
            {"A": ("0", "0"), "B": ("0", "5")},
            ["line:A,B"],
            "edge",
            "value",
            "a vertical line",
        )
        add(
            {"A": ("0", "0"), "B": ("5", "0")},
            ["line:A,B"],
            "edge",
            "value",
            "a horizontal line",
        )
        add(
            {"A": ("0", "0"), "B": ("1", "1")},
            ["line:A,B"],
            "edge",
            "value",
            "a line at forty-five degrees",
        )
    elif op_id == "transform.mirror":
        for _ in range(TARGET):
            pts = _points(rng, 3)
            add(pts, ["A", "line:B,C"], "normal", "value", "reflect a point in a line")
        # A point on the line is its own mirror.
        add(
            {"A": ("0", "0"), "B": ("0", "0"), "C": ("5", "0")},
            ["A", "line:B,C"],
            "edge",
            "value",
            "the point is on the line",
        )
        for _ in range(DEGENERATE):
            pts = _points(rng, 3)
            add(pts, ["A", "line:B,B"], "degenerate", "error", "degenerate line")
    elif op_id == "transform.translate":
        for _ in range(TARGET):
            pts = _points(rng, 3)
            add(pts, ["A", "B"], "normal", "value", "translate by a vector")
        # A zero vector translates nothing.
        add(
            {"A": ("3", "4"), "B": ("0", "0")},
            ["A", "B"],
            "edge",
            "value",
            "a zero vector",
        )
        add(
            {"A": ("3", "4"), "B": ("-2", "7")},
            ["A", "B"],
            "edge",
            "value",
            "a negative vector",
        )
        add(
            {"A": ("0", "0"), "B": ("0", "0")},
            ["A", "B"],
            "edge",
            "value",
            "translating the origin by nothing",
        )
    elif op_id == "transform.rotate":
        for _ in range(TARGET):
            pts = _points(rng, 3)
            # The special angles are where an exact answer shows up:
            # a quarter turn and a third of a turn both stay rational
            # or quadratic.
            add(pts, ["A", "90", "C"], "normal", "value", "a quarter turn")
            add(pts, ["A", "120", "C"], "normal", "value", "a third of a turn")
            add(pts, ["A", "60", "C"], "normal", "value", "a sixth of a turn")
        add(
            {"A": ("3", "4"), "C": ("0", "0")},
            ["A", "0", "C"],
            "edge",
            "value",
            "no turn at all",
        )
        add(
            {"A": ("3", "4"), "C": ("0", "0")},
            ["A", "360", "C"],
            "edge",
            "value",
            "a whole turn",
        )
        add(
            {"A": ("3", "4"), "C": ("0", "0")},
            ["A", "-90", "C"],
            "edge",
            "value",
            "a turn the other way",
        )
    elif op_id == "transform.dilate":
        for _ in range(TARGET):
            pts = _points(rng, 3)
            add(pts, ["A", "2", "C"], "normal", "value", "a factor of two")
            add(pts, ["A", "-1", "C"], "normal", "value", "a half turn")
            add(pts, ["A", "1", "C"], "normal", "value", "the identity")
        add(
            {"A": ("3", "4"), "C": ("1", "1")},
            ["A", "0", "C"],
            "edge",
            "value",
            "everything collapses onto the centre",
        )
        add(
            {"A": ("3", "4"), "C": ("1", "1")},
            ["A", "1", "C"],
            "edge",
            "value",
            "the identity",
        )
        add(
            {"A": ("3", "4"), "C": ("1", "1")},
            ["A", "1/2", "C"],
            "edge",
            "value",
            "a fractional factor",
        )
    else:
        raise ValueError(f"no fixture generator for {op_id!r}")
    return fixtures


OPERATORS = [
    "point.midpoint",
    "point.centroid",
    "point.foot",
    "point.intersect_lines",
    "point.intersect_line_circle",
    "point.intersect_circles",
    "point.nearest_on_object",
    "point.circumcenter",
    "point.incenter",
    "point.orthocenter",
    "line.free",
    "line.perpendicular_through",
    "line.parallel_through",
    "line.perpendicular_bisector",
    "line.angle_bisector",
    "line.tangent",
    "segment.free",
    "circle.through",
    "circle.free",
    "circle.center_point",
    "circle.incircle",
    "polygon.free",
    "arc.three_points",
    "sector.three_points",
    "ray.free",
    "polyline.free",
    "polygon.regular",
    "point.polygon_vertex",
    "point.affine_ratio",
    "line.polar",
    "measure.distance",
    "measure.length",
    "measure.area",
    "measure.perimeter",
    "measure.angle",
    "measure.radius",
    "measure.slope",
    "measure.direction",
    "transform.mirror",
    "transform.translate",
    "transform.rotate",
    "transform.dilate",
]


def main() -> None:
    for op_id in OPERATORS:
        # Every operator gets its own stream.  With one shared stream,
        # changing one battery silently rewrites every other one -- and a
        # battery that nobody looked at can hide a case the kernel gets
        # wrong.  A stream per operator means a change here stays here.
        rng = random.Random(f"{SEED}-{op_id}")
        fixtures = battery(op_id, rng)
        save_fixtures(op_id, fixtures)
        degenerate = sum(1 for f in fixtures if f.kind == "degenerate")
        print(f"{op_id}: {len(fixtures)} fixtures ({degenerate} degenerate)")


if __name__ == "__main__":
    main()
