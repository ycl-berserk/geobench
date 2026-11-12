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

    def zero_status(self, value: ExprLike) -> bool | None:
        """Whether the value is the zero expression -- and whether we know."""

    def has_zero_divisor(self, value: ExprLike) -> bool:
        """Whether the value divides by something that vanishes identically."""

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
        #: The most terms the expansion of a numerator may have.  This is
        #: the budget that matters: the size of the *unexpanded* expression
        #: says nothing about what expanding it costs.  A determinant
        #: cleared of its denominators can have hundreds of millions of
        #: terms, and expanding that is not a proof -- it is an outage.
        #:
        #: The number is calibrated against the proofs that have to keep
        #: working (the circumcentre: 3.4 million terms, seven seconds)
        #: and against the one that has to stop (the nine-point circle:
        #: 398 million terms, half an hour and more memory than the
        #: machine has).
        self.expand_term_budget = 10_000_000
        #: The strings this field has already parsed. Parsing is the
        #: slowest thing the exact path does, and the same strings come
        #: back every time: a point's coordinates, its placement.
        self._parsed: dict[str, Expr] = {}

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
            expr = self._parse(value)
        else:
            raise FieldError(f"unsupported value type: {type(value)!r}")
        if expr.atoms(sp.Float):
            raise FieldError("expression contains a floating point part")
        return expr

    def _parse(self, text: str) -> Expr:
        """A string as an exact expression, remembered.

        SymPy expressions are immutable, so one parsed expression can be
        shared by everything that asks for it. Without this, every
        evaluation re-parsed every point's coordinates and placement --
        and a rational such as "101/100" goes through the expression
        parser, which is slow enough to be felt.
        """
        cached = self._parsed.get(text)
        if cached is not None:
            return cached
        parsed = cast(Expr, sp.sympify(text))
        self._parsed[text] = parsed
        return parsed

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

    def zero_status(self, value: ExprLike) -> bool | None:
        """Whether this expression is the zero expression -- and whether we know.
        ``True``   the expression is provably the zero expression;
        ``False``  the expression is provably *not* zero;
        ``None``   the expression is not a rational function of its free
                   symbols, so the question has no cheap answer.

        This is the cheap *complete* test.  For a rational function of the
        free symbols, "is the numerator the zero polynomial" is a
        decision, not a search -- so unlike :meth:`simplify_to_zero` this
        needs no fallback on ``simplify`` and its unbounded cost, and the
        answer it gives is final.
        """
        expr = self.coerce(value)
        if expr == 0:
            return True
        symbols = sorted(expr.free_symbols, key=str)
        if not symbols:
            # A plain number: it is zero, or it is not.
            return bool(expr == 0)
        if sp.count_ops(expr) > self.identity_budget_ops:
            return None
        try:
            numerator, denominator = sp.fraction(sp.together(expr))
        except Exception:  # pragma: no cover - sympy internal failure
            return None
        try:
            num_poly = sp.Poly(numerator, *symbols, domain=sp.QQ)
            den_poly = sp.Poly(denominator, *symbols, domain=sp.QQ)
        except Exception:  # pragma: no cover - not a rational function
            return None
        if den_poly.is_zero:
            # The denominator vanishes identically: the expression has no
            # value anywhere, so it is not the zero expression.
            return False
        return bool(num_poly.is_zero)

    def has_zero_divisor(self, value: ExprLike) -> bool:
        """Does this expression divide by something that is identically zero?

        A relation that rests on such a division has no value *anywhere*.
        The construction under it -- the intersection of two lines that are
        always parallel, say -- produces nothing, so the relation built on
        it is not "true" and not "false": it is meaningless, and the
        kernel must say so rather than prove it.

        The check is on the divisor itself, not on the quotient: a base
        that vanishes identically makes every negative power of it vanish
        too.
        """
        expr = self.coerce(value)
        for node in sp.preorder_traversal(expr):
            if not isinstance(node, sp.Pow):
                continue
            exponent = node.exp
            if not (exponent.is_Integer and exponent.is_negative):
                continue
            if self.zero_status(node.base) is True:
                return True
        return False

    def expansion_size(self, value: ExprLike) -> int:
        """How many terms the expansion of this expression would have.

        The bound is exact for a polynomial and cheap to compute: the
        expansion of a sum is the sum of the expansions, and the
        expansion of a product is the product of the expansions.  So the
        tree itself says how big the expansion would be, *before* the
        work is done.

        It is a bound, not the exact count -- cancellation may make the
        real number smaller -- but a bound is what a budget needs.
        """
        return self._term_bound(self.coerce(value), self.expand_term_budget)

    def _term_bound(self, expression: Expr, limit: int) -> int:
        """The number of terms the expansion would have, at most."""
        if expression.is_Add:
            total = 0
            for part in expression.args:
                total += self._term_bound(part, limit)
                if total > limit:
                    return limit + 1
            return total
        if expression.is_Mul:
            product = 1
            for part in expression.args:
                product *= self._term_bound(part, limit)
                if product > limit:
                    return limit + 1
            return product
        if expression.is_Pow:
            exponent = expression.exp
            if not (exponent.is_Integer and 0 < int(exponent) <= 64):
                # A negative or fractional power is not a polynomial, and
                # a huge one is out of any budget.
                return limit + 1
            base = cast(Expr, expression.base)
            count = 1
            for _ in range(int(exponent)):
                count *= self._term_bound(base, limit)
                if count > limit:
                    return limit + 1
            return count
        return 1

    def reduction_note(self, value: ExprLike) -> str:
        """Why this expression could not be reduced, in one sentence.

        Empty when the reduction was not refused on size -- the caller
        uses it to tell the reader *why* the answer is "holds in the
        samples, but not proved" rather than just that.
        """
        expr = self.coerce(value)
        if not expr.free_symbols:
            return ""
        try:
            numerator, _ = sp.fraction(sp.together(expr))
        except Exception:  # pragma: no cover - sympy internal failure
            return ""
        size = self._term_bound(numerator, 10**12)
        if size > self.expand_term_budget:
            if size > 10**12:
                return (
                    "the expansion would have more than a trillion terms, over "
                    f"the budget of {self.expand_term_budget}"
                )
            return (
                f"the expansion would have up to {size} terms, over the "
                f"budget of {self.expand_term_budget}"
            )
        return ""

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
            # A number with radicals is not zero by structure: the
            # tangent from a point outside a circle has radical
            # coefficients, and whether the line is tangent to the
            # circle is exactly the question whether those radicals
            # cancel.  So the structural comparison is only the first
            # answer, not the last one.
            return self._reduce_number_to_zero(expr)
        if sp.count_ops(expr) > self.identity_budget_ops:
            return False
        return self._reduce_to_zero(expr)

    def _reduce_number_to_zero(self, expr: Expr) -> bool:
        """Is this number exactly zero?

        The structural comparison settles most of them.  The rest are
        numbers whose radicals cancel -- and there the reductions are
        cheap, because there are no symbols left to expand.

        The assumptions system is asked first: it answers most algebraic
        numbers in microseconds, while ``simplify`` on a residual with
        nested radicals can take seconds.
        """
        verdict = expr.is_zero
        if verdict is not None:
            return bool(verdict)
        for candidate in (sp.radsimp(expr), sp.simplify(expr)):
            if candidate == 0:
                return True
        try:
            verdict = expr.equals(0)
        except Exception:  # pragma: no cover - sympy internal failure
            return False
        if verdict is None:
            return False
        return bool(verdict)

    def _reduce_to_zero(self, expr: Expr) -> bool:
        """Exact reductions, cheapest first.

        The order matters: clearing denominators and testing the numerator as
        a polynomial is far cheaper than asking sympy to ``simplify`` a
        rational function, whose default heuristics expand eagerly.

        Everything here is bounded by the size of the *expansion*, not by
        the size of the expression.  The two are wildly different: a
        determinant of four points whose coordinates are rational functions
        is a few hundred operations long and expands to hundreds of
        millions of terms.  A budget that counted operations would wave
        that through; a budget that counts terms does not.
        """
        symbols = sorted(expr.free_symbols, key=str)
        if symbols:
            try:
                numerator, denominator = sp.fraction(sp.together(expr))
            except Exception:  # pragma: no cover - sympy internal failure
                numerator, denominator = expr, sp.Integer(1)
            if self._is_zero_polynomial(denominator, symbols):
                # The expression is a rational function whose denominator
                # vanishes identically: it has no value *anywhere*, so it
                # cannot be the zero expression.  Without this guard, 0/0
                # would pass for 0 -- and a relation that has no meaning
                # would be reported as proved.
                return False
            if sp.count_ops(numerator) <= self.identity_budget_ops:
                if self._term_bound(numerator, self.expand_term_budget) > self.expand_term_budget:
                    # Expanding this would take longer than anyone would
                    # wait, and would use more memory than the machine
                    # should spare.  The judge falls back to sampling,
                    # which is honest about how much it knows -- and the
                    # other reductions below are no cheaper, because they
                    # all expand too.
                    return False
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

    @staticmethod
    def _is_zero_polynomial(expression: Expr, symbols: list[sp.Symbol]) -> bool:
        """Is this expression the zero polynomial in these symbols?

        An expression that is not a polynomial in them at all -- because it
        has a square root in it, say -- is not the zero polynomial; the
        answer is "no", not "I do not know".
        """
        try:
            return bool(sp.Poly(expression, *symbols, domain=sp.QQ).is_zero)
        except Exception:  # pragma: no cover - not a polynomial after all
            return False

    def to_float(self, value: ExprLike) -> float:
        return float(sp.N(self.coerce(value)))


FIELD = SympyField()
