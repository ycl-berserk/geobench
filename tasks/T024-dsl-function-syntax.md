# T024 —— DSL 改函数式 + GeoGebra 中文命令名

**状态**：已实现
**负责人**：Agent
**规格**：[`docs/dsl-spec.md`](../docs/dsl-spec.md)；决策 D17
**依赖**：T004、T025
**涉及层**：DSL

## 目标

让老师**在 GeoGebra 里怎么打，这里就怎么打**。

句子式（`BC 上 A 的垂足`）废弃，改成函数式：

```
M = 中点(A,B)
```

## 交付物

- `src/geobench/commands.py` —— **命令表**（T025）：GeoGebra 中文名 / 英文名 → 我们的算子或判定器，唯一真源。
- `src/geobench/dsl/lexer.py` —— 中文**整词**切分（一整串汉字是一个词），只把 `点` `断言` 当关键字。
- `src/geobench/dsl/parser.py` —— 重写：函数式语法 + **按参数消解重载**。
- `src/geobench/dsl/generate.py` —— 反向：构造图 → DSL（用中文命令名）。
- `tests/unit/dsl/test_parser.py` —— 重写（20 项）。
- `docs/dsl-spec.md` —— 重写。

## 关键做法

**中文名与英文名都认。** GeoGebra 自己的输入栏在任何语言下都认英文 —— 老师可能打 `Midpoint(A,B)`。两种名字指向同一条命令，测试里专门断言"中英文说的是同一件事"。

**重载由参数决定。** `交点` 有三种（两直线 / 直线与圆 / 两圆），`圆` 有两种。解析器按**参数的个数与类型**挑，挑不出来就报错。关系这一侧没有算子可查，所以命令表里给每条关系补了 `arg_kinds` —— `垂直` 既是"两线垂直"（两直线）也是"这个点垂直落在这条线上"（点 + 线），靠参数区分。

**线段可以直接写。** `断言 相等(AB,AC)` 是卷面的写法；判定器要的是四个点，解析器把线段拆开。

**选择器存规范值。** `另一交点` 写进构造图的是 `other`，不是中文词 —— 中文是**人怎么写**，规范值是**算子看到什么**。

## 验收标准

```bash
pytest tests/unit/dsl -q
pytest tests/property -q
ruff check . && mypy src
```

## 失败记录

见 [`T024-dsl-function-syntax.failures.md`](T024-dsl-function-syntax.failures.md)。
