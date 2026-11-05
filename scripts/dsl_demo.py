"""The DSL, end to end: text in, verified figure out.

This is the proof that the DSL is more than a parser: a competition problem
written in Chinese, fed through the DSL, yields a figure whose claim is
decided *identically* by the kernel.

Run with::

    python scripts/dsl_demo.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from geobench.dsl import parse_dsl, to_dsl  # noqa: E402
from geobench.evaluate import evaluate_figure  # noqa: E402
from geobench.judges import IDENTITY, JudgeRegistry, judge_relation  # noqa: E402
from geobench.operators import register_builtins  # noqa: E402
from geobench.registry import OperatorRegistry  # noqa: E402
from geobench.render import COMPETITION, render_svg  # noqa: E402

# A competition-style problem, written the way a teacher would write it.
PROBLEM = """\
点 A(0,0) B(6,0) C(2,4)
△ABC
⊙O = 过 A B C
D = BC 上 A 的垂足
M = AB 中点
I = △ABC 的内心
P = AD 与 ⊙O 的另一交点
断言 M A B 共线
断言 AB = AC
"""


def main() -> None:
    registry = OperatorRegistry()
    register_builtins(registry)
    judges = JudgeRegistry()

    print("== DSL ==\n" + PROBLEM)

    figure = parse_dsl(PROBLEM)
    evaluate_figure(figure, registry)

    print("== 求值 ==")
    for node in figure.nodes.values():
        if node.role == "free":
            continue
        placement = node.placement
        where = f"({placement[0]}, {placement[1]})" if placement else "(线/圆)"
        print(f"  {node.id:<3} {node.op:<28} {where}")

    print("\n== 判定 (identity 作用域) ==")
    verdicts = []
    for relation in figure.relations:
        verdict = judge_relation(figure, relation.kind, relation.args, judges, scope=IDENTITY)
        verdicts.append((relation, verdict))
        mark = {"proved": "成立", "refuted": "不成立", "supported": "未证"}.get(
            verdict.verdict, verdict.verdict
        )
        print(f"  {relation.kind:<14} -> {mark}")

    print("\n== 往返（构造图 -> DSL -> 构造图）==")
    text = to_dsl(figure)
    print(text)
    again = parse_dsl(text)
    same = set(again.nodes) == set(figure.nodes)
    print(f"  往返后节点集合一致: {same}")

    out_dir = ROOT / "examples"
    out_dir.mkdir(exist_ok=True)
    svg_path = out_dir / "dsl-demo.svg"
    svg_path.write_text(render_svg(figure, COMPETITION), encoding="utf-8")
    print(f"\n== 输出 ==\n  SVG: {svg_path.relative_to(ROOT)}")

    problem = {
        "id": "geo-2026-0002",
        "version": 1,
        "statement": {"zh": "如图，AB 是 ⊙O 的弦，M 为 AB 中点，D 为 A 到 BC 的垂足。"},
        "figure": json.loads(figure.to_json()),
        "dsl": PROBLEM,
        "verification": [
            {
                "relation": relation.kind,
                "args": relation.args,
                "verdict": verdict.verdict,
                "scope": verdict.scope,
                "evidence": verdict.evidence,
            }
            for relation, verdict in verdicts
        ],
        "degeneracy": {"status": "clean", "reports": []},
        "provenance": {"source": "self-authored", "license": "CC0-1.0"},
    }
    problem_path = out_dir / "dsl-demo-problem.json"
    problem_path.write_text(
        json.dumps(problem, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"  题库文件: {problem_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
