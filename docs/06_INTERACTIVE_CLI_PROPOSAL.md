# EvidenceCoder 交互式 CLI 与提交完善方案

> 状态：已于 2026-08-30 获用户审查通过；方案主体已实现并进入验收。
>
> 初稿日期：2026-08-28；实施日期：2026-08-30
>
> 依据：原始考核 PDF、当前 `0.1.0` 实现、真实 API 运行 `5be75b963114`。

## 1. 结论先行

当前 EvidenceCoder 已经满足题目最核心的“独立实现 Coding Agent”要求：它能调用真实
模型、读写工作区、执行命令、从错误中继续、管理上下文，并用本地操作凭证验证完成声明。
你刚才的真实 API 测试证明主链路可用。

下一阶段建议做两类工作：

1. **把一次性命令升级为连续交互式 CLI**：不带任务启动时进入提示符，完成一项任务后
   回到提示符，允许用户继续补充要求、查看历史、新建对话或退出；原有一次性调用保持兼容。
2. **修复真实运行暴露的问题并补齐提交物**：Windows 命令乱码、平台误判、审批等待被
   计入工具耗时、界面反馈不足；同时补 README.txt 仓库地址，准备真实任务视频和最终 zip。

不建议在截止日前加入全屏 TUI、流式 tool-call 解析、MCP、插件、子 Agent、LSP 或自动
Git 操作。这些不是题目硬要求，会扩大故障面，也削弱“关键逻辑简单且能答辩”的优势。

## 2. 真实 API 测试复盘

测试任务：创建 `hello.py`，输出 `EvidenceCoder works`，运行验证并提交结果。

### 已验证成功的能力

- 第 1 轮使用 `inspect_tree` 确认工作区为空。
- 第 2 轮通过 `write_text` 创建 `hello.py`，记录文件 SHA-256。
- 第 3、4 轮命令失败后没有提前退出，而是继续寻找可用命令。
- 第 5 轮执行 `python hello.py`，退出码为 0，输出正确。
- 第 6 轮 `submit_result` 只引用写入凭证 `op-0002` 和成功检查 `op-0005`，校验通过。
- 报告诚实记录限制：当前环境没有可用的 `python3` 命令。

这说明六阶段循环、错误回灌和“完成声明有凭证”不是只在 FakeGateway 测试中成立，真实
模型同样能够理解并正确使用。

### 暴露的问题

| 现象 | 根因 | 影响 | 优先级 |
|---|---|---|---|
| 模型先调用 `cat`、`python3` | 提示中没有操作系统、Shell 和当前 Python 可执行信息 | 浪费两轮模型调用和用户审批 | P0 |
| Windows 错误信息乱码 | 子进程输出被固定按 UTF-8 解码，`cmd.exe` 实际可能输出 OEM/ANSI 编码 | 用户和模型难以理解错误 | P0 |
| `write_text` 的 OperationRecord 显示 476843 ms | 计时从审批前开始，把用户等待时间算成执行耗时 | 日志证据失真 | P0 |
| 每完成一个任务程序退出 | CLI 入口只调用一次 `Engine.run(task)` | 无法连续补充需求 | P0 |
| 等模型时只有 `asking model` | 显示层只接收字符串观察信息 | 长请求中缺少状态和耗时反馈 | P1 |
| 命令退出 1 仍显示工具状态 `ok` | `ok` 表示“命令成功执行并返回观察”，不表示命令测试通过 | 语义正确但界面容易误解 | P1 |

## 3. 原始题目逐项对照

### 技术要求

| 原题要求 | 当前状态 | 还需完善 |
|---|---|---|
| 独立设计实现 Coding Agent | 已满足 | 保持现有自研边界 |
| 自主读写文件、执行命令、迭代完成任务 | 已满足并经真实 API 验证 | 增加交互式连续任务 |
| 不在现有 Agent 上封装界面 | 已满足 | 交互层只能调用自研 Engine |
| 不使用 Agent 框架/SDK | 已满足 | 不引入 prompt_toolkit 之外的 Agent 依赖；本方案甚至不需要 prompt_toolkit |
| 不依赖服务端代码执行或文件工具 | 已满足 | 保持本地执行 |
| 自研历史/上下文、工具、解析、终止、错误处理 | 已满足 | 增加多轮对话记录簿与恢复语义 |
| API Key 不入库、不进 README.txt/视频 | 已满足 | 视频录制前再次扫描环境输出与画面 |

