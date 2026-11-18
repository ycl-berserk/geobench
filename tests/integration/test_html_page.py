"""Run the page's JavaScript and check it against the kernel.

The HTML export prints the numeric path as JavaScript -- one function per
object.  That is a *third* consumer of the same formulas, and the way it
goes wrong is silently: a sign, a square root, a misplaced bracket, and
the page draws a figure that is not the one the kernel computed.

So the page is not trusted: this test takes the functions the page would
run, evaluates them with Node, and compares every number with what the
kernel's numeric path produces for the same figure.  If Node is not on
the machine the test is skipped -- CI does not need it to be, because the
page is generated from the same expressions the kernel evaluates.

The formulas are the page's *object functions*; the drawing code around
them needs a browser, and is checked by looking at the page (examples/).
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from geobench.app.export_html import html_source
from geobench.dsl import parse_dsl
from geobench.evaluate import evaluate_figure, evaluate_numeric
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="the page's formulas need node to run")

FIGURES = (
    "点 A(0,0) B(5,0) C(2,4)\nAB = 线段(A, B)\nBC = 线段(B, C)\nCA = 线段(C, A)\nM = 中点(B, C)\nO = 外心(A, B, C)\nw = 外接圆(A, B, C)\n",
    "点 A(0,0) B(5,0) C(1,1)\nAB = 线段(A, B)\nAC = 线段(A, C)\nl = 垂直(C, AB)\nP = 交点(l, AC)\nc = 圆(A, B)\nt = 切线(B, c)\n",
    "点 A(0,0) B(4,0) C(1,3)\nO = 内心(A, B, C)\nH = 垂心(A, B, C)\nG = 重心(A, B, C)\n外 = 外接圆(A, B, C)\n",
)


@pytest.fixture(scope="module")
def registry() -> OperatorRegistry:
    reg = OperatorRegistry()
    register_builtins(reg)
    return reg


def _page_nodes(source: str, registry: OperatorRegistry) -> tuple[str, dict]:
    """The node functions the page would run, and the kernel's numbers."""
    figure = evaluate_figure(parse_dsl(source), registry)
    evaluate_numeric(figure)
    page = html_source(figure, title="测试")
    start = page.index("nodes: [")
    end = page.index("\n  ]", start)
    nodes = page[start + len("nodes: [") : end]
    free = {
        node.id: (
            float(node.placement[0]),
            float(node.placement[1]),
        )
        for node in figure.nodes.values()
        if node.role == "free" and node.kind == "point" and node.placement is not None
    }
    return nodes, free


def _run_js(nodes: str, free: dict) -> dict:
    """Evaluate the page's functions with Node, and read the payloads."""
    script = (
        "const free = "
        + json.dumps(free)
        + ";\n"
        + "const nodes = ["
        + nodes
        + "];\n"
        + "const v = {};\n"
        + 'for (const [name, p] of Object.entries(free)) { v["x_"+name]=p[0]; v["y_"+name]=p[1]; }\n'
        + "for (const node of nodes) { v[node.id] = node.f(v); }\n"
        + "console.log(JSON.stringify(v));\n"
    )
    result = subprocess.run(
        [NODE, "-e", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("source", FIGURES, ids=["circumcentre", "tangent", "centres"])
def test_the_page_computes_what_the_kernel_computes(
    source: str, registry: OperatorRegistry
) -> None:
    nodes, free = _page_nodes(source, registry)
    values = _run_js(nodes, free)

    figure = evaluate_figure(parse_dsl(source), registry)
    evaluate_numeric(figure)
    for node_id, node in figure.nodes.items():
        if node.role == "free" or node.kind not in (
            "point",
            "segment",
            "line",
            "circle",
            "polygon",
            "polyline",
            "ray",
        ):
            continue
        payload = node.cache.get("numeric", {}).get(node.kind, None)
        if payload is None:
            continue
        expected = list(payload) if isinstance(payload, tuple) else [payload]
        got = values[node_id]
        assert len(got) == len(expected), node_id
        for left, right in zip(got, expected, strict=True):
            assert abs(left - right) <= 1e-9 * max(1.0, abs(right)), (
                f"{node_id}: the page says {got}, the kernel says {expected}"
            )
