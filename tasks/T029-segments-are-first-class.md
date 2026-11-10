# T029 —— 线段是一等公民

**状态**：已实现
**负责人**：Agent
**规格**：[`docs/plan.md`](../docs/plan.md) §M-B
**依赖**：T027
**涉及层**：内核 · DSL · 应用

## 目标

老师报了两件事：

1. **「画垂线和平行线都要求线是直线而不能是线段，但实际上竞赛当中大部分都是线段，你应该把线段的功能补全」**
2. **「我没有办法点出两条线/线段的交点，不管怎么点都会有自由度」**

## 第 1 件：垂线、平行线只认直线

内核其实**已经**知道线段带一条直线 —— `OpContext.as_line` 的注释就写着
「Competition figures draw segments, but the operations that need a line
(a foot, an intersection) work on the supporting line」。

问题是垂线和平行线问的是 `ctx.line(...)`（只认直线节点），不是 `as_line`。
于是 `线段` 一进去就报 `node 's1' is not a line`。

**做法**：两个算子改用 `as_line` ✓。垂足（`point.foot`）本来就是对的 ✓，
最近点（`point.nearest_on_object`）分情况处理 ✓，交点（`point.intersect_lines`）
也是对的 ✓ —— 只有这两个漏了。

## 第 2 件：点不出交点

复现之后发现两件事：

- **交点工具本身是好的** ✓：两条线段的交点能点出来 ✓；
- **点工具不会** ✗：它只有一种动作 —— 在哪儿点就在哪儿放一个**自由点**，
  所以「不管怎么点都会有自由度」✓。

于是把点工具按几何师的顺序改了：

1. **点在两线交点上** → 造**交点**（derived ✓ —— 没有自己的自由度 ✓）；
2. **点在圆上** → 造**圆上的点**（T027 ✓）；
3. **点在线或线段上** → 造**线上的点**（新 ✓）；
4. **别的地方** → 自由点 ✓。

第 3 条同时补上了 T027 之后一直挂着的那个缺口：**线段上的贴点** ✓。

## 线上的点

和「圆上的点」同一套机制，但参数是**沿线比例** ✓：

```
P = 线上的点(s, 1/4)
```

- `s` 可以是**线**也可以是**线段** ✓（竞赛里多是线段 ✓）；
- 参数是比例 ✓：0 是一端，1 是另一端，1/2 是中点 ✓；
- 线段上的点**拖不出线段** ✓ —— 参数被夹在两端之间 ✓；
- 判定器能**证明**「P 在 s 上」✓（恒等作用域下就成立 ✓）；
- 线段的两个端点就是比例的两端 ✓；画出来的线用它自己被画过的两个点 ✓；
  构造出来的线（垂线之类）没有那两个点，就沿它自己的方向量 ✓。

## 交付物

- `op_perpendicular_through` / `op_parallel_through` 改用 `as_line`
- 新算子 `point.on_line`（`线上的点`），节点角色 `attached`
- 数值路径：`numeric.along_reference` / `point_on_line` / `parameter_on_line`
- 数值路径：`numeric.intersection_near` —— 光标下方的交点
- 点工具：交点 → 圆 → 线/线段 → 自由点
- 拖动贴点改参数（线段夹在两端之间）
- oracle 电池：23 个夹具（20 正常 + 3 退化）
- 测试 `tests/app/test_segments.py`（9 个用例）

## 验收标准

```bash
pytest tests/app/test_segments.py -q
pytest tests/oracle -q
pytest -q
ruff check . && mypy src
```
