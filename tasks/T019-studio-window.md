# T019 —— 桌面工作台：画板、构造步骤表、判定面板

**状态**：已实现
**负责人**：Agent
**规格**：[`docs/plan.md`](../docs/plan.md) §3.2、§5；决策 D16、D19、D20
**依赖**：T015、T018
**涉及层**：渲染 / 服务端

## 目标

**有窗口了。** 这是一个能双击打开的桌面软件：左边是构造步骤，中间是画板，右边是判定。

## 交付物

- `src/geobench/app/controller.py` —— **不含 Qt** 的状态层：加点、构造、拖点、加关系、判定、加样式。绝大部分逻辑因此可以无头测试。
- `src/geobench/app/canvas.py` —— 画布（`QWidget` + `QPainter`）：缩放、平移、命中测试、拖点。
- `src/geobench/app/window.py` —— 主窗口，三栏 + 工具栏。
- `src/geobench/app/theme.py` —— 字体与配色（**中文字体必须显式挑**，否则满屏方框）。
- `src/geobench/app/main.py` —— `geobench-app` 命令的入口。
- `src/geobench/primitives.py` —— **原语列表**（T018）：点 / 线段 / 直线 / 圆 / 标注。SVG 后端与画布后端**吃同一份**。
- `src/geobench/style.py` —— 竞赛图规范预设（原来在 render.py 里，两个后端都要读它）。
- `tests/app/test_controller.py`（11 项）、`tests/app/test_window.py`（5 项，含真实拖点）。
- `scripts/app_preview.py` —— 开窗、造图、截图到 `examples/studio-window.png`。

## 关键做法

**屏幕与导出吃同一份原语。** SVG 渲染器被改成消费 `primitives.py` 的原语列表，画布也消费同一份。一致性由结构保证，而不是靠两套代码碰巧不跑偏（D20）。

**画布是 `QWidget`，不是 `QGraphicsView`。** 图里只有几十个对象，直接用 `QPainter` 画比维护场景图更简单也更快；而且 Qt 的 SVG 渲染扛不住逐帧重绘。

**拖动只走数值路径。** 拖动时内核重算的是**摆放**（微秒级），符号表达式一个字符都不变。判定在松手后触发（判定可能慢，不能绑在拖动上）。

**退化 = 空心点。** 一个在这个摆放下没有值的对象，在画布上是**空心**的（GeoGebra 的 undefined），其余照常画。

**构造步骤表是"有序投影"。** 每一步一行（名字 + 构造式），关系用蓝色标出。

## 验收标准

```bash
pytest tests/app -q
ruff check . && mypy src
```

另需人工确认：

- 拖动自由点时图形跟手，判定结论不变（identity）；
- 工具栏能构造：中点 / 重心 / 外心 / 内心 / 垂心 / 外接圆；
- 画板上的图与导出的 SVG 是同一张图。

## 已知不足（下一版要补）

- 关系的选择是"取前 N 个对象"，不是让用户逐个挑 —— **必须改**，现在只能验证恰好用到的那些关系；
- 判定面板不能手动触发（现在是每次变更自动判）；
- 没有右键菜单、没有撤销、没有保存；
- 圆心/内心的标注位置在某些构型下会压线。

## 失败记录

见 [`T019-studio-window.failures.md`](T019-studio-window.failures.md)。
