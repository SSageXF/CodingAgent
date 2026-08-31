# EvidenceCoder

EvidenceCoder 是一个不依赖 Agent 框架的本地 Coding Agent。它通过
OpenAI-compatible Chat Completions API 使用模型原生 tool calling，自行实现上下文、
工具分派、审批、执行循环、终止条件和错误处理。运行时只依赖 HTTP 客户端 `httpx`
和终端显示库 `Rich`，不使用
LangChain、LlamaIndex、OpenAI Agents SDK、Claude Agent SDK、AutoGen 或 CrewAI。

它的核心约束是“结论必须有凭证”：所有本地动作形成单调递增的
`OperationRecord`；模型只能通过 `submit_result` 结束任务，并引用成功的操作编号。
文件声明必须对应该文件最新一次成功写入；检查声明必须对应发生在最新修改之后、
退出码为 0 的命令。

## 一分钟理解这个项目

用户给 EvidenceCoder 一条编程任务后，它不是直接生成一大段答案，而是反复执行下面的闭环：

1. 把任务、近期对话、工作区事实和可用工具发给模型；
2. 检查模型返回的是普通说明还是结构化工具调用；
3. 在本地校验路径、参数和危险程度，必要时让用户确认；
4. 执行读取、写入、Git 观察或本地命令，并把真实结果记入 RunBook；
5. 把结果反馈给模型，让模型继续判断、修改或验证；
6. 只有 `submit_result` 中的完成声明能被本轮操作凭证证明时，任务才算完成。

因此，模型负责“决定下一步”，EvidenceCoder 负责“允许什么、实际做什么、记录了什么，
以及模型能否有证据地宣布完成”。API 服务只负责生成 tool call；文件和命令始终由本机执行。

当前版本为 `0.3.2`。自动测试结果为 47 项通过、1 项因本机符号链接能力跳过；三个真实 API
隔离案例已验证创建程序、复现并修复错误、Git 只读审查以及执行凭证闭环。完整结果和已知问题见
[真实 API 验收报告](docs/08_REAL_API_ACCEPTANCE_REPORT.md)。

## 能力边界

- 在指定工作区内列目录、单文件或批量分段读取、搜索、精确替换和写入 UTF-8 文本。
- 通过固定的只读工具查看仓库状态和有界 Git diff，不自动提交、回滚或推送。
- 在固定工作目录执行独立的本地命令，记录退出码、超时和截断后的输出。
- 对写入和命令请求终端确认；`--yes` 只能跳过普通确认，不能绕过硬拒绝规则。
- 提供连续交互式 CLI；每条指令独立验收，并可保存、恢复同一工作区的已验证对话事实。
- 使用彩色面板、模型等待状态和紧凑工具结果；写入审批前显示有界 unified diff。
- 汇总模型调用、工具调用、耗时和网关返回的 token 用量。
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

复制模板并填写本地配置；`.env` 已被 Git 忽略，不会上传：

```powershell
Copy-Item .env.example .env
notepad .env
```

程序从启动命令所在目录读取 `.env`。格式见 [.env.example](.env.example)：

```dotenv
EVIDENCECODER_MODEL=your-model-name
EVIDENCECODER_BASE_URL=https://api.openai.com/v1
EVIDENCECODER_API_KEY=replace-me
```

配置优先级为命令行参数、已有系统环境变量、`.env`、程序默认值。也就是说，原来的
PowerShell 环境变量用法仍然有效，并可临时覆盖 `.env`。

兼容网关需要支持 `/chat/completions` 以及 `tools`/`tool_calls` 字段。

## 使用

不带任务参数时进入交互模式：

```powershell
evidencecoder --workspace C:\path\to\project
```

如果 PowerShell 提示无法识别 `evidencecoder`，通常是可执行脚本目录尚未进入 `PATH`。
可直接使用等价且更稳妥的模块启动方式：

```powershell
python -m evidencecoder --workspace C:\path\to\project
```

直接输入任务即可连续工作；内置命令为 `/help`、`/status`、`/history`、`/new`、
`/resume [id|latest]`、`/retry`、`/export [path]`、`/paste` 和 `/exit`。不带参数的
`/resume` 会列出当前工作区的最近对话，输入序号即可恢复；`/resume latest` 和指定 ID
的方式仍然可用。`/retry`
使用新的 RunBook 重试上一条指令，不复用旧凭证；`/export` 输出 Markdown 对话报告。
对话默认原子保存到
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

## 视频演示推荐

仓库已经提供一个固定、可复现的运费边界错误项目，不需要另外寻找测试项目。先在
EvidenceCoder 仓库根目录运行准备脚本；脚本会把模板复制到系统临时目录，初始化为独立 Git
仓库并提交有缺陷的初始版本，不会修改当前项目仓库：

