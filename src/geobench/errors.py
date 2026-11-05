"""Typed errors raised by the geobench kernel.

Every error is expected to carry an *actionable* message: which object, which
argument, and why. See docs/spec.md section 11.3.
"""

from __future__ import annotations


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
