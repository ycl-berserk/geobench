# T004 —— 中文几何 DSL：语法、解析器、DSL ↔ 构造图

**状态**：已实现（20 个单元测试 + 2 个属性测试通过）
**负责人**：Agent
**规格**：[`docs/dsl-spec.md`](../docs/dsl-spec.md)（本文档的正本）、`docs/spec.md` §9
**依赖**：T001
**涉及层**：DSL

## 目标

给"文字 → 图"一个**受限但确定**的中间层：

```
自然语言 ──(AI 翻译 或 人工)──▶ DSL ──(确定性解析器)──▶ 构造图 ──(确定性内核)──▶ 判定 / 渲染
   不确定                            受限确定                        确定性
```

DSL → 构造图永远确定性：毫秒级、离线、零 API 成本、逐条可单测。AI 只负责翻译，且翻译结果必须过解析器校验。

## 交付物

- `docs/dsl-spec.md` —— 语法规格（记号、语句、构造子句 → 算子映射、解析器契约、**缺口清单**）。
- `src/geobench/dsl/lexer.py` —— 行式词法分析；中文关键字优先于标识符（Python 认为汉字是字母）。
- `src/geobench/dsl/parser.py` —— 递归下降解析器；错误带精确行列。
- `src/geobench/dsl/generate.py` —— 构造图 → DSL（`to_dsl`）与 DSL → 构造图（`apply_dsl`）。
- `src/geobench/dsl/errors.py` —— `DSLParseError(line, col, span, message)`。
- `tests/unit/dsl/test_parser.py` —— 20 个测试。
- `tests/property/test_dsl_roundtrip.py` —— 往返一致性（属性测试）。

## 语法（当前支持的子集）

```
点 A(0,0) B(6,0) C(2,4)
△ABC
⊙O = 过 A B C
D = BC 上 A 的垂足
M = AB 中点
I = △ABC 的内心
P = AD 与 ⊙O 的另一交点
断言 M A B 共线
断言 AB = AC
```

## 验收标准

```bash
pytest tests/unit/dsl -q
pytest tests/property -q
ruff check . && mypy src
```

另需人工确认：

- 未识别的子句**必须报错**并给出行列，不许静默忽略；
- 往返后节点集合与关系集合一致；
- 解析出的图形可以被内核求值、判定、渲染（见 `scripts/dsl_demo.py`）。

## 失败记录

见 [`T004-dsl-parser.failures.md`](T004-dsl-parser.failures.md)。这一批的失败集中在**中文与英文两种语言在同一个词法器里打架**，以及**"另一交点"这个语义本身比想象中难**。

## 非目标

- 立体几何、圆锥曲线、弧中点、切点、旁心、角平分线点。
- 自然语言理解（那是 T005，且由外部模型完成）。
- 自由点坐标的约束求解（那是 T009）。
