"""The GeoGebra command table.

The table is the single source of truth for names: the DSL resolves a
command name through it, the toolbar is generated from it, and the
coverage table in the plan document is checked against it. These tests
are what keep the three in agreement -- and what stops the document from
quietly falling behind the code.
"""

from __future__ import annotations

import re
from pathlib import Path

from geobench.commands import (
    COMMANDS,
    FAMILIES,
    JUDGEMENT,
    SELECTORS,
    CommandSpec,
    by_id,
    coverage_rows,
    implemented,
    lookup,
    lookup_all,
)
from geobench.judges import JudgeRegistry
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry

ROOT = Path(__file__).resolve().parents[2]


def _operators() -> OperatorRegistry:
    registry = OperatorRegistry()
    register_builtins(registry)
    return registry


def test_every_command_has_a_family_we_know() -> None:
    for command in COMMANDS:
        assert command.family in FAMILIES, f"{command.id} is in no known family"


def test_the_overloads_are_told_apart_by_their_arguments() -> None:
    """GeoGebra overloads names on purpose; we must be able to tell them apart.

    Two commands may share a name only if they differ in how many
    arguments they take or in what those arguments are -- otherwise the
    DSL could not know which one was meant.
    """
    registry = _operators()
    by_name: dict[str, list[tuple[tuple[object, ...], str]]] = {}
    for command in COMMANDS:
        if command.alias_of is not None:
            continue
        by_name.setdefault(command.name_zh, []).append(
            (_signature(command, registry), command.id)
        )
        by_name.setdefault(command.name_en, []).append(
            (_signature(command, registry), command.id)
        )
    for name, entries in by_name.items():
        signatures = [signature for signature, _ in entries]
        assert len(set(signatures)) == len(signatures), (
            f"{name!r} is used by commands that cannot be told apart: "
            f"{', '.join(command_id for _, command_id in entries)}"
        )


def _signature(command: CommandSpec, registry: OperatorRegistry) -> tuple[object, ...]:
    """What a command looks like from the caller's side."""
    if command.kind == JUDGEMENT:
        return (command.kind, command.arity, command.arg_kinds)
    specs = {spec.id: spec for spec in registry.all_specs()}
    spec = specs.get(command.id)
    if spec is None:
        return (command.kind, command.arity)
    return (command.kind, command.arity, tuple(arg.type for arg in spec.args))


def test_every_operator_we_have_is_in_the_table() -> None:
    """An operator with no command name cannot be reached from the DSL."""
    registry = _operators()
    for spec in registry.all_specs():
        assert by_id(spec.id) is not None, f"operator {spec.id!r} is not in the table"


def test_every_judge_we_have_is_in_the_table() -> None:
    judges = JudgeRegistry()
    for judge_id in judges.ids():
        command = by_id(judge_id)
        assert command is not None, f"judge {judge_id!r} is not in the table"
        assert command.kind == JUDGEMENT


def test_a_command_marked_done_actually_exists() -> None:
    """The table must not claim more than the code has."""
    registry = _operators()
    judges = JudgeRegistry()
    for command in implemented():
        # A synonym is implemented by the command it points at.
        target = command.alias_of or command.id
        if command.kind == JUDGEMENT:
            assert judges.has(target), f"{command.id} is marked done but has no judge"
        elif command.id == "point.free":
            continue  # handled by the store, not by an operator
        else:
            assert registry.has(target), (
                f"{command.id} is marked done but has no operator"
            )


def test_a_command_is_found_by_either_name() -> None:
    """GeoGebra's input bar accepts English in every language, so ours does."""
    for command in COMMANDS:
        assert lookup(command.name_zh) is not None
        assert lookup(command.name_en) is not None


def test_the_overloaded_names_keep_all_their_meanings() -> None:
    """``交点`` is three different commands; all of them must be reachable."""
    intersections = lookup_all("交点")
    assert len(intersections) == 3
    assert {command.id for command in intersections} == {
        "point.intersect_lines",
        "point.intersect_line_circle",
        "point.intersect_circles",
    }


def test_the_selectors_are_canonical() -> None:
    """The graph holds the canonical value, not the Chinese word."""
    assert SELECTORS["另一交点"] == "other"
    for value in SELECTORS.values():
        assert value in {"0", "1", "other"}


def test_the_coverage_table_has_a_row_for_every_command() -> None:
    rows = coverage_rows()
    assert len(rows) == len(COMMANDS)
    for command in COMMANDS:
        assert any(row[2] == command.id for row in rows)


def test_the_plan_document_knows_about_every_command() -> None:
    """The document is the checklist; it must not fall behind the code."""
    plan = (ROOT / "docs" / "plan.md").read_text(encoding="utf-8")
    missing = [command.id for command in COMMANDS if command.id not in plan]
    assert not missing, f"docs/plan.md does not mention: {', '.join(missing)}"


def test_the_plan_document_marks_what_is_done() -> None:
    """The tick marks in the document must match the table."""
    plan = (ROOT / "docs" / "plan.md").read_text(encoding="utf-8")
    for command in COMMANDS:
        row = _row_for(plan, command.id)
        assert row is not None, f"docs/plan.md has no row for {command.id}"
        done = "[x]" in row
        assert done == command.implemented, (
            f"docs/plan.md and the command table disagree about {command.id}"
        )


def _row_for(plan: str, command_id: str) -> str | None:
    """The table row that mentions this command id, and only this one."""
    for line in plan.splitlines():
        if f"`{command_id}`" in line and line.strip().startswith("|"):
            return line
    return None


def test_the_command_names_are_written_in_chinese() -> None:
    """A Chinese name that is only ASCII is a placeholder, not a name."""
    for command in COMMANDS:
        assert re.search(r"[\u4e00-\u9fff]", command.name_zh), (
            f"{command.id} has no Chinese name"
        )
