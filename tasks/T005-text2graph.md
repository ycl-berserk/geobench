# T005 —— text2graph 通道：自然语言 → DSL 的翻译接口与题面生成

**状态**：提案
**负责人**：Agent
**规格**：`docs/spec.md` §9.1、§9.5、§11.1
**依赖**：T004
**涉及层**：DSL / 服务端

## 目标

把"文字出图"这件事做成**可靠**的流程，而不是"模型直接画图"。做法是把不确定性关进一个盒子里：

```
自然语言 ──(模型翻译 或 人工)──▶ DSL ──(确定性解析器)──▶ 构造图 ──(内核)──▶ 验证 / 渲染 / 题面
```

模型只做翻译；翻译结果必须过解析器校验；解析失败时错误带精确行列，供 Agent 重试。

## 交付物

- `src/geobench/tools/apply_dsl.py` —— `geo_apply_dsl` 工具：`{ figure_id?, dsl, mode }`，成功返回构造图增量，失败返回带 `line`/`col`/`span` 的错误。
- `src/geobench/tools/to_dsl.py` —— `geo_to_dsl` 工具：由构造图 + 断言反生成 DSL 与**题面草稿**（"如图，△ABC 中 …，证明 …"）。
- `docs/text2graph.md` —— 翻译契约：DSL 子集怎么定义、模型被允许做什么、错误重试循环长什么样、什么情况下必须转人工。
- `prompts/translate-to-dsl.md` —— 给翻译模型的提示词模板（输入自由中文，输出 DSL，附子集约束与错误反馈循环）。
- `prompts/problem-from-figure.md` —— 由构造图反推题面与"求证目标"的提示词模板。
- `tests/unit/tools/test_apply_dsl.py`、`test_to_dsl.py`。
- `tests/integration/test_text2graph_loop.py` —— 模拟"翻译出错 → 解析器报错 → 带错误重试"整轮。

## 验收标准

```bash
pytest tests/unit/tools -q
pytest tests/integration -q
ruff check . && mypy src
```

另需人工确认：

- `geo_apply_dsl` 对语法错误返回**可定位**错误（行/列/片段），且不修改图形；
- `geo_to_dsl` 对一个含 8 个节点、2 条断言的构造图，产出可被解析器**重新解析成功**的 DSL（往返一致）；
- 题面草稿里出现"如图"、正确列出已知条件与求证目标，且**不臆造**图上不存在的点；
- 集成测试里，翻译故意写错时，整轮流程以"解析器拒绝"结束，**不会**留下半成品图形。

## 非目标

- 在仓库内内置任何模型调用（决策 D4：内核不含模型；翻译由外部 Agent 用 `prompts/` 里的模板完成）。
- 题面润色（自动生成的只是**草稿**，最终措辞由人定）。
- 评测用的中文题面语料（属于 `evals/` 的数据政策范畴）。
