"""The MCP tool contract, as data.

``docs/spec.md`` section 11.1 is the prose form of this table.
``tests/contract/test_mcp_contract.py`` checks the two against each other,
so the document and the code cannot drift apart: a tool that is added here
but not to the document (or the other way round) fails the contract gate.

The table says *which* tools exist and *what* they take. It deliberately
does not repeat the JSON schema: the schema is generated from the tool
function's signature, so there is exactly one copy of it in the codebase.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldSpec:
    """One input field of a tool."""

    name: str
    kind: str
    """``string``, ``integer``, ``boolean``, ``array`` or ``object``."""
    required: bool
    description: str


@dataclass(frozen=True)
class ToolSpec:
    """One tool of the MCP interface."""

    name: str
    summary: str
    description: str
    inputs: tuple[FieldSpec, ...]
    output: str
    """What the tool returns, in one line."""

    @property
    def required_inputs(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.inputs if f.required)

    @property
    def optional_inputs(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.inputs if not f.required)

    @property
    def input_names(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.inputs)


TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="geo_state",
        summary="Read the current figure.",
        description=(
            "Return the construction graph of a figure, together with a validation "
            "summary and the current degeneracy report. Use it to find out what "
            "the figure actually contains before building on it."
        ),
        inputs=(
            FieldSpec(
                name="figure_id",
                kind="string",
                required=False,
                description="Which figure to read. Omit it for the default figure.",
            ),
        ),
        output="The figure, its validation summary and its degeneracy report.",
    ),
    ToolSpec(
        name="geo_construct",
        summary="Apply a batch of constructions to a figure.",
        description=(
            "Apply a batch of operations to a figure: each operation names an "
            "operator and its arguments. The whole batch is applied atomically: "
            "if any operation fails, none of them is committed. Use mode "
            "'dry-run' to see what would happen without changing anything."
        ),
        inputs=(
            FieldSpec(
                name="figure_id",
                kind="string",
                required=False,
                description="Which figure to change. Omit it for the default figure.",
            ),
            FieldSpec(
                name="ops",
                kind="array",
                required=True,
                description=(
                    "The operations to apply, in order. Each is an object with "
                    "'op' (an operator id), 'args' (its arguments) and an "
                    "optional 'id' (the node id to create)."
                ),
            ),
            FieldSpec(
                name="mode",
                kind="string",
                required=False,
                description="'apply' to commit the batch, 'dry-run' to only report.",
            ),
        ),
        output="The ids created, updated and removed, plus any errors.",
    ),
    ToolSpec(
        name="geo_evaluate",
        summary="Evaluate a geometric quantity exactly.",
        description=(
            "Evaluate a geometric expression on a figure and return both the "
            "exact value (in terms of the free points' symbols) and a display "
            "approximation (under the figure's current placement). Supported "
            "expressions: Angle(B,A,C) for the angle at A, Distance(A,B) for a "
            "length, and Area(A,B,C) for an area. An unknown name is an error, "
            "never a guess."
        ),
        inputs=(
            FieldSpec(
                name="figure_id",
                kind="string",
                required=False,
                description="Which figure to evaluate on. Omit it for the default figure.",
            ),
            FieldSpec(
                name="expr",
                kind="string",
                required=True,
                description="The expression to evaluate, e.g. 'Angle(B,A,C)'.",
            ),
        ),
        output="The exact value and its display approximation.",
    ),
)

TOOL_SPECS_BY_NAME = {spec.name: spec for spec in TOOL_SPECS}


#: The tools of docs/spec.md section 11.1 that are not implemented yet.
#:
#: They are listed here rather than left out of the contract, so that the
#: contract test can insist that the union of the two sets is exactly the
#: set of tools the specification promises. A tool cannot quietly vanish.
PENDING_TOOLS: tuple[str, ...] = (
    "geo_verify",
    "geo_solve",
    "geo_variants",
    "geo_check_degenerate",
    "geo_render",
    "geo_apply_dsl",
    "geo_to_dsl",
)
