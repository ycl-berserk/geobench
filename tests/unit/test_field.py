"""Exact arithmetic: the kernel must never accept an approximation."""

from __future__ import annotations

import pytest
import sympy as sp

from geobench.errors import FieldError
from geobench.field import FIELD


def test_float_literal_is_rejected() -> None:
    with pytest.raises(FieldError):
        FIELD.coerce(0.5)


def test_sympy_float_is_rejected() -> None:
    with pytest.raises(FieldError):
        FIELD.coerce(sp.Float(0.5))


def test_bool_is_rejected() -> None:
    with pytest.raises(FieldError):
        FIELD.coerce(True)


def test_int_and_rational_stay_exact() -> None:
    assert FIELD.coerce(3) == sp.Integer(3)
    assert FIELD.coerce(sp.Rational(1, 3)) == sp.Rational(1, 3)
    assert FIELD.coerce("1/2") == sp.Rational(1, 2)


def test_arithmetic_is_exact() -> None:
    x = sp.Symbol("x")
    assert FIELD.add(x, 1) == x + 1
    assert FIELD.sub(x, 1) == x - 1
    assert FIELD.mul(x, 2) == 2 * x
    assert FIELD.div(x, 2) == x / 2
    assert FIELD.sqrt(2) == sp.sqrt(2)


def test_division_by_zero_is_an_error() -> None:
    with pytest.raises(FieldError):
        FIELD.div(1, 0)


def test_simplify_to_zero_recognises_identities() -> None:
    x = sp.Symbol("x")
    assert FIELD.simplify_to_zero(x - x)
    assert FIELD.simplify_to_zero(sp.sin(x) ** 2 + sp.cos(x) ** 2 - 1)
    assert FIELD.simplify_to_zero((x + 1) - (x + 1))
    assert FIELD.simplify_to_zero(sp.sqrt(8) - 2 * sp.sqrt(2))


def test_simplify_to_zero_rejects_non_identities() -> None:
    x = sp.Symbol("x")
    assert not FIELD.simplify_to_zero(x - 1)
    assert not FIELD.simplify_to_zero(x)
    assert not FIELD.simplify_to_zero(sp.sin(x))


def test_to_float_is_the_only_approximation() -> None:
    assert FIELD.to_float(sp.sqrt(2)) == pytest.approx(1.4142135623730951)
    assert FIELD.to_float(sp.Rational(1, 3)) == pytest.approx(0.3333333333, rel=1e-9)
