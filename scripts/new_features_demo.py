"""Try the newer commands end to end: polygon, arc, sector, measurements."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from geobench.dsl import parse_dsl, to_dsl  # noqa: E402
from geobench.evaluate import evaluate_figure  # noqa: E402
from geobench.judges import INSTANCE, JudgeRegistry, judge_relation  # noqa: E402
from geobench.operators import register_builtins  # noqa: E402
from geobench.registry import OperatorRegistry  # noqa: E402
from geobench.render import render_svg  # noqa: E402

PROBLEM = """\
点 A(0,0) B(6,0) C(2,4) D(5,5) O(0,0)
四边形 = 多边形(A,B,C,D)
圆 = 外接圆(A,B,C)
弧 = 圆弧(A, B, C)
扇 = 三点扇形(O, A, B)
d = 距离(A, B)
p = 周长(四边形)
s = 面积(四边形)
ang = 角度(A, B, C)
r = 半径(圆)
断言 共线(A, B, C)
"""

registry = OperatorRegistry()
register_builtins(registry)
judges = JudgeRegistry()

print("== DSL ==\n" + PROBLEM)

figure = parse_dsl(PROBLEM)
evaluate_figure(figure, registry)

print("== 图上的东西 ==")
for node in figure.nodes.values():
    payload = figure.node(node.id).cache.get("numeric")
    if not payload:
        continue
    if node.kind == "number":
        print(f"  {node.id:<6} {node.kind:<8} {payload['value']:.4f}")
    elif node.kind == "polygon":
        print(f"  {node.id:<6} {node.kind:<8} {len(payload['polygon']) // 2} 个顶点")
    elif node.kind in {"arc", "sector"}:
        print(f"  {node.id:<6} {node.kind:<8} 圆心 {payload[node.kind][:2]}")
    elif node.kind == "circle":
        print(f"  {node.id:<6} {node.kind:<8} 圆心 {payload['circle'][:2]}")

print("\n== 判定（这一张图）==")
verdict = judge_relation(figure, "collinear", ["A", "B", "C"], judges, scope=INSTANCE)
print(f"  共线(A,B,C) -> {verdict.verdict}")

print("\n== 图 -> DSL -> 图 ==")
text = to_dsl(figure)
again = parse_dsl(text)
evaluate_figure(again, registry)
print("  往返一致:", [n.id for n in figure.nodes.values()] == [n.id for n in again.nodes.values()])

svg = render_svg(figure)
out = ROOT / "examples" / "new-features.svg"
out.write_text(svg, encoding="utf-8")
print(f"\n== SVG: {out} ==")