```powershell
$demo = powershell -ExecutionPolicy Bypass -File .\demo\prepare_video_demo.ps1
python -m unittest discover -s "$demo\tests" -v
```

第二条命令应显示 3 项测试中 1 项失败：100 元订单本应免运费，却被计算为 8 元；结算总额也
因此从预期的 100 元变成 108 元。这让观看者在 Agent 启动前就能明确看到问题和验收标准。

然后进入交互模式。演示时不要使用 `--yes`，这样视频能展示写入 diff 和人工审批：

```powershell
python -m evidencecoder --workspace $demo
```

进入后只输入这一句：

```text
请先读取 VIDEO_TASK.txt，然后严格按照文件中的要求完成任务。
```

详细提示词已经保存在演示项目的 `VIDEO_TASK.txt` 中。让 Agent 自己读取它，比在终端粘贴一大段
任务更能直观证明本地文件读取能力。该文件明确要求 Agent 使用 `inspect_tree`、`git_status`、
`git_diff`、`read_many`、`run_local`、文件修改和 `submit_result`，并禁止联网、安装依赖、修改
测试或执行 Git 写操作。

这一个固定任务可以在较短视频中集中展示：

- `inspect_tree`、`git_status`、`git_diff` 和 `read_many` 的观察能力；
- 失败命令作为有效观察反馈给模型；
- 写入前的 unified diff 与人工审批；
- 模型根据工具结果继续迭代，而不是一次性输出代码；
- 修改后的完整测试和 `submit_result` 凭证校验；
- 最终面板中的修改文件、检查记录、限制、耗时和 token 用量。

预期修复仅把 `shipping.py` 中免运费判断的 `>` 改为 `>=`，测试文件不变，最终 3 项测试全部
通过。演示后可继续输入 `/history`、`/status`、`/export demo-report.md`，再用 `/new` 和
`/resume` 展示对话保存与恢复；这些斜杠命令不必塞进同一条修复任务。

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
- `display.py`：Rich 显示、结构化运行事件、结果表格和审批 diff；不拥有 Agent 状态。
- `context_window.py`：从 RunBook 投影当前上下文并压缩早期历史。
- `platform_facts.py`：向模型提供非敏感的本机系统、Shell 和 Python 命令事实。
- `toolbox.py`：固定 schema、参数校验和分派。
- `guard.py`：平台侧允许、询问或拒绝决策。
- `completion.py`：把完成声明与真实操作凭证交叉核验。
- `tool_impl/`：工作区文件、独立子进程和只读 Git 操作。

固定工具共 10 个：`inspect_tree`、`read_segment`、`read_many`、`find_matches`、
`replace_text`、`write_text`、`run_local`、`git_status`、`git_diff`、`submit_result`。
Git 工具要求 `--workspace` 指向仓库根目录；它们不提供 Git 写操作。

工具调用失败会作为结构化结果反馈给模型，不会让主循环直接崩溃。非零命令退出码是
有效观察，但不能作为“检查通过”的凭证。

## 测试

```powershell
python -m pip install -e ".[dev]"
python -m pytest
```

测试包含本地 `FakeGateway`，无需 API Key 即可验证完整的写入—命令—凭证提交循环。
它还覆盖路径穿越、符号链接越界、精确替换、命令超时、API 重试、危险命令、schema、
`.env` 配置与优先级、上下文压缩、对话恢复、Rich 输出、diff 预览、批量读取、只读 Git、
使用统计、报告导出、Windows 输出解码、计时边界和主要终止条件。

## 完成度与已知限制

对照项目最初要求，当前版本已经独立实现：模型 API 调用、上下文管理、固定工具定义与本地
分派、模型输出解析、Agent 循环、完成校验、错误处理、CLI 交互、对话恢复和运行记录。它没有
使用 Agent 框架、服务端代码执行器或其他 Coding Agent 作为运行时。

目前最重要的限制是 `run_local` 仍然属于本机 Shell，而不是操作系统级沙箱。真实 API 验收中，
模型曾在自动批准模式下执行 `git config --global`；测试新增的配置已经撤销，但这证明普通命令
仍可能在工作区外产生副作用。因此在实现更严格的子进程隔离前，建议保留人工命令审批，不要对
不熟悉的仓库使用 `--yes`。此外，项目尚不提供流式输出、撤销、浏览器、MCP、插件、多 Agent、
自动 Git 提交/推送或全屏 TUI；这些是明确的范围选择，不影响本次考核要求中的核心闭环。

## 独立性说明

项目从空白目录实现，没有 fork、vendor 或复制其他 Coding Agent 的源码、提示词、测试
和目录结构。调研来源、逐库差异和模块级相似性标准见 [docs](docs/REVIEW_INDEX.md)。
通用的“模型调用—工具执行—结果回传”模式不能归属于单一仓库；本项目以六阶段循环、
RunBook 操作凭证和完成声明校验形成自己的控制流与数据模型。
