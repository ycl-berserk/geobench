# T001 —— 内核骨架：构造图、精确数域、算子注册表

**状态**：已实现（本地门禁全绿：`ruff` / `mypy --strict` / `pytest` 34 passed；待 CI 复核）
**负责人**：Agent
**规格**：`docs/spec.md` §3（数据模型）、§4（精确算术）、§5.1（注册表契约）
**依赖**：—
**涉及层**：模型 / 基础设施

## 目标

内核能加载、修改、序列化构造图，所有几何量以精确表达式持有，算子以统一契约注册。这一层不做渲染、不做求解，但它是其余一切的地基。

## 交付物

- `src/geobench/field.py` —— `Field` 协议：`add`、`sub`、`mul`、`div`、`sqrt`、`simplify_to_zero(expr) -> bool`、`to_float(expr) -> float`；SymPy 实现；构造时拒绝浮点字面量。
- `src/geobench/model.py` —— `Node`、`Relation`、`Figure` 数据类；校验（id 唯一、DAG、参数个数、参数类型）；JSON 往返逐字节稳定。
- `src/geobench/registry.py` —— 算子注册表：`register`、`lookup`、`describe`（返回 §5.1 契约）、重复 id 拒绝、透传 `degenerate_when`。
- `src/geobench/state.py` —— 图形存储：应用/试运行操作、派生节点依赖重算、撤销历史（自实现快照列表，不依赖 `ggbApplet.undo`）。
- `tests/unit/test_model.py`、`tests/unit/test_field.py`、`tests/unit/test_registry.py`。
- `tests/no_float/test_no_float.py` —— AST 遍历 `src/geobench`，除 `to_float` 与展示层外出现浮点字面量即失败。

## 验收标准

```bash
pytest tests/unit/test_model.py tests/unit/test_field.py tests/unit/test_registry.py -q
pytest tests/no_float -q
ruff check . && mypy src
python -c "from geobench.model import Figure; f=Figure.from_json(Figure.example().to_json()); assert f.to_json()==Figure.example().to_json()"
```

另需人工确认：

- 插入参数个数与算子契约不符的节点时，错误信息里带算子名与期望个数；
- 成环依赖被拒绝，错误信息里带环路径；
- `simplify_to_zero` 对 `x - x` 与 `sin(x)**2 + cos(x)**2 - 1` 返回 `True`，对 `x - 1` 返回 `False`。

## 非目标

- 除测试所需外不实现任何算子（算子目录由 T006 负责）。
- 渲染、求解、判定、MCP。
- 性能优化。
