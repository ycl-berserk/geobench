# geobench —— 技术规格

**版本 0.2 · 状态：草案（proposed）· 本文档是实现的唯一真源。**

`tasks/` 下的每个任务都引用本文档的某一节。当本文档与实现冲突时，**以本文档为准，实现是错的**；若实现确实需要改变语义，**先改本文档，再改代码**。

术语约定：本文档中**中文为正文语言**，标识符（算子 id、判定器 id、工具名、字段名）一律使用英文小写下划线/点号风格，因为它们同时是 API 契约与 Agent 的调用对象。

---

## 1. 范围

### 1.1 v1 做什么

- **平面几何**（二维直角坐标系）。
- 确定性内核：按精确图元构造图形、判定几何关系、检测退化、渲染导出。
- **中文几何 DSL**及其确定性解析器（§9），作为"文字→图"的标准化中间层。
- MCP 服务端：把内核暴露给任意 MCP 客户端。
- 题库文件（题面 + 图 + 验证记录），导出 SVG / TikZ / PNG / LaTeX。
- 评测框架：衡量内核判定与自动出题的**有效性**。

### 1.2 v1 不做什么

| 不做 | 原因 | 何时再议 |
|---|---|---|
| 立体几何 | 3D 约束求解与空间共面/异面判定成本高一个量级，需要 CAD 内核而非自研 | v2，用 OpenCascade + three.js |
| 圆锥曲线 | 目标用户（初中/奥赛平面几何）不需要 | 若有人提需求则 v1.1 |
| 训练几何模型 | 国家队的事（BIGAI+北大、DeepMind），我们的杠杆在最后一公里 | 永不做 |
| 学生端"解题 App" | 不同产品、不同人群 | — |
| 可调数值容差 | 内核是精确的；容差只属于渲染层 | — |

### 1.3 目标用户

1. **竞赛学生与教练**（主）：出原创题、组题。
2. **初中几何教师**（次）："找一个满足这个关系的三角形" → 可编辑图形 → 打印讲义。

两者共同需要的是：**精确的图 + 不会退化的保证 + 能直接进卷的排版**。都不需要通用动态几何环境。

---

## 2. 术语

| 术语 | 含义 |
|---|---|
| **构造图**（construction graph） | 图形的序列化描述：节点（点/线/圆）、依赖边、待验关系 |
| **算子**（operator） | 确定性函数 `参数 → 节点`，如 `point.midpoint(A, B)` |
| **判定器**（judge） | 确定性函数 `参数 → 结论`，如 `collinear(A, B, C)` |
| **结论**（verdict） | `proved` / `refuted` / `supported` / `undecided`，附证据 |
| **退化**（degeneracy） | 构造中某部分无定义或塌缩的构型 |
| **变体**（variant） | 同一构造族（自由点不同取值）下的不同合法构型 |
| **题库文件**（problem file） | 一道题一个 JSON 文档，见 §12 |
| **对拍基准**（oracle） | 用于交叉验证算子的独立实现，见 §5.3 |
| **DSL** | 受限的中文几何描述语言，见 §9 |

---

## 3. 核心数据模型：构造图

### 3.1 结构

```jsonc
{
  "version": "1.0",
  "id": "fig_0001",
  "nodes": [
    { "id": "A", "kind": "point", "role": "free",
      "coords": ["0", "0"], "label": "A", "style": {} },

    { "id": "B", "kind": "point", "role": "free",
      "coords": ["4", "0"], "label": "B", "style": {} },

    { "id": "M", "kind": "point", "role": "derived",
      "op": "point.midpoint", "args": ["A", "B"], "label": "M", "style": {} },

    { "id": "l1", "kind": "line", "role": "derived",
      "op": "line.free", "args": ["A", "B"], "label": "AB", "style": {} },

    { "id": "c1", "kind": "circle", "role": "derived",
      "op": "circle.through", "args": ["A", "B", "C"], "label": "⊙O", "style": {} }
  ],
  "relations": [
    { "id": "r1", "kind": "collinear", "args": ["A", "M", "C"], "expected": true }
  ],
  "meta": { "tags": [], "source": "manual", "notes": "" }
}
```

