# T004 —— 中文几何 DSL：语法、递归下降解析器、DSL ↔ 构造图

**状态**：提案
**负责人**：Agent
**规格**：`docs/spec.md` §9（中文几何 DSL）
**依赖**：T001
**涉及层**：DSL

## 目标

"文字 → 图"的标准化层落地：**DSL → 构造图完全确定性**，毫秒级、离线、零 API 成本、可逐条单测。解析失败必须精确报错，不许猜测。

这一层是双通道设计的支点（决策 D7）：手绘通道产出构造图，文字通道也产出构造图，此后一切一致。

## 交付物

- `docs/dsl-spec.md` —— DSL 语法定稿：词法（关键字、记号 `⊥ ∥ ∩ ⊙ △ ≅ ∽`、数字、标识符）、语法（行式语句、构造子句、断言、约束）、错误定位约定；含 §9.3 映射表的完整版与**明确的未覆盖清单**。
- `src/geobench/dsl/lexer.py` —— 词法分析，产出带位置（行/列/跨度）的 token 流；全角标点与空白容错。
- `src/geobench/dsl/parser.py` —— 递归下降解析器；构造子句 → 算子调用；产出构造图。
- `src/geobench/dsl/errors.py` —— `DSLParseError(line, col, span, message)`。
- `src/geobench/dsl/generate.py` —— 构造图 → DSL（`geo_to_dsl` 的内核侧实现）。
- `tests/unit/dsl/test_lexer.py`、`test_parser.py`、`test_roundtrip.py`。
- `tests/property/test_dsl_roundtrip.py` —— 构造图 → DSL → 构造图 的**等价性**属性测试。

## 验收标准

```bash
pytest tests/unit/dsl -q
pytest tests/property -q
ruff check . && mypy src
```

另需人工确认：

- 解析 `spec.md` §9.2 的示例 DSL，产出的构造图与手写等价构造图逐字节相同；
- 未识别的构造子句（如"作 P 关于 AB 的对称点后再旋转 30 度"）**报错**并给出 `line`/`col`，不被忽略、不被猜测；
- `DSLParsError` 的 `span` 覆盖出错的那一段文本；
- 往返测试：随机生成的小构造图 → DSL → 解析 → 构造图，节点集合与依赖关系一致（允许 id 重命名）；
- **同一份 DSL 在原生 Python 与 Pyodide 下产出逐字节相同的构造图**（这条在 D10 的浏览器通道可用后再验一次，先在 Python 侧固定）。

## 非目标

- 自然语言理解（那是 T005，且由外部模型完成）。
- 题面自然语言生成（T005）。
- DSL 的自举/DSL→DSL 变换。
