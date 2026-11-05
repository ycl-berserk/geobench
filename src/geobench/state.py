"""Figure store: applies operations to a construction graph.

The store owns the *state* side of the kernel. The operator implementations
own the *mathematics* side. In this milestone only the state side exists, so
an operator without an implementation is reported as a warning rather than
silently producing a wrong figure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from geobench.errors import RegistryError, StateError
from geobench.model import (
    DERIVED,
    FREE,
    POINT,
    Figure,
    Node,
    Relation,
)
from geobench.registry import OperatorRegistry


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
            except (StateError, RegistryError, ValueError) as exc:
                result.errors.append(f"op[{index}] {request.op}: {exc}")
                continue
            result.created.extend(outcome[0])
            result.updated.extend(outcome[1])
            result.removed.extend(outcome[2])
            result.warnings.extend(outcome[3])

        if not dry_run and result.ok:
            self._figures[figure_id] = working
            self._history[figure_id].append(snapshot)
        return result

    def _apply_one(
        self, figure: Figure, request: OpRequest
    ) -> tuple[list[str], list[str], list[str], list[str]]:
        if request.op == "point.free":
            return self._apply_free_point(figure, request)
        if request.op == "relation.add":
            return self._apply_relation(figure, request)

        spec = self.registry.lookup(request.op)
        if len(request.args) != len(spec.args):
            raise StateError(
                f"operator {spec.id!r} takes {len(spec.args)} arguments, "
                f"got {len(request.args)}"
            )

        node_id = request.id or self._next_id(figure)
        for arg, arg_spec in zip(request.args, spec.args, strict=True):
            if arg_spec.type == "point" and arg not in figure.nodes:
                raise StateError(f"unknown node id {arg!r}")

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

    def _apply_free_point(
        self, figure: Figure, request: OpRequest
    ) -> tuple[list[str], list[str], list[str], list[str]]:
        if len(request.args) != 2:
            raise StateError("point.free takes exactly 2 arguments (x, y)")
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
            raise StateError("relation.add takes at least 2 arguments (kind, [args])")
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
