# T015 —— 求值分层：精确路径（缓存）+ 数值路径（编译）

**状态**：已实现
**负责人**：Agent
**规格**：[`docs/plan.md`](../docs/plan.md) §3.1、§7；决策 D18
**依赖**：T001
**涉及层**：算子

## 目标

让"交互像画图工具一样快"和"判定精确"这两件事**不再互相冲突**。

冲突的来源：GeoGebra 快是因为它用 double；我们要精确。但这两件事**不需要同时发生** —— 关键事实是：

> **派生对象的符号表达式不随自由点摆放变化。**

中点的表达式永远是 `(x_A + x_B)/2`，拖动 A 不会改它一个字符。由此推出三件事：

1. 拖动只走数值路径 → 永不快到卡；
2. 精确求值只在**构造变了**时做一次 → 判定前不必"现算一遍"；
3. **identity 结论与摆放无关**（这正是 D12 的定义）→ 拖动时 `proved` 仍是 `proved`。

## 交付物

- `src/geobench/numeric.py` —— **数值路径**：把符号表达式编译成 float 函数、算出摆放、发现退化。
- `src/geobench/evaluate.py` —— 拆成 `evaluate_exact` / `evaluate_numeric` / `evaluate_figure`；精确路径**增量**（按依赖版本号跳过没变的节点）。
- `src/geobench/model.py` —— `Figure.runtime`（不序列化的暂存区）；`copy()` 保留缓存。
- `tests/unit/test_evaluate.py` —— 11 个测试。
- `tests/contract/test_kernel_contract.py` —— 判定器**不得** import 数值路径；判定结果与数值路径无关。
- `tests/no_float/test_no_float.py` —— 浮点的例外改为**按模块名显式列举**（新增 `numeric`，附理由）。

## 关键做法

**算子只写一遍。** 数值路径用 `lambdify` 把**同一份符号表达式**编译成 float 函数，不另写一套数值实现。

**编译函数只带它用到的符号。** 最初版本让每个函数接收**全部**自由点符号（400 个点 = 800 个参数），于是每帧要传 32 万个参数 —— 数值路径慢了 25 倍。改成只带用到的符号后，400 个对象的拖动帧从 40.5ms 降到 1.6ms。

**退化 = undefined，不是失败。** 数值路径遇 ZeroDivisionError / 非有限值 → 该对象标 `undefined`，**其余部分照常**（GeoGebra 语义，D19）。`geo_construct` 因此把这种情况报成 `degraded`（原因在 `warnings` 里），而不是 `error` —— 请求本身没错。

**增量靠版本号。** 每个节点记一个版本号；节点的签名 = (算子, 参数, 参数的版本号)。签名不变 → 表达式不变 → 跳过。

## 验收标准

```bash
pytest tests/unit/test_evaluate.py -q
pytest tests/contract -q
pytest tests/no_float -q
ruff check . && mypy src
```

## 实测（对照：旧路径 = 符号求值 + 逐坐标 `simplify`）

| 对象数 | 旧数值步 | 新数值路径 | 倍数 |
|---|---|---|---|
| 20 | 69.7 ms | 0.083 ms | **841×** |
| 100 | 1521.4 ms | 0.408 ms | **3727×** |
| 300 | 13498.9 ms | 1.190 ms | **11343×** |

完整拖动一帧（精确路径检查 + 数值路径）：

| 对象数 | 拖动一帧 | 预算 |
|---|---|---|
| 100 | 0.93 ms | ≤ 16 ms ✓ |
| 400 | 3.92 ms | ≤ 16 ms ✓ |

首次构建（全部精确求值）：100 对象 168ms，400 对象 692ms。

## 失败记录

见 [`T015-evaluation-split.failures.md`](T015-evaluation-split.failures.md)。
