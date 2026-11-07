"""The application's state, without any Qt in it.

The window is a view; this is the model behind it. Keeping the two apart
means the interesting behaviour -- constructing, dragging, judging -- can
be tested without a display (and without a human clicking).

It owns:

- the figure (through the store),
- the relations to judge,
- the listeners to tell when something changed.

Everything it does is deterministic: the AI, the mouse and the tests all
drive it the same way.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from geobench.errors import GeobenchError
from geobench.evaluate import evaluate_figure, undefined_nodes
from geobench.judges import IDENTITY, JudgeRegistry, Verdict, judge_relation
from geobench.model import Figure, Node, Relation
from geobench.operators import register_builtins
from geobench.primitives import Primitive, figure_primitives
from geobench.registry import OperatorRegistry
from geobench.state import FigureStore, OpRequest
from geobench.style import COMPETITION, FigureStyle

DEFAULT_FIGURE_ID = "figure"


class StudioController:
    """The state behind the studio window."""

    def __init__(
        self,
        registry: OperatorRegistry | None = None,
        style: FigureStyle = COMPETITION,
        figure_id: str = DEFAULT_FIGURE_ID,
    ) -> None:
        if registry is None:
            registry = OperatorRegistry()
            register_builtins(registry)
        self.registry = registry
        self.store = FigureStore(registry)
        self.style = style
        self.figure_id = figure_id
        self.judges = JudgeRegistry()
        self._listeners: list[Callable[[], None]] = []
        self._next_label = 1

    # -- listeners ---------------------------------------------------------

    def on_change(self, callback: Callable[[], None]) -> None:
        """Be told when the figure changes."""
        self._listeners.append(callback)

    def _changed(self) -> None:
        for callback in self._listeners:
            callback()

    # -- the figure --------------------------------------------------------

    def figure(self) -> Figure:
        return self.store.figure(self.figure_id)

    def evaluate(self) -> Figure:
        """Re-evaluate and repaint the numbers."""
        figure = self.figure()
        evaluate_figure(figure, self.registry)
        return figure

    def primitives(self) -> list[Primitive]:
        """What the screen should draw."""
        return figure_primitives(self.figure(), self.style)

    def undefined(self) -> list[tuple[str, str]]:
        return undefined_nodes(self.figure())

    # -- editing -----------------------------------------------------------

    def add_free_point(self, x: float, y: float, label: str | None = None) -> str:
        """Put a free point on the canvas."""
        node_id = label or self._new_label()
        result = self.store.apply(
            self.figure_id,
            [OpRequest(op="point.free", args=[repr(x), repr(y)], id=node_id)],
        )
        if not result.ok:
            raise GeobenchError(result.errors[0] if result.errors else "cannot add a point")
        self.evaluate()
        self._changed()
        return node_id

    def move_point(self, node_id: str, x: float, y: float) -> None:
        """Move a free point. The whole point of the product is this call."""
        figure = self.figure()
        node = figure.nodes.get(node_id)
        if node is None:
            raise GeobenchError(f"unknown node id {node_id!r}")
        if node.role != "free":
            raise GeobenchError(f"node {node_id!r} is not a free point")
        node.placement = (repr(x), repr(y))
        self.evaluate()
        self._changed()

    def construct(self, op: str, args: list[Any], node_id: str | None = None) -> str:
        """Apply one construction."""
        result = self.store.apply(
            self.figure_id, [OpRequest(op=op, args=list(args), id=node_id)]
        )
        if not result.ok:
            raise GeobenchError(result.errors[0] if result.errors else f"{op} failed")
        self.evaluate()
        self._changed()
        return result.created[0] if result.created else ""

    def remove_node(self, node_id: str) -> None:
        """Remove an object and everything that depends on it."""
        figure = self.figure()
        dependents = [
            other.id
            for other in figure.nodes.values()
            if node_id in other.args
        ]
        for dependent in dependents:
            figure.remove_node(dependent)
        figure.remove_node(node_id)
        self.evaluate()
        self._changed()

    def add_relation(self, kind: str, args: list[str]) -> str:
        """Add a relation to be judged."""
        figure = self.figure()
        relation_id = f"r{len(figure.relations) + 1}"
        figure.add_relation(
            Relation(id=relation_id, kind=kind, args=list(args), expected=True)
        )
        self._changed()
        return relation_id

    def remove_relation(self, relation_id: str) -> None:
        figure = self.figure()
        figure.relations = [r for r in figure.relations if r.id != relation_id]
        self._changed()

    # -- judging -----------------------------------------------------------

    def judge(self, scope: str = IDENTITY) -> list[Verdict]:
        """Judge every relation of the figure."""
        figure = self.figure()
        verdicts: list[Verdict] = []
        for relation in figure.relations:
            try:
                verdicts.append(
                    judge_relation(
                        figure, relation.kind, list(relation.args), self.judges, scope=scope
                    )
                )
            except GeobenchError as exc:
                verdicts.append(
                    Verdict(
                        kind=relation.kind,
                        verdict="undecided",
                        scope=scope,
                        evidence=str(exc),
                    )
                )
        return verdicts

    # -- helpers -----------------------------------------------------------

    def point_positions(self) -> dict[str, tuple[float, float]]:
        """Every point and where it is, for hit testing."""
        out: dict[str, tuple[float, float]] = {}
        for node in self.figure().nodes.values():
            if node.kind != "point":
                continue
            if node.placement is None:
                continue
            try:
                out[node.id] = (float(node.placement[0]), float(node.placement[1]))
            except (TypeError, ValueError):
                continue
        return out

    def free_points(self) -> list[str]:
        return [
            node.id
            for node in self.figure().nodes.values()
            if node.role == "free" and node.kind == "point"
        ]

    def _new_label(self) -> str:
        """The next free point label: A, B, C, ... then A1, B1, ..."""
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        index = self._next_label - 1
        self._next_label += 1
        if index < len(letters):
            return letters[index]
        return f"P{index - len(letters) + 1}"


def figure_of(controller: StudioController) -> Figure:
    """The controller's figure, evaluated. For the tests."""
    return controller.evaluate()


def node_by_id(figure: Figure, node_id: str) -> Node:
    return figure.nodes[node_id]
