# T006 —— 第一批算子与对拍电池

**状态**：已实现（对拍全绿：13 个算子，340+ 组夹具）
**负责人**：Agent
**规格**：`docs/spec.md` §5（算子目录）、§4.1（化简预算）
**依赖**：T002
**涉及层**：算子

## 目标

把第一批算子做出来，并让每一个都**有独立实现对它作证**。几何代码"看着对"却经常在边界处是错的，只有对拍能发现。

## 交付物

- `src/geobench/operators.py` —— 算子实现与注册表装配：
  - 点：`point.midpoint`、`point.centroid`、`point.foot`、`point.intersect_lines`、
    `point.circumcenter`、`point.incenter`、`point.orthocenter`
  - 线：`line.free`、`line.perpendicular_through`、`line.parallel_through`
  - 线段：`segment.free`
  - 圆：`circle.through`、`circle.free`
- `src/geobench/evaluate.py` —— 按依赖顺序求值，产出符号坐标与数值摆放两栏。
- `scripts/gen_fixtures.py` —— 确定性夹具生成器（固定种子，可重跑、可 diff）。
- `tests/oracle/fixtures/*.json` —— 每个算子 ≥ 24 组，含退化用例。

## 验收标准

```bash
python scripts/gen_fixtures.py
pytest tests/oracle -q
ruff check . && mypy src
```

另需人工确认：

- 每个算子的夹具数 ≥ 24，其中退化 ≥ 3；
- 退化夹具断言的是**错误**，不是"值不同"；
- `point.centroid` 这类**处处有定义**的算子，用"edge"类夹具（退化三角形仍有重心）而不是伪造退化。

## 失败记录

见 [`T006-operators-batch1.failures.md`](T006-operators-batch1.failures.md)。这一批的失败集中在两个地方：**sympy 1.14 的 API 变化**，以及**判定"什么算退化"时想当然**。

## 非目标

- Tier-B 算子（反射、内切、旁心、弧中点、切点、根轴…）。
- 3D 与圆锥曲线。
- 退化检测器本身（T013）。
