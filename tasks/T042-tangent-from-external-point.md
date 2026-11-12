# T042 —— 从圆外一点作切线：一条命令，两种情形

**状态**：已实现
**负责人**：Agent
**规格**：[`docs/spec.md`](../docs/spec.md) §7.2
**依赖**：T027（切线原本只支持圆上一点）、T041（评测集）
**涉及层**：内核 · 服务端 · 应用

## 问题

T041 的评测集撞出来的：模型很自然地写

```
点 O(0,0) A(2,0) P(4,0)
c = 圆(O, A)
t = 切线(P, c)
```

—— 这是「过圆外一点作切线」，**竞赛图的常见构图**。而内核的 `切线` 原本是
「圆上那一点处的切线」，P 必须在圆上；于是这张图**每次都撞墙**，
规范里还写着「从圆外一点作切线本软件做不了」。

用户的裁决：**两条切线里任意一条都行**，保留一条即可，不用纠结。

## 做法

`切线(P, c)` 现在有三种情形，**一个公式**：

| P 在哪 | 结果 |
|---|---|
| 圆上 | 该点处的切线 |
| 圆外 | 两条切线中的**一条**（约定：切点在射线 O→P 左侧） |
| 圆内 | **没有切线** —— 对象没有值（D19），图继续活着 |

公式（圆心 C、`r²`、`u = P - C`、`d² = u·u`）：

```
切点  T = C + (r²·u + r·√(d² - r²)·u⊥) / d²
切线  过 T 且垂直于 CT
```

P 在圆上时根号为零，T 缩到 P —— 正是原来那条切线，也就是 P 的**极线**。

「取哪一条」是**约定**，不是几何事实，所以对拍时 oracle（SymPy 的
`Circle.tangent_lines`）返回**两条**，harness 检查内核那条**是其中之一**。

### 新增第三类条件：`must_be_nonnegative`

「点不得在圆内」不是等式，是**序**：`d² - r² ≥ 0`。原来的两类条件
（不得为零 / 必须为零）说不清它，于是加了第三类。

数值路径在摆放已知时裁定它；精确路径（判定的实例作用域）也会查它，
所以「这张图上这个对象没有值」是精确判断，不靠数值路径。

## 顺带修掉的两个真问题

1. **判定的数值零判定是结构比较**（`field.py`）：`simplify_to_zero` 遇到
   数字直接 `expr == 0`。切线带根号，代入后是两个含根号的式子相减 ——
   **数学上是 0，结构上不是**，于是被误判成 `refuted`。现在数字也走
   根号感知的约简（`radsimp` / `simplify` / `equals`）。
   这个 bug 在切线之前一直潜伏着：任何**值带根号**的关系在实例作用域下
   都会被误判。
2. **对拍夹具的随机流是共用的**（`scripts/gen_fixtures.py`）：改一个算子的
   夹具，会把**后面所有算子**的夹具全部重洗。这次重洗就翻出一个潜伏的
   坏夹具（`sector.three_points` 把一个退化的构型标成了「有值」）。
   现在**每个算子一条独立的流**（`random.Random(f"{SEED}-{op_id}")`），
   一个算子的改动只影响它自己。

## 交付物

- `src/geobench/operators.py`：`op_tangent` 重写 + `_sign_of`
- `src/geobench/model.py`：`CONDITION_NONNEGATIVE`
- `src/geobench/numeric.py`：三类条件的编译与裁定
- `src/geobench/judges.py`：实例作用域查 `must_be_nonnegative`
- `src/geobench/field.py`：数字的零判定改成根号感知
- `src/geobench/commands.py`：命令说明改成「过点作圆的切线」
- `tests/oracle/oracles.py`：oracle 改为 SymPy 的 `Circle.tangent_lines`
  （返回两条，harness 查成员）
- `tests/oracle/harness.py`：线的集合比较；**「没有值」也算拒绝**
- `scripts/gen_fixtures.py`：切线夹具加「圆外一点」与「圆内一点」；
  每个算子独立的随机流
- 测试：`tests/unit/test_tangent.py`（5）、`tests/unit/test_conditions.py`（4）
- 规范：`prompts/figure-standards.md`、`prompts/figure-examples.md`
- 评测集：新增「圆外一点的切线」，真模型 **9/9**

## 验收标准

```bash
pytest tests/oracle tests/unit/test_tangent.py tests/unit/test_conditions.py -q
pytest -q
ruff check . && mypy src
python scripts/eval_ai.py        # 手动：要网络
```

## 已知限制

- **只给一条切线**。GeoGebra 给两条；本题的裁决是「任意一条都行」。
  要另一条，取镜像。
- **约定是「切点在射线 O→P 左侧」**，文档写了，但界面上不显示是哪一条 ——
  老师看到的就是一条切线，一般也不需要知道。
- `must_be_zero` 这个条件种类**目前没有算子发布**（切线原来用它）；
  词汇表保留、数值路径保留、单测覆盖（`tests/unit/test_conditions.py`），
  留给以后需要「某表达式必须为零」的算子。