### 三项提交物

| 提交物 | 当前状态 | 缺口 |
|---|---|---|
| 新建公开 Git 仓库并保留历史 | 已完成：`https://github.com/SSageXF/CodingAgent` | 后续仍需正常提交并在截止后停止推送 |
| README.txt 不超过 1000 汉字 | 当前 629 字 | **缺少原题明确要求的 Git 仓库地址**；交互功能完成后更新运行说明 |
| 2 分钟内、MP4、≤200 MB 的演示视频 | 未完成 | 不能只演示 hello world；应准备真实 bug 修复任务并简述设计 |
| 最终姓名命名 zip，仅含 README.txt 和视频 | 未完成 | 视频验收后生成；姓名需由用户提供或用户自行命名 |

因此，代码主链路已过关，但还不能说“最终提交物全部完成”。README.txt 的仓库地址是
一个明确、容易修复的硬缺口；视频和 zip 是剩余最大的提交工作。

## 4. 交互式 CLI 的用户体验

### 启动规则

- `evidencecoder --workspace <目录> "任务"`：保持现有一次性模式，脚本和自动化不受影响。
- `evidencecoder --workspace <目录>` 且 stdin 是终端：进入交互模式。
- 无任务且 stdin 不是终端：返回配置错误，避免 CI 管道意外挂起等待输入。
- 可选 `--resume <dialogue-id|latest>`：恢复此前保存的交互对话。

启动后显示一次简短横幅：版本、工作区、模型、审批策略、对话编号。不得显示 API Key。

```text
EvidenceCoder 0.2.0
workspace: C:\project    model: ...    approvals: ask
type /help for commands

evidencecoder> 修复分页函数在 size=0 时的错误，并运行测试
...
completed: 修改 1 个文件，验证 2 项

evidencecoder> 再补一个负数输入测试
...
evidencecoder>
```

### 最小内置命令

| 命令 | 行为 |
|---|---|
| `/help` | 显示命令和审批说明 |
| `/status` | 显示工作区、模型、当前对话编号、累计任务数和最近结果 |
| `/history` | 显示本次对话中每条用户指令及完成/失败状态，不输出大段工具日志 |
| `/new` | 清空对话上下文并生成新对话编号；**不回滚或删除工作区文件** |
| `/resume <id|latest>` | 载入本工作区保存的对话记录 |
| `/exit` | 保存记录并退出；EOF 具有相同行为 |

暂不支持运行中切换工作区或模型。动态切换会使路径边界、凭证来源和上下文含义变得不清楚；
需要切换时退出并重新启动，答辩也更容易解释。

### 输入和中断

- 普通一行文本就是新任务或对上一任务的追问。
- 第一版不引入全屏编辑器；多行长任务可用 `/paste`，以单独一行 `/end` 结束。
- Agent 执行时按一次 Ctrl+C：取消当前任务并回到交互提示符，保留此前对话。
- 在空闲提示符按 Ctrl+C：只清空当前输入；连续再次按下或输入 `/exit` 才退出。
- 审批提示支持 `y`、`n`、`a`、`q`：允许一次、拒绝一次、在本次进程中允许同类普通操作、
  取消当前任务。`a` 永远不能绕过 Guard 的硬拒绝规则。

## 5. 多轮上下文与凭证设计

这里最容易出错。不能简单把上一个 RunBook 接着写，因为第二条任务可能引用第一条任务的
旧 `op_id`，从而把旧测试冒充成新修改后的验证。

建议新增 `DialogueBook`，它只负责交互对话，不接管 Agent 循环：

```text
DialogueBook
├─ dialogue_id
├─ workspace_fingerprint
├─ created_at / updated_at
└─ entries[]
   ├─ user_instruction
   ├─ run_id
   ├─ status
   ├─ verified_summary
   ├─ changed_files / checks / limitations
   └─ compact_trace（少量最近消息，非完整工具输出）
```

