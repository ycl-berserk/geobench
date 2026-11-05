# T008 —— 竞赛图规范预设与 SVG 渲染器

**状态**：已实现（SVG；TikZ 导出待做，见 T014）
**负责人**：Agent
**规格**：`docs/spec.md` §10（渲染与导出）、§3.4（样式）
**依赖**：T001
**涉及层**：渲染

## 目标

把构造图画成**可以直接进卷面**的图：黑白、细线、实心小圆点、衬线斜体标注、辅助线虚线、图注留给题面。

## 交付物

- `src/geobench/render.py` —— 样式预设与 SVG 渲染：
  - `FigureStyle` / `COMPETITION` / `PLAIN`，取值依据见决策 D6（TikZ 通行约定 + 中文卷面 house rule）；
  - `fit_view` —— 视图只由点与圆决定（无限直线会把视图撑爆）；
  - `clip_line` —— Cyrus–Beck，把无限直线裁剪到视口；
  - `render_svg` —— 纯函数：同样的输入必须产生同样的字节。
- `tests/unit/test_render.py` —— 7 个测试（结构、确定性、标注、样式、视图）。
- `scripts/demo.py` —— 端到端演示，产出 `examples/demo-figure.svg` 与题库文件。

## 验收标准

```bash
pytest tests/unit/test_render.py -q
python scripts/demo.py
ruff check . && mypy src
```

另需人工确认：

- 渲染是**纯函数**：同一图形两次渲染字节一致；
- 不可见节点不画；
- 三角形边画成**线段**而不是无限直线；
- 辅助线为虚线且默认无标注。

## 已知不足

- **TikZ 导出未实现**（T014）。竞赛圈大量用 LaTeX + TikZ 出题，这是必需项。
- 标注位置按"图形质心 → 该点"方向外移，**没有避让压线**，复杂图形上可能压线。
- 派生点与自由点目前都是实心圆点，未区分（见决策 D6 的待复核项）。

## 非目标

- 交互式画布（属于前端，属另一个任务）。
- 3D 渲染。
