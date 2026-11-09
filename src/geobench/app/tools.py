"""The construction tools, generated from the command table.

The toolbar is not maintained by hand. Every implemented construction in
the command table becomes a tool, in the group of its family -- the
families are GeoGebra's own grouping (points, lines, polygons, circles,
transforms, measurements), so the toolbar and the table cannot drift
apart in the way a hand-written list always does.

What a tool needs, and where it comes from:

- **which objects to click** -- the operator's argument types, which are
  the real contract (the command table's ``arg_kinds`` is a summary);
- **what it is called** -- the command's Chinese name;
- **how to say it** -- generated from the argument types ("依次选 2 个点").

The one thing not generated is the order of the groups, because that is
a design decision, not a fact about the table.
"""

from __future__ import annotations

from dataclasses import dataclass

from geobench.commands import COMMANDS, JUDGEMENT, CommandSpec
from geobench.registry import ArgSpec, OperatorRegistry

__all__ = [
    "POINT_TOOL",
    "ToolArg",
    "ToolGroup",
    "ToolSpec",
    "build_toolbar",
]

#: The order of the groups. GeoGebra's, roughly: the things a figure is
#: drawn from first, then what is measured on it.
GROUPS: tuple[tuple[str, str], ...] = (
    ("点", "点"),
    ("线", "线"),
    ("多边形", "多边形"),
    ("圆", "圆"),
    ("变换", "变换"),
    ("测量", "测量"),
)

#: How each argument type is described to the user.
_KIND_TEXT = {
    "point": "点",
    "line": "线",
    "segment": "线段",
    "circle": "圆",
    "polygon": "多边形",
    "scalar": "数字",
    "selector": "交点选择",
}

#: The argument kinds a click can pick.
CLICKABLE = frozenset({"point", "line", "segment", "circle", "polygon"})


@dataclass(frozen=True)
class ToolArg:
    """One argument a tool needs."""

    kind: str
    default: str = ""

    @property
    def clickable(self) -> bool:
        return self.kind in CLICKABLE

    @property
    def text(self) -> str:
        return _KIND_TEXT.get(self.kind, self.kind)


@dataclass(frozen=True)
class ToolSpec:
    """One construction tool."""

    key: str
    label: str
    op: str
    args: tuple[ToolArg, ...]
    variable: bool = False
    min_args: int = 0
    summary: str = ""
    var_kind: str = "point"
    """The kind of the extra arguments a variable tool keeps collecting."""

    @property
    def hint(self) -> str:
        """What to do with this tool, in one line."""
        if self.op == "point.free":
            return "在空白处点击，放一个自由点"
        if self.variable:
            return f"依次选{self.min_args}个以上的{self.args[0].text}，按回车结束"
        if not self.args:
            return "点一下"
        parts = "、".join(
            f"{count} 个{arg.text}" for arg in self.args for count in [1]
        )
        # Consecutive arguments of the same kind read better together.
        collected: list[tuple[str, int]] = []
        for arg in self.args:
            if collected and collected[-1][0] == arg.text:
                collected[-1] = (arg.text, collected[-1][1] + 1)
            else:
                collected.append((arg.text, 1))
        parts = "、".join(f"{count} 个{text}" for text, count in collected)
        return f"依次选：{parts}"

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "op": self.op,
            "args": [arg.kind for arg in self.args],
            "variable": self.variable,
            "hint": self.hint,
        }


@dataclass(frozen=True)
class ToolGroup:
    """A group of tools: one button on the toolbar, one menu under it."""

    key: str
    label: str
    tools: tuple[ToolSpec, ...]


#: The point tool is always first and always armed at startup: a figure
#: starts with points.
POINT_TOOL = ToolSpec(
    key="point.free",
    label="点",
    op="point.free",
    args=(),
    summary="放一个自由点",
)


def _arg_specs(registry: OperatorRegistry, command: CommandSpec) -> tuple[ArgSpec, ...]:
    try:
        return registry.lookup(command.id).args
    except Exception:  # pragma: no cover - the table and the registry agree
        return ()


def _tool_from(command: CommandSpec, specs: tuple[ArgSpec, ...]) -> ToolSpec:
    """One tool from one command."""
    variable = bool(specs) and specs[-1].variadic
    required = specs[:-1] if variable else specs
    args = tuple(
        ToolArg(kind=spec.type, default="second" if spec.type == "selector" else "")
        for spec in required
    )
    return ToolSpec(
        key=command.id,
        label=command.name_zh,
        op=command.id,
        args=args,
        variable=variable,
        min_args=len(required),
        summary=command.summary,
        var_kind=specs[-1].type if variable else "point",
    )


def _distinct(tools: list[ToolSpec]) -> tuple[ToolSpec, ...]:
    """Give tools that share a name a suffix that says how they differ.

    ``圆`` is both "a circle with a radius" and "a circle through a
    point"; two menu entries with the same word would be a guess.
    """
    counts: dict[str, int] = {}
    for tool in tools:
        counts[tool.label] = counts.get(tool.label, 0) + 1
    out: list[ToolSpec] = []
    for tool in tools:
        if counts[tool.label] == 1:
            out.append(tool)
            continue
        if tool.args:
            kind = "、".join(dict.fromkeys(arg.text for arg in tool.args))
            out.append(
                ToolSpec(
                    key=tool.key,
                    label=f"{tool.label}（{kind}）",
                    op=tool.op,
                    args=tool.args,
                    variable=tool.variable,
                    min_args=tool.min_args,
                    summary=tool.summary,
                    var_kind=tool.var_kind,
                )
            )
        else:
            out.append(tool)
    return tuple(out)


def build_toolbar(registry: OperatorRegistry) -> tuple[ToolGroup, ...]:
    """The whole toolbar: one group per family, generated from the table."""
    groups: list[ToolGroup] = []
    used: set[str] = set()
    for family, label in GROUPS:
        tools: list[ToolSpec] = []
        for command in COMMANDS:
            if command.family != family:
                continue
            # Anything that makes a node is a tool: a construction makes
            # a figure object, a measurement makes a number. A judgement
            # makes neither, so it lives in the judgement pane instead.
            if command.kind == JUDGEMENT or not command.implemented:
                continue
            if command.alias_of is not None:
                # A synonym is not a separate tool; it is the same tool
                # under another name.
                continue
            if command.id in used:
                continue
            if command.id == "point.free":
                continue
            used.add(command.id)
            tools.append(_tool_from(command, _arg_specs(registry, command)))
        if tools:
            groups.append(
                ToolGroup(key=family, label=label, tools=_distinct(tools))
            )

    # The point tool goes into the first group so the toolbar opens on it.
    point_group = ToolGroup(
        key="点", label="点", tools=(POINT_TOOL, *groups[0].tools)
    ) if groups and groups[0].key == "点" else groups[0]
    if groups:
        groups[0] = point_group
    return tuple(groups)
