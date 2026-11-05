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
    else:
        raise ValueError(f"no fixture generator for {op_id!r}")
    return fixtures


OPERATORS = [
    "point.midpoint",
    "point.centroid",
    "point.foot",
    "point.intersect_lines",
    "point.intersect_line_circle",
    "point.circumcenter",
    "point.incenter",
    "point.orthocenter",
    "line.free",
    "line.perpendicular_through",
    "line.parallel_through",
    "segment.free",
    "circle.through",
    "circle.free",
]


def main() -> None:
    rng = random.Random(SEED)
    for op_id in OPERATORS:
        fixtures = battery(op_id, rng)
        save_fixtures(op_id, fixtures)
        degenerate = sum(1 for f in fixtures if f.kind == "degenerate")
        print(f"{op_id}: {len(fixtures)} fixtures ({degenerate} degenerate)")


if __name__ == "__main__":
    main()
