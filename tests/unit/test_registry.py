"""The operator registry: contracts are data, and must be retrievable."""

from __future__ import annotations

import pytest

from geobench.errors import RegistryError
from geobench.registry import ArgSpec, OperatorRegistry, OpSpec


def _spec(op_id: str = "point.midpoint") -> OpSpec:
    return OpSpec(
        id=op_id,
        kind="point",
        args=(ArgSpec("a", "point"), ArgSpec("b", "point")),
        returns="point",
        degenerate_when=("a == b",),
        oracle="sympy:segment_midpoint",
    )


def test_register_and_lookup() -> None:
    registry = OperatorRegistry()
    registry.register(_spec())
    assert registry.has("point.midpoint")
    assert registry.lookup("point.midpoint").returns == "point"


def test_duplicate_registration_is_rejected() -> None:
    registry = OperatorRegistry()
    registry.register(_spec())
    with pytest.raises(RegistryError, match="already registered"):
        registry.register(_spec())


def test_unknown_operator_lists_the_known_ones() -> None:
    registry = OperatorRegistry()
    registry.register(_spec())
    with pytest.raises(RegistryError) as excinfo:
        registry.lookup("point.nope")
    assert "point.midpoint" in str(excinfo.value)


def test_describe_matches_the_spec_contract() -> None:
    registry = OperatorRegistry()
    registry.register(_spec())
    described = registry.describe("point.midpoint")
    assert described["id"] == "point.midpoint"
    assert described["exact"] is True
    assert described["returns"] == {"type": "point"}
    assert described["degenerate_when"] == ["a == b"]
    assert described["oracle"] == "sympy:segment_midpoint"
    assert [arg["name"] for arg in described["args"]] == ["a", "b"]


def test_implementation_is_optional_and_tracked() -> None:
    registry = OperatorRegistry()
    registry.register(_spec())
    assert not registry.has_implementation("point.midpoint")
    registry.register(OpSpec(id="point.foot", kind="point", args=(), returns="point"), lambda: None)
    assert registry.has_implementation("point.foot")
