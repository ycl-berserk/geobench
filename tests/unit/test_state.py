"""The figure store: applying operations, previewing them, undoing them."""

from __future__ import annotations

from geobench.model import Figure
from geobench.registry import ArgSpec, OperatorRegistry, OpSpec
from geobench.state import FigureStore, OpRequest


def _store() -> FigureStore:
    registry = OperatorRegistry()
    registry.register(
        OpSpec(
            id="point.midpoint",
            kind="point",
            args=(ArgSpec("a", "point"), ArgSpec("b", "point")),
            returns="point",
        )
    )
    return FigureStore(registry)


def test_free_point_is_created() -> None:
    store = _store()
    result = store.apply("f1", [OpRequest(op="point.free", args=["0", "0"], id="A")])
    assert result.ok
    assert result.created == ["A"]
    assert store.figure("f1").node("A").coords == ("0", "0")


def test_derived_point_without_implementation_is_a_warning_not_a_silent_lie() -> None:
    store = _store()
    store.apply("f1", [OpRequest(op="point.free", args=["0", "0"], id="A")])
    store.apply("f1", [OpRequest(op="point.free", args=["4", "0"], id="B")])
    result = store.apply("f1", [OpRequest(op="point.midpoint", args=["A", "B"], id="M")])
    assert result.ok
    assert result.created == ["M"]
    assert result.warnings and "no implementation" in result.warnings[0]


def test_dry_run_does_not_mutate() -> None:
    store = _store()
    before = store.figure("f1").to_json()
    store.apply("f1", [OpRequest(op="point.free", args=["0", "0"], id="A")], dry_run=True)
    assert store.figure("f1").to_json() == before


def test_undo_restores_the_previous_state() -> None:
    store = _store()
    store.apply("f1", [OpRequest(op="point.free", args=["0", "0"], id="A")])
    after = store.figure("f1").to_json()
    assert store.undo("f1")
    assert store.figure("f1").to_json() != after
    assert store.figure("f1").nodes == {}


def test_failed_batch_leaves_the_figure_untouched() -> None:
    store = _store()
    store.apply("f1", [OpRequest(op="point.free", args=["0", "0"], id="A")])
    before = store.figure("f1").to_json()
    result = store.apply(
        "f1",
        [
            OpRequest(op="point.free", args=["1", "1"], id="B"),
            OpRequest(op="point.midpoint", args=["A", "MISSING"], id="M"),
        ],
    )
    assert not result.ok
    assert store.figure("f1").to_json() == before


def test_figure_can_be_reloaded_from_json() -> None:
    store = _store()
    store.apply("f1", [OpRequest(op="point.free", args=["0", "0"], id="A")])
    payload = store.figure("f1").to_json()
    assert Figure.from_json(payload).to_json() == payload