**规则**

- `id` 在图内唯一、跨编辑稳定，所有工具调用都用它指代对象。
- `role: "free"` 的节点带精确坐标，是**唯一的变异来源**。`role: "derived"` 的节点带 `op` + `args`，**不允许**存与算子结果矛盾的坐标；坐标只是缓存，内核每次变更后重算。
- `coords` 是精确表达式的字符串形式（§4）。
- `relations` 是**待验断言**。内核从不假定其成立——这正是 `geo_verify` 要裁定的东西。`expected` 记录作者意图，用于回归测试和"假题"检测。
- 构造图是 **DAG**；插入成环依赖时以精确错误拒绝，并给出环路径。

### 3.2 图元类型

`point`、`line`、`segment`、`circle`（v1 仅此四种）。

| 类型 | 参数 |
|---|---|
| `point` | 精确 `(x, y)`；可附 `on: [节点 id]` 作为共线/共圆提示（仅提示，由判定器验证） |
| `line` | 精确隐式方程 `ax + by + c = 0`（要求 `a² + b² ≠ 0`） |
| `segment` | 两个端点（竞赛图里的"边"；直线是无限延伸的，图上通常要画的是线段） |
| `circle` | 精确圆心 + 精确**半径平方**，或精确隐式方程 `x² + y² + dx + ey + f = 0`（要求 `d² + e² - 4f > 0`） |

### 3.3 两套坐标：符号与摆放

**这是 v1 最重要的一次设计修正**（决策 D11）。自由点同时携带两套坐标：

| 字段 | 内容 | 谁用 |
|---|---|---|
| `coords` | **符号**表达式，自由点写作 `x_A` / `y_A` | 判定器：关系必须是恒等式，不能只是"这一张图恰好成立" |
| `placement` | **数值**精确值，如 `("0", "0")` | 渲染器、以及采样式反例搜索 |

派生节点的 `coords` 由算子算出的符号表达式给出，`placement` 是同一表达式在自由点摆放下的数值结果。

**为什么必须分开**：如果自由点只有数值，那么"三点共线"永远只能是"这张图上共线"，无法区分定理与巧合。只有当自由点是符号时，判定器问的才是"对**任意**摆放是否成立"——这正是竞赛命题需要的判断。

### 3.4 样式

样式不影响几何，只影响渲染：`visible`、`color`、`line_width`、`line_style`（`solid`/`dashed`/`dotted`）、`point_size`、`fill`、`label`、`label_pos`。竞赛规范预设见 §10.2。

---

## 4. 精确算术

- **精确是强制要求。** 所有坐标与判定计算使用精确符号表达式（`sympy` 的 `Rational`、代数根、符号和积）。
- **禁止隐式浮点。** 算子参数里出现浮点字面量是**硬错误**而非警告。近似值只在渲染边界由精确值导出。
- **数域自动提升。** 有理数 → 需要时自动升到含 `sqrt` 的代数数域，不存在"手动切浮点模式"。
- **只存半径平方。** `circle` 存 `r²`，`r` 为派生量，可能无理。这样下游表达式不会普遍带根号。
- **交点显式择一。** 交点同时返回精确解与被选中的数值根，**根的序号显式记录**，不把"选哪一个"藏起来。

### 4.1 化简预算

符号表达式在自由点变多时会长得很快：判定"四点共圆"的那个行列式已经到几千项。因此**化简必须有预算**：

- `Field.simplify_to_zero(expr)` 在表达式规模超过预算（默认 20000 ops）时**直接返回"未能证明"**，而不是无界地展开。
- 归约策略按代价从低到高：`together` → 取分子 → 按多项式判零 → `trigsimp`/`radsimp` → 小规模时才 `simplify`。
- **不使用 `Matrix.det()`**：sympy 的通用行列式会展开，而手写的余子式展开保持表达式因式分解，使 `together` 只需 0.1 秒就能处理同一问题。

