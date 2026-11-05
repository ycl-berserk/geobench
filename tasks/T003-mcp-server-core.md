# T003 —— MCP 服务端核心：`geo_state` / `geo_construct` / `geo_evaluate`

**状态**：已实现（契约 16 项 + 端到端 8 项全绿）
**负责人**：Agent
**规格**：`docs/spec.md` §11（MCP 接口）、§14
**依赖**：T001
**涉及层**：服务端

## 目标

内核可以被 MCP 客户端驱动。这三个工具足以让 Agent 从零搭出一个图形并读回其精确状态——这是后续一切的前提。

## 交付物

- `src/geobench/server.py` —— MCP 服务端（stdio 传输），`geobench-mcp` 命令的入口。
- `src/geobench/tools/spec.py` —— **工具契约表**（工具名、输入字段、输出说明）。
- `src/geobench/tools/models.py` —— 请求/响应模型（pydantic），响应一律带 `status`。
- `src/geobench/tools/state.py`、`construct.py`、`evaluate.py` —— 一个工具一个模块。
- `src/geobench/tools/errors.py` —— 内核异常 → 结构化错误对象的**唯一**映射。
- `src/geobench/errors.py` —— 类型化错误：`ArgumentCountError` / `ArgumentTypeError` / `UnknownNodeError` / `DegenerateError` / `AmbiguousIntersectionError`。
- `src/geobench/evaluate.py` —— 摆放层有限性检查（退化构型在这里才看得见）。
- `tests/contract/test_mcp_contract.py` —— 断言线上工具清单与 schema 与 spec §11.1 一致。
- `tests/integration/test_client_session.py` —— 通过真实 MCP 客户端会话（独立进程 + stdio）驱动服务端。

## 工具契约（spec §11.1 的前三个）

| 工具 | 输入 | 输出 |
|---|---|---|
| `geo_state` | `{ figure_id? }` | 构造图、校验摘要、退化报告占位 |
| `geo_construct` | `{ ops: [{ id?, op, args }], figure_id?, mode: "apply"\|"dry-run" }` | 新建/更新/删除的 id、逐算子状态、精确错误 |
| `geo_evaluate` | `{ expr, figure_id? }` | 精确值 + 显示近似值 |

`expr` 支持 `Angle(B,A,C)`、`Distance(A,B)`、`Area(A,B,C)`。

## 三态响应

每个响应都带 `status`：

| status | 含义 | Agent 该做什么 |
|---|---|---|
| `ok` | 请求被理解且完整执行 | 继续 |
| `error` | 请求错了（未知 id、参数不对、表达式不认识） | **改请求** |
| `degraded` | 请求没错，但几何算不出来（退化构型） | 读 `warnings`/`errors` 里的原因 |

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

## 失败记录

见 [`T003-mcp-server-core.failures.md`](T003-mcp-server-core.failures.md)。这一批的失败集中在**"退化"到底意味着什么**：符号层面看三点永远不共线，只有摆放到一起才知道。

## 非目标

- `geo_verify`、`geo_solve`、`geo_variants`、`geo_check_degenerate`、`geo_render`、`geo_apply_dsl`、`geo_to_dsl`（后续任务；前七个工具名已列在 `tools/spec.py` 的 `PENDING_TOOLS` 里，契约测试保证"已实现 + 待实现 = 文档承诺的十个"）。
- **服务端内不得调用任何模型**（决策 D4：内核不含模型）。
- 退化检测器的完整目录（spec §7 的九条）——那是 T013；本任务只做到"能发现求值不出的构型"。
- 认证与多用户状态（v1 是本地单用户）。
