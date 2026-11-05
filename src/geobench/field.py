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
    """SymPy-backed implementation of :class:`Field`."""

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
        """
        expr = self.coerce(value)
        if expr == 0:
            return True
        candidates = (
            sp.simplify(expr),
            sp.trigsimp(expr),
            sp.radsimp(expr),
            sp.cancel(sp.together(expr)),
            sp.simplify(sp.trigsimp(sp.expand(expr))),
        )
        for candidate in candidates:
            if candidate == 0:
                return True
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
