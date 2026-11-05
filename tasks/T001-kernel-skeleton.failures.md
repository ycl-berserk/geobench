# T001 失败记录

按 `docs/ai-workflow.md` §6：**被门禁拦下的产出必须留档，不许删除。** 这份文件是本仓库第一份失败记录，也是"AI 产出需要门禁"的第一次实证。

---

### F1 — 2026-11-05 · mypy strict：sympy 无类型存根，18 处报错

- **任务**：T001
- **症状**：`mypy src` 报 `Skipping analyzing "sympy": module is installed, but missing library stubs or py.typed marker`，随后 17 处派生报错。
- **根因**：sympy 不带 `py.typed`，strict 模式下视为 `Any`，凡是引用 sympy 类型的签名全部失配。
- **修法**：在 `pyproject.toml` 加 `[[tool.mypy.overrides]] module = ["sympy", "sympy.*"] ignore_missing_imports = true`。
- **本该拦住它的门禁**：`types`（本任务就是被它拦下的）。
- **动作**：mypy 门禁保留在 CI；同时记下：sympy 的类型信息是缺失的，这意味着**内核的类型检查对 sympy 内部是失效的**，所以算子的正确性必须靠对拍与属性测试兜底，不能只靠 mypy。

### F2 — 2026-11-05 · mypy：`ExprLike` 被当成变量而非类型别名

- **症状**：`Variable "geobench.field.ExprLike" is not valid as a type`，出现在所有使用该别名的签名上。
- **根因**：类型别名用 `=` 定义后，mypy 需要显式 `TypeAlias` 标注才能把它当别名处理。
- **修法**：`ExprLike: TypeAlias = Expr | int | sp.Rational`。
- **本该拦住它的门禁**：`types`。
- **动作**：无后续动作（一次性修正）。

### F3 — 2026-11-05 · mypy：`sp.Rational` 分支不可达

- **症状**：`Statement is unreachable`。
- **根因**：`sp.Rational` 是 `Expr` 的子类，先判 `Expr` 之后该分支永远进不去。
- **修法**：删除 `sp.Rational` 分支——它已被 `Expr` 分支覆盖。
- **本该拦住它的门禁**：`types`。
- **动作**：无后续动作。

### F4 — 2026-11-05 · ruff：6 项风格/正确性告警

- **症状**：`__all__` 未排序、`typing.Iterable`/`typing.Callable` 应从 `collections.abc` 导入、`RUF005` 列表拼接、`B905` `zip()` 缺 `strict=`、一处 import 顺序。
- **根因**：初版代码未按仓库既定的 ruff 规则集书写。
- **修法**：4 项用 `ruff check --fix` 自动修；`RUF005` 改 `[*stack[start:], nxt]`；`B905` 显式写 `strict=True`（此处长度已在前面校验过，用 `strict=True` 是有意的）。
- **本该拦住它的门禁**：`lint`。
- **动作**：无后续动作。

### F5 — 2026-11-05 · 测试里用了 `__import__` 绕过导入顺序

- **症状**：`tests/unit/test_model.py` 里出现 `__import__("geobench.model", fromlist=["Relation"]).Relation(...)`。
- **根因**：写测试时刻意避开顶部导入，属图省事的坏习惯。
- **修法**：改为顶部正常 `from geobench.model import Figure, Node, Relation`。
- **本该拦住它的门禁**：`lint`（`I001` 类问题会在 CI 暴露，但当时是先被 ruff 的其它问题盖住）。
- **动作**：无后续动作；但记一条原则：**测试文件里不允许出现动态导入**。
