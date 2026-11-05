"""End-to-end demo: build a figure, judge it, render it.

This is the script that produces the artefacts in ``examples/``. It is also the
project's smoke test: if it runs, the whole chain -- construction graph,
evaluation, judgement, rendering, problem file -- works.

Run with::

    python scripts/demo.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from geobench.evaluate import evaluate_figure  # noqa: E402
from geobench.judges import IDENTITY, JudgeRegistry, judge_relation  # noqa: E402
from geobench.model import Figure, Node, Relation, Style  # noqa: E402
from geobench.operators import register_builtins  # noqa: E402
from geobench.registry import OperatorRegistry  # noqa: E402
from geobench.render import COMPETITION, render_svg  # noqa: E402


def build_figure() -> Figure:
    """A triangle with its circumcircle, a median and an altitude foot.

    The relations below are the ones a competition problem would ask about,
    and every one of them is decided *identically*, not just for the drawn
    placement.
    """
    registry = OperatorRegistry()
    register_builtins(registry)

    figure = Figure(id="geo-2026-0001")
    for node_id, (x, y) in {"A": ("0", "0"), "B": ("6", "0"), "C": ("2", "4")}.items():
        figure.add_node(
            Node(
                id=node_id,
                kind="point",
                role="free",
                coords=(f"x_{node_id}", f"y_{node_id}"),
                placement=(x, y),
                label=node_id,
            )
        )

    # Derived construction. Competition figures draw sides as *segments* and
    # auxiliary lines as dashed, so the model needs both.
    for node_id, a, b in (("sAB", "A", "B"), ("sBC", "B", "C"), ("sCA", "C", "A")):
        figure.add_node(
            Node(id=node_id, kind="segment", role="derived", op="segment.free", args=[a, b])
        )
    figure.add_node(
        Node(id="lBC", kind="line", role="derived", op="line.free", args=["B", "C"], label="BC")
    )
    figure.add_node(
        Node(id="M", kind="point", role="derived", op="point.midpoint", args=["A", "B"], label="M")
    )
    figure.add_node(
        Node(id="D", kind="point", role="derived", op="point.foot", args=["A", "lBC"], label="D")
    )
    figure.add_node(
        Node(id="O", kind="point", role="derived", op="point.circumcenter", args=["A", "B", "C"], label="O")
    )
    figure.add_node(
        Node(id="c1", kind="circle", role="derived", op="circle.through", args=["A", "B", "C"], label="⊙O")
    )

    # The claims a problem would be built around.
    figure.add_relation(Relation(id="r1", kind="midpoint_of", args=["M", "A", "B"], expected=True))
    figure.add_relation(Relation(id="r2", kind="equal_length", args=["O", "A", "O", "B"], expected=True))
    figure.add_relation(Relation(id="r3", kind="collinear", args=["A", "M", "B"], expected=True))

    # Auxiliary objects are dashed and carry no label, the way competition
    # papers draw them.
    figure.nodes["lBC"].style = Style(line_style="dashed")

    evaluate_figure(figure, registry)
    return figure


def main() -> None:
    figure = build_figure()
    judges = JudgeRegistry()

    print("== 构造图 ==")
    print(f"  节点 {len(figure.nodes)} 个，关系 {len(figure.relations)} 条")

    print("\n== 判定 ==")
    results = []
    for relation in figure.relations:
        verdict = judge_relation(figure, relation.kind, relation.args, judges, scope=IDENTITY)
        results.append((relation, verdict))
        print(f"  {relation.kind}({', '.join(relation.args)}) -> {verdict.verdict}")
        print(f"      {verdict.evidence[:150]}")

    out_dir = ROOT / "examples"
    out_dir.mkdir(exist_ok=True)

    svg = render_svg(figure, COMPETITION)
    svg_path = out_dir / "demo-figure.svg"
    svg_path.write_text(svg, encoding="utf-8")
    print(f"\n== 输出 ==\n  SVG: {svg_path.relative_to(ROOT)} ({len(svg)} bytes)")

    problem = {
        "id": figure.id,
        "version": 1,
        "statement": {
            "zh": "如图，在△ABC 中，M 是 AB 的中点，D 是 A 到 BC 的垂足，O 是△ABC 的外心。",
        },
        "figure": json.loads(figure.to_json()),
        "givens": ["M 为 AB 中点", "AD ⊥ BC"],
        "goal": "证明：OA = OB = OC",
        "verification": [
            {
                "relation": relation.kind,
                "args": relation.args,
                "verdict": verdict.verdict,
                "scope": verdict.scope,
                "evidence": verdict.evidence,
            }
            for relation, verdict in results
        ],
        "degeneracy": {"status": "clean", "reports": []},
        "provenance": {"source": "self-authored", "license": "CC0-1.0"},
    }
    problem_path = out_dir / "demo-problem.json"
    problem_path.write_text(
        json.dumps(problem, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"  题库文件: {problem_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
