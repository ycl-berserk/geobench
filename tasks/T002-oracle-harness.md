# T002 —— 对拍框架与夹具格式

**状态**：提案
**负责人**：Agent
**规格**：`docs/spec.md` §5.3（对拍要求）、§14（验收标准）
**依赖**：T001
**涉及层**：基础设施

## 目标

每个算子都能在进入注册表之前，被一个**独立实现**证明正确。这是全项目最重要的门禁：几何代码"看着对"却经常在边界处是错的。

## 交付物

- `tests/oracle/harness.py` —— 给定算子 id 与夹具集，分别跑内核实现与对拍实现，比较**精确**结果，输出结构化差集（符号差，而不是"不相等"）。
- `tests/oracle/fixtures/<op>.json` —— 夹具格式：参数元组列表，每条标注 `{"kind": "normal" | "degenerate", "expect": "value" | "error"}`；每个算子 ≥ 20 组，其中 ≥ 3 组退化。
- `tests/oracle/oracles.py` —— 独立实现：能用 SymPy 几何/符号例程的用它，能写闭式的写闭式，GeoGebra JS API 作为第三方意见。
- `pytest tests/oracle -q` —— **覆盖门禁**：任何已注册的 Tier-A 算子缺夹具或夹具不足 20 组即失败。
- `docs/oracles.md` —— 每个算子：对拍基准是什么、为什么它独立、已知局限。

## 验收标准

```bash
pytest tests/oracle -q
ruff check . && mypy src
```

另需人工确认：

- 故意写坏的算子（临时副本）会让对拍失败，且差集指出**具体哪个坐标不一致**；
- 覆盖报告列出全部已注册算子，报告文件为 `tests/oracle/coverage.md`，由 `pytest tests/oracle --coverage-report` 生成；
- 退化夹具断言的是**错误**，不只是"值不同"。

## 非目标

- 算子本身的实现（T006）。
- 判定器语义测试（反例要求由 T007 负责）。
