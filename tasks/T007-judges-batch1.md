# T007 —— 第一批判定器

**状态**：已实现（16 个测试通过）
**负责人**：Agent
**规格**：`docs/spec.md` §6（判定器目录、作用域与结论语义）
**依赖**：T006
**涉及层**：判定器

## 目标

让内核能回答"这条关系成立吗"，并且**分清两种成立**：对任意摆放成立（定理），还是只在这一张图上成立（实例）。这是整个项目存在意义的落点。

## 交付物

- `src/geobench/judges.py` —— 判定器目录与判定逻辑：
  `collinear`、`perpendicular`、`point_perpendicular`、`concyclic`、`equal_length`、
  `midpoint_of`、`angle_bisector`、`tangent_to`、`concurrency`
- `tests/unit/test_judges.py` —— 16 个测试，含每个判定器的**反例路径**。

## 验收标准

```bash
pytest tests/unit/test_judges.py -q
ruff check . && mypy src
```

另需人工确认：

- 每个判定器都能**证伪**一条假关系（否则它不是判定器）；
- `identity` 作用域下，"三个自由点共线"判 `refuted` 而不是 `proved`；
- `instance` 作用域下，矩形四点共圆判 `proved`；
- 真恒等式（如"两垂足与 A、B 共圆"）判 `proved`；
- `supported` 绝不与 `proved` 混淆。

## 失败记录

见 [`T007-judges-batch1.failures.md`](T007-judges-batch1.failures.md)。

## 非目标

- 退化检测器（T013）。
- 约束求解与反例搜索（T009）。
