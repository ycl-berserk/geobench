"""DSL -> construction graph, and back.

The reverse direction matters as much as the forward one: a problem file must
be able to state its figure in the same language a person would write, and
the two directions must agree. The round trip is a property test
(``tests/property/test_dsl_roundtrip.py``).

The text produced here uses the same Chinese command names the parser
accepts, so a figure and its script read the same way (decision D17).
"""

from __future__ import annotations

from typing import NoReturn

from geobench.commands import JUDGEMENT, by_id
from geobench.dsl.parser import parse
from geobench.model import Figure
from geobench.style import describe_color

__all__ = ["apply_dsl", "parse", "parse_dsl", "to_dsl"]

#: How a selector argument is written back out.
_SELECTOR_TEXT = {
    "0": "第一交点",
    "1": "第二交点",
    "other": "另一交点",
}


def apply_dsl(source: str, figure: Figure | None = None) -> Figure:
    """Parse a DSL script and return the construction graph it describes.

    Raises :class:`DSLParseError` with an exact position when the script is
    malformed -- the caller (an agent, typically) is expected to fix and
    retry rather than to receive a half-built figure.
    """
    parsed = parse(source)
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
    free_numbers = [
        node
        for node in figure.nodes.values()
        if node.role == "free" and node.kind == "number" and node.op == "number.free"
    ]
    for node in free_numbers:
        lines.append(f"数 {node.id} = {node.args[0]}")

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
        if node.role not in ("derived", "attached"):
            continue
        assert node.op is not None
        lines.append(f"{node.id} = {_call(node.op, node.args)}")

    # The attributes come last: they speak about objects that are
    # already there.
    for node in figure.nodes.values():
        if not node.style.visible:
            lines.append(f"\u9690\u85cf {node.id}")
        if node.style.line_style == "dashed":
            lines.append(f"\u8f85\u52a9 {node.id}")
        if node.style.color not in ("", "#000000"):
            lines.append(f"\u989c\u8272 {node.id} {describe_color(node.style.color)}")
        if node.style.line_width is not None:
            lines.append(f"\u7ebf\u5bbd {node.id} {node.style.line_width:g}")
        if node.style.point_size is not None:
            lines.append(f"\u70b9\u5927\u5c0f {node.id} {node.style.point_size:g}")
        if node.style.label_pos:
            lines.append(f"\u6807\u7b7e\u4f4d\u7f6e {node.id} {node.style.label_pos}")

    for relation in figure.relations:
        lines.append(_assertion(relation.kind, relation.args))

    return "\n".join(lines) + ("\n" if lines else "")


def _call(op: str, args: list[str]) -> str:
    command = by_id(op)
    if command is None:
        raise _unknown(op)
    rendered = [_argument(arg) for arg in args]
    return f"{command.name_zh}({', '.join(rendered)})"


def _argument(arg: str) -> str:
    if arg in _SELECTOR_TEXT:
        return _SELECTOR_TEXT[arg]
    return arg


def _assertion(kind: str, args: list[str]) -> str:
    command = by_id(kind)
    if command is None or command.kind != JUDGEMENT:
        raise _unknown(kind)
    rendered = ", ".join(args)
    return f"断言 {command.name_zh}({rendered})"


def _unknown(op: str) -> NoReturn:
    raise ValueError(f"cannot express operator {op!r} in the DSL yet")


#: The old name, kept so that existing callers keep working.
parse_dsl = parse
