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
from dataclasses import replace
from fractions import Fraction
from typing import Any

import sympy as sp

from geobench.dsl import parse_dsl, to_dsl
from geobench.errors import GeobenchError
from geobench.evaluate import (
    evaluate_figure,
    evaluate_numeric,
    evaluate_numeric_direct,
    parameter_on_circle,
    undefined_nodes,
)
from geobench.judges import IDENTITY, JudgeRegistry, Verdict, judge_relation
from geobench.model import Figure, Node, Relation
from geobench.numeric import Crossing, crossing_near, parameter_on_line
from geobench.operators import register_builtins
from geobench.primitives import Primitive, figure_primitives
from geobench.registry import OperatorRegistry
from geobench.state import FigureStore, OpRequest
from geobench.style import COMPETITION, FigureStyle

DEFAULT_FIGURE_ID = "figure"


def _as_float(value: str) -> float:
    """An exact placement ("29/20") as a number, for hit testing and drawing."""
    return float(Fraction(value))


def _exact_text(text: str) -> str:
    """A number the user typed, as the exact rational the kernel wants.

    "1/2" is one half and "0.5" is the same one half: the kernel holds
    no floats, and a figure a teacher typed is a figure they meant.
    """
    try:
        value = Fraction(text.strip())
    except (ValueError, ZeroDivisionError) as exc:
        raise GeobenchError(f"{text!r} is not a number") from exc
    return str(value)


def _number_text(value: object) -> str:
    """A witness coordinate as the exact rational the kernel wants."""
    text = str(value)
    try:
        return _exact_text(text)
    except GeobenchError:
        return text


def _exact(value: float) -> str:
    """A coordinate as an exact rational.

    A point dragged to a fraction of a pixel is at a fraction, and the
    kernel wants fractions: no floats, ever, in the exact path. A
    denominator of a million is plenty -- a pixel is worth far less than
    that.
    """
    return str(sp.Rational(value).limit_denominator(10**6))


#: The label each construction gives its result, the way a competition
#: paper names it.
_LABELS_BY_OP: dict[str, str] = {
    "point.midpoint": "M",
    "point.centroid": "G",
    "point.circumcenter": "O",
    "point.incenter": "I",
    "point.orthocenter": "H",
    "point.foot": "F",
    "point.affine_ratio": "P",
    "point.polygon_vertex": "V",
    "circle.through": "ω",
    "circle.incircle": "ω",
    "line.perpendicular_bisector": "m",
    "line.angle_bisector": "l",
    "line.polar": "p",
}


