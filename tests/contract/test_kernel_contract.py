"""Contracts about the kernel itself, checked against the source.

Two of them are about the separation between the exact path and the
numeric path (decision D18):

- the numeric path may not be imported by the judges -- a verdict must
  never depend on an approximation;
- the verdict must be the same whether or not the numeric path has run.

The third is the plain one: the public API of the kernel must exist,
because everything else is built on it.
"""

from __future__ import annotations

import ast
from pathlib import Path

from geobench.evaluate import evaluate_exact, evaluate_numeric
from geobench.judges import IDENTITY, JudgeRegistry, judge_relation
from geobench.model import FREE, POINT, Figure, Node
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry

SRC = Path(__file__).resolve().parents[2] / "src" / "geobench"


def _imports_of(module: str) -> set[str]:
    """The modules a kernel module imports, read from its source."""
    tree = ast.parse((SRC / module).read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _figure() -> Figure:
    registry = OperatorRegistry()
    register_builtins(registry)
    figure = Figure(id="fig_contract")
    for name, x, y in (("A", "0", "0"), ("B", "6", "0"), ("C", "2", "4")):
        figure.add_node(
            Node(
                id=name,
                kind=POINT,
                role=FREE,
                coords=(f"x_{name}", f"y_{name}"),
                placement=(x, y),
            )
        )
    figure.add_node(
        Node(
            id="M",
            kind=POINT,
            role="derived",
            op="point.midpoint",
            args=["A", "B"],
        )
    )
    return figure, registry


def test_the_judges_do_not_import_the_numeric_path() -> None:
    """A verdict must never depend on an approximation."""
    assert "geobench.numeric" not in _imports_of("judges.py")


def test_the_canvas_reads_primitives_and_computes_no_geometry() -> None:
    """The screen draws the picture; it does not make it (decision D20).

    If the canvas computed geometry itself, the screen and the exported
    figure would be two independent implementations of "how a figure
    looks", and they would drift apart.
    """
    imports = _imports_of("app/canvas.py")
    assert "geobench.evaluate" not in imports
    assert "geobench.numeric" not in imports
    assert "geobench.primitives" in imports


def test_the_verdict_does_not_depend_on_the_numeric_path() -> None:
    figure, registry = _figure()
    evaluate_exact(figure, registry)
    judges = JudgeRegistry()
    without = judge_relation(figure, "collinear", ["A", "M", "B"], judges, scope=IDENTITY)

    evaluate_numeric(figure)
    with_numeric = judge_relation(
        figure, "collinear", ["A", "M", "B"], judges, scope=IDENTITY
    )

    assert without.verdict == with_numeric.verdict
    assert without.evidence == with_numeric.evidence


def test_the_public_api_exists() -> None:
    import geobench

    for name in geobench.__all__:
        assert hasattr(geobench, name), f"geobench.{name} is promised but missing"
