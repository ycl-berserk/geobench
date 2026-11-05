"""Exact arithmetic layer.

Every geometric quantity in the kernel is a sympy expression. Floating point
is rejected at the door and may only appear at the render boundary, through
:meth:`SympyField.to_float` (see docs/spec.md section 4).

The exactness invariant is enforced mechanically by ``tests/no_float``.
"""

from __future__ import annotations

from typing import Protocol, TypeAlias, cast, runtime_checkable

import sympy as sp
from sympy import Expr

from geobench.errors import FieldError

ExprLike: TypeAlias = Expr | int | sp.Rational


@runtime_checkable
class Field(Protocol):
    """The arithmetic interface the kernel is written against.

    Keeping the kernel behind this protocol is what makes it possible to swap
    the backend (for example with a rational-only fast path) without touching
    the operator layer. See docs/decisions.md D2.
    """

    def coerce(self, value: ExprLike) -> Expr:
        """Return ``value`` as an exact expression, or raise FieldError."""

    def add(self, a: ExprLike, b: ExprLike) -> Expr: ...

    def sub(self, a: ExprLike, b: ExprLike) -> Expr: ...

    def mul(self, a: ExprLike, b: ExprLike) -> Expr: ...

    def div(self, a: ExprLike, b: ExprLike) -> Expr: ...

    def sqrt(self, a: ExprLike) -> Expr: ...

    def simplify_to_zero(self, value: ExprLike) -> bool:
        """Return True only if ``value`` is provably the zero expression."""

    def to_float(self, value: ExprLike) -> float:
        """Display-only approximation. The single place floats may appear."""


class SympyField:
    """SymPy-backed implementation of :class:`Field`.

    ``identity_budget_ops`` bounds the size of an expression the kernel is
    willing to reduce symbolically. Expressions over free symbols grow
    quickly, and an unbudgeted reduction can take unbounded time; the budget
    turns "too big to prove" into a cheap, honest answer, and the judge then
    falls back to sampling.
    """

    def __init__(self, identity_budget_ops: int = 20000, expand_budget_ops: int = 400) -> None:
        self.identity_budget_ops = identity_budget_ops
        self.expand_budget_ops = expand_budget_ops

    def coerce(self, value: ExprLike) -> Expr:
        if isinstance(value, bool):
            raise FieldError("bool is not a geometric value")
        if isinstance(value, float):
            raise FieldError(
                "float literal is not allowed in the kernel; "
                "use an integer, a Rational, or a symbolic expression"
            )
        if isinstance(value, sp.Float):
            raise FieldError(
                "sympy.Float is not allowed; use Rational or a symbolic expression"
            )
        if isinstance(value, sp.Expr):
            expr = value
        elif isinstance(value, int):
            expr = sp.Integer(value)
        elif isinstance(value, str):
            expr = cast(Expr, sp.sympify(value))
        else:
            raise FieldError(f"unsupported value type: {type(value)!r}")
        if expr.atoms(sp.Float):
            raise FieldError("expression contains a floating point part")
        return expr

    def add(self, a: ExprLike, b: ExprLike) -> Expr:
        return self.coerce(a) + self.coerce(b)

    def sub(self, a: ExprLike, b: ExprLike) -> Expr:
        return self.coerce(a) - self.coerce(b)

    def mul(self, a: ExprLike, b: ExprLike) -> Expr:
        return self.coerce(a) * self.coerce(b)

    def div(self, a: ExprLike, b: ExprLike) -> Expr:
        denominator = self.coerce(b)
        if denominator == 0:
            raise FieldError("division by zero")
        return self.coerce(a) / denominator

    def sqrt(self, a: ExprLike) -> Expr:
        return sp.sqrt(self.coerce(a))

    def simplify_to_zero(self, value: ExprLike) -> bool:
        """Return True only when ``value`` is provably the zero expression.

        ``supported`` in the judge vocabulary means "holds in the samples but
        is not an identity"; this method is the boundary between the two, so
        it must never answer True on a numerical coincidence.

        The reduction is *budgeted*. Expressions over free symbols grow fast
        -- the determinant that decides four points to be concyclic already
        reaches thousands of terms -- and an unbudgeted ``simplify`` on such
        an expression does not finish. So the cheap exact reductions run
        first, and anything too large is reported as "not proved" rather than
        stalling the caller. The judge then falls back to sampling, which is
        decisive for refutation.
        """
        expr = self.coerce(value)
        if expr == 0:
            return True
        if expr.is_number:
            return bool(expr == 0)
        if sp.count_ops(expr) > self.identity_budget_ops:
            return False
        return self._reduce_to_zero(expr)

    def _reduce_to_zero(self, expr: Expr) -> bool:
        """Exact reductions, cheapest first.

        The order matters: clearing denominators and testing the numerator as
        a polynomial is far cheaper than asking sympy to ``simplify`` a
        rational function, whose default heuristics expand eagerly.
        """
        symbols = sorted(expr.free_symbols, key=str)
        if symbols:
            try:
                numerator, _ = sp.fraction(sp.together(expr))
            except Exception:  # pragma: no cover - sympy internal failure
                numerator = expr
            if sp.count_ops(numerator) <= self.identity_budget_ops:
                try:
                    if sp.Poly(numerator, *symbols, domain=sp.QQ).is_zero:
                        return True
                except Exception:  # pragma: no cover - fall through to the next method
                    pass
        for candidate in (
            sp.trigsimp(expr),
            sp.radsimp(expr),
        ):
            if candidate == 0:
                return True
        if sp.count_ops(expr) <= self.expand_budget_ops:
            try:
                if sp.simplify(expr) == 0:
                    return True
            except Exception:  # pragma: no cover - sympy internal failure
                pass
        try:
            verdict = expr.equals(0)
        except Exception:  # pragma: no cover - sympy internal failure
            return False
        if verdict is None:
            return False
        return bool(verdict)

    def to_float(self, value: ExprLike) -> float:
        return float(sp.N(self.coerce(value)))


FIELD = SympyField()
