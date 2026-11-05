# T003 —— MCP 服务端核心：`geo_state` / `geo_construct` / `geo_evaluate`

**状态**：提案
**负责人**：Agent
**规格**：`docs/spec.md` §11（MCP 接口）、§14
**依赖**：T001
**涉及层**：服务端

## 目标

内核可以被 MCP 客户端驱动。这三个工具足以让 Agent 从零搭出一个图形并读回其精确状态——这是后续一切的前提。

## 交付物

- `src/geobench/server.py` —— MCP 服务端，stdio 传输（streamable HTTP 留到后续任务），暴露 spec §11.1 的工具集。
- `src/geobench/tools/state.py`、`tools/construct.py`、`tools/evaluate.py` —— 一个工具一个模块。
- 工具 schema 由规格常量生成（单一真源，不在手写 JSON 里重复第二遍）。
- `src/geobench/errors.py` —— 类型化错误与可执行消息：未知节点 id、参数类型错、参数个数错、退化构型、交点序号歧义。
- `tests/contract/test_mcp_contract.py` —— 断言线上工具清单与 schema 与 spec §11.1 一致。
- `tests/integration/test_client_session.py` —— 通过真实 MCP 客户端会话驱动服务端。

## 验收标准

```bash
pytest tests/contract -q
pytest tests/integration -q
ruff check . && mypy src
```

另需人工确认：

- `geo_construct` 在 `dry-run` 模式下不改变图形（前后 `geo_state` 逐字节一致）；
- `args` 里出现未知节点 id 时返回 `status: "error"`，错误中带该 id 与合法 id 列表；
- `geo_evaluate` 求 `Angle(B,A,C)` 返回精确值与显示近似值；表达式含未知符号时**报错而不是猜**；
- 所有响应都是合法 JSON，且带 `status` ∈ {`ok`, `error`, `degraded`}。

## 非目标

- `geo_verify`、`geo_solve`、`geo_variants`、`geo_check_degenerate`、`geo_render`、`geo_apply_dsl`、`geo_to_dsl`（后续任务）。
- **服务端内不得调用任何模型**（决策 D4：内核不含模型）。
- 认证与多用户状态（v1 是本地单用户）。
