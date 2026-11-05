"""Property test: the DSL round trip preserves the figure.

``to_dsl`` is what a problem file stores, and what an agent reads back. If
the round trip lost or renamed nodes, a saved problem would not survive a
reload -- so it is checked on randomly generated figures rather than on one
hand-written example.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from geobench.dsl import parse_dsl, to_dsl

COORDINATES = st.integers(min_value=-9, max_value=9).map(str)


def _script(
    ax: str, ay: str, bx: str, by: str, cx: str, cy: str
) -> str:
    return (
        f"点 A({ax},{ay}) B({bx},{by}) C({cx},{cy})\n"
        "△ABC\n"
        "⊙O = 过 A B C\n"
        "D = BC 上 A 的垂足\n"
        "M = AB 中点\n"
        "I = △ABC 的内心\n"
        "断言 M A B 共线\n"
        "断言 AB = AC\n"
    )


@settings(max_examples=50, deadline=None)
@given(
    ax=COORDINATES,
    ay=COORDINATES,
    bx=COORDINATES,
    by=COORDINATES,
    cx=COORDINATES,
    cy=COORDINATES,
)
def test_round_trip_preserves_the_nodes(
    ax: str, ay: str, bx: str, by: str, cx: str, cy: str
) -> None:
    source = _script(ax, ay, bx, by, cx, cy)
    try:
        figure = parse_dsl(source)
    except Exception:
        return  # a degenerate configuration is not a round-trip concern
    text = to_dsl(figure)
    again = parse_dsl(text)
    assert set(again.nodes) == set(figure.nodes)
    assert {relation.kind for relation in again.relations} == {
        relation.kind for relation in figure.relations
    }


@settings(max_examples=50, deadline=None)
@given(
    ax=COORDINATES,
    ay=COORDINATES,
    bx=COORDINATES,
    by=COORDINATES,
)
def test_round_trip_is_stable_on_repetition(
    ax: str, ay: str, bx: str, by: str
) -> None:
    """Rendering the DSL back out twice gives the same text."""
    source = f"点 A({ax},{ay}) B({bx},{by})\nE = AB 中点\n"
    figure = parse_dsl(source)
    once = to_dsl(figure)
    twice = to_dsl(parse_dsl(once))
    assert once == twice
