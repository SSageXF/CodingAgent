# 实现复核与逐库模块映射

> 本文针对当前 `0.1.0` 实现。自动相似性扫描的固定版本、命中结果和最终结论将在功能冻结后写入 `04_FINAL_SIMILARITY_REPORT.md`。

## 1. 自研模块事实

当前运行时代码是 Python 单进程 CLI，共有八个职责边界：

| 自研模块 | 状态/职责 | 有意避免的结构 |
|---|---|---|
| `engine.py` | 唯一控制流所有者；六阶段顺序循环 | Session/Turn 类族、Controller/EventStream、Agent/Environment 双层驱动 |
| `runbook.py` | 只追加 transcript 与 OperationRecord；没有订阅者 | 事件总线、持久会话服务、Git trajectory |
| `context_window.py` | RunBook 的请求投影和事实兜底压缩 | Repo Map、远端线程、分层 context manager |
| `toolbox.py` | 七个固定 schema 的校验与一次分派 | 动态 registry、插件、MCP、扩展覆盖 |
| `guard.py` | 工具执行前的 allow/ask/deny | 权限 profile 合并、沙箱策略仿真 |
| `completion.py` | 完成声明与 op_id、写入顺序、命令退出码核验 | 普通“完成”文本或仅靠模型判断 |
| `tool_impl/files.py` | 工作区边界、原子文本写入和哈希事实 | 专用 diff 语言、Git edit block、LSP |
| `tool_impl/commands.py` | 每次独立 Shell、超时和输出截断 | 长期终端会话、Docker Runtime |

## 2. 逐仓库实现级映射

### openai/codex — 风险：中低

两者都有上下文、工具、审批和循环，这是产品问题的必然交集。Codex 的核心以 Rust
Session/Turn/StepContext、ToolRouter/Registry、事件协议、app-server 和 OS 沙箱组成；
本项目没有这些层次。`Engine` 直接拥有一个同步循环，`Toolbox` 是构造时固定字典，
`RunBook` 不能发布事件。独有的结束条件是 `submit_result` 对 OperationRecord 做顺序凭证
核验。没有发现能够与 Codex 整模块一一对应的自研模块。

### Aider — 风险：低

本项目没有 Coder 子类、Repo Map、Git 状态、自动提交或编辑格式解析。`replace_text`
接收原生 JSON 参数，仅在旧文本匹配数等于 `expected_count` 时原子写入；它不解析或生成
SEARCH/REPLACE block。共同点限于读取、精确修改和运行测试等基础能力。

### mini-SWE-agent — 风险：中低

同为小型 Python Agent，但 mini-SWE-agent 的主要动作空间是 Bash，消息轨迹由
Agent/Environment/Model 协作推进。本项目有七个 typed tools、平台审批、RunBook 投影和
完成凭证；模型不能用普通文本结束。`Engine` 没有 Environment 对象，也不解析模型输出的
命令文本。规模接近，需要继续用 AST 扫描排除无意函数结构相似。

### OpenHands — 风险：低

本项目没有 Action/Observation 类族、AgentController、EventStream、Runtime、Server 或
Docker action executor。OperationRecord 是普通不可变事实记录，不驱动组件、不广播事件。
“模型意图与环境事实分离”属于通用原则，具体表达方式不同。

### Cline — 风险：中低

两者都有 schema 工具、审批和显式完成动作，但本项目没有 SDK/Core/应用分层、IDE、
daemon、checkpoint、hook、MCP 或计划模式。`submit_result` 不是简单完成信号：它必须核对
最新写入和修改后的成功命令，这构成不同的状态与失败语义。

### Goose — 风险：低

本项目不含 Extensions、Profile、Exchange、Notifier、MCP、ACP 或桌面端。工具错误回到
模型、命令输出受限属于通用可靠性机制；固定 Toolbox 和单 Engine 与 Goose 的扩展架构
不存在模块对应关系。

### OpenCode — 风险：中低

两者都有工具参数校验、权限和上下文压缩。OpenCode 使用 TypeScript/Bun、Session 服务、
动态 ToolRegistry、权限规则、主/子 Agent 和后台能力；本项目是同步 Python 进程、固定工具
表和单次 RunBook 投影。精确替换只使用 Python 字符串计数与临时文件原子替换，没有复刻
OpenCode edit 工具的 schema、锁或服务结构。

## 3. 当前人工结论

截至当前实现，没有发现连续复制的源码、注释、提示词、schema 文案或测试，也没有发现
通过改名形成的整模块对应。最高剩余风险来自与 Codex、mini-SWE-agent、Cline 和 OpenCode
解决同一领域问题，风险等级为中低；必须以固定提交的 token/AST 扫描完成最后核查。

本结论不是法律意见。功能冻结前若新增插件、会话服务、Git 自动化或动态工具架构，需要
重新进行模块映射。
