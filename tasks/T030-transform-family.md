# T030 —— 变换族：镜像 / 平移 / 旋转 / 位似

**状态**：已实现
**负责人**：Agent
**规格**：[`docs/plan.md`](../docs/plan.md) §6；决策 D17
**依赖**：T025
**涉及层**：算子

## 目标

出题时常用的四个变换。四个都产出**点**，所以不需要新增图元种类 ✓。

## 交付物

- `transform.mirror`（镜像）：关于直线的对称点
- `transform.translate`（平移）：按一个向量平移
- `transform.rotate`（旋转）：绕点旋转，**角度用度**（同 GeoGebra）
- `transform.dilate`（位似）：以点为中心位似
- 各 27–75 组对拍夹具

## 关键做法

**旋转的角度用度，而且**保持精确**。这是这一族最要紧的一件事：弧度角写成 `θ·π/180`，sympy 会把特殊角的三角函数**化成精确值**：

| 角度 | cos | sin |
|---|---|---|
| 30° | `√3/2` | `1/2` |
| 45° | `√2/2` | `√2/2` |
| 60° | `1/2` | `√3/2` |
| 90° | `0` | `1` |

如果角度写成弧度的小数（0.5236…），结果就全是浮点近似 —— **精确性当场就没了**。所以角度的单位不是口味问题。

**镜像 = 2×垂足 − 点。** 垂足是原点与像的中点 ✓。直接用直线方程写也更快：`d = (a·p_x + b·p_y + c)/(a²+b²)`，像 = `p − 2d·(a,b)` ✓。

**平移的向量写成一个点**（GeoGebra 的写法）：那个点的坐标就是位移量 ✓。

**对拍用 sympy 自己的几何方法**：镜像用 `Point.reflect`，旋转用 `Point.rotate`，平移用 `Point.translate`。位似要注意：sympy 的 `Point.scale` 缩放的是**坐标**、不是绕点位似 ✗，所以对拍改用 sympy 的**点向量运算** ✓。

## 验收标准

```bash
pytest tests/oracle -q
pytest tests/unit/dsl -q
ruff check . && mypy src
```

## 失败记录

见 [`T030-transform-family.failures.md`](T030-transform-family.failures.md)。
