# geobench

**面向竞赛级平面几何命题的确定性几何内核 + Agent 接口（MCP）。**

> **状态：pre-alpha（立项阶段）**。内核尚未实现。实现的契约在 [`docs/spec.md`](docs/spec.md)，实现的生产方式在 [`docs/ai-workflow.md`](docs/ai-workflow.md)，决策记录在 [`docs/decisions.md`](docs/decisions.md)。
>
> English version: [README.en.md](README.en.md)

---

## 要解决的问题

手写一道竞赛平面几何题，实际要做六件事：

1. 构思一个**看起来像竞赛图**的构型；
2. 把它钉在**精确坐标**上（不是随手画）；
3. 证明所设关系对自由点的**任意合法取值**都成立；
4. 证明**不发生退化**（点重合、平行无交点、分母为零）；
5. 按排版规范把图重画一遍；
6. 导出成题目（题面 + 图 + 答案）。

第 3、4 步是**静默失败**的重灾区：一道"看着对"的题可能根本不成立，或者在某个特殊位置就塌了。第 1、5、6 步是纯体力活。

`geobench` 用确定性内核自动化 2–4，用 MCP 把内核暴露给任意 LLM 客户端，用符合竞赛排版规范的导出覆盖 5–6。

## 现状：研究侧已经做完，工具侧还空着

| | |
|---|---|
| **研究** | AlphaGeometry（DeepMind, 2024）、TongGeometry（通矩模型，BIGAI + 北大，《自然·机器智能》2026）、GeoGen、FormalGeo / FGeo-Parser、GeoLoom、Math-VR（港大 + 美团）。这些工作证明了"几何推理可自动化"，但产出的是**数据集和论文**。 |
| **通用工具** | GeoGebra、Desmos、Sketchpad、Cabri。强大、通用，但**不以出题为中心**，数值也不是精确的。 |
| **AI 出题产品** | 以文字题/练习题为主，产出**文本**，而不是**精确的几何构造**。 |
| **geobench** | 最后一公里：精确内核 + Agent 接口 + 可直接进卷排版的导出 + 一个衡量"有效性"而非"观感"的 benchmark。 |

**明确不做**：训练几何模型（国家队的事）、通用动态几何、立体几何（v2）、学生端"解题 App"。

## 架构一页纸

```
   自然语言（人手写 / AI 翻译）
        │  → 中文几何 DSL（§12，确定性子集）
        ▼
  ┌──────────────────────────────────────────────┐
  │ geobench 内核（Python · SymPy）               │
  │  DSL 解析 → 构造图 → 精确坐标                 │
  │  判定器 → proved / refuted / supported / …    │
  │  退化检测                                    │
  └──────────────────────────────────────────────┘
        │  MCP（stdio / HTTP）暴露给任意 Agent
        ▼
   Claude Code / Cursor / opencode / …
        │
        ▼
  渲染（SVG · TikZ · PNG）+ 题库文件（JSON）
```

三条不变量，按重要性排序：

1. **内核负责判定，模型只负责提议。** LLM 可以提构造（写 DSL），但"某关系成立"只能由内核断言，且每个结论都带证据。
2. **内核里没有浮点数。** 坐标是精确符号表达式，近似值只出现在渲染边界。
3. **每个算子都要对拍。** 上线前必须与独立实现（SymPy / GeoGebra）交叉验证。

## 两条输入通道

| 通道 | 路径 | 适用 |
|---|---|---|
| **手绘 / 交互** | 直接拖点、点选工具 → 构造图 | 已有想法、要微调构型、要"试一下" |
| **text2graph** | 自然语言 →（AI 或人工）→ DSL → 构造图 | 从零起题、把题面翻译成图、Agent 批量出题 |

两条通道汇入**同一个构造图**，此后的一切（验证、退化检测、渲染、出题）完全一致。DSL 是确定性子集：覆盖常用构造的绝大部分，AI 只负责把自由中文翻译进这个子集，翻译结果必须过解析器校验。

## 仓库结构

```
docs/spec.md          契约：数据模型、DSL、算子、判定器、MCP schema、题库格式、评测
docs/decisions.md     决策记录 D1–D10，含理由、备选、结论
docs/ai-workflow.md   实现由 Agent 生产的过程与门禁
tasks/                任务制：每个任务一份，验收标准必须机器可判
prompts/              驱动实现的 prompt 模板
evals/                benchmark 定义、指标、数据来源政策
src/geobench/         内核与服务端（尚未开始）
```

## Benchmark

衡量的是**有效性**，不是好不好看。定义冻结在 [`evals/README.md`](evals/README.md)。

| 指标 | 定义 | 结果 |
|---|---|---|
| `construct_success` | 构造无错误完成的比例 | 待测 |
| `oracle_agreement` | 与独立实现的坐标一致率 | 待测 |
| `verify_precision` | `proved` 结论在对抗性重采样后仍成立的比例 | 待测 |
| `degenerate_rate` | 被判定退化的构型比例 | 待测 |
| `problem_validity` | 自动生成的题中，目标可证且不退化的比例 | 待测 |
| `variant_diversity` | 同族变体之间的差异度 | 待测 |

## 复现

```bash
git clone https://github.com/ycl-berserk/geobench.git
cd geobench
python -m venv .venv && . .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q                 # unit + oracle + property + degeneracy 套件
```

立项阶段测试套件尚未存在；以上命令即实现必须满足的契约。

## 路线图

任务流推进（不设日期，见 [`tasks/`](tasks/README.md)）：

- [ ] **M0 立项**：spec、决策、流程、任务格式（当前）
- [ ] **M1 内核骨架**：构造图、精确算术、算子注册表
- [ ] **M2 对拍框架**：算子与 SymPy / GeoGebra 交叉验证
- [ ] **M3 判定器**：共线 / 垂直 / 共圆 / 等长 / 中点 / 角平分 / 相切 / 共点
- [ ] **M4 MCP 服务端**：八工具 + 算子/判定器目录资源
- [ ] **M5 DSL**：中文几何 DSL 语法、递归下降解析器、DSL↔构造图
- [ ] **M6 渲染**：SVG + TikZ 导出，竞赛图规范预设
- [ ] **M7 自动出题**：变体采样 + 约束求解接 LLM，端到端 demo
- [ ] **M8 Benchmark**：评测框架与公开报告

## 参与贡献

欢迎 issue 和 PR。实现遵循 [`docs/ai-workflow.md`](docs/ai-workflow.md)：工作以 `tasks/` 中的任务形式表达，验收标准机器可判；没有对拍验证的算子不得进入注册表。

## 许可

MIT（见 [`LICENSE`](LICENSE)）。题库文件各自记录来源与许可，见 [`evals/README.md`](evals/README.md)。
