"""The construction graph: structure, references, acyclicity, round-trip."""

from __future__ import annotations

import pytest

from geobench.errors import FieldError, ModelError
from geobench.model import Figure, Node, Relation


def test_example_round_trip_is_byte_stable() -> None:
    figure = Figure.example()
    payload = figure.to_json()
    assert Figure.from_json(payload).to_json() == payload


def test_duplicate_node_id_is_rejected() -> None:
    figure = Figure()
    figure.add_node(Node(id="A", kind="point", role="free", coords=("0", "0")))
    with pytest.raises(ModelError, match="already exists"):
        figure.add_node(Node(id="A", kind="point", role="free", coords=("1", "1")))


def test_free_point_requires_exact_coordinates() -> None:
    figure = Figure()
    with pytest.raises(ModelError, match="needs exact coordinates"):
        figure.add_node(Node(id="A", kind="point", role="free"))


def test_free_point_rejects_floating_coordinates() -> None:
    figure = Figure()
    with pytest.raises(FieldError):
        figure.add_node(Node(id="A", kind="point", role="free", coords=("0.5", "0")))


def test_derived_node_requires_operator_and_arguments() -> None:
    figure = Figure()
    with pytest.raises(ModelError, match="must name an operator"):
        figure.add_node(Node(id="M", kind="point", role="derived", args=["A"]))
    with pytest.raises(ModelError, match="must have arguments"):
        figure.add_node(Node(id="M", kind="point", role="derived", op="point.midpoint"))


def test_unknown_reference_is_rejected() -> None:
    figure = Figure()
    with pytest.raises(ModelError, match="unknown node id"):
        figure.add_node(Node(id="M", kind="point", role="derived", op="point.midpoint", args=["A"]))


def test_relation_must_reference_existing_nodes() -> None:
    figure = Figure()
    figure.add_node(Node(id="A", kind="point", role="free", coords=("0", "0")))
    with pytest.raises(ModelError, match="unknown node id"):
        figure.add_relation(
            Relation(id="r1", kind="collinear", args=["A", "Q"])
        )


def test_dependency_cycle_is_detected_with_its_path() -> None:
    figure = Figure()
    figure.nodes["A"] = Node(id="A", kind="point", role="derived", op="point.midpoint", args=["B"])
    figure.nodes["B"] = Node(id="B", kind="point", role="derived", op="point.midpoint", args=["A"])
    with pytest.raises(ModelError) as excinfo:
        figure.validate()
    assert "A -> B -> A" in str(excinfo.value)


def test_removing_a_used_node_is_rejected() -> None:
    figure = Figure.example()
    with pytest.raises(ModelError, match="used by"):
        figure.remove_node("A")


def test_removing_a_referenced_node_is_rejected() -> None:
    figure = Figure.example()
    with pytest.raises(ModelError, match="referenced by relation"):
        figure.remove_node("M")


def test_point_coordinates_are_exact() -> None:
    figure = Figure()
    figure.add_node(Node(id="A", kind="point", role="free", coords=("1/2", "3")))
    x, y = figure.point_coords("A")
    assert x == 0.5 or str(x) == "1/2"
    assert y.as_numer_denom() == (3, 1)


def test_example_figure_validates() -> None:
    Figure.example().validate()
