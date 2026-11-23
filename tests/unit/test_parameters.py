"""Free numbers: a constant a lesson can drag.

``数 a = 2.5`` makes a number an object.  It is exact (5/2), it can be
used wherever a construction takes a number -- a radius, an angle, a
parameter -- and the construction remains exact, because the constant
is exact too.

The slider is the interface; this file is the arithmetic behind it.
"""

from __future__ import annotations

import pytest

from geobench.dsl import parse_dsl, to_dsl
from geobench.dsl.errors import DSLParseError
from geobench.errors import GeobenchError
from geobench.evaluate import evaluate_figure
from geobench.operators import register_builtins
from geobench.primitives import CirclePrimitive, figure_primitives
from geobench.registry import OperatorRegistry
from geobench.style import COMPETITION


@pytest.fixture()
def registry() -> OperatorRegistry:
    ops = OperatorRegistry()
    register_builtins(ops)
    return ops


def test_a_number_is_an_exact_object(registry: OperatorRegistry) -> None:
    figure = parse_dsl("数 a = 2.5\n点 P(0,0)\n")
    node = figure.nodes["a"]
    assert node.kind == "number"
    assert node.role == "free"
    assert node.op == "number.free"
    assert node.args == ["5/2"]


def test_a_number_can_be_a_radius(registry: OperatorRegistry) -> None:
    figure = evaluate_figure(
        parse_dsl("数 a = 2.5\n点 P(0,0)\nw = 圆(P, a)\n"), registry
    )
    circle = figure.nodes["w"]
    assert str(circle.cache["circle"][2]) == "25/4"
    drawn = [
        primitive
        for primitive in figure_primitives(figure, COMPETITION)
        if isinstance(primitive, CirclePrimitive)
    ]
    assert drawn and drawn[0].radius == pytest.approx(2.5)


def test_a_number_can_be_an_angle(registry: OperatorRegistry) -> None:
    figure = evaluate_figure(
        parse_dsl(
            "数 a = 90\n"
            "点 A(0,0) B(1,0)\n"
            "C = 旋转(B, a, A)\n"
        ),
        registry,
    )
    node = figure.nodes["C"]
    assert node.coords is not None
    coords = node.cache["numeric"]["coords"]
    assert coords[0] == pytest.approx(0.0, abs=1e-12)
    assert coords[1] == pytest.approx(1.0, abs=1e-12)


def test_the_number_and_its_uses_survive_the_round_trip(
    registry: OperatorRegistry,
) -> None:
    source = "数 a = 2.5\n点 P(0,0)\nw = 圆(P, a)\n"
    figure = parse_dsl(source)
    text = to_dsl(figure)
    assert "数 a = 5/2" in text
    again = parse_dsl(text)
    assert again.nodes["a"].args == ["5/2"]
    assert again.nodes["w"].args == ["P", "a"]


def test_a_measured_number_is_not_a_parameter(registry: OperatorRegistry) -> None:
    """A measurement moves with the figure; a parameter must not."""
    figure = parse_dsl(
        "点 A(0,0) B(3,0)\n"
        "AB = 线段(A, B)\n"
        "r = 长度(AB)\n"
        "w = 圆(A, r)\n"
    )
    with pytest.raises(GeobenchError) as caught:
        evaluate_figure(figure, registry)
    assert "free number" in str(caught.value)


def test_a_number_needs_a_number() -> None:
    with pytest.raises(DSLParseError):
        parse_dsl("数 a = b\n")


def test_a_number_statement_needs_its_parts() -> None:
    with pytest.raises(DSLParseError):
        parse_dsl("数 a\n")
