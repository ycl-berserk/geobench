# 任务清单

一个工作单元 = 一个文件。**任务文件是代码进入仓库的唯一通道。**

## 格式

```markdown
# T0XX —— <标题>
**状态**：提案 | 已规格化 | 已实现 | 门禁通过 | 已接受 | 已合并
**负责人**：Agent | 人
**规格**：docs/spec.md §X.Y
**依赖**：T0YY
**涉及层**：模型 | 算子 | 判定器 | 求解 | 渲染 | 服务端 | DSL | 基础设施

## 目标
一段话：内核的使用者会因此得到什么。

## 交付物
- 文件 / 符号

## 验收标准
只写可执行命令，不写散文式标准。

## 非目标
本任务明确不做什么。
```

## 规则

1. **验收标准必须是命令。** `pytest tests/unit/test_model.py -q`，而不是"模型工作正常"。
2. **一个任务只碰一层**（见"涉及层"）。
3. **不顺手重构。** 重构单独立任务，这样回归可归因。
4. **算子任务必须含对拍**（spec §5.3）；**判定器任务必须含反例测试**（spec §6.3）。
5. **被拒的 Agent 产出必须留档**在 `T0XX.failures.md`，不许删除（见 `docs/ai-workflow.md` §6）。

## 索引

| ID | 标题 | 层 | 状态 | 依赖 |
|---|---|---|---|---|
| [T001](T001-kernel-skeleton.md) | 内核骨架：构造图、精确数域、算子注册表 | 模型 / 基础设施 | 已实现（门禁本地通过） | — |
| [T002](T002-oracle-harness.md) | 对拍框架与夹具格式 | 基础设施 | 提案 | T001 |
| [T003](T003-mcp-server-core.md) | MCP 服务端核心：`geo_state` / `geo_construct` / `geo_evaluate` | 服务端 | 提案 | T001 |
| [T004](T004-dsl-parser.md) | 中文几何 DSL：语法、递归下降解析器、DSL↔构造图 | DSL | 提案 | T001 |
| [T005](T005-text2graph.md) | text2graph 通道：自然语言→DSL 的翻译接口与题面生成 | DSL / 服务端 | 提案 | T004 |
| T006 | Tier-A 算子第一批（`midpoint` `foot` `intersect_lines` `circumcenter` …） | 算子 | 提案 | T002 |
| T007 | 第一批判定器（`collinear` `perpendicular` `concyclic`） | 判定器 | 提案 | T006 |
| T008 | 竞赛图规范预设 + SVG/TikZ 渲染器 | 渲染 | 提案 | T001 |
| T009 | `geo_solve` 与 `geo_variants` | 求解 | 提案 | T006, T007 |
| T010 | 题库文件格式与导出器 | 基础设施 | 提案 | T008 |
| T011 | 评测框架（`evals/`） | 基础设施 | 提案 | T007, T009 |
| T012 | 英文版 spec 快照（best-effort） | 文档 | 提案 | — |
