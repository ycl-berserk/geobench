# T039b —— 模型服务的设置：钥匙从哪来

**状态**：已实现
**负责人**：Agent
**规格**：[`docs/plan.md`](../docs/plan.md) M-E
**涉及层**：服务端 · 应用

## 问题

「这个一定要靠环境变量来实现吗？能不能让软件读取已有环境变量，
或者让用户在软件里面手动输入 api key，或者引导用户提供什么东西？」

答案是：**不用**。环境变量只是一种做法，而且是最先被读到的那种，
不是唯一的一种。

## 查过的通用做法

Claude Code、Cursor、Cline、Continue、Copilot CLI、OpenCode、
Gemini CLI —— 这些工具都遇到同一个问题：**钥匙放在哪**。
它们的答案不是单选，而是一条**优先级链**：

| 工具 | 钥匙的来源 |
|---|---|
| Claude Code | 环境变量 → 系统钥匙串 → `~/.claude/.credentials.json` |
| Cursor / Windsurf | 系统钥匙串 |
| Cline | VS Code 的 SecretStorage（加密） |
| Copilot CLI | 系统钥匙串；没有就退回明文文件（会问） |
| Continue | `~/.continue/config.json`（明文），支持 `${ENV_VAR}` 替换 |
| OpenCode | `~/.local/share/opencode/auth.json`（CLI 与桌面版共用） |
| Gemini CLI | 环境变量 / `~/.gemini/.env` |

共识是那条链：**环境变量 → 系统钥匙串 → 应用自己的设置**。

本项目照这个做，**取 Claude Code 记录在案的那条顺序：环境变量优先**。
已经导出过密钥的用户不会被再问一遍。

## 本项目的三层

1. **环境变量** —— `GEOBENCH_AI_API_KEY`（总开关）、`GEOBENCH_AI_BASE_URL`、
   `GEOBENCH_AI_MODEL`，以及各服务自己的 `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` / …
   **而且**：什么都没配置时，环境里若已经有某个服务的密钥，
   **那个服务就被选中** —— 这台机器上 `DEEPSEEK_API_KEY` 已经设着，
   所以**开箱即用，一行配置都不需要**。
2. **密钥文件** —— 用户指定的一个 `.env` 风格的文件（默认在
   `%APPDATA%/geobench/api_key`）。文件里可以写 `${MY_KEY}`，
   **说清楚钥匙在哪，而不含钥匙本身**（Continue 的做法）。
3. **应用里输入的** —— 对话框里的密码框。保存时写进**密钥文件**，
   **不写进设置文件** —— 设置文件是可以复制给别人看的，密钥不是。

（系统钥匙串这一层没做：Windows 上要拉一个依赖，
而前两层已经覆盖了绝大多数人的情况。）

## 最重要的一条

**界面必须说清楚钥匙会从哪来。**
「不工作」不是一个答案，「去检查你的环境变量」对不懂环境变量的人也不是。
对话框底部那行字永远在说：**现在会用什么、钥匙从哪来、还缺什么**。

## 做法

- `src/geobench/ai_settings.py`（服务端层）
  - `PROVIDERS`：10 个 OpenAI 兼容服务的预设（DeepSeek / OpenAI / 通义 /
    Moonshot / MiniMax / SiliconFlow / OpenRouter / Groq / Ollama / 自定义）
    —— **Anthropic 自己的 API 故意不在里面**：它不兼容这个协议，
    假装兼容是个坑。
  - `resolve_provider()`：按上面的顺序找，返回 `(provider, 来源)`；
    找不到就返回 `(None, 缺什么)`。
  - `read_key_file` / `write_key_file`：`.env` 风格，支持 `${ENV}` 间接引用；
    写入时 `chmod 0600`。
  - 设置文件与密钥文件**分开**：设置可以被分享，密钥不行。
- `src/geobench/app/settings_dialog.py`（应用层）
  - 服务 / 地址 / 模型 / 密钥 / 密钥文件 / 「优先用这里保存的密钥」
  - 「从环境变量读取」按钮：**用户不必知道该看哪个变量**，
    程序自己扫一遍并报告找到了哪个。
  - 底部状态行：**现在会用什么、钥匙从哪来、还缺什么**。
- `src/geobench/app/ai_panel.py`：面板显示
  「模型：DeepSeek（密钥来自环境变量 DEEPSEEK_API_KEY）」，
  并且**没有服务时，「设置模型服务…」就在眼前**。
- `src/geobench/app/window.py`：菜单「设置 → 模型服务…」。
- `src/geobench/ai.py`：把「钥匙从哪来」从这里**移走** ——
  这一层只管 transport（怎么跟服务说话），policy 只在一个地方。

## 交付物

- `src/geobench/ai_settings.py`、`src/geobench/app/settings_dialog.py`
- 测试 `tests/app/test_ai_settings.py`（17 个）、
  `tests/app/test_settings_dialog.py`（6 个）、`tests/app/test_ai_panel.py`（4 个）
  —— **全部离线**，且**不碰用户真实的设置目录**（`GEOBENCH_CONFIG_DIR` 指到临时目录）

## 验收标准

```bash
pytest tests/app/test_ai_settings.py tests/app/test_settings_dialog.py tests/app/test_ai_panel.py -q
pytest -q
ruff check . && mypy src
```

## 顺带修的

- 对话框的按钮在 Qt 里永远是英文的 "OK" / "Cancel"。
  中文为主的程序里那读起来像失误而不是选择 ——
  `theme.button_words()` 统一改了（4 个对话框）。

## 已知限制

- 没有接系统钥匙串（Windows 凭据管理器）。
- 「在画板上作图」仍然是**整图替换**（可撤销）；增量合并留待以后。
