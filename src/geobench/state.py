"""Figure store: applies operations to a construction graph.

The store owns the *state* side of the kernel. The operator implementations
own the *mathematics* side. In this milestone only the state side exists, so
an operator without an implementation is reported as a warning rather than
silently producing a wrong figure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from geobench.errors import (
    ArgumentCountError,
    ArgumentTypeError,
    GeobenchError,
    RegistryError,
    StateError,
    UnknownNodeError,
)
from geobench.model import (
    DERIVED,
    FREE,
    POINT,
    Figure,
    Node,
    Relation,
)
from geobench.registry import OperatorRegistry

# The argument types of an operator that name a node. The remaining types
# ("scalar", "selector") are literals carried in the argument itself.
_NODE_ARG_TYPES = frozenset({"point", "line", "circle", "segment"})


@dataclass
class OpRequest:
    """One operation to apply.

    ``op`` is an operator id (``point.midpoint``, ``line.free``, ...) or one of
    the two structural operations ``point.free`` and ``relation.add``.
    """

    op: str
    args: list[Any] = field(default_factory=list)
    id: str | None = None


@dataclass
class ApplyResult:
    """The outcome of applying a batch of operations."""

    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    exceptions: list[GeobenchError] = field(default_factory=list)
    """The failures behind ``errors``, kept as typed exceptions.

    The strings in ``errors`` are for humans; the exceptions carry the
    machine-readable parts (which operator, which argument index, which
    node id, which legal ids) that the MCP layer turns into structured
    error objects.
    """
    figure: Figure | None = None
    """The figure as it stands after the batch.

    In ``dry_run`` mode this is the *would-be* figure and the store still
    holds the old one; in ``apply`` mode it is the figure that was
    committed.
    """

    @property
    def ok(self) -> bool:
        return not self.errors


class FigureStore:
    """A collection of figures plus an undo history for each of them."""

    def __init__(self, registry: OperatorRegistry | None = None) -> None:
        self.registry = registry if registry is not None else OperatorRegistry()
        self._figures: dict[str, Figure] = {}
        self._history: dict[str, list[str]] = {}
        self._counters: dict[str, int] = {}

    # -- figures ----------------------------------------------------------

    def figure(self, figure_id: str) -> Figure:
        """Return the figure, creating an empty one if it does not exist."""
        if figure_id not in self._figures:
            self._figures[figure_id] = Figure(id=figure_id)
            self._history[figure_id] = []
            self._counters[figure_id] = 0
        return self._figures[figure_id]

    def has_figure(self, figure_id: str) -> bool:
        return figure_id in self._figures

    def figure_ids(self) -> list[str]:
        return list(self._figures)

    # -- operations -------------------------------------------------------

    def apply(
        self, figure_id: str, requests: list[OpRequest], dry_run: bool = False
    ) -> ApplyResult:
        """Apply a batch of operations.

        In ``dry_run`` mode nothing is committed: the result reports what
        *would* happen, which is what ``geo_construct`` needs for its preview.
        """
        result = ApplyResult()
        working = self.figure(figure_id).copy()
        snapshot = working.to_json()

        for index, request in enumerate(requests):
            try:
                outcome = self._apply_one(working, request)
            except (StateError, RegistryError) as exc:
                result.errors.append(f"op[{index}] {request.op}: {exc}")
                result.exceptions.append(exc)
                continue
            except ValueError as exc:
                error = StateError(str(exc))
                result.errors.append(f"op[{index}] {request.op}: {error}")
                result.exceptions.append(error)
                continue
            result.created.extend(outcome[0])
            result.updated.extend(outcome[1])
            result.removed.extend(outcome[2])
            result.warnings.extend(outcome[3])

        result.figure = working
        if not dry_run and result.ok:
            self._figures[figure_id] = working
            self._history[figure_id].append(snapshot)
        return result

    def set_figure(self, figure_id: str, figure: Figure) -> None:
        """Replace a figure wholesale.

        The server uses this to commit the *evaluated* form of a figure --
        the one whose derived nodes carry their computed coordinates -- after
        the evaluation pass has succeeded. The undo history is untouched:
        the history holds the states to restore, not the states that were
        committed.
        """
        self._figures[figure_id] = figure
        self._history.setdefault(figure_id, [])
        self._counters.setdefault(figure_id, 0)

    def _apply_one(
        self, figure: Figure, request: OpRequest
    ) -> tuple[list[str], list[str], list[str], list[str]]:
        if request.op == "point.free":
            return self._apply_free_point(figure, request)
        if request.op == "relation.add":
            return self._apply_relation(figure, request)

        spec = self.registry.lookup(request.op)
        if len(request.args) != len(spec.args):
            raise ArgumentCountError(spec.id, len(spec.args), len(request.args))

        node_id = request.id or self._next_id(figure)
        for index, (arg, arg_spec) in enumerate(zip(request.args, spec.args, strict=True)):
            self._check_argument(figure, spec.id, index, arg, arg_spec.type)

        node = Node(
            id=node_id,
            kind=spec.kind,
            role=DERIVED,
            op=spec.id,
            args=[str(arg) for arg in request.args],
        )
        figure.add_node(node)

        warnings: list[str] = []
        if not self.registry.has_implementation(spec.id):
            warnings.append(
                f"operator {spec.id!r} has no implementation yet; "
                "the node is recorded but not evaluated"
            )
        return [node_id], [], [], warnings

    def _check_argument(
        self, figure: Figure, op: str, index: int, arg: Any, expected: str
    ) -> None:
        """Check one argument against the operator's contract.

        The error says which operator, which argument, and what the legal
        node ids are -- an agent can act on that without a second round trip
        to ask what the figure contains.
        """
        if expected not in _NODE_ARG_TYPES:
            # A literal argument: a radius, an intersection selector.
            return
        node_id = str(arg)
        if node_id not in figure.nodes:
            raise UnknownNodeError(node_id, list(figure.nodes), op=op, index=index)
        node = figure.nodes[node_id]
        # A segment carries a line: "the foot on BC" is the same request
        # whether BC is drawn as a segment or as a line.
        if expected == "line" and node.kind in {"line", "segment"}:
            return
        if node.kind != expected:
            raise ArgumentTypeError(op, index, expected, node_id)

    def _apply_free_point(
        self, figure: Figure, request: OpRequest
    ) -> tuple[list[str], list[str], list[str], list[str]]:
        if len(request.args) != 2:
            raise ArgumentCountError("point.free", 2, len(request.args))
        node_id = request.id or self._next_id(figure)
        # A free point carries both a symbolic coordinate (what the judges see)
        # and a numeric placement (what the renderer draws). See spec 3.2.
        placement = (str(request.args[0]), str(request.args[1]))
        coords = (f"x_{node_id}", f"y_{node_id}")
        node = Node(id=node_id, kind=POINT, role=FREE, coords=coords, placement=placement)
        figure.add_node(node)
        return [node_id], [], [], []

    def _apply_relation(
        self, figure: Figure, request: OpRequest
    ) -> tuple[list[str], list[str], list[str], list[str]]:
        if len(request.args) < 2:
            raise ArgumentCountError("relation.add", 2, len(request.args))
        kind = str(request.args[0])
        args = [str(a) for a in request.args[1]]
        relation_id = request.id or f"r{len(figure.relations) + 1}"
        figure.add_relation(
            Relation(id=relation_id, kind=kind, args=args, expected=True)
        )
        return [], [], [relation_id], []

    def remove(self, figure_id: str, node_id: str) -> ApplyResult:
        result = ApplyResult()
        figure = self.figure(figure_id)
        try:
            figure.remove_node(node_id)
        except (StateError, ValueError) as exc:
            result.errors.append(str(exc))
            return result
        result.removed.append(node_id)
        self._history[figure_id].append(figure.to_json())
        return result

    # -- undo -------------------------------------------------------------

    def undo(self, figure_id: str) -> bool:
        """Restore the previous state of the figure. Returns False if empty."""
        history = self._history.get(figure_id)
        if not history:
            return False
        snapshot = history.pop()
        self._figures[figure_id] = Figure.from_json(snapshot)
        return True

    def history_depth(self, figure_id: str) -> int:
        return len(self._history.get(figure_id, []))

    # -- helpers ----------------------------------------------------------

    def _next_id(self, figure: Figure) -> str:
        counter = self._counters.get(figure.id, 0) + 1
        self._counters[figure.id] = counter
        while f"n{counter}" in figure.nodes:
            counter += 1
            self._counters[figure.id] = counter
        return f"n{counter}"
