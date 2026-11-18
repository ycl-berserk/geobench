"""Finding coordinates that satisfy the problem's conditions.

A teacher who says "AB=AC and ∠A=40°" has said what the figure must be
like, not how to build it.  Most of the time the construction is the
better answer -- a rotation carries an angle exactly, while a solver can
only carry it numerically.  But sometimes the condition is a *system*
(three lengths, a right angle and a midpoint at once), and then the
coordinates have to be *found*.

This module finds them, and it is deliberately narrow:

- it moves the **free points** only, and as **few of them as it can**:
  the points declared first are the frame, and a solution that shifts
  the whole drawing is not the one the teacher means;
- it starts from where the figure already is, so it finds the solution
  *near the drawing*;
- and it only returns a solution whose coordinates are **exact**
  numbers.  A solution is rationalised (or written with roots when it
  needs them), and then **checked exactly**: if the constraints are not
  satisfied by the exact figure, the answer is refused, not returned
  with a warning (spec section 8).

The refusal is not a failure of the method.  It is the honest answer to
"draw a 40° apex": that point is transcendental, no exact coordinate
exists, and the right way to draw it is a rotation -- which the DSL has.
So the solver's message says so, and the model learns the better tool.

The arithmetic is small and explicit: a Levenberg-Marquardt step on a
handful of unknowns, with the normal equations solved by Gaussian
elimination.  There is no numpy here, and there does not need to be.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Iterator
from dataclasses import dataclass, field

import sympy as sp
from sympy import Expr

from geobench.errors import StateError
from geobench.field import FIELD
from geobench.model import Figure
from geobench.numeric import placement_float

#: How small the residual has to get, in figure units, before the
#: solution is worth rationalising.
TOLERANCE = 1e-10

#: How many accepted steps before giving up.
MAX_STEPS = 80


@dataclass(frozen=True)
class Condition:
    """One condition the figure has to satisfy.

    ``expression`` is an exact expression in the free points' symbols;
    the condition holds where it is zero.  That is the same shape the
    judges use, which is why a constraint can be written as a judgement
    ("AE is perpendicular to BC") as well as an equation ("|AB| = 5").
    """

    label: str
    expression: Expr


@dataclass(frozen=True)
class Outcome:
    """What the solver found, and how sure it is."""

    ok: bool
    placements: dict[str, tuple[str, str]] = field(default_factory=dict)
    """The exact coordinates, by node id -- only when ``ok``."""

    reason: str = ""
    """Why it did not find an exact configuration, when it did not."""

    degrees_of_freedom: int = 0
    """How much freedom the constraints leave at the solution."""

    moved: tuple[str, ...] = ()
    """The free points whose coordinates changed."""

    steps: int = 0


# -- the frame --------------------------------------------------------------


@dataclass(frozen=True)
class _Frame:
    """The figure's free points, and which of them may move."""

    mapping: dict[Expr, float]
    """Every free symbol and its current value."""

    movable: tuple[str, ...]
    """The points the solver may move, in declaration order."""

    symbols: tuple[Expr, ...]
    """The symbols of the movable points, x then y."""

    start: tuple[float, ...]
    """Where the movable points are now."""

    exact: dict[Expr, Expr]
    """Every free symbol and its exact current value."""


def _frame(figure: Figure, movable: tuple[str, ...]) -> _Frame | None:
    """The free points of the figure, with ``movable`` free to move."""
    mapping: dict[Expr, float] = {}
    exact: dict[Expr, Expr] = {}
    for node_id, node in figure.nodes.items():
        if node.role != "free" or node.kind != "point" or node.placement is None:
            continue
        x = placement_float(node.placement[0])
        y = placement_float(node.placement[1])
        if x is None or y is None:
            return None
        xs = FIELD.coerce(f"x_{node_id}")
        ys = FIELD.coerce(f"y_{node_id}")
        mapping[xs] = float(x)
        mapping[ys] = float(y)
        exact[xs] = FIELD.coerce(node.placement[0])
        exact[ys] = FIELD.coerce(node.placement[1])

    symbols: list[Expr] = []
    start: list[float] = []
    for node_id in movable:
        xs = FIELD.coerce(f"x_{node_id}")
        ys = FIELD.coerce(f"y_{node_id}")
        if xs not in mapping or ys not in mapping:
            return None
        symbols.extend((xs, ys))
        start.extend((mapping[xs], mapping[ys]))
    return _Frame(
        mapping=mapping,
        movable=movable,
        symbols=tuple(symbols),
        start=tuple(start),
        exact=exact,
    )


