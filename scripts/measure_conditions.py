"""Does the channel survive a *real* problem statement?

The evaluation set in ``evals/`` measures the **contract**: does the
model know our language, our commands and our conventions.  Every case
there was written by us, with one phrasing each, and the skill even
hands the model a table of good coordinates to reuse.

This asks the other question -- the one a teacher asks: type the
problem, get a figure that satisfies the problem's conditions.

The conditions here are numeric (a length, an angle) or relational
(perpendicular, tangent, midpoint), because those are what a problem
statement carries.  A model cannot satisfy "AC=4, BC=3" by remembering
a table: it has to *compute* a 3-4-5 triangle.  That is the point.

    python scripts/measure_conditions.py            # every case
    python scripts/measure_conditions.py 平行四边形   # only matching cases
    python scripts/measure_conditions.py --show     # and the figures

This is a diagnostic, not a gate: it talks to the network, so it never
enters CI.  The record of what it found is in
``tasks/T043-real-statements.md``.
"""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from geobench.ai import propose  # noqa: E402
from geobench.ai_settings import resolve_provider  # noqa: E402
from geobench.evaluate import evaluate_figure, numeric_coords  # noqa: E402
from geobench.model import Figure  # noqa: E402
from geobench.operators import register_builtins  # noqa: E402
from geobench.registry import OperatorRegistry  # noqa: E402

#: How close a length or an angle has to be to count.
TOLERANCE = 1e-6


@dataclass(frozen=True)
class Condition:
    """One condition the figure has to satisfy, and how to check it."""

    name: str
    check: Callable[[Figure], bool | None]
    """``None`` when the check could not be run (an object is missing)."""


@dataclass(frozen=True)
class Statement:
    """A problem statement, the way a teacher types it, and its conditions."""

    name: str
    request: str
    conditions: tuple[Condition, ...] = field(default=())


# -- the checks -------------------------------------------------------------


def _coords(figure: Figure, name: str) -> tuple[float, float] | None:
    try:
        return numeric_coords(figure, name)
    except Exception:
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


def _close(got: float, want: float) -> bool:
    return abs(got - want) <= TOLERANCE * max(1.0, abs(got), abs(want))


def _length_is(want: float, first: str, second: str) -> Callable[[Figure], bool | None]:
    def check(figure: Figure) -> bool | None:
        a, b = _coords(figure, first), _coords(figure, second)
        if a is None or b is None:
            return None
        return _close(_distance(a, b), want)

    return check


def _angle_is(
    want: float, at: str, first: str, third: str
) -> Callable[[Figure], bool | None]:
    def check(figure: Figure) -> bool | None:
        a, b, c = _coords(figure, at), _coords(figure, first), _coords(figure, third)
        if a is None or b is None or c is None:
            return None
        got = _angle_at(b, a, c)
        return None if got is None else _close(got, want)

    return check


def _is_midpoint(mid: str, first: str, second: str) -> Callable[[Figure], bool | None]:
    def check(figure: Figure) -> bool | None:
        m, a, b = _coords(figure, mid), _coords(figure, first), _coords(figure, second)
        if m is None or a is None or b is None:
            return None
        centre = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        return _distance(m, centre) <= TOLERANCE * max(1.0, _distance(a, b))

    return check


def _perpendicular(
    p: str, q: str, r: str, s: str
) -> Callable[[Figure], bool | None]:
    def check(figure: Figure) -> bool | None:
        a, b, c, d = (_coords(figure, name) for name in (p, q, r, s))
        if None in (a, b, c, d):
            return None
        u = (a[0] - b[0], a[1] - b[1])
        v = (c[0] - d[0], c[1] - d[1])
        nu, nv = math.hypot(*u), math.hypot(*v)
        if nu == 0 or nv == 0:
            return None
        return abs(u[0] * v[0] + u[1] * v[1]) <= TOLERANCE * nu * nv

    return check


def _parallel(p: str, q: str, r: str, s: str) -> Callable[[Figure], bool | None]:
    def check(figure: Figure) -> bool | None:
        a, b, c, d = (_coords(figure, name) for name in (p, q, r, s))
        if None in (a, b, c, d):
            return None
        u = (a[0] - b[0], a[1] - b[1])
        v = (c[0] - d[0], c[1] - d[1])
        nu, nv = math.hypot(*u), math.hypot(*v)
        if nu == 0 or nv == 0:
            return None
        return abs(u[0] * v[1] - u[1] * v[0]) <= TOLERANCE * nu * nv

    return check


def _tangent(point: str, contact: str, centre: str) -> Callable[[Figure], bool | None]:
    def check(figure: Figure) -> bool | None:
        p, t, o = (_coords(figure, name) for name in (point, contact, centre))
        if p is None or t is None or o is None:
            return None
        radius = (t[0] - o[0], t[1] - o[1])
        tangent = (p[0] - t[0], p[1] - t[1])
        nr, nt = math.hypot(*radius), math.hypot(*tangent)
        if nr == 0 or nt == 0:
            return None
        dot = radius[0] * tangent[0] + radius[1] * tangent[1]
        return abs(dot) <= 1e-7 * nr * nt

    return check


