# T060 —— Windows 免安装包 + GitHub Release

**状态**：已实现
**负责人**：Agent
**规格**：`docs/teacher-guide.md`、D16（桌面外壳）
**依赖**：T019（工作台）
**涉及层**：打包 · 发布

## 目标

老师从 GitHub Releases 下载一个 zip，解压、双击就能用：**不需要 Python、pip、GeoGebra 或其它依赖**。

## 做法

- **PyInstaller one-folder**（`packaging/geobench.spec`）：不是 one-file —— 启动快，杀毒软件也不那么敏感；
- 打包内容：Python 运行时、PySide6-Essentials（Widgets/Gui/Svg）、SymPy、`prompts/`（AI skill 在运行时读它）、窗口图标；
- **图标**：`scripts/make_icon.py` 用 QPainter 画（蓝底、白外接圆与三角形、金色顶点），生成 PNG + 256px ICO；
- **AI 资源路径**：`geobench.ai._resource` 优先读 `sys._MEIPASS`，源码树和打包后读同一份 `prompts/`；
- **冒烟测试**：`geobench.exe --smoke-test` 用 offscreen 平台建窗口、渲染、检查三份 prompt 文件存在，退出码 0/2；
- **发布物**：`dist/geobench/` 附带 `samples/`、`使用说明.md`、`LICENSE`，压缩为 `geobench-win64.zip`；
- **CI**：`.github/workflows/release.yml`（windows-latest）手动触发构建 artifact；`v*` tag 时自动发布 Release；
- **本地构建**：`packaging/build.ps1`。

## 依赖（写给老师）

- **Windows 10/11 64 位**；不需要 Python，不需要 VC++ 运行库（`VCRUNTIME140*.dll` 已在包里）；
- **不需要 GeoGebra**；`.ggb` 可以导入；
- **AI 作图可选**：需要自备 OpenAI 兼容服务的地址/模型/钥匙；不配也能作图、判定、导出；
- 未买代码签名证书：SmartScreen 会提示“未知发布者”，点「更多信息 → 仍要运行」；
- 压缩包约 **69 MB**，解压后约 **150 MB**。

## 验收

```powershell
.\packaging\build.ps1
$env:QT_QPA_PLATFORM="offscreen"
Start-Process .\dist\geobench\geobench.exe -ArgumentList "--smoke-test" -Wait -PassThru
# 退出码 0
```

- 资源在 `_internal/prompts`、`_internal/icon.png`；
- VC 运行库在 `_internal/VCRUNTIME140*.dll`；
- 无 Python 的机器上双击可开窗（用干净的 Windows 账户验证）。

## 非目标

- 安装器（Inno Setup / MSI）—— zip 够了；
- 自动更新、代码签名证书；
- macOS / Linux 包。
