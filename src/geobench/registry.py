"""The operator registry.

An operator is a deterministic function from typed arguments to a node. Its
contract is data, not code, so the contract can be published to agents over
MCP (``geobench://spec/operators``) and checked by the test suites.

See docs/spec.md section 5.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from geobench.errors import RegistryError


@dataclass(frozen=True)
class ArgSpec:
    """One argument of an operator."""

    name: str
    type: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "type": self.type}


@dataclass(frozen=True)
class OpSpec:
    """The contract of an operator (docs/spec.md section 5.1)."""

    id: str
    kind: str
    args: tuple[ArgSpec, ...]
    returns: str
    exact: bool = True
    degenerate_when: tuple[str, ...] = ()
    oracle: str | None = None
    since: str = "v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "args": [arg.to_dict() for arg in self.args],
            "exact": self.exact,
            "returns": {"type": self.returns},
            "degenerate_when": list(self.degenerate_when),
            "oracle": self.oracle,
            "since": self.since,
        }


OpImpl = Callable[..., Any]


class OperatorRegistry:
    """Holds every known operator and its (optional) implementation."""

    def __init__(self) -> None:
        self._specs: dict[str, OpSpec] = {}
        self._impls: dict[str, OpImpl] = {}

    def register(self, spec: OpSpec, impl: OpImpl | None = None) -> OpSpec:
        if spec.id in self._specs:
            raise RegistryError(f"operator {spec.id!r} is already registered")
        self._specs[spec.id] = spec
        if impl is not None:
            self._impls[spec.id] = impl
        return spec

    def lookup(self, op_id: str) -> OpSpec:
        try:
            return self._specs[op_id]
        except KeyError:
            raise RegistryError(
                f"unknown operator {op_id!r}; known operators: {', '.join(self.ids())}"
            ) from None

    def has(self, op_id: str) -> bool:
        return op_id in self._specs

    def ids(self) -> list[str]:
        return list(self._specs)

    def describe(self, op_id: str) -> dict[str, Any]:
        return self.lookup(op_id).to_dict()

    def implementation(self, op_id: str) -> OpImpl | None:
        self.lookup(op_id)
        return self._impls.get(op_id)

    def has_implementation(self, op_id: str) -> bool:
        return op_id in self._impls

    def all_specs(self) -> list[OpSpec]:
        return list(self._specs.values())