超预算不是失败，而是交给 §6.2 的采样路径 —— 采样给出 `refuted`，采样全过而超预算则诚实地说 `supported`。**内核永远不会为了"看起来能用"而返回一个它没有证明的 `proved`。**

---

## 5. 算子目录

### 5.1 注册表契约

```jsonc
{
  "id": "point.midpoint",
  "kind": "point",
  "args": [{ "name": "a", "type": "point" }, { "name": "b", "type": "point" }],
  "exact": true,
  "returns": { "type": "point" },
  "degenerate_when": ["a == b"],
  "oracle": "sympy:segment_midpoint",
  "since": "v1"
}
```

`degenerate_when` 是契约的一部分：§7 的退化检测据此判断何时该报警。

### 5.2 v1 算子

**Tier A —— v1 必须实现（16 个）**

| 算子 | 参数 | 说明 |
|---|---|---|
| `point.free` | `(x, y)` 精确 | 唯一变异来源 |
| `line.free` | `(a, b)` 点 | |
| `circle.free` | `(center, r²)` | |
| `point.midpoint` | `(a, b)` | |
| `point.foot` | `(p, line)` | 垂足 |
| `point.intersect_lines` | `(l1, l2)` | 平行时退化 |
| `point.intersect_line_circle` | `(line, circle, index)` | `index ∈ {0,1}` |
| `point.intersect_circles` | `(c1, c2, index)` | 相切/相离/同心时退化 |
| `point.circumcenter` | `(a, b, c)` | 三点共线时退化 |
| `point.incenter` | `(a, b, c)` | |
| `point.orthocenter` | `(a, b, c)` | |
| `point.centroid` | `(a, b, c)` | |
| `point.angle_bisector_point` | `(a, b, c, side)` | 角平分线 ∩ `side` |
| `line.perpendicular_through` | `(p, line)` | |
| `line.parallel_through` | `(p, line)` | |
| `circle.through` | `(a, b, c)` | 三点共线时退化 |

**Tier B —— v1.1（18 个）**：`point.reflect`、`point.tangent_point`、`point.inverse`、`point.arc_midpoint`、`point.touchpoint`、`point.excenter`、`point.symmedian_point`、`point.nine_point_center`、`line.angle_bisector`、`line.perpendicular_bisector`、`line.median`、`line.altitude`、`line.tangent_at`、`circle.incircle`、`circle.circumcircle`、`point.projection`、`point.rotate`、`point.scale_from`。

**Tier C —— 不在 v1**：3D 算子、圆锥曲线算子、轨迹、作为一等公民的变换。

### 5.3 对拍要求

每个进入注册表的算子，**必须**先通过对拍：独立实现（SymPy 几何/符号例程、GeoGebra JS API、手工闭式解）在**固定的一组 ≥ 20 组构型**（含退化构型）上交叉验证，差集必须为空。对拍框架见 `tasks/T002`。**没有通过对拍的算子不得进注册表。**

---

## 6. 判定器目录

### 6.1 作用域与结论语义

判定有两个**作用域**，这决定了结论的含义：

| 作用域 | 问题 | 用途 |
|---|---|---|
| `identity` | 该关系对自由点的**任意**合法摆放都成立吗？ | 命题：结论必须是定理，不能是巧合 |
| `instance` | 该关系在**当前画出的这一张图**上成立吗？ | 审图：检查图形与题面是否自洽 |

| 结论 | 含义 | 必须附带的证据 |
|---|---|---|
| `proved` | 在该作用域下成立 | `identity`：表达式恒等于 0（化简后的表达式）；`instance`：代入摆放后为 0 |
| `refuted` | 在该作用域下不成立 | 一个具体的合法构型使其失败（精确坐标，即"见证"） |
| `supported` | 在所有采样构型中成立，但**未被证明** | 采样次数、采样方案、表达式规模 |
| `undecided` | 内核无法裁定 | 原因（不支持的算子、域膨胀、关系歧义） |

`supported` **绝不**被静默升级为 `proved`。

### 6.2 判定顺序：先采样，后符号

判定的执行顺序是**刻意的**（决策 D13）：

