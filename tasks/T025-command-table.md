# T025 —— GeoGebra 几何命令总表与算子映射

**状态**：已实现
**负责人**：Agent
**规格**：[`docs/plan.md`](../docs/plan.md) §6；决策 D17
**依赖**：T024
**涉及层**：算子

## 目标

把"我们要覆盖 GeoGebra 的几何命令"这件事变成**一张机器可读的表**，而不是文档里的一段散文。

这张表要同时喂三处：

- **DSL**：命令名 → 算子；
- **工具栏**：算子 → 工具；
- **覆盖表**：`docs/plan.md` §6 —— 逐条推进的清单。

三处共用一张表，就不会有"文档说支持、代码里没有"这种事。

## 交付物

- `src/geobench/commands.py` —— **命令表**（77 条）。
- `scripts/gen_coverage.py` —— 由命令表**生成** `docs/plan.md` §6；`--check` 供 CI 用。
- `tests/unit/test_commands.py` —— 12 项。

## 关键做法

**命令表是唯一真源。** 每个条目记：中文名（正本）、英文名（GeoGebra 的，也接受）、族、种类（构造/判定/测量）、参数个数、参数种类、是否已实现。

**英文名始终接受。** GeoGebra 的输入栏在任何语言下都认英文，老师不必学第二套。这也让"中文名记错了"从致命变成只是不方便。

**重载必须能靠参数分开。** 有一条测试专门盯这个：同名命令的"签名"（种类 + 参数个数 + 参数种类）必须互不相同 —— 否则 DSL 猜不出写的是哪一个。

**覆盖表是生成的。** `docs/plan.md` §6 由 `scripts/gen_coverage.py` 写出来，CI 用 `--check` 盯着它。文档因此**不可能**落后于代码。

**表要说实话。** 有一条测试断言：标成"已实现"的命令，**必须**真的有算子或判定器；反过来，已有算子**必须**在表里（否则它从 DSL 里够不着）。

## 验收标准

```bash
pytest tests/unit/test_commands.py -q
python scripts/gen_coverage.py --check
ruff check . && mypy src
```

## 失败记录

见 [`T025-command-table.failures.md`](T025-command-table.failures.md)。
