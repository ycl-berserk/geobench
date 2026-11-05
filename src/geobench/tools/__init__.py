"""The MCP tools of the geobench server.

Each tool is a function over the figure store, wrapped so that the MCP
layer can expose it with a flat, agent-friendly signature. The tool
contract itself lives in :mod:`geobench.tools.spec`.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from geobench.registry import OperatorRegistry
from geobench.state import FigureStore
from geobench.tools.construct import make_construct_tool
from geobench.tools.evaluate import make_evaluate_tool
from geobench.tools.spec import PENDING_TOOLS, TOOL_SPECS, TOOL_SPECS_BY_NAME
from geobench.tools.state import DEFAULT_FIGURE_ID, make_state_tool

__all__ = [
    "DEFAULT_FIGURE_ID",
    "PENDING_TOOLS",
    "TOOL_SPECS",
    "TOOL_SPECS_BY_NAME",
    "register_tools",
]


def register_tools(
    server: MCPServer, store: FigureStore, registry: OperatorRegistry
) -> None:
    """Register every implemented tool on ``server``."""
    server.add_tool(
        make_state_tool(store),
        name="geo_state",
        description=TOOL_SPECS_BY_NAME["geo_state"].description,
    )
    server.add_tool(
        make_construct_tool(store, registry),
        name="geo_construct",
        description=TOOL_SPECS_BY_NAME["geo_construct"].description,
    )
    server.add_tool(
        make_evaluate_tool(store, registry),
        name="geo_evaluate",
        description=TOOL_SPECS_BY_NAME["geo_evaluate"].description,
    )
