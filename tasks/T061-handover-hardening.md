# T061 交接前加固

**目标**：让真实老师能放心把一节课的图交给这个程序；把用户提供的四个
GeoGebra 文件全部读进来；补上“文件不会丢”的基本保证和 P1 功能。

## 完成

### GeoGebra 导入（真实语料）

- [x] `geogebra_macro.xml`：自定义工具按文件里的**定义展开**，不再按名字猜。
      `旁心`、`外心`、`垂心`、`垂线段` 等与内置同名的工具，以文件为准。
- [x] `Point(circle)`：读保存位置，反算成 `圆上的点(c, t)`，不再丢约束。
- [x] `Line(Point, Line)` → `平行`；`Midpoint(segment)` → `中点(A,B)`。
- [x] `PerpendicularSegment` → `垂足` + `线段` 两条命令，垂足可被后续对象依赖。
- [x] `Mirror(Point, Point)` → `点对称`（新增算子）。
- [x] 齐次坐标 `x/z, y/z`；`H'` / `H_{1}` 改名并记录。
- [x] 多输出命令（切线、多边形边）只导入第一个，其余逐条报告。
- [x] 依赖未导入对象的构造整体跳过并报告，绝不输出解析不了的 DSL。
- [x] 四个真实 `.ggb` 全部导入、解析、求值通过；`tests/unit/test_ggb.py`
      里有一组“语料在就运行”的回归测试。

### 数据安全

- [x] `文件 → 新建`（`Ctrl+N`），有改动时先问保存。
- [x] 标题栏脏标记 `*`；关闭窗口时保存/放弃/取消。
- [x] 自动保存到 `%APPDATA%\geobench\recovery.geobench`，正常关闭时删除。
- [x] 下次启动发现恢复文件时询问是否恢复。
- [x] `%APPDATA%\geobench\geobench.log` 记录未捕获异常。
- [x] 最近打开（最多 8 个）与文件拖放。

### AI 面板

- [x] 明确写“AI 是选用的；不连模型也能作图、判定、导出”。
- [x] 说明只有点「问模型」时才发送当前图形。
- [x] 没有服务时“问模型”禁用，设置入口仍在。

### P1

- [x] 自由弧 `圆弧(O, A, B)`（圆心 + 两点，逆时针）与 `圆扇形(O, A, B)`；
      过三点弧仍叫 `三点弧`，与 GeoGebra 的 `CircularArc` / `CircumcircularArc` 对齐。
- [x] 判定成立的等长（短横线）和垂直（直角方框）直接画在图上。
- [x] 导出 GeoGebra `.ggb`：常见构造写回；写不回去的逐条报告。
- [x] 高 DPI 图标按屏幕倍率绘制。

## 验证

```text
ruff check .              All checks passed
mypy src                  Success: no issues found in 45 source files
pytest -q                 1321 passed, 1 skipped
四个真实 .ggb             全部导入、解析、数值求值通过
```

## 仍未做（明确范围外）

- 圆锥曲线、轨迹/包络/参数曲线（D21）。
- 测量值作为参数（请用 `数 a = …`）。
- 导出 `.ggb` 的极端构造（极线、依附点的动态约束等）会报告而不是写回。
