# T023b —— 构造是原子的

**状态**：已实现
**负责人**：Agent
**规格**：[`docs/plan.md`](../docs/plan.md) §M-B
**依赖**：T023
**涉及层**：应用 · 图元

## 目标

用户用"直线"工具在**同一个点上点了两下** ✓，程序报 `cannot build a line through a single point twice` ✓，然后**整张图崩了** ✓、程序退出 ✓。

## 根因

`construct` 不是原子的 ✓：节点**先加进图** ✓，再评估 ✗ —— 评估失败时节点**留在图里**且**没有缓存** ✓ ✓。于是：

- 下一次 `evaluate` 又失败 ✓；
- 每一次 `paintEvent` 也失败 ✓；
- 异常从 Qt 事件里逃出来 → **进程结束** ✓。

## 交付物

- **构造全有或全无** ✓：失败就回滚到快照 ✓
- **图元层的保护接住 `KeyError`** ✓（"节点没有载荷"也是"没有值" ✓）
- **同一个对象连着点两下只算一次** ✓
- **斜率和方向改用 `as_line`** ✓（契约允许线段 ✓，算子就得真的收 ✓）
- 测试 `tests/app/test_atomic_construct.py`（3 个用例 ✓）

## 关键做法

**"拒绝"必须什么都不留下。** 半成品比没有更糟 ✓ —— 它不但没用 ✓，还让整张图不再能用 ✓。

**兜底要按"会出什么"写。** 上一次修"图不崩"时 ✓ 只接了我想到的异常 ✗ —— 而这次的形状是 `KeyError` ✓ ✓。兜底的地方宁可宽一点 ✓。

**点击是"选一个对象"，不是"记一次"。** 同一个东西连着点两下 ✓，意思一定是手抖了 ✓。

## 验收标准

```bash
pytest tests/app/test_atomic_construct.py -q
pytest tests/app/test_every_tool.py -q
ruff check . && mypy src
```

## 失败记录

见 [`T023b-atomic-construct.failures.md`](T023b-atomic-construct.failures.md)。