1. **先采样**（毫秒级）。在若干组随机有理数摆放上求值，任一次不为 0 ⇒ 直接 `refuted`，并给出见证。**反例即证明**，这一步是决定性的。
2. **再符号化简**（可能很慢）。只有通过了全部采样的关系，才值得付出化简代价。表达式恒等于 0 ⇒ `proved`。
3. 两步都没结论 ⇒ `supported`。

顺序反过来会让常见情况（判一条**假**关系）付出几秒的化简代价；反过来则只要几毫秒。实测：判定器测试从 64 秒降到 16 秒，且差异全部落在"真恒等式"那一条上。

### 6.2 v1 判定器（8 个）

| 判定器 | 参数 | 典型用途 |
|---|---|---|
| `collinear` | `(p1, p2, p3)` | Menelaus、Desargues |
| `perpendicular` | `(l1, l2)` 或 `(p, l)` | 正交性 |
| `concyclic` | `(p1, p2, p3, p4)` | Miquel、点的幂 |
| `equal_length` | `(seg1, seg2)` | 等腰、全等 |
| `midpoint_of` | `(m, a, b)` | 中线、平行四边形 |
| `angle_bisector` | `(p, a, b, c)` | 角平分线定理 |
| `tangent_to` | `(line, circle)` | 相切构造 |
| `concurrency` | `(l1, l2, l3)` | Ceva、根轴 |

**v1.1**：`parallel`、`equal_angle`、`similar`(AA)、`area_ratio`、`segment_ratio`、`power_equal`、`isosceles`、`right_angle`。

### 6.3 对称性要求

每个判定器必须同时提供**正例**（关系成立）与**反例**（关系不成立）两组测试。**无法对被篡改的图形给出 `refuted` 的判定器不可信，不得上线。**

---

## 7. 退化模型

构型在下列情形下判为**退化**。每个检测器返回涉及的节点与原因。

| 检测器 | 条件 |
|---|---|
| `coincident_points` | 两个不同 id 的点坐标相同 |
| `zero_length` | 参与长度关系的线段长度为 0 |
| `collinear_triple` | 需要成圆的三点共线 |
| `parallel_no_intersection` | 必须相交的两直线平行 |
| `tangent_multiplicity` | 圆–圆 / 直线–圆交点的重数与预期不符 |
| `zero_denominator` | 比值或面积表达式除以 0 |
| `undefined_angle` | 角的两条射线同点或反向 |
| `circle_degenerate` | 圆节点 `r² ≤ 0` |
| `off_domain` | 算子结果越出定义域（如在圆心上求 `point.inverse`） |

**不变式**：`geo_check_degenerate` 必须报告**全部**适用检测器，而不是遇到第一个就停。

---

## 8. 约束求解与变体

`geo_solve` 接收一组约束（共线、共圆、垂直、平行、等长、等角、共点……）加一个构造模板，返回合法构型。

契约：

- **数值优先**（自由点坐标上的 Newton / 延续法），**符号验证**返回的解确实满足约束。
- 响应报告：解的个数、是否**一般位置**（不在任何退化轨迹上）、剩余**自由度**、自由点取值。
- 数值解若通不过符号验证，**丢弃**而非"带警告返回"。
- 求解是**采样**机制（用于 §8 变体与寻找反例），不是通用求解器。

`geo_variants` 在此之上采样同一构造族的 N 个**互不相同**的合法构型，并附各自的退化报告。

---

## 9. 中文几何 DSL（text2graph 的标准化层）

### 9.1 为什么要有 DSL

自然语言 → 图，若直接由模型输出构造图（JSON 节点或 GeoGebra 命令），错误率极高且无法逐条单测。**中间插入一个受限的、确定性的 DSL**，把问题拆成两段：

```
自然语言  ──(AI 翻译 或 人工)──▶  DSL  ──(确定性递归下降解析器)──▶  构造图
   不确定                              受限确定                        确定性
```