#: What the undo stack keeps: the nodes, the relations, and the counter
#: that names the next free point.
Snapshot = tuple[dict[str, "Node"], list["Relation"], int]


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
        #: Bumped when the construction (not the placement) changes, so a
        #: worker that finishes late can be told its answer is stale.
        self._exact_version = 0
        self._listeners: list[Callable[[], None]] = []
        # A second, cheaper channel: "only a point moved". The full
        # change means the construction changed and everything that
        # depends on it has to be looked at again; a move means only
        # that the picture has to be redrawn.
        self._move_listeners: list[Callable[[str], None]] = []
        self._next_label = 1
        # The undo stack. A figure is a few dozen objects, so a
        # snapshot is cheap -- and a snapshot cannot be wrong in the way
        # an "undo the last operation" can be.
        self._undo: list[Snapshot] = []
        self._redo: list[Snapshot] = []

    # -- listeners ---------------------------------------------------------

    def on_change(self, callback: Callable[[], None]) -> None:
        """Be told when the figure changes."""
        self._listeners.append(callback)

    def on_move(self, callback: Callable[[str], None]) -> None:
        """Be told when a point has been moved, and nothing else.

        The callback is told which point, so it can update the one row
        that changed instead of rebuilding everything.
        """
        self._move_listeners.append(callback)

    def _changed(self) -> None:
        for callback in self._listeners:
            callback()

    def _moved(self, node_id: str) -> None:
        for callback in self._move_listeners:
            callback(node_id)

    # -- the figure --------------------------------------------------------

    # -- undo ---------------------------------------------------------------

    def push_undo(self) -> None:
        """Remember the figure as it is now, so it can come back."""
        self._undo.append(self._snapshot())
        self._redo.clear()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> bool:
        """Step back. Returns whether there was anything to step back to."""
        if not self._undo:
            return False
        self._redo.append(self._snapshot())
        self._restore(self._undo.pop())
        return True

    def redo(self) -> bool:
        """Step forward again."""
        if not self._redo:
            return False
        self._undo.append(self._snapshot())
        self._restore(self._redo.pop())
        return True

    def _snapshot(self) -> Snapshot:
        figure = self.figure()
        nodes = {
            node_id: replace(node, args=list(node.args), cache=dict(node.cache))
            for node_id, node in figure.nodes.items()
        }
        relations = [replace(relation) for relation in figure.relations]
        return nodes, relations, self._next_label

    def _restore(self, snapshot: Snapshot) -> None:
        figure = self.figure()
        figure.nodes.clear()
        figure.nodes.update(snapshot[0])
        figure.relations[:] = snapshot[1]
        # The counter that names the next free point goes back too: a
        # point that was undone is still free to be named.
        self._next_label = snapshot[2]
        self.evaluate()
        self._changed()

    def figure(self) -> Figure:
        return self.store.figure(self.figure_id)

    def evaluate(self) -> Figure:
        """Draw now; the exact path fills in behind the picture.

        The **picture** is numeric, and it is three milliseconds for a
        figure of forty objects.  The exact layer is what judging needs,
        and it can take minutes on a figure with circle intersections --
        so it never runs on the way to the screen.  The figure is marked
        ``pending``, and the window asks for the exact evaluation on a
        copy, in another thread, exactly the way it asks for verdicts.

        That is the whole deal: **the teacher never waits for a
        decision**; what they get at once is the figure, and what
        arrives later is the ability to judge it.
        """
        figure = self.figure()
        figure.runtime["exact"] = {"status": "pending", "reason": ""}
        self._exact_version += 1
        evaluate_numeric_direct(figure, self.registry, strict=True)
        return figure

    def evaluate_exact(self) -> Figure:
        """Run the exact pass now, and wait for it.

        The screen never calls this: it runs the same pass on a copy, in
        a worker, so the picture is on screen first (see
        ``Window._refresh_exact``).  This is the synchronous version --
        what a test needs, and what "tell me now" means.
        """
        figure = self.figure()
        self.evaluate_exact_figure(figure)
        return figure

    def evaluate_exact_figure(self, figure: Figure) -> dict[str, str]:
        """Evaluate a figure exactly, and draw it if that is out of budget.

        Safe to call on a copy from a worker thread: it touches only the
        figure it was given.  The figure that comes back is ready to be
        absorbed -- exact where exactness is affordable, numeric
        everywhere else.
        """
        evaluate_figure(figure, self.registry)
        state = dict(figure.runtime.get("exact") or {})
        if state.get("status") == "too-big":
            evaluate_numeric_direct(figure, self.registry)
        return state

    def _numeric_pass(self) -> None:
        """Recompute the picture, with whichever path can do it now.

        While the exact evaluation is on its way (or was out of budget)
        the compiled functions do not exist yet, so the drag runs the
        operators on numbers directly -- the same arithmetic, the same
        picture, three milliseconds.  Once the exact pass has been
        absorbed, the compiled path is faster and is what runs.
        """
        figure = self.figure()
        if self.exact_pending() or self.inexact():
            evaluate_numeric_direct(figure, self.registry)
        else:
            evaluate_numeric(figure)

    def absorb_exact(self, done: Figure, state: dict[str, str]) -> bool:
        """Take the exact evaluation a worker finished, if it still fits.

        The worker ran on a copy, so the answer is only about the figure
        it copied: if the construction has changed since, the answer is
        about a figure that no longer exists and is dropped.
        """
        live = self.figure()
        if set(done.nodes) != set(live.nodes):
            return False
        for node_id, node in live.nodes.items():
            source = done.nodes[node_id]
            node.coords = source.coords
            node.cache.update(source.cache)
        live.runtime["exact"] = dict(state)
        # The worker computed the numbers at the placement *it* copied.
        # If a point moved while it was thinking, those numbers are old
        # ones, and the picture would jump back for a frame.  Redraw at
        # the placement the figure has now.
        if state.get("status") == "too-big":
            evaluate_numeric_direct(live, self.registry)
        else:
            evaluate_numeric(live)
        return True

    def primitives(self) -> list[Primitive]:
        """What the screen should draw."""
        return figure_primitives(self.figure(), self.style)

    def undefined(self) -> list[tuple[str, str]]:
        return undefined_nodes(self.figure())

    def inexact(self) -> str:
        """Why this figure cannot be judged, or "" when it can.

        ``pending`` is not a reason: the exact evaluation is on its way.
        """
        state = self.figure().runtime.get("exact") or {}
        status = state.get("status")
        if status in ("too-big", "failed"):
            return str(state.get("reason") or "精确求值没有完成")
        return ""

    def exact_version(self) -> int:
        return self._exact_version

    def exact_pending(self) -> bool:
        """Is the exact evaluation still on its way?"""
        state = self.figure().runtime.get("exact") or {}
        return state.get("status") == "pending"

    # -- editing -----------------------------------------------------------

    def add_free_point(self, x: float, y: float, label: str | None = None) -> str:
        """Put a free point on the canvas."""
        before = self._snapshot()
        node_id = label or self._new_label()
        # The coordinates are exact rationals. The kernel does not allow
        # floats -- the exact path has to stay exact -- and a placement
        # feeds the symbolic substitution the judges use.
        result = self.store.apply(
            self.figure_id,
            [
                OpRequest(
                    op="point.free",
                    args=[_exact(x), _exact(y)],
                    id=node_id,
                )
            ],
        )
        if not result.ok:
            raise GeobenchError(result.errors[0] if result.errors else "cannot add a point")
        try:
            self.evaluate()
        except GeobenchError:
            self._restore(before)
            raise
        self.push_undo_past(before)
        self._changed()
        return node_id

    def move_point(self, node_id: str, x: float, y: float) -> None:
        """Move a free point. The whole point of the product is this call.

        Only the **numeric** path runs. The construction has not changed,
        so the exact path has nothing to say about it -- and the screen
        must not wait for symbolic work while the mouse is moving
        (decision D18).

        The undo entry is pushed by the canvas **before** the drag
        starts, not here: a drag is one change, however many frames it
        takes, and an undo stack with an entry per frame would be
        useless.
        """
        figure = self.figure()
        node = figure.nodes.get(node_id)
        if node is None:
            raise GeobenchError(f"unknown node id {node_id!r}")
        if node.role == "attached":
            # A point on a circle has no position of its own: what the
            # drag changes is *where on the circle* it is. The parameter
            # is part of the construction, so this is a change, not a
            # move -- and it stays true however the circle moves later.
            self._set_parameter(node_id, x, y)
            return
        if node.role != "free":
            raise GeobenchError(f"node {node_id!r} is not a free point")
        node.placement = (_exact(x), _exact(y))
        self._numeric_pass()
        self._moved(node_id)

    def _set_parameter(self, node_id: str, x: float, y: float) -> None:
        """Move a point that lives on an object, along that object."""
        figure = self.figure()
        node = figure.nodes[node_id]
        if not node.args:
            raise GeobenchError(f"node {node_id!r} is attached to nothing")
        target = node.args[0]
        object_node = figure.nodes.get(target)
        if object_node is None:
            raise GeobenchError(f"node {node_id!r} is attached to nothing")
        if object_node.kind == "circle":
            parameter = parameter_on_circle(figure, target, x, y)
        elif object_node.kind in {"line", "segment"}:
            parameter = parameter_on_line(figure, target, x, y)
        else:
            raise GeobenchError(
                f"node {node_id!r} is attached to an object that cannot be dragged on"
            )
        node.args = [target, parameter]
        # Only the numeric path: the exact expression is rebuilt once, on
        # release, not on every frame of the drag.
        self._numeric_pass()
        # A drag is a move, not a change: the steps pane updates the one
        # row that changed, and the verdicts are settled on release. A
        # proof request per frame would be a thread per frame.
        self._moved(node_id)

    def parameter_on_circle(self, circle_id: str, x: float, y: float) -> str:
        """Where on a circle a click landed, as the parameter a point takes."""
        return parameter_on_circle(self.figure(), circle_id, x, y)

    def parameter_on_line(self, line_id: str, x: float, y: float) -> str:
        """Where on a line or a segment a click landed, as the parameter."""
        return parameter_on_line(self.figure(), line_id, x, y)

    def crossing_near(self, x: float, y: float, tolerance: float) -> Crossing | None:
        """The nearest crossing of two drawn objects, if any."""
        return crossing_near(self.figure(), x, y, tolerance)

    def apply_witness(self, witness: dict[str, object]) -> bool:
        """Put the free points where a counterexample says they are.

        The witness is the judges' own record of a placement that makes
        a claim fail.  Seeing it is the difference between "the program
        says it is false" and "look -- put A there, and the three points
        stop being collinear".  One undo step puts them back.
        """
        figure = self.figure()
        placements: dict[str, tuple[str, str]] = {}
        for name, value in witness.items():
            node = figure.nodes.get(str(name))
            if node is None or node.role != "free" or node.kind != "point":
                continue
            if not isinstance(value, (list, tuple)) or len(value) < 2:
                continue
            placements[str(name)] = (
                _number_text(value[0]),
                _number_text(value[1]),
            )
        if not placements:
            return False
        self.push_undo()
        for name, placement in placements.items():
            figure.nodes[name].placement = placement
        # Only the picture moves: the exact expressions do not depend on
        # where a free point is, so nothing has to be re-derived.
        self._numeric_pass()
        self._changed()
        return True

    def set_number(
        self,
        node_id: str,
        value: float,
        final: bool = False,
        record: bool = True,
    ) -> None:
        """Set a free number's value.

        While a slider is being dragged, only the picture is recomputed:
        the constant is fed to the same operators, numerically.  On
        release (``final``) the exact expressions are rebuilt, because a
        constant that changed changes what the construction *is*.
        """
        figure = self.figure()
        node = figure.nodes.get(node_id)
        if node is None or node.op != "number.free":
            raise GeobenchError(f"node {node_id!r} is not a free number")
        if record:
            self.push_undo()
        # ``replace_node`` bumps the version, so every construction that
        # reads this number is re-derived rather than kept stale.
        updated = replace(node, args=[_exact(value)])
        figure.replace_node(updated)
        # The constant is part of the construction: an exact answer about
        # the old value is no longer an answer about this figure.
        self._exact_version += 1
        figure.runtime["exact"] = {"status": "pending", "reason": ""}
        if final:
            self.evaluate()
            self._changed()
        else:
            evaluate_numeric_direct(figure, self.registry)
            self._moved(node_id)

    def set_point_position(self, node_id: str, x: str, y: str) -> None:
        """Put a free point exactly where the user says.

        The numbers are read as they are typed: a fraction stays a
        fraction, and a decimal becomes the rational it stands for.
        """
        figure = self.figure()
        node = figure.nodes.get(node_id)
        if node is None:
            raise GeobenchError(f"unknown node id {node_id!r}")
        if node.role != "free":
            raise GeobenchError(f"node {node_id!r} is not a free point")
        placement = (_exact_text(x), _exact_text(y))
        self.push_undo()
        node.placement = placement
        self._numeric_pass()
        self._moved(node_id)

    def set_hidden(self, node_id: str, hidden: bool) -> None:
        """Hide an object, or show it again.

        A hidden object keeps its place in the construction: it still
        exists, it still carries the proof, and it is still in the file.
        It is only not drawn. That is what a teacher wants when the
        scaffolding of the figure should not be in the paper.
        """
        figure = self.figure()
        node = figure.nodes.get(node_id)
        if node is None:
            raise GeobenchError(f"unknown node id {node_id!r}")
        self.push_undo()
        node.style = replace(node.style, visible=not hidden)
        self._changed()

    def set_auxiliary(self, node_id: str, auxiliary: bool) -> None:
        """Mark an object as auxiliary, or as part of the figure.

        An auxiliary object supports the figure but is not part of the
        problem's statement -- the altitude, the perpendicular
        bisector, the auxiliary circle. Chinese competition papers draw
        these dashed.
        """
        figure = self.figure()
        node = figure.nodes.get(node_id)
        if node is None:
            raise GeobenchError(f"unknown node id {node_id!r}")
        self.push_undo()
        node.style = replace(
            node.style, line_style="dashed" if auxiliary else "solid"
        )
        self._changed()

    def set_label(self, node_id: str, label: str) -> None:
        """What the object is called on the figure.

        The name in the construction and the name on the paper are two
        different things: a midpoint built as ``M`` may be ``D`` in the
        problem, and a paper that says D while the figure says M is a
        paper with a mistake in it. An empty label falls back to the
        object's name.
        """
        figure = self.figure()
        node = figure.nodes.get(node_id)
        if node is None:
            raise GeobenchError(f"unknown node id {node_id!r}")
        self.push_undo()
        node.style = replace(node.style, label=label.strip() or None)
        self._changed()

    def set_color(self, node_id: str, color: str | None) -> None:
        """Set, or clear, the colour this object is drawn in.

        ``None`` is not "black": it is "the figure's colour", which is
        what the object had before anyone said otherwise.
        """
        self._set_style(node_id, color=color or "#000000")

    def set_appearance(
        self,
        node_id: str,
        *,
        color: str | None = None,
        line_width: float | None = None,
        point_size: float | None = None,
        label_pos: str | None = None,
        label: str | None = None,
    ) -> None:
        """Change every appearance attribute at once, as one undo step.

        "Make this the key point -- red, bigger, label on the right" is
        one intention; it should not cost three entries on the undo
        stack.  Only appearance is touched.
        """
        figure = self.figure()
        node = figure.nodes.get(node_id)
        if node is None:
            raise GeobenchError(f"unknown node id {node_id!r}")
        updated = replace(
            node.style,
            color=color or "#000000",
            line_width=line_width,
            point_size=point_size,
            label_pos=label_pos,
            label=(label.strip() or None) if label is not None else node.style.label,
        )
        if updated == node.style:
            return
        self.push_undo()
        node.style = updated
        self._changed()

    def set_line_width(self, node_id: str, width: float | None) -> None:
        """Set, or clear, this object's stroke width (in points)."""
        self._set_style(node_id, line_width=width)

    def set_point_size(self, node_id: str, size: float | None) -> None:
        """Set, or clear, this point's radius (in pixels)."""
        self._set_style(node_id, point_size=size)

    def set_label_pos(self, node_id: str, position: str | None) -> None:
        """Set, or clear, where this object's label sits."""
        self._set_style(node_id, label_pos=position)

    def _set_style(self, node_id: str, **fields: Any) -> None:
        """Change one drawing attribute, as one undoable step."""
        figure = self.figure()
        node = figure.nodes.get(node_id)
        if node is None:
            raise GeobenchError(f"unknown node id {node_id!r}")
        self.push_undo()
        node.style = replace(node.style, **fields)
        self._changed()

    def draggable(self, node_id: str) -> bool:
        """Can this node be dragged? Free points and points on an object."""
        node = self.figure().nodes.get(node_id)
        return node is not None and node.role in ("free", "attached")

    def finish_move(self) -> None:
        """The drag is over: settle the figure and settle the verdicts.

        The exact path runs now. It has nothing to redo -- the
        construction did not change -- but the figure is whole again,
        and the verdicts can be recomputed on a figure that is not in
        the middle of a drag.
        """
        self.evaluate()
        self._changed()

    def construct(self, op: str, args: list[Any], node_id: str | None = None) -> str:
        """Apply one construction, or none of it.

        A construction that cannot be evaluated is rolled back: a node
        that is in the figure but has no value makes every later
        evaluation fail, and the figure would be poisoned for good. A
        refusal is a refusal, not a half-built object.
        """
        before = self._snapshot()
        if node_id is None:
            node_id = self._name_for(op)
        result = self.store.apply(
            self.figure_id, [OpRequest(op=op, args=list(args), id=node_id)]
        )
        if not result.ok:
            raise GeobenchError(result.errors[0] if result.errors else f"{op} failed")
        try:
            self.evaluate()
        except GeobenchError:
            self._restore(before)
            raise
        self.push_undo_past(before)
        self._changed()
        return result.created[0] if result.created else ""

    def push_undo_past(self, before: Snapshot) -> None:
        """Record the state from before a change that has now succeeded."""
        self._undo.append(before)
        self._redo.clear()

    def _name_for(self, op: str) -> str | None:
        """The name a construction gives its result.

        The midpoint is M, the circumcentre is O, the incentre is I, the
        orthocentre is H -- the letters competition papers use. The name
        is the node's **id**, not just a label on it, so that it
        survives being written to a file and read back.
        """
        base = _LABELS_BY_OP.get(op)
        if base is None:
            return None
        used = set(self.figure().nodes)
        label = base
        counter = 1
        while label in used:
            label = f"{base}{counter}"
            counter += 1
        return label

    def to_text(self) -> str:
        """The figure as text.

        The DSL is the whole figure -- the free points with their
        positions, the constructions, the relations -- so it is what a
        file holds. A teacher can read it, edit it and hand it on.
        """
        return to_dsl(self.figure())

    def clear(self) -> None:
        """Start a new, empty figure (文件 → 新建)."""
        self.push_undo()
        figure = self.figure()
        figure.nodes.clear()
        figure.relations.clear()
        self.evaluate()
        self._changed()

    def load_text(self, source: str) -> None:
        self.push_undo()
        """Replace the figure with the one in the text.

        The text is parsed strictly: a file that does not make sense is
        refused with the line and the reason, and the figure on screen
        is left alone.
        """
        parsed = parse_dsl(source)
        figure = self.figure()
        # The figure is emptied directly rather than node by node: the
        # model refuses to remove a node that others depend on, which is
        # the right rule for editing and the wrong one for replacing
        # the whole figure.
        figure.nodes.clear()
        figure.relations.clear()
        for node in parsed.nodes.values():
            figure.add_node(node)
        for relation in parsed.relations:
            figure.add_relation(relation)
        self.evaluate()
        self._changed()

    def remove_node(self, node_id: str) -> None:
        """Remove an object, what depends on it, and the claims about it.

        A claim about a point that no longer exists is not a claim any
        more, so deleting a point deletes the relations that name it.
        The model refuses the other way round -- it will not leave a
        relation pointing at nothing -- and that is right: the refusal
        belongs in the model, the cascade belongs here.
        """
        self.remove_nodes([node_id])

    def remove_nodes(self, node_ids: list[str]) -> int:
        """Remove several objects and their dependents, as **one** undo step.

        Selecting three construction lines and pressing Delete is one
        action; three entries in the undo stack would make it three.
        """
        figure = self.figure()
        gone: set[str] = set()
        for node_id in node_ids:
            if node_id in figure.nodes:
                gone |= self._with_dependents(figure, node_id)
        if not gone:
            return 0
        removed = len(gone)
        self.push_undo()
        # The claims first: the model will not leave a relation pointing
        # at nothing, and it is right not to.
        figure.relations = [
            relation
            for relation in figure.relations
            if not (set(relation.args) & gone)
        ]
        # Then the objects, the dependents before what they depend on --
        # which is the order the model insists on.
        while gone:
            # "Ready" means nothing that is still in the figure uses it.
            # Reading the figure rather than the `gone` set matters: a
            # dependent is gone only once it has actually been removed.
            ready = [
                candidate
                for candidate in gone
                if not any(candidate in other.args for other in figure.nodes.values())
            ]
            if not ready:  # pragma: no cover - a cycle cannot happen here
                break
            for candidate in ready:
                figure.remove_node(candidate)
                gone.discard(candidate)
        self.evaluate()
        self._changed()
        return removed

    @staticmethod
    def _with_dependents(figure: Figure, node_id: str) -> set[str]:
        """The object and everything that only exists because of it."""
        gone = {node_id}
        changed = True
        while changed:
            changed = False
            for node in figure.nodes.values():
                if node.id not in gone and set(node.args) & gone:
                    gone.add(node.id)
                    changed = True
        return gone

    def add_relation(self, kind: str, args: list[str]) -> str:
        """Add a relation to be judged."""
        self.push_undo()
        figure = self.figure()
        relation_id = self._next_relation_id(figure)
        figure.add_relation(
            Relation(id=relation_id, kind=kind, args=list(args), expected=True)
        )
        self._changed()
        return relation_id

    def remove_relation(self, relation_id: str) -> None:
        self.push_undo()
        figure = self.figure()
        figure.relations = [r for r in figure.relations if r.id != relation_id]
        self._changed()

    # -- judging -----------------------------------------------------------

    def judge(self, scope: str = IDENTITY) -> list[Verdict]:
        """Judge every relation of the figure, exactly, right now.

        The screen never calls this: it judges a snapshot in a worker
        (see ``Window._refresh_exact``).  This is the synchronous
        version -- "tell me now" -- so it makes the figure exact first
        if the background evaluation has not got there yet.
        """
        figure = self.figure()
        if self.exact_pending():
            self.evaluate_exact_figure(figure)
        return self.judge_figure(figure, scope)

    def snapshot_figure(self) -> Figure:
        """A copy of the figure, safe to judge in another thread.

        The worker needs a figure that will not change under it: the
        user may go on dragging points while the proof runs, and a proof
        that reads a moving figure is not a proof of anything.
        """
        source = self.figure()
        copy = Figure(id=source.id)
        for node in source.nodes.values():
            copy.add_node(
                replace(node, args=list(node.args), cache=dict(node.cache))
            )
        for relation in source.relations:
            copy.add_relation(replace(relation))
        # The versions and the verdicts already reached: both are worth
        # keeping, and neither is safe to share with the live figure.
        copy.runtime.update(source.runtime)
        copy.runtime["verdicts"] = dict(source.runtime.get("verdicts", {}))
        return copy

    def absorb_verdicts(self, snapshot: Figure) -> None:
        """Keep the verdicts a background proof reached.

        The proof ran on a copy of the figure, so what it found is in
        the copy's cache. The live figure has to learn it, or the same
        claim is proved again on every change -- in the background, so
        the screen is still free, but the worker would never catch up.
        """
        found = snapshot.runtime.get("verdicts")
        if not found:
            return
        live = self.figure()
        cache = live.runtime.setdefault("verdicts", {})
        cache.update(found)

    def judge_figure(self, figure: Figure, scope: str = IDENTITY) -> list[Verdict]:
        """Judge every relation of a given figure."""
        inexact = self.inexact()
        if inexact:
            # The figure was drawn numerically: there are no exact
            # expressions to decide anything with, and deciding on
            # numbers is what this project refuses to do (D18).
            return [
                Verdict(kind=relation.kind, verdict="undecided", scope=scope, evidence=inexact)
                for relation in figure.relations
            ]
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
                out[node.id] = (
                    _as_float(node.placement[0]),
                    _as_float(node.placement[1]),
                )
            except (TypeError, ValueError, ZeroDivisionError):
                continue
        return out

    def free_points(self) -> list[str]:
        return [
            node.id
            for node in self.figure().nodes.values()
            if node.role == "free" and node.kind == "point"
        ]

    def _next_relation_id(self, figure: Figure) -> str:
        """The next free name for a relation.

        Counting the relations is not enough: remove one and the count
        goes down, and the next relation would take a name that is
        already in use.
        """
        used = {relation.id for relation in figure.relations}
        index = len(used) + 1
        while f"r{index}" in used:
            index += 1
        return f"r{index}"

    def _new_label(self) -> str:
        """The next free point label: A, B, C, ... then A1, B1, ...

        The counter is not enough on its own: a file that is opened can
        bring its own names, and a point must never be given a name that
        is already on the figure.
        """
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        used = set(self.figure().nodes)
        while True:
            index = self._next_label - 1
            self._next_label += 1
            label = (
                letters[index]
                if index < len(letters)
                else f"P{index - len(letters) + 1}"
            )
            if label not in used:
                return label


def figure_of(controller: StudioController) -> Figure:
    """The controller's figure, evaluated. For the tests."""
    return controller.evaluate()


def node_by_id(figure: Figure, node_id: str) -> Node:
    return figure.nodes[node_id]
