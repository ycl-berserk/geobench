# T040 —— 退化构型不是反例

**状态**：已实现
**负责人**：Agent
**规格**：[`docs/spec.md`](../docs/spec.md) §6.1.1 · §7.1
**依赖**：T015 · T023
**涉及层**：判定器 · 算子 · 应用

## 问题

用户在**一道真实的竞赛题**上试了软件，结论是「没办法用」：

> 在锐角三角形 ABC 中，AB < AC，设 O 为外心，H 为垂心。D 为边 BC 的中点，
> 过 D 作 BC 的垂线，与直线 AH 交于点 P。设 E 为直线 AB 上一点，满足 DE ∥ AC，
> 设 F 为直线 AC 上一点，满足 DF ∥ AB。证明：P、E、F 三点共线。

软件给出的结论是**「不成立（refuted）」**，还附了一个反例。

## 两件事，一件是题面的，一件是内核的

### 一、题面本身：P 不存在

过 D 作 BC 的垂线，就是 **BC 的垂直平分线**；而 **AH 是 A 点的高**，也垂直于 BC。
于是这两条线**平行**，永远不相交。

`AB < AC` 恰恰保证它们是**两条不同的线** —— 这正是 P 不存在的原因。

内核自己就能证明这件事：

```
平行(d, ah)   -> proved
垂直(ah, bc)  -> proved
```

### 二、内核的毛病：退化构型被当成了反例（**真 bug**）

P 不存在 ⇒ 交点算子除以了一个**恒为零**的行列式 ⇒ 表达式里留下 0/0。

判定器原来的写法是「采样值 `!= 0` ⇒ 反例」，而：

- `nan != 0` 是 `True`；
- `zoo != 0` 是 `True`；
- 带自由符号的残留也「不等于 0」。

于是 **0/0 被当成了反例**，判定器对一个**没人反驳成功过的真命题**说出了「不成立」。

这违反了本项目自己的规则（spec §6.1）：**反例必须是合法构型**。

## 做法

### 判定器（`src/geobench/judges.py`）

- 新增 `_is_admissible(value)`：只有**有限实数**才算数。`nan` / `zoo` / `∞` /
  复数 / 仍带自由符号的表达式，**一律不是反例**。
- 采样时跳过退化摆放，并且**数清楚**有几个摆放是合法的。
- 全部采样都退化 ⇒ `undecided`（除非表达式恒等于 0，那才是 `proved`）。
- `instance` 作用域：先用**精确**的条件（算子公布的 `must_be_nonzero`）
  问一遍「这些对象在这个摆放下有没有值」；没有值 ⇒ `undecided`。
  这个检查是**精确**的（条件是符号表达式，摆放是有理数），不碰数值路径，
  因此判定结论与数值路径跑没跑过无关（契约测试盯着这条）。

### 算子（`src/geobench/operators.py`）

- `op_intersect_lines` 公布 `must_be_nonzero: {"parallel_lines": det}` ——
  算子工作在符号上，看不见这一次的摆放，所以它**公布**条件而不是自己检查。
- 两条直线**恒**平行时（由别的构造造成，不是这一张图画歪了），
  交点**根本没有值**，算子直接说「没有值」并给出理由。

### 代数层（`src/geobench/field.py`）

- `zero_status(value)`：**有理函数**的零判定是一次**判定**而不是一次搜索
  （「分子是不是零多项式」），所以又快又是终局的 —— 实测 2–12 ms。
- `has_zero_divisor(value)`：表达式里有没有除以恒为零的东西。
- `simplify_to_zero` 加了守卫：**分母恒为零的表达式不是零表达式**。
  没有这条，0/0 会被化简成 0 —— 一个毫无意义的关系会被「证明」。

### 求值层（`src/geobench/evaluate.py`）

- 算子可以声明「我什么也造不出来」（`no_value`），理由会被记下来，
  屏幕因此能说清楚**为什么**没有这个对象。

### 界面（`src/geobench/app/window.py`）

- 「没有值」的理由有中文对照表：两条直线平行，没有交点 / 判别式为零（退化）……
- 构造完立刻在状态栏说：「P 没有值：两条直线平行，没有交点」。
- 判定面板说「**无法判定（undecided）**」，证据是
  「对象 P 没有值：两条直线平行，没有交点」。

## 交付物

- `src/geobench/judges.py`、`src/geobench/field.py`、`src/geobench/operators.py`、
  `src/geobench/evaluate.py`、`src/geobench/numeric.py`、`src/geobench/model.py`
- `src/geobench/app/window.py`
- 测试 `tests/unit/test_degenerate_relations.py`（11 个）、
  `tests/app/test_degenerate.py`（3 个）
  —— **用户那道题就是夹具**

## 验收标准

```bash
pytest tests/unit/test_degenerate_relations.py tests/app/test_degenerate.py -q
pytest -q
ruff check . && mypy src
```

## 顺带修的

- `simplify_to_zero` 之前会把「分母恒为零」的表达式判成零；
- 证据栏的「= 0」是写死的，看不到实际值；
- `must_be_nonzero` / `must_be_zero` 两个字面量散在三个文件里，
  现在是 `model.py` 里的两个常量。

## 已知限制

- 用户那道题**本身**是错的：P 不存在。软件能指出这一点，
  但**猜不出**题目原本想说的是什么 —— 那要问人（见下）。
- 退化检测器（spec §7 那九条）仍然只落地了一部分。