- **DSL → 图永远确定性**：毫秒级、离线、零 API 成本、可逐条单测。
- **AI 只负责翻译**，且翻译结果必须过解析器校验；解析失败时错误信息带**精确行列**，供 Agent 重试。
- DSL 同时是：手绘通道与文字通道的公共中间表示、比 JSON 节点更适合 LLM 生成的表示、以及**题面生成的目标**（DSL ↔ 题面双向）。

**DSL 是子集，不是自然语言。** 先覆盖常用构造的绝大部分；剩余表达由 AI 翻译 + 人工兜底。

> **语法的正本是 [`docs/dsl-spec.md`](dsl-spec.md)。** 本节是规格层面的概览，细则（记号、缺口清单、交点序号约定）以 `dsl-spec.md` 为准。

### 9.2 语法

行式语法，一行一条语句。**函数式**：`名称(参数, ...)`，名称与参数均用 GeoGebra 的**中文命令名**（决策 D17）。**GeoGebra 的英文命令名同样接受** —— GeoGebra 自己的输入栏在任何语言下都认英文，老师不必学第二套。

```
点 A(0,0) B(4,0) C(1,3)
△ABC
D = 垂足(A,BC)
M = 中点(A,B)
O = 外接圆(A,B,C)
P = 交点(AD,O,另一交点)
断言 共线(M,A,B)
断言 相等(AB,AC)
```

语句类型：

| 类型 | 形式 | 语义 |
|---|---|---|
| 引入点 | `点 A(x,y) B(x,y)` | `point.free` |
| 声明图元 | `△ABC` / `AB = 线段(A,B)` | 断言存在，不改变几何 |
| 构造点 | `X = <命令>(参数, ...)` | 映射到 §5.2 的算子 |
| 构造子句 | `中点(A,B)` / `垂直(A,l)` / `交点(l,c,选择器)` | 见 §9.3 |
| 断言关系 | `断言 <关系>(参数, ...)` | 写入 `relations`，由判定器裁定 |

**重载由参数决定**：同名命令（`交点` 有三种、`圆` 有两种）按参数的个数与类型挑出唯一的那一个，挑不出来就报错。

### 9.3 命令 → 算子的映射

命令名与 GeoGebra 中文命令名一致（决策 D17）；**命令表是唯一真源**（`src/geobench/commands.py`），完整的覆盖表见 [`plan.md`](plan.md) §6 —— 那张表是**生成的**，CI 盯着它不让它落后于代码。

| 命令 | 算子 |
|---|---|
| `中点(A,B)` | `point.midpoint` |
| `重心(A,B,C)` | `point.centroid` |
| `外心(A,B,C)` | `point.circumcenter` |
| `内心(A,B,C)` | `point.incenter` |
| `垂心(A,B,C)` | `point.orthocenter` |
| `垂足(A,l)` | `point.foot` |
| `交点(l1,l2)` | `point.intersect_lines` |
| `交点(l,c,选择器)` | `point.intersect_line_circle` |
| `交点(c1,c2,选择器)` | `point.intersect_circles` |
| `垂直(A,l)` | `line.perpendicular_through` |
| `平行(A,l)` | `line.parallel_through` |
| `直线(A,B)` | `line.free` |
| `线段(A,B)` | `segment.free` |
| `外接圆(A,B,C)` | `circle.through` |
| `圆(A,r)` | `circle.free` |

断言侧的命令（`共线` `共圆` `相等` `垂直` `相切` `共点` `中点`）映射到 §6 的判定器。

### 9.4 解析器契约

- **递归下降**，纯确定性，无副作用，无外部依赖。
- 错误类型 `DSLParseError(line, col, span, message)`：定位到行列与出错片段。
- 未识别的命令**必须报错**，不得静默忽略或猜测；**尚未实现**的命令与**参数不对**分别报错。
- 解析产物是 §3.1 的构造图；DSL 与构造图**双向可转**（`to_dsl`）。
- 同一份 DSL 在**桌面应用**与 **MCP 服务端**下必须产生**逐字节相同**的构造图。

### 9.5 题面生成