def _equal_lengths(
    want: float, first: str, second: str, third: str, fourth: str
) -> Callable[[Figure], bool | None]:
    def check(figure: Figure) -> bool | None:
        a, b, c, d = (_coords(figure, name) for name in (first, second, third, fourth))
        if None in (a, b, c, d):
            return None
        return (
            _close(_distance(a, b), want)
            and _close(_distance(c, d), want)
            and _close(_distance(a, b), _distance(c, d))
        )

    return check


def _exists(*names: str) -> Callable[[Figure], bool | None]:
    def check(figure: Figure) -> bool | None:
        return all(_coords(figure, name) is not None for name in names)

    return check


# -- the statements ---------------------------------------------------------

STATEMENTS: tuple[Statement, ...] = (
    Statement(
        name="等腰三角形 + 中点 + 高",
        request="画一个等腰三角形ABC，AB=AC，D是BC的中点，作AD",
        conditions=(
            Condition("AB=AC", _equal_lengths(0.0, "A", "B", "A", "C")),
            Condition("D是BC的中点", _is_midpoint("D", "B", "C")),
            Condition("AD⊥BC", _perpendicular("A", "D", "B", "C")),
        ),
    ),
    Statement(
        name="直角三角形（带长度）+ 垂足",
        request="画一个直角三角形ABC，∠A=90°，AC=4，BC=3，作A到BC的垂线，垂足为H",
        conditions=(
            Condition("∠A=90°", _angle_is(90.0, "A", "B", "C")),
            Condition("AC=4", _length_is(4.0, "A", "C")),
            Condition("BC=3", _length_is(3.0, "B", "C")),
            Condition("H在BC上", _exists("H")),
            Condition("AH⊥BC", _perpendicular("A", "H", "B", "C")),
        ),
    ),
    Statement(
        name="外接圆 + 圆外点 + 切线",
        request="作三角形ABC的外接圆O，圆外取一点P，使OP=5，过P作圆O的切线PT，T为切点",
        conditions=(
            Condition("OP=5", _length_is(5.0, "O", "P")),
            Condition("PT切圆", _tangent("P", "T", "O")),
        ),
    ),
    Statement(
        name="平行四边形（带边长和角）",
        request="画一个平行四边形ABCD，AB=5，AD=3，∠DAB=60°",
        conditions=(
            Condition("AB=5", _length_is(5.0, "A", "B")),
            Condition("AD=3", _length_is(3.0, "A", "D")),
            Condition("∠DAB=60°", _angle_is(60.0, "A", "D", "B")),
            Condition("AB∥DC", _parallel("A", "B", "D", "C")),
            Condition("AD∥BC", _parallel("A", "D", "B", "C")),
        ),
    ),
    Statement(
        name="等边三角形 + 外接圆 + 内切圆",
        request="画一个等边三角形ABC，边长4，作它的外接圆和内切圆",
        conditions=(
            Condition("三边都=4", _equal_lengths(4.0, "A", "B", "B", "C")),
            Condition("外接圆在", _exists("O")),
            Condition("内切圆在", _exists("I")),
        ),
    ),
    Statement(
        name="对照组：没有条件的三角形",
        request="画一个三角形ABC",
        conditions=(Condition("三个点都在", _exists("A", "B", "C")),),
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pattern", nargs="?", default="", help="only matching cases")
    parser.add_argument("--show", action="store_true", help="print the figures too")
    parser.add_argument("--retries", type=int, default=2, help="how many tries the model gets")
    args = parser.parse_args()

    resolution = resolve_provider()
    if not resolution.ok:
        print(f"没有可用的模型服务：{resolution.reason}", file=sys.stderr)
        return 1
    print(f"服务：{resolution.provider.name}")
    print()

    registry = OperatorRegistry()
    register_builtins(registry)

    statements = [s for s in STATEMENTS if args.pattern in s.name]
    if not statements:
        print("没有匹配的题面", file=sys.stderr)
        return 1

    satisfied = 0
    for statement in statements:
        print("=" * 74)
        print(statement.name)
        print(f"  题面：{statement.request}")
        proposal = propose(
            resolution.provider, statement.request, "", registry, retries=args.retries
        )
        if not proposal.ok:
            print(f"  ✗ 解析失败：{proposal.error}")
            print(proposal.text)
            print()
            continue
        figure = evaluate_figure(proposal.figure, registry)
        failed: list[str] = []
        for condition in statement.conditions:
            try:
                verdict = condition.check(figure)
            except Exception:  # pragma: no cover - a check that cannot run
                verdict = None
            if verdict is not True:
                failed.append(condition.name)
        if failed:
            print(f"  ✗ 不满足：{'、'.join(failed)}")
        else:
            print("  ✓ 条件全满足")
            satisfied += 1
        if args.show:
            print(proposal.text)
        print()

    print("=" * 74)
    print(f"{satisfied}/{len(statements)} 满足题面条件")
    return 0 if satisfied == len(statements) else 1


if __name__ == "__main__":
    raise SystemExit(main())
