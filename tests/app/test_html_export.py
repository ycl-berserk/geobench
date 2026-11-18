"""The figure as a page: small, self-contained, and honest about limits.

The page exists so a teacher can hand a student something they can
move.  Two things make or break that: it has to open without a network
(a page that needs a CDN is a page that stops working), and it has to be
small enough to email.

The numbers in the page are checked against the kernel in
``tests/integration/test_html_page`` (which runs the JavaScript); this
file checks the page itself.
"""

from __future__ import annotations

import pytest
import sympy as sp

from geobench.app.export_html import html_source, js_expression
from geobench.dsl import parse_dsl
from geobench.errors import GeobenchError
from geobench.evaluate import evaluate_figure, evaluate_numeric
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry


@pytest.fixture(scope="module")
def registry() -> OperatorRegistry:
    reg = OperatorRegistry()
    register_builtins(reg)
    return reg


def _page(source: str, registry: OperatorRegistry) -> str:
    figure = evaluate_figure(parse_dsl(source), registry)
    evaluate_numeric(figure)
    return html_source(figure, title="三角形的外心")


TRIANGLE = """
点 A(0,0) B(5,0) C(2,4)
AB = 线段(A, B)
BC = 线段(B, C)
CA = 线段(C, A)
M = 中点(B, C)
O = 外心(A, B, C)
w = 外接圆(A, B, C)
"""


def test_the_page_is_self_contained(registry: OperatorRegistry) -> None:
    """No CDN, no external font, no network: it opens in five years."""
    page = _page(TRIANGLE, registry)
    assert "http://" not in page
    assert "https://" not in page
    assert "//cdn" not in page


def test_the_page_is_small(registry: OperatorRegistry) -> None:
    """A figure is a few kilobytes of formulas, not a geometry engine."""
    page = _page(TRIANGLE, registry)
    assert len(page.encode("utf-8")) < 40_000, len(page.encode("utf-8"))


def test_every_object_has_something_to_move(registry: OperatorRegistry) -> None:
    """Each drawn object carries an id, so the script can update it."""
    page = _page(TRIANGLE, registry)
    for node_id in ("A", "B", "C", "M", "O"):
        assert f'id="o-{node_id}"' in page, node_id
    for node_id in ("AB", "BC", "CA", "w"):
        assert f'id="o-{node_id}"' in page, node_id


def test_the_page_says_how_to_use_it(registry: OperatorRegistry) -> None:
    page = _page(TRIANGLE, registry)
    assert "拖动" in page
    assert "构造步骤" in page


def test_the_title_is_escaped(registry: OperatorRegistry) -> None:
    figure = evaluate_figure(parse_dsl(TRIANGLE), registry)
    evaluate_numeric(figure)
    page = html_source(figure, title="<script>alert(1)</script>")
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def test_a_measurement_cannot_be_dragged_yet(registry: OperatorRegistry) -> None:
    """Saying no is better than a page where half the figure moves.

    A measurement's position is worked out by the kernel from what it
    measures, and that has not been ported to the page: rather than
    draw a number that stays put while the figure moves, the export
    says so and the teacher uses the SVG.
    """
    figure = evaluate_figure(
        parse_dsl(
            """
点 A(0,0) B(4,0)
AB = 线段(A, B)
m = 长度(AB)
"""
        ),
        registry,
    )
    evaluate_numeric(figure)
    with pytest.raises(GeobenchError) as failure:
        html_source(figure, title="测量")
    assert "SVG" in str(failure.value)


# -- the printer ------------------------------------------------------------


def test_a_number_is_a_number() -> None:
    assert js_expression(sp.Rational(1, 3)) == "(1/3)"
    assert js_expression(sp.Integer(5)) == "5"


def test_a_coordinate_is_read_from_the_map() -> None:
    assert js_expression(sp.Symbol("x_A")) == 'v["x_A"]'


def test_a_shared_subterm_is_read_from_the_local_name() -> None:
    assert js_expression(sp.Symbol("t0"), frozenset({"t0"})) == "t0"


def test_a_root_is_a_math_sqrt() -> None:
    assert js_expression(sp.sqrt(2)) == "Math.sqrt(2)"


def test_pi_is_math_pi() -> None:
    assert js_expression(sp.pi) == "Math.PI"


def test_an_acosine_is_a_math_acos() -> None:
    # 1/3 is not a special angle, so the acos survives as an acos.
    assert "Math.acos" in js_expression(sp.acos(sp.Rational(1, 3)))
