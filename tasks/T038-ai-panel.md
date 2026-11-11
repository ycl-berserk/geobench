# T038 —— 应用内 AI 面板（NL→DSL）

**状态**：已实现
**负责人**：Agent
**规格**：[`docs/ai-workflow.md`](../docs/ai-workflow.md) §10；[`docs/plan.md`](../docs/plan.md) M-E
**涉及层**：服务端 · 应用

## 目标

让用户在应用里用一句话说要什么图，模型写出作图代码，画板把它画出来。

## 最重要的一条

**模型负责翻译，解析器负责拒绝**（`docs/ai-workflow.md` §10）。

模型永远不碰内核：它只输出文本。解析器要么接受这段文本为一张图，要么拒绝，
并说清楚第几行、为什么。出来的图照样由同一批判定器检查。

所以：**模型说错东西的后果是"一段代码被拒绝"，不是"一张错的图"**。

## 做法

- `geobench/ai.py`（服务端层）
  - `Provider` 协议：谁都能接
  - `OpenAICompatibleProvider`：OpenAI 兼容的 chat API —— 一个 HTTP 调用，
    兼容 MiniMax / DeepSeek / 通义 / 本地 Ollama；key 走环境变量
    （`GEOBENCH_AI_MODEL` / `GEOBENCH_AI_API_KEY` / `GEOBENCH_AI_BASE_URL`）
  - `propose()`：问模型 → 解析 → 成图或拒绝。**解析器的意见会回给模型一次**
    （"第 3 行：点的坐标应该是两个数"），第二次还不行就拒绝。
  - 命令清单由命令表生成 → 模型不可能用一个不存在的命令。
- `prompts/nl-to-dsl.md`：提示词模板，命令清单是填进去的。
- `app/ai_panel.py`：面板。请求框、结果框、状态行；
  **拒绝时把原因摆在屏幕上**（拒绝就是诚实的答案，藏起来只会把问题挪到更不显眼的地方）。
  模型调用在**后台线程**（屏幕永远不等）。
- 工具栏上的「AI 作图」。

## 交付物

- `src/geobench/ai.py`、`src/geobench/app/ai_panel.py`、`prompts/nl-to-dsl.md`
- 测试 `tests/app/test_ai.py`（8 个用例，**全部离线** —— CI 不碰网络）

## 验收标准

```bash
pytest tests/app/test_ai.py -q
pytest -q
ruff check . && mypy src
```

## 已知限制

- 「在画板上作图」是**整图替换**（可撤销）。增量合并留待以后。
- 只有 OpenAI 兼容协议；接别的协议要另写一个 `Provider`。
