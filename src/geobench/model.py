"""The construction graph: the kernel's data model.

See docs/spec.md section 3. A figure is a DAG of nodes (points, lines,
circles) plus the relations that are *claimed* about it and are to be
adjudicated by the judges.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from geobench.errors import ModelError
from geobench.field import FIELD

POINT = "point"
LINE = "line"
SEGMENT = "segment"
CIRCLE = "circle"
POLYGON = "polygon"
ARC = "arc"
SECTOR = "sector"

FREE = "free"
DERIVED = "derived"

_KINDS = (POINT, LINE, SEGMENT, CIRCLE, POLYGON, ARC, SECTOR)
_ROLES = (FREE, DERIVED)


@dataclass(frozen=True)
class Style:
    """Rendering attributes only. Never affects geometry."""

    visible: bool = True
    color: str = "#000000"
    line_width: float | None = None
    line_style: str = "solid"
    point_size: float | None = None
    fill: str | None = None
    label: str | None = None
    label_pos: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "visible": self.visible,
            "color": self.color,
            "line_width": self.line_width,
            "line_style": self.line_style,
            "point_size": self.point_size,
            "fill": self.fill,
            "label": self.label,
            "label_pos": self.label_pos,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Style:
        return cls(
            visible=bool(data.get("visible", True)),
            color=str(data.get("color", "#000000")),
            line_width=data.get("line_width"),
            line_style=str(data.get("line_style", "solid")),
            point_size=data.get("point_size"),
            fill=data.get("fill"),
            label=data.get("label"),
            label_pos=data.get("label_pos"),
        )


@dataclass
class Node:
    """A point, line or circle.

    ``role == FREE`` nodes carry exact coordinates and are the only source of
    variation. ``role == DERIVED`` nodes carry an operator and its arguments;
    their coordinates are a cache, recomputed by the kernel after every change.

    Coordinates are **symbolic** (docs/spec.md section 3.2): a free point's
    ``coords`` may be expressions in symbols such as ``x_A``/``y_A``, which is
    what lets a judge decide a relation *identically* rather than on one
    sample. ``placement`` holds the numeric exact values used for drawing and
    for sampling.
    """

    id: str
    kind: str
    role: str
    op: str | None = None
    args: list[str] = field(default_factory=list)
    coords: tuple[str, str] | None = None
    placement: tuple[str, str] | None = None
    label: str | None = None
    style: Style = field(default_factory=Style)
    cache: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "role": self.role,
            "op": self.op,
            "args": list(self.args),
            "coords": list(self.coords) if self.coords is not None else None,
            "placement": list(self.placement) if self.placement is not None else None,
            "label": self.label,
            "style": self.style.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Node:
        raw_coords = data.get("coords")
        coords: tuple[str, str] | None = None
        if raw_coords is not None:
            coords = (str(raw_coords[0]), str(raw_coords[1]))
        raw_placement = data.get("placement")
        placement: tuple[str, str] | None = None
        if raw_placement is not None:
            placement = (str(raw_placement[0]), str(raw_placement[1]))
        return cls(
            id=str(data["id"]),
            kind=str(data["kind"]),
            role=str(data["role"]),
            op=data.get("op"),
            args=[str(a) for a in data.get("args", [])],
            coords=coords,
            placement=placement,
            label=data.get("label"),
            style=Style.from_dict(dict(data.get("style", {}))),
        )


@dataclass
class Relation:
    """A claim about the figure that the judges must adjudicate."""

    id: str
    kind: str
    args: list[str] = field(default_factory=list)
    expected: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "args": list(self.args),
            "expected": self.expected,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Relation:
        expected = data.get("expected")
        return cls(
            id=str(data["id"]),
            kind=str(data["kind"]),
            args=[str(a) for a in data.get("args", [])],
            expected=None if expected is None else bool(expected),
        )


@dataclass
class Figure:
    """A construction graph."""

    version: str = "1.0"
    id: str = "fig_0001"
    nodes: dict[str, Node] = field(default_factory=dict)
    relations: list[Relation] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    runtime: dict[str, Any] = field(
        default_factory=dict, repr=False, compare=False
    )
    """Scratch space for the evaluator.

    Never serialised: it holds compiled functions and version counters,
    which are only meaningful for the process that built them. The
    *contents* are preserved across :meth:`copy`, because a copy is the
    same construction and therefore the same cached expressions.
    """

    # -- mutation ---------------------------------------------------------

    def add_node(self, node: Node) -> None:
        if node.id in self.nodes:
            raise ModelError(f"node id {node.id!r} already exists")
        self._check_node_shape(node)
        self.nodes[node.id] = node

    def remove_node(self, node_id: str) -> None:
        if node_id not in self.nodes:
            raise ModelError(f"unknown node id {node_id!r}")
        users = [n.id for n in self.nodes.values() if node_id in n.args]
        if users:
            raise ModelError(
                f"node {node_id!r} is used by {', '.join(sorted(users))}; "
                "remove the dependents first"
            )
        for relation in self.relations:
            if node_id in relation.args:
                raise ModelError(
                    f"node {node_id!r} is referenced by relation {relation.id!r}; "
                    "remove the relation first"
                )
        del self.nodes[node_id]

    def add_relation(self, relation: Relation) -> None:
        if any(r.id == relation.id for r in self.relations):
            raise ModelError(f"relation id {relation.id!r} already exists")
        for arg in relation.args:
            if arg not in self.nodes:
                raise ModelError(
                    f"relation {relation.id!r} references unknown node id {arg!r}"
                )
        self.relations.append(relation)

    def remove_relation(self, relation_id: str) -> None:
        for index, relation in enumerate(self.relations):
            if relation.id == relation_id:
                del self.relations[index]
                return
        raise ModelError(f"unknown relation id {relation_id!r}")

    # -- validation -------------------------------------------------------

    def _check_node_shape(self, node: Node) -> None:
        if not node.id:
            raise ModelError("node id must not be empty")
        if node.kind not in _KINDS:
            raise ModelError(
                f"node {node.id!r} has unknown kind {node.kind!r}; expected one of {_KINDS}"
            )
        if node.role not in _ROLES:
            raise ModelError(
                f"node {node.id!r} has unknown role {node.role!r}; expected one of {_ROLES}"
            )
        if node.role == FREE:
            if node.kind == POINT:
                if node.coords is None:
                    raise ModelError(f"free point {node.id!r} needs exact coordinates")
                for value in node.coords:
                    FIELD.coerce(value)
            else:
                # A free line or circle is given directly by its exact equation;
                # the coefficients live in the node cache after evaluation.
                if not node.op:
                    raise ModelError(
                        f"free {node.kind} {node.id!r} must name the operator that defines it"
                    )
        else:
            if not node.op:
                raise ModelError(f"derived node {node.id!r} must name an operator")
            if not node.args:
                raise ModelError(f"derived node {node.id!r} must have arguments")
        for arg in node.args:
            if arg in self.nodes:
                continue
            if _is_literal(arg):
                # A numeric argument is a literal (a radius, a scale), not a
                # reference to another node.
                continue
            raise ModelError(
                f"node {node.id!r} references unknown node id {arg!r}"
            )

    def validate(self) -> None:
        """Structural validation: shapes, references, acyclicity."""
        for node in self.nodes.values():
            self._check_node_shape(node)
        for relation in self.relations:
            if not relation.kind:
                raise ModelError(f"relation {relation.id!r} must name a judge kind")
            for arg in relation.args:
                if arg not in self.nodes:
                    raise ModelError(
                        f"relation {relation.id!r} references unknown node id {arg!r}"
                    )
        cycle = self._find_cycle()
        if cycle is not None:
            raise ModelError("dependency cycle: " + " -> ".join(cycle))

    def _find_cycle(self) -> list[str] | None:
        """Return one dependency cycle, if any (edges point arg -> dependent)."""
        edges: dict[str, list[str]] = {node_id: [] for node_id in self.nodes}
        for node in self.nodes.values():
            for arg in node.args:
                if arg in edges:
                    edges[arg].append(node.id)

        WHITE, GREY, BLACK = 0, 1, 2
        colour = dict.fromkeys(self.nodes, WHITE)
        stack: list[str] = []

        def visit(node_id: str) -> list[str] | None:
            colour[node_id] = GREY
            stack.append(node_id)
            for nxt in edges[node_id]:
                if colour[nxt] == GREY:
                    start = stack.index(nxt)
                    return [*stack[start:], nxt]
                if colour[nxt] == WHITE:
                    found = visit(nxt)
                    if found is not None:
                        return found
            stack.pop()
            colour[node_id] = BLACK
            return None

        for node_id in self.nodes:
            if colour[node_id] == WHITE:
                found = visit(node_id)
                if found is not None:
                    return found
        return None

    # -- serialisation ----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "id": self.id,
            "nodes": [self.nodes[node_id].to_dict() for node_id in self.nodes],
            "relations": [relation.to_dict() for relation in self.relations],
            "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Figure:
        figure = cls(
            version=str(data.get("version", "1.0")),
            id=str(data.get("id", "fig_0001")),
            meta=dict(data.get("meta", {})),
        )
        for raw in data.get("nodes", []):
            node = Node.from_dict(dict(raw))
            figure.nodes[node.id] = node
        for raw in data.get("relations", []):
            relation = Relation.from_dict(dict(raw))
            figure.relations.append(relation)
        return figure

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=False
        )

    @classmethod
    def from_json(cls, payload: str) -> Figure:
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise ModelError("figure payload must be a JSON object")
        return cls.from_dict(data)

    # -- helpers ----------------------------------------------------------

    def node(self, node_id: str) -> Node:
        try:
            return self.nodes[node_id]
        except KeyError:
            raise ModelError(f"unknown node id {node_id!r}") from None

    def point_coords(self, node_id: str) -> tuple[Any, Any]:
        node = self.node(node_id)
        if node.kind != POINT:
            raise ModelError(f"node {node_id!r} is not a point")
        if node.coords is None:
            raise ModelError(f"point {node_id!r} has no coordinates")
        return FIELD.coerce(node.coords[0]), FIELD.coerce(node.coords[1])

    def dependencies(self, node_id: str) -> list[str]:
        return list(self.node(node_id).args)

    def ids(self) -> list[str]:
        return list(self.nodes)

    @classmethod
    def example(cls) -> Figure:
        """A small, fully valid figure used by the test suites."""
        figure = cls(id="fig_example")
        figure.add_node(
            Node(id="A", kind=POINT, role=FREE, coords=("x_A", "y_A"),
                 placement=("0", "0"), label="A")
        )
        figure.add_node(
            Node(id="B", kind=POINT, role=FREE, coords=("x_B", "y_B"),
                 placement=("4", "0"), label="B")
        )
        figure.add_node(
            Node(id="C", kind=POINT, role=FREE, coords=("x_C", "y_C"),
                 placement=("1", "3"), label="C")
        )
        figure.add_node(
            Node(id="M", kind=POINT, role=DERIVED, op="point.midpoint", args=["A", "B"], label="M")
        )
        figure.add_node(
            Node(id="l1", kind=LINE, role=DERIVED, op="line.free", args=["A", "B"], label="AB")
        )
        figure.add_node(
            Node(id="c1", kind=CIRCLE, role=DERIVED, op="circle.through", args=["A", "B", "C"], label="⊙O")
        )
        figure.add_relation(Relation(id="r1", kind="collinear", args=["A", "M", "B"], expected=True))
        return figure

    def copy(self) -> Figure:
        clone = Figure.from_json(self.to_json())
        # The copy is the same construction, so the cached expressions and
        # the compiled numeric functions are still valid for it. Keeping
        # them is what makes an edit cheap: only the part of the graph
        # that actually changed has to be recomputed.
        clone.runtime = dict(self.runtime)
        for node_id, node in self.nodes.items():
            if node_id in clone.nodes:
                clone.nodes[node_id].cache = dict(node.cache)
        return clone


def iter_points(figure: Figure) -> Iterable[Node]:
    for node in figure.nodes.values():
        if node.kind == POINT:
            yield node


_DIGITS = frozenset("0123456789")


def _is_literal(text: str) -> bool:
    """Is this argument a literal rather than a node reference?

    Numeric literals (a radius, a scale) and the intersection selector
    ``other`` are literals; everything else must name a node.

    The numeric test is deliberately textual and strict: the kernel is
    exact, so only a plain decimal is a literal. ``1e5``, ``nan`` and
    ``inf`` are not -- and ``float()`` is not used to decide, because
    parsing a float to ask "is this a number?" would be exactly the
    inexactness this project forbids.
    """
    if text == "other":
        return True
    body = text[1:] if text[:1] in {"+", "-"} else text
    if not body:
        return False
    whole, _, fraction = body.partition(".")
    if whole and not _DIGITS.issuperset(whole):
        return False
    if fraction and not _DIGITS.issuperset(fraction):
        return False
    return bool(whole or fraction)