def _free_points(figure: Figure) -> tuple[str, ...]:
    return tuple(
        node_id
        for node_id, node in figure.nodes.items()
        if node.role == "free" and node.kind == "point" and node.placement is not None
    )


# -- evaluating a condition -------------------------------------------------


def _residual(expression: Expr, frame: _Frame, values: tuple[float, ...]) -> float:
    """The expression's value at a placement, as a real number."""
    mapping = dict(frame.mapping)
    mapping.update(dict(zip(frame.symbols, values, strict=True)))
    try:
        value = sp.N(expression.subs(mapping), 30)
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise StateError(f"the condition cannot be evaluated here: {exc}") from None
    number = complex(value)
    if abs(number.imag) > 1e-9:
        raise StateError("the condition has no real value here")
    if not math.isfinite(number.real):
        raise StateError("the condition has no finite value here")
    return float(number.real)


def _jacobian(
    expressions: list[Expr], frame: _Frame, values: tuple[float, ...]
) -> list[list[float]]:
    """The derivative of every condition by every unknown, numerically.

    A central difference: the expressions are symbolic, but they can
    contain ``acos`` and ``sqrt``, and differentiating them symbolically
    would be slower than evaluating them twice.
    """
    rows: list[list[float]] = []
    for expression in expressions:
        row: list[float] = []
        for index, value in enumerate(values):
            step = 1e-6 * (1.0 + abs(value))
            up = list(values)
            down = list(values)
            up[index] = value + step
            down[index] = value - step
            high = _residual(expression, frame, tuple(up))
            low = _residual(expression, frame, tuple(down))
            row.append((high - low) / (2.0 * step))
        rows.append(row)
    return rows


# -- linear algebra ---------------------------------------------------------


