# T003 失败记录

按 `docs/ai-workflow.md` §6 留档。

---

### F1 — 2026-11-06 · MCP SDK 2.x 把 `FastMCP` 改名成了 `MCPServer`

- **症状**：`from mcp.server.fastmcp import FastMCP` 抛 `ModuleNotFoundError`。
- **根因**：装的是 `mcp` 2.3.0，2.x 里 `FastMCP` 改名为 `MCPServer`，并且 `Tool.inputSchema` 改成了 `input_schema`。
- **修法**：改用 `mcp.server.mcpserver.MCPServer`；读写 schema 时用 `input_schema` / `output_schema`。
- **本该拦住它的门禁**：`contract`（第一次导入就炸）。
- **动作**：**依赖升级要读迁移说明，不要照着旧记忆写**。`pyproject.toml` 里把 `mcp>=1.2` 收紧成 `mcp>=2.0`，免得有人装到 1.x。

### F2 — 2026-11-06 · 工具参数写成模型，schema 就被包了一层 `request`

- **症状**：生成的输入 schema 是 `{"properties": {"request": {"$ref": ...}}, "required": ["request"]}`——agent 得写 `{"request": {"figure_id": "f1"}}`。
- **根因**：SDK 从函数签名生成 schema；函数只有一个 Pydantic 模型参数时，模型就被当成**一个字段**。
- **修法**：工具函数用**扁平的关键字参数**（`figure_id: str | None = None`），模型只用于**响应**（响应才有结构化输出 schema）。输入 schema 因此是扁平的。
- **本该拦住它的门禁**：`contract`。
- **动作**：**schema 只能有一份**。输入 schema 由函数签名生成，输出 schema 由响应模型生成，谁都没有手写 JSON。

### F3 — 2026-11-06 · `float(text)` 用来判断"这是不是个字面量"

- **症状**：`model.py` 里用 `float(text)` 判断参数是数字字面量还是节点引用。
- **根因**：这是内核，而内核的规矩是"精确"（决策 D2）。用浮点解析器去问"这是不是个数"，等于把不允许的东西偷偷带进来；而且 `float("nan")`、`float("1e5")` 都会被当成数字。
- **修法**：改成纯字符判断——只接受普通十进制（可带正负号与小数点），`1e5` / `nan` / `inf` 一律不算字面量。
- **本该拦住它的门禁**：`unit`（`no_float` 只拦字面量，拦不住 `float()` 调用——**这条门禁有盲区，已记在 `docs/ai-workflow.md` §11.5**）。

### F4 — 2026-11-06 · 退化构型在符号层面根本看不出来

- **症状**：三点共线时 `point.circumcenter` 不报错，算出 `placement = ('2', 'zoo')`——一个画在无穷远处的点。
- **根因**：自由点是**符号**（`x_A`, `y_A`），所以三点共线的行列式**不是恒等于零**，只是在这个摆放下等于零。算子的 `if det == 0` 分支永远不会命中。
- **修法**：在**求值层**检查摆放的有限性：`zoo` / `nan` / `oo` 一律判为退化（`evaluate.py` 的 `_check_finite`）。
- **本该拦住它的门禁**：`integration`（"三点共线求外心应当报 degraded"）。
- **动作**：这是 D11 的直接后果：**符号化之后，"这个构型合法吗"就必须换一个问题来问**。符号问"是不是恒等式"，摆放问"是不是退化的"。

### F5 — 2026-11-06 · `degraded` 这个状态一开始无处安放

- **症状**：三类构造失败——参数写错、构型退化、图被改坏——本来都塞进同一个 `errors` 数组，agent 分不清"我该改请求"还是"我该接受现实"。
- **根因**：只设计了一种失败语义。
- **修法**：定下三态：`ok` / `error`（请求错了，改请求）/ `degraded`（请求没错，几何算不出来，读原因）。这写进了 `docs/spec.md` §11.3 与 D15。
- **本该拦住它的门禁**：`contract`（每个响应都必须带 `status`，且枚举值固定）。

### F6 — 2026-11-06 · 未知 id 的错误没有告诉 agent 合法 id 是哪些

- **症状**：算子报"unknown node id 'Q'"——agent 知道错了，但不知道该用哪个。
- **根因**：`state.py` 抛的是一句普通 `StateError`。
- **修法**：新增 `UnknownNodeError`，消息里带上**合法 id 列表**，并把它单列成结构化字段 `known_node_ids`。
- **本该拦住它的门禁**：`integration`（"错误中带该 id 与合法 id 列表"）。
- **动作**：**错误消息是给 agent 看的**。能自愈的错误要把自愈需要的信息一并给出。

### F7 — 2026-11-06 · 契约测试一开始只查了工具名

- **症状**：工具名对上了就算过。
- **根因**：契约测试最初只写了"名字集合相等"。
- **修法**：加上——每个工具的**输入字段集合与必填集合**必须与契约表一致；规格文档的输入列必须提到每个字段；每个响应必须有 `status` 且枚举值固定；已实现 + 待实现必须**恰好等于**文档承诺的十个工具。
- **本该拦住它的门禁**：`contract`。
- **动作**：**契约测试要能挡住"字段名改了但没人发现"**，否则它只是摆设。

### F8 — 2026-11-06 · `geo_evaluate` 的错误消息里有 id，结构化字段里却是空的

- **症状**：冒烟测试里 `Angle(B,A,Q)` 的响应，`message` 写着"unknown node id 'Q'; known node ids: A, B, C, M"，但 `node_id` 是 `null`、`known_node_ids` 是空数组。
- **根因**：`geo_evaluate` 自己定义了 `ExpressionError`（一个普通 `Exception`），没有走内核的错误体系，所以 `to_error_info` 认不出它，只能塞一条空结构。
- **修法**：`ExpressionError` 带上 `node_id` 与 `known_node_ids`，并给了一个 `to_error_info()` 方法——两个工具的错误结构就此一致。
- **本该拦住它的门禁**：`integration`（后来加的断言：未知 id 的错误必须带上合法 id 列表）。
- **动作**：**同一个概念只许有一种表达**。错误消息给人看，错误字段给机器看，两者必须同时完整，不能一个填了另一个空着。

### F9 — 2026-11-06 · `mcp>=1.2` 这个版本区间装得上、跑不起来

- **症状**：开发机上装的是 `mcp` 2.3.0，代码用的是 2.x 的 `MCPServer`。
- **根因**：`pyproject.toml` 写的是 `mcp>=1.2`，而 1.x 里根本没有 `mcp.server.mcpserver`——这个区间允许装出一个**必然 ImportError** 的环境。
- **修法**：收紧成 `mcp>=2.0`。
- **本该拦住它的门禁**：`contract`（装错版本会在导入时直接失败）。
- **动作**：**依赖的版本区间要按"实际用的 API"写，不是按"听说有这个东西"写**。下界应当是"用到的第一个 API 出现的版本"。
