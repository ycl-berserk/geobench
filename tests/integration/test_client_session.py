"""Driving the server through a real MCP client session.

The unit tests call the tool functions directly, which would not catch a
broken registration, a schema the client cannot satisfy, or a response
that is not the JSON the specification promises. This suite starts the
server as a **separate process** and talks to it over stdio, exactly the
way an agent would.

The contract gate (tests/contract) checks the *shape* of the interface;
this gate checks that it actually works end to end.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"

STATUS_VALUES = {"ok", "error", "degraded"}


def _server_params() -> StdioServerParameters:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR)
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "geobench.server"],
        env=env,
    )


def _with_session(
    work: Callable[[ClientSession], Awaitable[Any]],
    params: StdioServerParameters | None = None,
) -> Any:
    """Run ``work`` against a freshly started server."""

    async def main() -> Any:
        async with stdio_client(params or _server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await work(session)

    return asyncio.run(main())


def _payload(result: Any) -> dict[str, Any]:
    """The JSON body of a tool response."""
    blocks = [block for block in result.content if getattr(block, "text", None)]
    assert blocks, "the tool returned no text content"
    return json.loads(blocks[0].text)


def _triangle_ops() -> list[dict[str, Any]]:
    return [
        {"id": "A", "op": "point.free", "args": ["0", "0"]},
        {"id": "B", "op": "point.free", "args": ["4", "0"]},
        {"id": "C", "op": "point.free", "args": ["1", "3"]},
    ]


def test_the_client_sees_the_documented_tools() -> None:
    async def work(session: ClientSession) -> list[str]:
        result = await session.list_tools()
        return [tool.name for tool in result.tools]

    names = _with_session(work)
    assert set(names) == {"geo_state", "geo_construct", "geo_evaluate"}


def _console_script() -> str | None:
    """The installed ``geobench-mcp`` command, if the package is installed.

    It lives next to the interpreter running the tests, which is not
    necessarily on ``PATH`` -- so look there too before giving up.
    """
    found = shutil.which("geobench-mcp")
    if found is not None:
        return found
    name = "geobench-mcp.exe" if os.name == "nt" else "geobench-mcp"
    candidate = Path(sys.executable).parent / name
    return str(candidate) if candidate.exists() else None


def test_the_installed_console_script_starts_the_server() -> None:
    """The ``geobench-mcp`` command is what a client config actually names."""
    executable = _console_script()
    if executable is None:
        pytest.skip("geobench is not installed with its console script")

    async def work(session: ClientSession) -> list[str]:
        result = await session.list_tools()
        return [tool.name for tool in result.tools]

    params = StdioServerParameters(command=executable, args=[], env=dict(os.environ))
    names = _with_session(work, params)
    assert set(names) == {"geo_state", "geo_construct", "geo_evaluate"}


def test_a_figure_can_be_built_and_read_back() -> None:
    async def work(session: ClientSession) -> tuple[dict[str, Any], dict[str, Any]]:
        built = _payload(
            await session.call_tool("geo_construct", {"ops": _triangle_ops()})
        )
        state = _payload(await session.call_tool("geo_state", {}))
        return built, state

    built, state = _with_session(work)
    assert built["status"] == "ok"
    assert built["created"] == ["A", "B", "C"]
    assert state["status"] == "ok"
    assert state["node_count"] == 3
    assert {node["id"] for node in state["figure"]["nodes"]} == {"A", "B", "C"}


def test_every_response_is_json_with_a_status() -> None:
    async def work(session: ClientSession) -> list[dict[str, Any]]:
        responses = []
        responses.append(
            _payload(await session.call_tool("geo_construct", {"ops": _triangle_ops()}))
        )
        responses.append(_payload(await session.call_tool("geo_state", {})))
        responses.append(
            _payload(await session.call_tool("geo_evaluate", {"expr": "Area(A,B,C)"}))
        )
        responses.append(
            _payload(await session.call_tool("geo_evaluate", {"expr": "Angle(B,A,Z)"}))
        )
        return responses

    for response in _with_session(work):
        assert response["status"] in STATUS_VALUES


def test_a_dry_run_does_not_change_the_figure() -> None:
    async def work(session: ClientSession) -> tuple[dict[str, Any], dict[str, Any]]:
        await session.call_tool("geo_construct", {"ops": _triangle_ops()})
        before = _payload(await session.call_tool("geo_state", {}))
        preview = _payload(
            await session.call_tool(
                "geo_construct",
                {
                    "ops": [{"id": "M", "op": "point.midpoint", "args": ["A", "B"]}],
                    "mode": "dry-run",
                },
            )
        )
        after = _payload(await session.call_tool("geo_state", {}))
        return preview, {"before": before, "after": after}

    preview, states = _with_session(work)
    assert preview["status"] == "ok"
    assert preview["created"] == ["M"]
    assert states["before"] == states["after"], "a dry run changed the figure"


def test_an_unknown_node_id_is_an_error_that_names_the_legal_ids() -> None:
    async def work(session: ClientSession) -> dict[str, Any]:
        await session.call_tool("geo_construct", {"ops": _triangle_ops()})
        return _payload(
            await session.call_tool(
                "geo_construct",
                {"ops": [{"op": "point.midpoint", "args": ["A", "Q"]}]},
            )
        )

    response = _with_session(work)
    assert response["status"] == "error"
    error = response["errors"][0]
    assert error["code"] == "unknown_node"
    assert error["node_id"] == "Q"
    assert set(error["known_node_ids"]) == {"A", "B", "C"}
    assert "Q" in error["message"]


def test_evaluating_returns_an_exact_value_and_an_approximation() -> None:
    async def work(session: ClientSession) -> dict[str, Any]:
        await session.call_tool("geo_construct", {"ops": _triangle_ops()})
        return _payload(
            await session.call_tool("geo_evaluate", {"expr": "Angle(B,A,C)"})
        )

    response = _with_session(work)
    assert response["status"] == "ok"
    assert response["exact_unit"] == "radian"
    assert response["approx_unit"] == "degree"
    assert response["exact"], "the exact value must not be empty"
    assert response["approx"] == pytest.approx(71.56505117707799)


def test_an_unknown_symbol_is_an_error_rather_than_a_guess() -> None:
    async def work(session: ClientSession) -> dict[str, Any]:
        await session.call_tool("geo_construct", {"ops": _triangle_ops()})
        return _payload(
            await session.call_tool("geo_evaluate", {"expr": "Distance(A,Z)"})
        )

    response = _with_session(work)
    assert response["status"] == "error"
    assert response["exact"] is None
    assert response["approx"] is None
    assert response["errors"][0]["code"] == "unknown_node"


def test_a_degenerate_construction_is_reported_as_degraded() -> None:
    async def work(session: ClientSession) -> dict[str, Any]:
        return _payload(
            await session.call_tool(
                "geo_construct",
                {
                    "ops": [
                        {"id": "A", "op": "point.free", "args": ["0", "0"]},
                        {"id": "B", "op": "point.free", "args": ["4", "0"]},
                        {"id": "C", "op": "point.free", "args": ["8", "0"]},
                        {"id": "O", "op": "point.circumcenter", "args": ["A", "B", "C"]},
                    ]
                },
            )
        )

    response = _with_session(work)
    assert response["status"] == "degraded"
    # A degenerate configuration is not a mistake in the request, so it is
    # reported as a warning: "error" would tell the agent to change
    # something that is already correct.
    assert not response["errors"], "a degenerate construction is not an error"
    assert response["warnings"], "a degraded construction must say why"
    assert "O" in response["warnings"][0]