从构造图 + 断言反向生成题面草稿（"如图，△ABC 中 …，证明 …"），模板拼装 + 人工润色。这是"写题"工作量的主要削减点。

---

## 10. 渲染与导出

### 10.1 输出

| 目标 | 用途 |
|---|---|
| SVG | 无损、可脚本化、可被 LaTeX 嵌入、老师可二次编辑 |
| TikZ / PGF | 直接进 LaTeX 试卷 |
| PNG | 预览 / 网页 / Word 粘贴 |
| JSON | 题库文件（§12） |

### 10.2 竞赛图规范预设（中国奥赛卷面）

预设的具体数值待定（见 `docs/decisions.md` D6），框架要求：

- 纯黑线条，无彩色；背景透明或白。
- 线宽：图形线 ≈ 0.4 pt，辅助线虚线且更细。
- 自由点：实心黑圆点，半径 ≈ 0.8–1.0 pt；派生点可空心。
- 标注：正体衬线（Times），变量可用斜体，字号 ≈ 10 pt；置于图形外侧，不压线。
- 辅助线（垂足、延长线、辅助圆）默认虚线且不标注。
- 记号：圆写 `⊙O`，线段写 `AB`；**图注不画进图里**（属于题面："如图"）。
- 保留标号约定：`A B C …` 顶点、`O` 外心、`I` 内心、`H` 垂心、`G` 重心、`D E F` 垂足、`P Q R …` 自由点、`M N` 中点。

### 10.3 往返一致性

渲染是 `(构造图, 样式, 视图变换)` 的**纯函数**，无隐藏状态。因此同一文件今天导出与明天导出必须逐字节一致——这是回归测试，不是锦上添花。

**实现约定（决策 D20）。** 内核产出**一份原语列表**（点 / 线段 / 直线 / 圆 / 标注），屏幕后端（QPainter）与导出后端（SVG）**消费同一份**。因此：

- 屏幕上看到的与导出的 SVG **必然一致**（一致性由结构保证，不由两套代码的巧合保证）；
- 屏幕走 QPainter 而非 SVG，因为 Qt 的 SVG 渲染不足以支撑逐帧重绘；
- 两个后端产出的原语集合**必须逐条相等**（回归测试）。

---

## 11. MCP 接口

传输：stdio（默认）与 streamable HTTP。服务端是图形状态的纯函数；客户端只持有图形 id。

### 11.1 工具

| 工具 | 输入 | 输出 |
|---|---|---|
| `geo_state` | `{ figure_id? }` | 构造图、校验摘要、当前退化报告 |
| `geo_construct` | `{ figure_id?, ops: [{ id?, op, args }], mode: "apply"\|"dry-run" }` | 新建/更新/删除的节点 id、逐算子状态、精确错误 |
| `geo_evaluate` | `{ figure_id?, expr }` | 精确值 + 显示近似值（`Angle(B,A,C)`、`Distance(A,B)`、`Area(A,B,C)` 等） |
| `geo_verify` | `{ figure_id?, relation }` | 结论 + 证据 + 成立所依赖的假设 |
| `geo_solve` | `{ figure_id?, constraints, template, count }` | 构型 + 解报告（个数、一般性、自由度） |
| `geo_variants` | `{ figure_id?, family, count, seed }` | 同族的不同合法构型 + 各自的退化报告 |
| `geo_check_degenerate` | `{ figure_id? }` | 全部退化报告 |
| `geo_render` | `{ figure_id?, format: "svg"\|"tikz"\|"png", style: "competition"\|"plain", view? }` | 渲染产物 |
| `geo_apply_dsl` | `{ figure_id?, dsl, mode }` | 解析并应用 DSL，返回构造图增量；失败时返回 `line`/`col` 定位错误 |
| `geo_to_dsl` | `{ figure_id? }` | 由构造图反生成 DSL / 题面草稿 |

### 11.2 资源

| URI | 内容 |
|---|---|
| `geobench://spec/operators` | 算子注册表（§5） |
| `geobench://spec/judges` | 判定器目录（§6） |
| `geobench://spec/dsl` | DSL 语法与构造子句表（§9） |
| `geobench://style/competition` | 竞赛图规范预设（§10.2） |
| `geobench://figure/{id}` | 单个构造图 |

