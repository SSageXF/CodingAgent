# EvidenceCoder

EvidenceCoder 是一个不依赖 Agent 框架的本地 Coding Agent。它通过
OpenAI-compatible Chat Completions API 使用模型原生 tool calling，自行实现上下文、
工具分派、审批、执行循环、终止条件和错误处理。项目只依赖 `httpx`，不使用
LangChain、LlamaIndex、OpenAI Agents SDK、Claude Agent SDK、AutoGen 或 CrewAI。

它的核心约束是“结论必须有凭证”：所有本地动作形成单调递增的
`OperationRecord`；模型只能通过 `submit_result` 结束任务，并引用成功的操作编号。
文件声明必须对应该文件最新一次成功写入；检查声明必须对应发生在最新修改之后、
退出码为 0 的命令。

## 能力边界

- 在指定工作区内列目录、分段读取、搜索、精确替换和写入 UTF-8 文本。
- 在固定工作目录执行独立的本地命令，记录退出码、超时和截断后的输出。
- 对写入和命令请求终端确认；`--yes` 只能跳过普通确认，不能绕过硬拒绝规则。
- 提供连续交互式 CLI；每条指令独立验收，并可保存、恢复同一工作区的已验证对话事实。
- 根据 token 软预算压缩早期上下文，同时保留原始 RunBook 和操作事实。
- 检测最大轮数、墙钟时间、连续工具错误、重复动作和用户中断。

本项目不是操作系统沙箱。命令工具虽然固定 `cwd`、要求审批并拦截已知高危模式，
但 Shell 本身仍可能访问工作区外资源；不要在不可信环境中以高权限运行。它不提供
浏览器、联网搜索、MCP、插件、子 Agent、自动 Git commit/push 或托管代码执行器。

## 安装

要求 Python 3.11+：

```powershell
cd C:\path\to\CodingAgent
python -m pip install -e .
```

配置环境变量（程序不会自动读取 `.env`）：

```powershell
$env:EVIDENCECODER_MODEL = "your-model-name"
$env:EVIDENCECODER_BASE_URL = "https://api.openai.com/v1"
$env:EVIDENCECODER_API_KEY = "your-key"
```

兼容网关需要支持 `/chat/completions` 以及 `tools`/`tool_calls` 字段。

## 使用

不带任务参数时进入交互模式：

```powershell
evidencecoder --workspace C:\path\to\project
```

直接输入任务即可连续工作；内置命令为 `/help`、`/status`、`/history`、`/new`、
`/resume <id|latest>`、`/paste` 和 `/exit`。对话默认原子保存到
`.evidencecoder/dialogues/`，以后可恢复：

```powershell
evidencecoder --workspace C:\path\to\project --resume latest
```

普通写入或命令的审批支持 `y`（本次允许）、`n`（本次拒绝）、`a`（本进程允许同类）和
`q`（取消当前任务）。`a` 不能绕过硬拒绝规则。

一次性模式保持兼容：

```powershell
evidencecoder --workspace C:\path\to\project "修复边界条件错误并运行测试"
```

默认每次写入和命令都会显示完整参数并询问。可按风险分别预批准：

```powershell
evidencecoder --yes-writes --workspace . "补充单元测试"
evidencecoder --yes --workspace . "修复测试失败"
```

`git push`、`git reset --hard`、强制清理、系统关机和工作区整体递归删除等命令即使
使用 `--yes` 也会拒绝。运行记录默认写到目标工作区的
`.evidencecoder/runs/<run-id>.json`。

查看全部参数：

```powershell
python -m evidencecoder --help
```

## 架构

主循环由 `Engine` 单独拥有，每轮显式经历六个阶段：

```text
COMPOSE → ASK → CHECK → AUTHORIZE → ACT → ASSESS
    ↑                                      │
    └──────────────────────────────────────┘
```

- `api_link.py`：直接构造 HTTP 请求、重试并解析模型响应。
- `engine.py`：六阶段循环、预算、卡死检测和终止状态。
- `runbook.py`：只追加的对话与本地操作记录。
- `dialogue.py`：跨任务的已验证事实、工作区绑定和原子持久化。
- `interactive.py`：行式 REPL、斜杠命令和进程内审批状态。
- `context_window.py`：从 RunBook 投影当前上下文并压缩早期历史。
- `platform_facts.py`：向模型提供非敏感的本机系统、Shell 和 Python 命令事实。
- `toolbox.py`：固定 schema、参数校验和分派。
- `guard.py`：平台侧允许、询问或拒绝决策。
- `completion.py`：把完成声明与真实操作凭证交叉核验。
- `tool_impl/`：工作区文件操作和独立子进程执行。

工具调用失败会作为结构化结果反馈给模型，不会让主循环直接崩溃。非零命令退出码是
有效观察，但不能作为“检查通过”的凭证。

## 测试

```powershell
python -m pip install -e ".[dev]"
python -m pytest
```

测试包含本地 `FakeGateway`，无需 API Key 即可验证完整的写入—命令—凭证提交循环。
它还覆盖路径穿越、符号链接越界、精确替换、命令超时、API 重试、危险命令、schema、
上下文压缩、对话恢复、Windows 输出解码、计时边界和主要终止条件。

## 独立性说明

项目从空白目录实现，没有 fork、vendor 或复制其他 Coding Agent 的源码、提示词、测试
和目录结构。调研来源、逐库差异和模块级相似性标准见 [docs](docs/REVIEW_INDEX.md)。
通用的“模型调用—工具执行—结果回传”模式不能归属于单一仓库；本项目以六阶段循环、
RunBook 操作凭证和完成声明校验形成自己的控制流与数据模型。
