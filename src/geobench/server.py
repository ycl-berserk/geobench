"""The geobench MCP server.

The server is a thin shell around the kernel. It owns no geometry of its
own, it never calls a model, and every tool is a function of the figure
store plus its arguments -- so an agent that has the tools has everything
the kernel knows, and nothing it does not.

Run it with::

    geobench-mcp

which speaks MCP over stdio.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from geobench import __version__
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry
from geobench.state import FigureStore
from geobench.tools import register_tools

INSTRUCTIONS = """\
geobench is a deterministic plane-geometry kernel. It builds figures from
exact constructions and adjudicates claims about them.

The usual loop is:

1. geo_construct -- apply a batch of operations (points, lines, circles,
   segments) and read back the ids it created;
2. geo_evaluate -- ask for an exact quantity (an angle, a length, an area)
   and get both the symbolic value and the number on screen;
3. geo_state -- read the whole figure back when you need to see what
   exists.

Two rules matter. First, every response carries a status: 'ok', 'error'
(the request was wrong -- fix it) or 'degraded' (the request was fine but
the geometry could not be completed, for instance a degenerate
configuration). Second, the kernel never guesses: an unknown node id, an
unknown operator and an expression naming a point that does not exist are
all errors, not defaults.
"""


def build_registry() -> OperatorRegistry:
    """A registry holding every built-in operator."""
    registry = OperatorRegistry()
    register_builtins(registry)
    return registry


def build_server(
    store: FigureStore | None = None, registry: OperatorRegistry | None = None
) -> MCPServer:
    """Build the MCP server.

    The store and the registry can be supplied, which is how the tests
    drive several figures without sharing state.
    """
    if registry is None:
        registry = build_registry()
    if store is None:
        store = FigureStore(registry)
    server = MCPServer(
        name="geobench",
        version=__version__,
        instructions=INSTRUCTIONS,
    )
    register_tools(server, store, registry)
    return server


def main() -> None:
    """Entry point of the ``geobench-mcp`` command."""
    build_server().run("stdio")


if __name__ == "__main__":  # pragma: no cover
    main()