### 11.3 面向 Agent 的规则

- 所有工具响应**只返回 JSON**，绝不返回散文；一律带机器可读的 `status`（`ok` / `error` / `degraded`）。
- 错误必须**可执行**：指出算子、参数序号与原因（未知节点 id、参数类型错、参数个数错、退化构型、交点序号歧义）。
- 尽可能**幂等**（`geo_construct` 带显式 id 时幂等）。
- 不做隐藏网络访问；不改动地址图形之外的状态。
- **内核内不含模型**（决策 D4）：翻译、提议这类需要模型的事由客户端或外部 Agent 完成。

**三态语义**（决策 D15）：

| status | 含义 | Agent 该做什么 |
|---|---|---|
| `ok` | 请求被理解且完整执行 | 继续 |
| `error` | 请求错了 | **改请求** |
| `degraded` | 请求没错，但几何算不出来（退化构型等） | 读原因，接受现实 |

**错误结构。** 响应里的 `errors` 是对象数组，每个对象至少有 `code` 与 `message`；涉及参数时带 `op` 与 `index`（第几个参数），涉及节点时带 `node_id` 与 `known_node_ids`（合法的 id 列表，让 agent 能自己改对）。

---

## 12. 题库文件格式

一道题一个 JSON 文档，带版本号：

```jsonc
{
  "id": "geo-2026-0001",
  "version": 1,
  "statement": { "zh": "如图，…", "en": "As shown, …" },
  "figure": { "构造图（§3.1）" },
  "givens": ["AD ⊥ BC", "E 为 BC 中点"],
  "goal": "证明 P, Q, R 三点共线",
  "relations": [{ "kind": "collinear", "args": ["P", "Q", "R"], "expected": true }],
  "verification": {
    "verdict": "proved",
    "evidence": "…",
    "checked_at": "2026-11-05T00:00:00Z",
    "kernel_version": "0.1.0"
  },
  "degeneracy": { "status": "clean", "reports": [] },
  "variants": [{ "id": "v1", "figure_ref": "fig_0002", "notes": "锐角三角形" }],
  "difficulty": { "tier": "联赛", "tags": ["相似", "面积比"], "est_minutes": 25 },
  "provenance": { "source": "self-authored", "license": "CC0-1.0", "notes": "" }
}
```

`verification` 与 `degeneracy` **必填**：缺少 `proved` 结论或退化报告不干净的题，不能导出为"成品题"，但可以存为草稿。

---

## 13. 评测

位于 [`../evals/`](../evals/)，指标定义见 `evals/README.md`：

- `construct_success` —— 构造无错误完成的比例
- `oracle_agreement` —— 算子输出与对拍基准逐项一致的比例
- `verify_precision` —— `proved` 结论在对抗性重采样下仍成立的比例
- `degenerate_rate` —— 被退化检测器标记的构型比例
- `problem_validity` —— 目标可证且退化干净的自动出题比例
- `variant_diversity` —— 同族变体之间的平均差异度

每次评测必须记录内核版本、种子集与**确切命令**，使仓库里的任何一个数字都可复现。

---

## 14. 验收标准

一个组件算完成，当且仅当：

1. 在 [`../tasks/`](../tasks/) 有对应任务，验收标准**机器可判**；
2. 单元测试通过，且每个判定器至少有一条**反例**测试；
3. 算子通过对拍（§5.3）；
4. 退化情形被退化测试套件覆盖（§7）；
5. 几何量上**不含浮点运算**（由 lint 规则保证，而非人眼审查）；
6. 公开 API 与本文档一致；若必须变更，**先改本文档**。

---

## 15. 待决与关联文档

- 决策记录：[`decisions.md`](decisions.md)（D1–D10）
- 实现流程：[`ai-workflow.md`](ai-workflow.md)
- 任务清单：[`../tasks/README.md`](../tasks/README.md)
- 评测定义：[`../evals/README.md`](../evals/README.md)