def _solve_linear(matrix: list[list[float]], right: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting."""
    size = len(right)
    rows = [[*row, right[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(rows[row][column]))
        if abs(rows[pivot][column]) < 1e-14:
            raise StateError("the constraints are linearly dependent here")
        rows[column], rows[pivot] = rows[pivot], rows[column]
        head = rows[column][column]
        for index in range(column, size + 1):
            rows[column][index] /= head
        for row in range(size):
            if row == column:
                continue
            factor = rows[row][column]
            if factor == 0:
                continue
            for index in range(column, size + 1):
                rows[row][index] -= factor * rows[column][index]
    return [rows[index][size] for index in range(size)]


def _normal_step(
    jacobian: list[list[float]], residual: list[float], damping: float
) -> list[float]:
    """One Levenberg-Marquardt step: (JtJ + damping*I) delta = -Jt r."""
    unknowns = len(jacobian[0])
    normal = [[0.0] * unknowns for _ in range(unknowns)]
    right = [0.0] * unknowns
    for row, value in zip(jacobian, residual, strict=True):
        for first in range(unknowns):
            right[first] -= row[first] * value
            for second in range(unknowns):
                normal[first][second] += row[first] * row[second]
    for index in range(unknowns):
        normal[index][index] += damping * max(1.0, normal[index][index])
    return _solve_linear(normal, right)


def _norm(values: list[float] | tuple[float, ...]) -> float:
    return math.sqrt(sum(value * value for value in values))


# -- the exact answer --------------------------------------------------------


def _candidates(value: float) -> list[Expr]:
    """The exact numbers that could be this value, simplest first.

    A rational with a small denominator first (that is what a 3-4-5
    triangle gives), then a rational combination of small roots (what a
    5-6-7 triangle gives).  Each candidate is only a *guess*; the exact
    check decides, which is why a plausible-looking big fraction is
    harmless here -- it is rejected if it is not the true value.
    """
    found: list[Expr] = []
    try:
        simple = sp.Rational(value).limit_denominator(1000)
        if abs(float(simple) - value) <= 1e-9:
            found.append(simple)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        pass
    for tolerance in (1e-6, 1e-9):
        try:
            roots = [sp.sqrt(index) for index in range(2, 21)]
            candidate = sp.nsimplify(value, constants=roots, tolerance=tolerance)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            continue
        if isinstance(candidate, Expr) and not candidate.free_symbols:
            found.append(candidate)
    unique: list[Expr] = []
    for candidate in found:
        if any(candidate == seen for seen in unique):
            continue
        unique.append(candidate)
    return unique


def _combinations(
    options: list[list[Expr]], limit: int = 2000
) -> Iterator[tuple[Expr, ...]]:
    """Every way to pick one candidate per coordinate, simplest first.

    The product is over small lists (a handful of guesses per
    coordinate), and the exact check is cheap; when it would be too
    large, only the simplest guess per coordinate is tried.
    """
    total = 1
    for entries in options:
        total *= max(1, len(entries))
    if total > limit:
        yield tuple(entries[0] for entries in options)
        return
    yield from itertools.product(*options)


def _check_exactly(
    conditions: list[Condition], frame: _Frame, moved: dict[Expr, Expr]
) -> str:
    """Are the conditions satisfied by these exact coordinates?

    Returns "" when they are, and the label of the first condition that
    is not otherwise.  This is the gate: a numeric solution that does
    not survive it is not returned.
    """
    mapping = dict(frame.exact)
    mapping.update(moved)
    for condition in conditions:
        try:
            value = condition.expression.subs(mapping)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return condition.label
        if not FIELD.simplify_to_zero(value):
            return condition.label
    return ""


# -- the solver --------------------------------------------------------------


def _scales(
    expressions: list[Expr], frame: _Frame, initial: list[float]
) -> list[float]:
    """How much each condition moves per unit of coordinate.

    A length condition and an area condition are not the same size, and
    a least-squares step would let the bigger one win.  Dividing each
    residual by its own gradient turns them all into distances.
    """
    scales: list[float] = []
    for expression in expressions:
        norms: list[float] = []
        for index, coordinate in enumerate(frame.start):
            step = 1e-6 * (1.0 + abs(coordinate))
            up = list(frame.start)
            down = list(frame.start)
            up[index] = coordinate + step
            down[index] = coordinate - step
            try:
                high = _residual(expression, frame, tuple(up))
                low = _residual(expression, frame, tuple(down))
            except StateError:
                continue
            norms.append(abs(high - low) / (2.0 * step))
        scale = max(norms, default=0.0)
        scales.append(scale if scale > 1e-9 else 1.0)
    del initial
    return scales


def _figure_size(figure: Figure) -> float:
    """How big the drawing is, in its own units."""
    xs: list[float] = []
    ys: list[float] = []
    for node in figure.nodes.values():
        if node.kind != "point" or node.placement is None:
            continue
        x = placement_float(node.placement[0])
        y = placement_float(node.placement[1])
        if x is None or y is None:
            continue
        xs.append(x)
        ys.append(y)
    if not xs:
        return 1.0
    return max(max(xs) - min(xs), max(ys) - min(ys), 1.0)


def _rank(matrix: list[list[float]], tolerance: float = 1e-9) -> int:
    """The rank of a small matrix, by elimination."""
    if not matrix:
        return 0
    rows = [list(row) for row in matrix]
    height = len(rows)
    width = len(rows[0])
    rank = 0
    for column in range(width):
        pivot = None
        for row in range(rank, height):
            biggest = max((abs(value) for value in rows[row]), default=1.0)
            if abs(rows[row][column]) > tolerance * max(1.0, biggest):
                pivot = row
                break
        if pivot is None:
            continue
        rows[rank], rows[pivot] = rows[pivot], rows[rank]
        head = rows[rank][column]
        for row in range(rank + 1, height):
            factor = rows[row][column] / head
            if factor == 0:
                continue
            for index in range(column, width):
                rows[row][index] -= factor * rows[rank][index]
        rank += 1
        if rank == height:
            break
    return rank


def _attempt(
    figure: Figure,
    conditions: list[Condition],
    movable: tuple[str, ...],
    *,
    tolerance: float,
    max_steps: int,
) -> Outcome:
    """Try to solve with exactly these points free to move."""
    frame = _frame(figure, movable)
    if frame is None:
        return Outcome(ok=False, reason="图里没有可以移动的自由点")
    expressions = [condition.expression for condition in conditions]
    symbols = frame.symbols
    try:
        scales = _scales(expressions, frame, [])
        residuals = [_residual(expression, frame, frame.start) / scale
                     for expression, scale in zip(expressions, scales, strict=True)]
    except StateError as exc:
        return Outcome(ok=False, reason=str(exc))

    size = _figure_size(figure)
    limit = tolerance * max(1.0, size)
    if max((abs(value) for value in residuals), default=0.0) < limit:
        # Already true: nothing to find, and nothing to move.
        return Outcome(ok=True, placements={}, moved=(), steps=0,
                       degrees_of_freedom=len(symbols) - _rank(
                           _jacobian(expressions, frame, frame.start)))

    values = tuple(frame.start)
    current = _norm(residuals)
    damping = 1e-3
    steps = 0
    for steps in range(1, max_steps + 1):
        residual = [
            _residual(expression, frame, values) / scale
            for expression, scale in zip(expressions, scales, strict=True)
        ]
        if max((abs(value) for value in residual), default=0.0) < limit:
            break
        try:
            jacobian = _jacobian(expressions, frame, values)
            jacobian = [
                [entry / scale for entry in row]
                for row, scale in zip(jacobian, scales, strict=True)
            ]
            step = _normal_step(jacobian, residual, damping)
        except StateError as exc:
            return Outcome(ok=False, reason=str(exc), steps=steps)
        # A step may not be longer than a tenth of the drawing: the
        # nearest solution is the one the teacher means, and a solver
        # that jumps across the page has found a different one.  A line
        # search would also do, and this is cheaper.
        length = math.sqrt(sum(value * value for value in step))
        if length > 0.1 * max(1.0, size):
            step = [value * (0.1 * max(1.0, size) / length) for value in step]
        proposal = tuple(value + delta for value, delta in zip(values, step, strict=True))
        try:
            trial = _norm(
                [
                    _residual(expression, frame, proposal) / scale
                    for expression, scale in zip(expressions, scales, strict=True)
                ]
            )
        except StateError:
            trial = math.inf
        if trial < current:
            values, current, damping = proposal, trial, max(damping / 3.0, 1e-12)
        else:
            damping *= 10.0
            if damping > 1e12:
                break

    final = _norm(
        [
            _residual(expression, frame, values) / scale
            for expression, scale in zip(expressions, scales, strict=True)
        ]
    )
    if final > max(limit, 1e-8):
        return Outcome(
            ok=False,
            reason=f"从这张图出发解不出来（残差 {final:.2e}）—— 约束可能互相矛盾，"
            "或者初始位置离解太远",
            steps=steps,
        )

    options = [_candidates(value) for value in values]
    if any(not entries for entries in options):
        ugly = next(
            f"{value:.10g}"
            for value, entries in zip(values, options, strict=True)
            if not entries
        )
        return Outcome(
            ok=False,
            reason=(
                f"解出来是 {ugly}，不是精确数 —— "
                "这种图要用『旋转』『位似』一步步构造，或者换一组条件"
            ),
            steps=steps,
        )

    chosen: dict[Expr, Expr] | None = None
    failed = ""
    for combination in _combinations(options):
        guess = dict(zip(symbols, combination, strict=True))
        failed = _check_exactly(conditions, frame, guess)
        if not failed:
            chosen = guess
            break
    if chosen is None:
        return Outcome(
            ok=False,
            reason=(
                f"解出来的坐标再代回去，『{failed}』并不精确成立 —— "
                "这组约束没有可以写下来的精确解；用『旋转』『位似』一步步构造会更好"
            ),
            steps=steps,
        )
    exact = chosen

    placements: dict[str, tuple[str, str]] = {}
    moved: list[str] = []
    for index, name in enumerate(movable):
        x, y = exact[symbols[2 * index]], exact[symbols[2 * index + 1]]
        placements[name] = (str(x), str(y))
        if abs(float(x) - frame.start[2 * index]) > 1e-12 or abs(
            float(y) - frame.start[2 * index + 1]
        ) > 1e-12:
            moved.append(name)

    return Outcome(
        ok=True,
        placements=placements,
        degrees_of_freedom=max(0, len(symbols) - _rank(_jacobian(expressions, frame, values))),
        moved=tuple(moved),
        steps=steps,
    )


def solve(
    figure: Figure,
    conditions: list[Condition],
    *,
    tolerance: float = TOLERANCE,
    max_steps: int = MAX_STEPS,
) -> Outcome:
    """Find exact coordinates for the free points that satisfy the conditions.

    The points declared **first** are the frame, and the solver tries to
    leave them alone: it moves the last-declared point first, then the
    last two, and so on.  That is not a detail of the algorithm, it is
    what "solve the figure I drew" means -- `|AC| = 3` does not care
    whether A or C moves, and a solver that moves both turns a 3-4-5
    triangle into three irrational coordinates.

    The first attempt whose coordinates are **exact** wins.  When none
    is, the reason from the widest attempt is returned, because that is
    the one that had the most freedom to succeed.
    """
    if not conditions:
        return Outcome(ok=False, reason="没有约束可解")

    points = _free_points(figure)
    if not points:
        return Outcome(ok=False, reason="图里没有自由点，没有可以移动的东西")

    reason = ""
    for count in range(1, len(points) + 1):
        movable = points[-count:]
        outcome = _attempt(
            figure, conditions, movable, tolerance=tolerance, max_steps=max_steps
        )
        if outcome.ok:
            return outcome
        reason = outcome.reason
    return Outcome(ok=False, reason=reason)


__all__ = ["Condition", "Outcome", "solve"]
