"""Typed errors raised by the geobench kernel.

Every error is expected to carry an *actionable* message: which object, which
argument, and why. See docs/spec.md section 11.3.

The classes below are the vocabulary the MCP layer speaks. A tool turns an
exception into a structured ``status: "error"`` response, so the distinction
between "you named a node that does not exist" and "that configuration is
degenerate" has to survive all the way from the kernel to the agent.
"""

from __future__ import annotations

from collections.abc import Sequence


class GeobenchError(Exception):
    """Base class for all kernel errors."""


class FieldError(GeobenchError):
    """A value was not an exact, admissible geometric quantity."""


class ModelError(GeobenchError):
    """A construction graph violated the structural rules (spec section 3)."""


class RegistryError(GeobenchError):
    """An operator was unknown, or registered twice."""


class StateError(GeobenchError):
    """An operation could not be applied to a figure."""


class OpNotImplementedError(GeobenchError):
    """The operator is registered but has no implementation yet."""


class ArgumentError(StateError):
    """Base class for the ways an operator argument can be wrong.

    Every argument error names the operator and the *index* of the offending
    argument, because "argument 1" is what an agent can act on; "the second
    one" is not.
    """

    def __init__(self, message: str, *, op: str, index: int) -> None:
        self.op = op
        self.index = index
        super().__init__(message)


class ArgumentCountError(ArgumentError):
    """The operator was called with the wrong number of arguments."""

    def __init__(self, op: str, expected: int, received: int) -> None:
        self.expected = expected
        self.received = received
        super().__init__(
            f"operator {op!r} takes {expected} argument(s) but got {received}",
            op=op,
            index=min(expected, received),
        )


class ArgumentTypeError(ArgumentError):
    """An argument had the wrong type for the operator's contract."""

    def __init__(self, op: str, index: int, expected: str, received: object) -> None:
        self.expected = expected
        self.received = received
        super().__init__(
            f"argument {index} of operator {op!r} should be a {expected}, "
            f"got {type(received).__name__}: {received!r}",
            op=op,
            index=index,
        )


class UnknownNodeError(ArgumentError):
    """An argument named a node id that the figure does not contain.

    The message carries the *legal* ids as well, because an agent that
    misspelled an id can usually fix itself if it is told what the right
    ones are.
    """

    def __init__(self, node_id: str, known: Sequence[str], *, op: str, index: int) -> None:
        self.node_id = node_id
        self.known = tuple(known)
        listed = ", ".join(sorted(self.known)) if self.known else "(the figure has no nodes yet)"
        super().__init__(
            f"argument {index} of operator {op!r} is the unknown node id {node_id!r}; "
            f"known node ids: {listed}",
            op=op,
            index=index,
        )


class DegenerateError(StateError):
    """The configuration is legal but has no unique geometric answer.

    Two identical points have no midpoint; three collinear points have no
    circumcircle; a tangent line has no second intersection. These are not
    mistakes in the request -- they are properties of the configuration --
    so they are reported separately from argument errors.
    """


class AmbiguousIntersectionError(StateError):
    """An intersection was requested without saying which one.

    The kernel never guesses between two solutions: a line and a circle
    meet in two points, and "the intersection" is not one of them until the
    caller says which.
    """
