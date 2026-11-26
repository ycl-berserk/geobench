"""Writing a `.ggb`, and proving it by reading it back.

The export is only worth having if the file it writes is a file the
import can read as the same figure.  That is what this test checks: not
the bytes, but the round trip.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from geobench.dsl import parse_dsl
from geobench.evaluate import evaluate_figure, evaluate_numeric
from geobench.ggb import import_ggb
from geobench.ggb_export import export_ggb
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry

SOURCE = """点 A(0, 0) B(4, 0) C(1, 3)
f = 线段(A, B)
M = 中点(A, B)
O = 外心(A, B, C)
c = 外接圆(A, B, C)
P = 交点(f, c, 0)
p = 垂直(A, f)
q = 平行(C, f)
多边形(A, B, C)
圆弧(O, A, B)
三点弧(A, B, C)
圆扇形(O, A, B)
文本 note("first line\\nsecond line", -1, -2)
"""


@pytest.fixture()
def registry() -> OperatorRegistry:
    reg = OperatorRegistry()
    register_builtins(reg)
    return reg


def _figure(registry: OperatorRegistry):
    figure = parse_dsl(SOURCE)
    evaluate_figure(figure, registry)
    evaluate_numeric(figure)
    return figure


def test_the_exported_file_is_the_same_figure(
    tmp_path: Path, registry: OperatorRegistry
) -> None:
    figure = _figure(registry)
    path = tmp_path / "figure.ggb"
    assert export_ggb(figure, path) == []

    result = import_ggb(path)
    again = parse_dsl(result.dsl)
    evaluate_figure(again, registry)
    evaluate_numeric(again)

    for node_id in ("A", "B", "C", "M", "O", "P"):
        assert node_id in again.nodes
        before = figure.nodes[node_id].cache["numeric"]["coords"]
        after = again.nodes[node_id].cache["numeric"]["coords"]
        assert before == pytest.approx(after)
    assert any(node.kind == "arc" for node in again.nodes.values())
    assert any(node.kind == "sector" for node in again.nodes.values())
    assert again.nodes["note"].args[0] == "first line\nsecond line"


def test_what_cannot_be_written_is_reported(
    tmp_path: Path, registry: OperatorRegistry
) -> None:
    source = """点 A(0, 0) B(4, 0) O(2, 0)
c = 圆(O, 2)
t = 切线(B, c)
d = 距离(A, B)
"""
    figure = parse_dsl(source)
    evaluate_figure(figure, registry)
    evaluate_numeric(figure)
    skipped = export_ggb(figure, tmp_path / "partial.ggb")
    assert any("t" in item for item in skipped)
    assert any("d" in item for item in skipped)