每次用户输入仍创建一个新的 `RunBook`：

1. 交互层从 DialogueBook 投影“此前已验证事实”。
2. Engine 以新指令、新 RunBook 和该事实投影开始执行。
3. 当前 `submit_result` 只能引用当前 RunBook 的 OperationRecord。
4. 任务结束后，把 CompletionReport 和少量对话摘要追加到 DialogueBook。
5. DialogueBook 原子保存到 `.evidencecoder/dialogues/<dialogue-id>.json`。

这样同时满足：用户可以说“再补一个测试”；模型知道前一任务改过什么；完成校验仍只接受
当前任务证据；`/new` 只需换一个 DialogueBook，不触碰工作区。

### 恢复安全

- 保存工作区规范化绝对路径的哈希；恢复时必须匹配当前工作区。
- 记录格式包含 `format_version`；未知版本拒绝载入，不静默误解。
- DialogueBook 不保存 API Key、Authorization header 或完整环境变量。
- 保存采用临时文件加 `os.replace`，避免中途退出留下半个 JSON。
- 对话记录只是上下文，不是可执行指令；恢复后仍必须经过模型、Toolbox 和 Guard。

## 6. 模块改动方案

### 新增模块

| 文件 | 职责 |
|---|---|
| `interactive.py` | 标准输入 REPL、斜杠命令、Ctrl+C、审批状态；不包含 Agent 决策 |
| `dialogue.py` | DialogueBook 数据、原子持久化、恢复、已验证历史投影 |
| `platform_facts.py` | 生成非敏感平台事实：OS、Shell、路径分隔符、当前 Python 可执行命令 |

### 修改模块

| 文件 | 改动 |
|---|---|
| `__main__.py` | 区分一次性/交互模式；增加 `--resume`；保持旧参数兼容 |
| `engine.py` | `run()` 接收只读 prior_context；暴露结构化显示回调；修正执行计时边界 |
| `context_window.py` | 在原始任务前加入平台事实和已验证对话事实，不把它们当工具结果 |
| `display.py` | 横幅、提示符、结果摘要、命令退出码措辞和审批选项 |
| `commands.py` | 以 bytes 捕获输出，优先严格 UTF-8，Windows 回退 OEM/ANSI 编码 |
| `settings.py` | 对话保存开关和 `--resume` 所需设置，不新增密钥文件读取 |

不采用 `Session/Turn/ToolRouter/EventStream` 等参考项目结构。InteractiveShell 只是 UI 循环，
DialogueBook 只是持久数据，Engine 仍是唯一 Agent 流程所有者；没有发布订阅、动态插件或
第二个控制器。完成后需重新运行七仓库相似性扫描，重点检查新增两个模块。

## 7. 真实测试问题的具体修复

### P0-1：平台事实

在系统上下文加入类似以下内容，由程序生成而非用户输入：

```json
{
  "os": "Windows",
  "shell": "cmd.exe",
  "path_separator": "\\",
  "python_executable": "C:\\...\\python.exe",
  "recommended_python_command": "\"C:\\...\\python.exe\""
}
```

只提供执行决策需要的字段，不泄露用户名、环境变量和主目录内容。系统提示明确要求优先
使用 `recommended_python_command`，避免再次尝试 `cat` 和 `python3`。

### P0-2：Windows 输出解码

`subprocess` 改为 bytes 模式：

1. 若输出是合法 UTF-8，按 UTF-8 解码。
2. Windows 下依次尝试当前 OEM code page 和 ANSI code page。
3. 最后才使用替换字符解码，并在 evidence 中记录所用编码和是否发生替换。

测试必须构造 GBK/UTF-8 两类输出，不能只在英文输出上通过。

### P0-3：计时边界

拆分三个概念：请求工具时间、等待审批时间、实际执行时间。OperationRecord 的
`duration_ms` 只表示 Toolbox 执行耗时；可额外记录 `approval_wait_ms`，但不把用户思考
时间伪装成文件写入耗时。拒绝操作的执行耗时为 0。

