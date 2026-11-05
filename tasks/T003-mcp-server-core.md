# T003 — MCP server core: `geo_state`, `geo_construct`, `geo_evaluate`

**Status**: proposed
**Owner**: agent
**Spec**: `docs/spec.md` §11 (MCP interface), §13
**Depends on**: T001
**Layers touched**: server

## Goal

The kernel becomes reachable by an MCP client. The three tools in this task are enough for an agent to build a figure from scratch and read its exact state — which is the precondition for everything else.

## Deliverables

- `src/geobench/server.py` — MCP server over stdio (streamable HTTP in a later task), exposing the tool set of `spec.md` §11.1.
- `src/geobench/tools/state.py`, `tools/construct.py`, `tools/evaluate.py` — one module per tool.
- Tool schemas generated from the spec (single source: the registry / spec constants, not hand-written JSON in two places).
- `src/geobench/errors.py` — typed errors with actionable messages: unknown node id, wrong argument type, wrong arity, degenerate configuration, ambiguous intersection index.
- `tests/contract/test_mcp_contract.py` — asserts the live tool list and schemas match `spec.md` §11.1.
- `tests/integration/test_client_session.py` — drives the server through a real MCP client session.

## Acceptance criteria

```bash
pytest tests/contract -q
pytest tests/integration -q
ruff check . && mypy src
```

Additionally, by hand:
- `geo_construct` in `dry-run` mode leaves the figure untouched (byte-identical `geo_state` before and after).
- An unknown node id in `args` returns `status: "error"` with the offending id and the list of valid ids.
- `geo_evaluate` on `Angle(B,A,C)` returns an exact value and a display approximation, and evaluating an expression with an unknown symbol errors rather than guessing.
- Every response is valid JSON with a `status` field of `ok` / `error` / `degraded`.

## Non-goals

- `geo_verify`, `geo_solve`, `geo_variants`, `geo_check_degenerate`, `geo_render` (later tasks).
- Any model calls inside the server. The kernel contains no model (decision D4).
- Authentication or multi-user state (v1 is single-user, local).
