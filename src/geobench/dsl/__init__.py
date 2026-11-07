"""The Chinese geometry DSL: text in, construction graph out.

The syntax is function-call, with GeoGebra's Chinese command names::

    点 A(0,0) B(6,0)
    M = 中点(A,B)
    断言 共线(A,M,B)

GeoGebra's English command names are accepted too, because GeoGebra's own
input bar accepts English in every language (decision D17).
"""

from __future__ import annotations

from geobench.dsl.errors import DSLParseError, Span
from geobench.dsl.generate import apply_dsl, to_dsl
from geobench.dsl.parser import parse, parse_dsl

__all__ = [
    "DSLParseError",
    "Span",
    "apply_dsl",
    "parse",
    "parse_dsl",
    "to_dsl",
]