### P1：显示语义

- `run_local` 退出非零时显示 `executed, exit=1`，不只显示容易误解的 `ok`。
- 模型响应含自然语言 content 时在终端显示，但工具参数仍以本地实际 schema 为准。
- 等待模型时显示当前轮数和完成后的耗时，不实现复杂 spinner 线程。
- 每个任务结束只显示摘要、变更、检查、限制和日志路径，详细记录留在 JSON。

## 8. 测试与验收标准

### 新增自动测试

- 无位置任务且 TTY 时进入 REPL；非 TTY 时不挂起。
- 连续两条指令：第一条创建文件，第二条基于该文件补测试。
- 第二条 `submit_result` 引用第一条旧 op_id 时必须失败。
- `/new` 清除对话上下文但不删除文件。
- `/resume latest` 恢复正确工作区；错误工作区拒绝。
- Ctrl+C 取消当前 Engine 后仍可输入下一条指令。
- 审批 `a` 只作用于当前进程，且硬拒绝规则仍生效。
- Windows GBK、UTF-8 和混合输出可读。
- 人工等待审批不会进入 `duration_ms`。
- 日志和对话文件中搜索不到 API Key 和 Authorization header。
- 原有 21 项测试全部继续通过，一次性 CLI 测试不变。

### 真实 API 验收

准备一个小型 Python 仓库：分页函数在 `size=0` 时失败，并有一条失败测试。交互演示：

1. 第一条指令要求定位并修复 bug、运行测试。
2. Agent 读取、运行失败测试、修改、运行成功测试、提交凭证。
3. 第二条追问“再补一个负数 size 的测试并验证”。
4. Agent 利用前序已验证上下文继续工作，但用新的操作凭证完成第二条任务。
5. 退出后使用 `--resume latest`，`/history` 能看到两条指令及结果。

验收时同时确认：无乱码、没有无意义的 Linux 命令、完成报告引用修改后的成功测试、API Key
不在屏幕和日志中。

## 9. 实施顺序

只有本报告审查通过后才开始：

1. 先为真实测试发现的三个 P0 bug 写失败测试。
2. 实现平台事实、命令解码和计时修正，运行全部回归测试。
3. 实现 DialogueBook 与当前任务凭证隔离。
4. 实现 InteractiveShell、斜杠命令、Ctrl+C 和审批状态。
5. 实现原子保存与 `--resume`。
6. 执行 FakeGateway 双任务测试和真实 API bug 修复测试。
7. 更新 README.md；为 README.txt 增加 Git URL 和交互运行方式，保持 1000 汉字以内。
8. 重新运行七仓库相似性扫描并更新最终报告。
9. 录制不超过 2 分钟的真实任务视频，检查画面中无 API Key。
10. 生成仅含 README.txt 与 MP4 的最终姓名 zip；在截止前完成最后一次推送。

建议按三次本地提交保留清晰历史：

1. `fix: improve platform-aware command execution`
2. `feat: add persistent interactive dialogue`
3. `docs: prepare final demonstration and submission`

## 10. 需要用户审查的决定

建议按以下默认方案实施：

- 不带任务参数时默认进入交互模式；带任务时保持一次性模式。
- 使用独立 DialogueBook，而不是把所有任务塞进一个 RunBook。
- 支持 `/help`、`/status`、`/history`、`/new`、`/resume`、`/paste`、`/exit`。
- 支持本地对话恢复，但不动态切换工作区和模型。
- 审批增加“本进程允许同类操作”，硬拒绝规则不可绕过。
- 优先修复 Windows 平台事实、乱码和计时，再开发交互功能。
- 截止日前不做流式响应、全屏 TUI、插件、MCP、子 Agent、LSP 或自动 Git。
- 用“两轮真实 bug 修复”作为最终视频，而不是 hello world。

审查通过的建议回复为：**“方案通过，可以按 06 报告开始实现。”** 如需删减范围，优先可删
`/paste` 和跨进程 `/resume`；交互循环、当前任务凭证隔离、Windows 修复和提交物补齐不建议删。
