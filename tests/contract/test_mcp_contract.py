"""The live MCP interface must match ``docs/spec.md`` section 11.1.

The specification is the promise; this file is the check. A tool that is
implemented but not documented, or documented but not implemented, fails
here -- as does a tool whose schema has drifted away from the contract
table in :mod:`geobench.tools.spec`.

The schema is generated from the tool functions' signatures, so it is
checked rather than copied: there is exactly one copy of it in the
codebase, and this test is what keeps it honest.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from geobench.server import build_server
from geobench.tools.spec import PENDING_TOOLS, TOOL_SPECS, ToolSpec

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / "docs" / "spec.md"

_STATUS_VALUES = ["ok", "error", "degraded"]

_ROW = re.compile(r"^\|\s*`(geo_[a-z_]+)`\s*\|(.*)$", flags=re.MULTILINE)


def _spec_section() -> str:
    text = SPEC_PATH.read_text(encoding="utf-8")
    assert "### 11.1" in text, "docs/spec.md no longer has a section 11.1"
    return text.split("### 11.1", 1)[1].split("### 11.2", 1)[0]


def _spec_rows() -> dict[str, str]:
    """The input column of every tool row of the specification table."""
    rows: dict[str, str] = {}
    for match in _ROW.finditer(_spec_section()):
        name = match.group(1)
        cells = [cell.strip() for cell in match.group(2).split("|")]
        rows[name] = cells[0]
    return rows


def _live_tools() -> list[object]:
    server = build_server()
    return asyncio.run(server.list_tools())


def _live_tool(name: str) -> object:
    for tool in _live_tools():
        if tool.name == name:
            return tool
    raise AssertionError(f"the server does not expose a tool called {name!r}")


def _property_kind(schema: dict[str, object]) -> str:
    """The kind of a JSON schema property, ignoring the null arm."""
    kind = schema.get("type")
    if kind in {"string", "array", "object", "integer", "boolean"}:
        return str(kind)
    arms = schema.get("anyOf")
    if isinstance(arms, list):
        for arm in arms:
            if isinstance(arm, dict) and arm.get("type") == "string":
                return "string"
    return str(kind)


def test_the_specification_lists_ten_tools() -> None:
    assert len(_spec_rows()) == 10, "docs/spec.md section 11.1 should list ten tools"


def test_every_documented_tool_is_implemented_or_pending() -> None:
    documented = set(_spec_rows())
    implemented = {spec.name for spec in TOOL_SPECS}
    pending = set(PENDING_TOOLS)
    assert implemented & pending == set(), "a tool is both implemented and pending"
    assert implemented | pending == documented


def test_the_live_server_exposes_exactly_the_implemented_tools() -> None:
    live = {tool.name for tool in _live_tools()}
    assert live == {spec.name for spec in TOOL_SPECS}


@pytest.mark.parametrize("spec", TOOL_SPECS, ids=lambda spec: spec.name)
def test_the_input_schema_matches_the_contract(spec: ToolSpec) -> None:
    tool = _live_tool(spec.name)
    schema = tool.input_schema
    properties = schema.get("properties", {})
    assert set(properties) == set(spec.input_names)
    assert set(schema.get("required", [])) == set(spec.required_inputs)
    for field in spec.inputs:
        assert _property_kind(properties[field.name]) == field.kind


@pytest.mark.parametrize("spec", TOOL_SPECS, ids=lambda spec: spec.name)
def test_the_specification_mentions_every_input(spec: ToolSpec) -> None:
    cell = _spec_rows()[spec.name]
    for field in spec.inputs:
        assert field.name in cell, (
            f"docs/spec.md does not mention the input {field.name!r} of {spec.name}"
        )


@pytest.mark.parametrize("spec", TOOL_SPECS, ids=lambda spec: spec.name)
def test_every_response_carries_a_status(spec: ToolSpec) -> None:
    schema = _live_tool(spec.name).output_schema
    assert schema is not None, f"{spec.name} has no output schema"
    status = schema["properties"]["status"]
    assert status["enum"] == _STATUS_VALUES


@pytest.mark.parametrize("spec", TOOL_SPECS, ids=lambda spec: spec.name)
def test_every_tool_is_described(spec: ToolSpec) -> None:
    tool = _live_tool(spec.name)
    assert tool.description == spec.description
    assert len(tool.description) > 40, "a tool description must say what it is for"


def test_the_tool_names_are_unique() -> None:
    names = [spec.name for spec in TOOL_SPECS]
    assert len(names) == len(set(names))
