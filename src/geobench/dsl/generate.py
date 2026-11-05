"""DSL -> construction graph, and back.

The reverse direction matters as much as the forward one: a problem file must
be able to state its figure in the same language a person would write, and
the two directions must agree. The round trip is a property test
(``tests/property/test_dsl_roundtrip.py``).
"""

from __future__ import annotations

from typing import NoReturn

from geobench.dsl.parser import parse_dsl
from geobench.model import Figure

__all__ = ["apply_dsl", "parse_dsl", "to_dsl"]


def apply_dsl(source: str, figure: Figure | None = None) -> Figure:
    """Parse a DSL script and return the construction graph it describes.

    Raises :class:`DSLParseError` with an exact position when the script is
    malformed -- the caller (an agent, typically) is expected to fix and
    retry rather than to receive a half-built figure.
    """
    parsed = parse_dsl(source)
    if figure is None:
        return parsed
    # Merge into an existing figure: the parsed nodes are added to it.
    for node in parsed.nodes.values():
        figure.add_node(node)
    for relation in parsed.relations:
        figure.add_relation(relation)
    return figure


def to_dsl(figure: Figure) -> str:
    """Render a construction graph back into DSL text."""
    lines: list[str] = []
    free_points = [
        node for node in figure.nodes.values() if node.role == "free" and node.kind == "point"
    ]
    if free_points:
        parts = []
        for node in free_points:
            placement = node.placement or ("0", "0")
            parts.append(f"{node.id}({placement[0]},{placement[1]})")
        lines.append("点 " + " ".join(parts))

    for node in figure.nodes.values():
        if node.role != "derived":
            continue
        if node.op == "segment.free" and len(node.args) == 2:
            lines.append(f"线段 {node.id}")
        elif node.op == "line.free" and len(node.args) == 2:
            lines.append(f"直线 {node.id} = 过 {node.args[0]} {node.args[1]}")
        elif node.op == "circle.through" and len(node.args) == 3:
            lines.append(f"⊙{node.id} = 过 {node.args[0]} {node.args[1]} {node.args[2]}")
        elif node.op == "circle.free" and len(node.args) == 2:
            lines.append(f"⊙{node.id} = 以 {node.args[0]} 为圆心 半径 {node.args[1]}")
        else:
            assert node.op is not None
            lines.append(f"{node.id} = {_clause(node.op, node.args)}")

    for relation in figure.relations:
        lines.append(_assertion(relation.kind, relation.args))

    return "\n".join(lines) + ("\n" if lines else "")


def _clause(op: str, args: list[str]) -> str:
    if op == "point.midpoint":
        return f"{args[0]}{args[1]} 中点"
    if op == "point.foot":
        return f"{args[1]} 上 {args[0]} 的垂足"
    if op == "point.intersect_lines":
        return f"{args[0]} 与 {args[1]} 的交点"
    if op == "point.intersect_line_circle":
        selector = args[2] if len(args) > 2 else "0"
        word = "另一交点" if selector == "other" else "交点"
        return f"{args[0]} 与 {args[1]} 的{word}"
    if op == "point.incenter":
        return f"△{_triangle(args)} 的内心"
    if op == "point.circumcenter":
        return f"△{_triangle(args)} 的外心"
    if op == "point.orthocenter":
        return f"△{_triangle(args)} 的垂心"
    if op == "point.centroid":
        return f"△{_triangle(args)} 的重心"
    if op == "line.perpendicular_through":
        return f"过 {args[0]} 的 {args[1]} 的垂线"
    if op == "line.parallel_through":
        return f"过 {args[0]} 的 {args[1]} 的平行线"
    raise _unknown(op)


def _unknown(op: str) -> NoReturn:
    raise ValueError(f"cannot express operator {op!r} in the DSL yet")


def _triangle(args: list[str]) -> str:
    return "".join(args)


def _assertion(kind: str, args: list[str]) -> str:
    if kind == "collinear":
        return f"断言 {' '.join(args)} 共线"
    if kind == "concyclic":
        return f"断言 {' '.join(args)} 共圆"
    if kind == "equal_length":
        return f"断言 {args[0]}{args[1]} = {args[2]}{args[3]}"
    if kind == "perpendicular":
        return f"断言 {args[0]} ⊥ {args[1]}"
    raise _unknown(kind)
