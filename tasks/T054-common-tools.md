# T054 —— 常用工具放在第一层

**状态**：已实现
**负责人**：Agent
**规格**：`docs/ui-review.md` §3.1
**依赖**：T021c（工具栏由命令表生成）
**涉及层**：应用

## 问题

中点、交点、垂线、平行线、圆都在各自家族的**第二层菜单**里。老师每节课要点十几次，
却要先记住"中点属于点家族、垂线属于线家族"。

## 做法

- `tools.COMMON_OPS` 固定五个算子：`point.midpoint`、`point.intersect_lines`、
  `line.perpendicular_through`、`line.parallel_through`、`circle.through`；
- `build_toolbar` 在家族组之前插入一个 `常用` 组（同一个 `ToolGroup` 机制，
  菜单由命令表生成，不手写）；
- 它们在各自家族里**仍然存在**——这是第二扇门，不是搬家；
- 组按钮默认工具是**中点**：打开程序后**一次点击**就能到中点；
- 新画一个星形图标（`FAMILY_GLYPHS["常用"] = "star"`），和家族图标区分开。

## 验收

```bash
pytest tests/app/test_common_tools.py -q   # 4 项：顺序、仍在家族里、一次点击、菜单五项
pytest tests/app -q
ruff check . && mypy src
```

## 非目标

- 可自定义的常用工具（先观察真实使用频率）；
- 快捷键 1–5（等确认不会与输入冲突）。
