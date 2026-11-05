"""Turning kernel exceptions into structured, machine-readable errors.

The kernel raises typed exceptions; an agent needs *structured* errors, not
prose. This module is the one place where the two vocabularies meet, so
the mapping is written down once.
"""

from __future__ import annotations

from geobench.errors import (
    AmbiguousIntersectionError,
    ArgumentCountError,
    ArgumentTypeError,
    DegenerateError,
    GeobenchError,
    RegistryError,
    UnknownNodeError,
)
from geobench.tools.models import ErrorInfo


def to_error_info(exc: GeobenchError) -> ErrorInfo:
    """Describe a kernel failure in a form an agent can act on."""
    if isinstance(exc, UnknownNodeError):
        return ErrorInfo(
            code="unknown_node",
            message=str(exc),
            op=exc.op,
            index=exc.index,
            node_id=exc.node_id,
            known_node_ids=list(exc.known),
        )
    if isinstance(exc, ArgumentCountError):
        return ErrorInfo(
            code="argument_count",
            message=str(exc),
            op=exc.op,
            index=exc.index,
        )
    if isinstance(exc, ArgumentTypeError):
        return ErrorInfo(
            code="argument_type",
            message=str(exc),
            op=exc.op,
            index=exc.index,
        )
    if isinstance(exc, DegenerateError):
        return ErrorInfo(code="degenerate", message=str(exc))
    if isinstance(exc, AmbiguousIntersectionError):
        return ErrorInfo(code="ambiguous_intersection", message=str(exc))
    if isinstance(exc, RegistryError):
        return ErrorInfo(code="unknown_operator", message=str(exc))
    return ErrorInfo(code="error", message=str(exc))
