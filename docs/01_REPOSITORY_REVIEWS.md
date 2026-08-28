# 开源 Coding Agent 逐库调研

## 1. 调研方法

调研只使用各项目的官方仓库、仓库内文档和官方产品文档，关注以下问题：

- Agent 循环放在哪里，怎样继续或终止。
- 模型接口与工具执行如何分离。
- 文件、Shell、补丁工具如何组织。
- 历史、上下文和压缩如何管理。
- 权限、审批和沙箱如何处理。
- 哪些结构不能直接迁移到本考核项目。

这里整理的是架构事实与设计原则，不复制源码、提示词、类型名或目录结构。

---

## 2. openai/codex

### 定位与范围

`openai/codex` 是以 Rust 为主体的大型 monorepo。OpenAI 官方资料将其描述为供 CLI、IDE 和应用端复用的开源 Agent harness：负责维持上下文、流式执行、工具调用、沙箱与审批，并通过 app-server 暴露线程、轮次和事件协议。

本次对仓库 `main` 分支提交 `6be2a6ca952ac9f70676ce4dd07fda27175aa9dd` 做了临时浅克隆检查。

### 关键结构

- `codex-rs/core/src/session/`：Session、Turn、StepContext、活动轮次和输入队列。
- `codex-rs/core/src/session/turn.rs`：`run_turn` 以及请求—工具—再请求的主要循环。
- `codex-rs/core/src/context_manager/`：历史记录、规范化、截断和提示投影。
- `codex-rs/core/src/compact*.rs`：本地/远端压缩和 token 预算。
- `codex-rs/core/src/tools/router.rs`：某一轮最终可见工具及其路由。
- `codex-rs/core/src/tools/registry.rs`：工具运行时注册与分发。
- `codex-rs/core/src/tools/approvals.rs`：集中式审批策略和请求路由。
- `codex-rs/core/src/sandboxing/` 及独立 sandbox crates：跨平台执行隔离。
- `codex-rs/app-server/`：把线程、轮次、事件和审批暴露给不同客户端。

典型循环是：构造当前轮上下文，向模型发起流式请求；若完成项是工具调用，则路由和执行工具、记录结果，并再次采样；若只得到最终助手消息，则本轮完成。上下文逼近预算时会执行压缩。

### 值得学习的原则

- 工具“模型可见描述”与“本地可执行实现”是两个边界。
- 审批必须发生在模型无法绕过的平台层。
- 历史写入、发送给模型前的规范化以及压缩是不同操作。
- 沙箱必须由操作系统能力真正执行，单纯把进程 cwd 设到项目目录不等于沙箱。
- 流式响应、工具生命周期和客户端事件需要一致的状态模型。

### 本项目不采用

- 不采用 Rust crate 分层和 `Session → Turn → StepContext` 对象层级。
- 不采用 ToolRouter/ToolRegistry 双层结构、app-server 协议或事件总线。
- 不采用 Codex 的工具名、权限 profile、Guardian、rollout/world-state 等命名与模块组织。
- 不实现多 Agent、插件、MCP、远程线程、流式 UI 或跨平台强沙箱。
- 不复制 Codex 提示词、审批模板和上下文片段。

### 资料

- [OpenAI：Codex as a platform](https://developers.openai.com/blog/codex-as-a-platform)
- [OpenAI Codex 开源组件说明](https://learn.chatgpt.com/docs/open-source)
- [官方仓库](https://github.com/openai/codex)
- [codex-core README](https://github.com/openai/codex/tree/main/codex-rs/core)

---

## 3. Aider

### 定位与结构

Aider 是 Python 编写、以终端和 Git 仓库为中心的结对编程工具。核心 `Coder` 负责对话、文件集合、模型调用、编辑格式、Git、测试和反思；不同 coder 子类实现不同编辑格式。

它的突出设计是 Repo Map：提取仓库中的关键符号和依赖关系，在 token 预算内向模型提供全局结构。另一个特点是专门设计的编辑格式，包括整文件和 SEARCH/REPLACE 块。

### 值得学习的原则

- 大仓库不能把所有源码直接塞入上下文，应提供紧凑结构线索。
- 小范围精确替换通常比整文件重写节省 token，也更容易审查。
- 修改后自动 lint/test 能形成验证闭环。
- 对模型畸形编辑结果应反馈错误并允许有限次数的反思重试。

### 本项目不采用

- 不实现 Repo Map、Tree-sitter 符号图或图排序。
- 不采用 `Coder` 大类及其 coder 子类体系。
- 不采用 Aider 的 SEARCH/REPLACE 文本协议；本项目使用原生 tool calling 的 JSON 参数。
- 不自动提交 Git，也不把 Git 作为核心状态。
- 不采用 Architect/Editor 双模型模式。

### 资料

- [官方仓库](https://github.com/Aider-AI/aider)
- [核心 Coder](https://github.com/Aider-AI/aider/blob/main/aider/coders/base_coder.py)
- [Repo Map](https://github.com/Aider-AI/aider/blob/main/aider/website/docs/repomap.md)
- [编辑格式](https://github.com/Aider-AI/aider/blob/main/aider/website/docs/more/edit-formats.md)

---

## 4. mini-SWE-agent

### 定位与结构

mini-SWE-agent 强调极简和可读性。它把系统拆成 `agents`、`environments`、`models` 和 `run`：Agent 保存线性消息列表，循环调用模型；模型输出动作；Environment 使用独立的 `subprocess` 执行动作；每一步都追加到轨迹。

默认形态主要依赖 Bash，而不是为读取、搜索、编辑分别定义工具。它包含步数、费用、墙钟时间和连续格式错误限制，并能保存完整 trajectory。

### 值得学习的原则

- 主循环应该小到可以完整解释和单元测试。
- 模型、循环与执行环境应通过小接口隔离。
- 每次命令独立执行，比维护隐藏的长期 Shell 状态更容易复现。
- 步数、成本、时间和格式错误都是一等终止条件。

### 本项目不采用

- 不采用 Bash-only 动作空间。
- 不采用“模型输出命令文本再解析”的协议。
- 不采用完全线性的消息列表作为唯一状态。
- 不复制 `Agent → Environment → Model` 的目录和类命名。
- 不依赖 LiteLLM；它可能被评委视为扩大了外部编排依赖。

### 资料

- [官方仓库](https://github.com/SWE-agent/mini-swe-agent)
- [默认 Agent](https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/agents/default.py)
- [本地环境](https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/environments/local.py)
- [仓库结构说明](https://github.com/SWE-agent/mini-swe-agent/blob/main/AGENTS.md)

---

## 5. OpenHands

### 定位与结构

OpenHands 是完整的软件工程 Agent 平台。其经典架构把模型决策表示为 Action，把环境结果表示为 Observation；AgentController 管理 State 并驱动循环，EventStream 负责各组件之间的事件传递，Runtime 在 Docker 等隔离环境中执行动作。

这套设计适用于后端、前端、会话和多个运行时共同参与的大系统，但明显超出本考核的时间与规模。

### 值得学习的原则

- 模型意图与环境事实应该是不同的数据类型。
- 执行结果应进入显式状态，而不是仅打印到终端。
- 真正执行任意代码时，容器化运行时比提示词约束可靠。
- Agent 状态转换、预算和卡死检测应由控制器掌握。

### 本项目不采用

- 不实现 EventStream、发布订阅或 Action/Observation 类族。
- 不实现 AgentController/Runtime/Server/Session 的平台分层。
- MVP 不要求 Docker，因此不声称提供 OpenHands 级隔离。
- 不采用 CodeAct 的代码动作协议或提示词。

### 资料

- [官方仓库](https://github.com/OpenHands/OpenHands)
- [Runtime 架构](https://github.com/OpenHands/docs/blob/main/openhands/usage/architecture/runtime.mdx)
- [OpenHands 架构论文](https://arxiv.org/abs/2407.16741)

---

## 6. Cline

### 定位与结构

Cline 已发展为 IDE、CLI 和 SDK 共用的 TypeScript Agent 系统。当前 SDK 把职责分成：模型提供方、无状态 Agent 循环、带会话持久化的 Core，以及应用/UI。工具由 schema、执行函数和策略组成；策略决定工具是否可见以及是否需要批准。

### 值得学习的原则

- 只读工具、写工具和命令工具应该有不同审批等级。
- 工具被拒绝也应形成模型可见结果，让 Agent 调整方法。
- 循环与持久化会话分离，有利于测试。
- 显式完成信号比“进程关闭即完成”更可靠。

### 本项目不采用

- 绝不依赖 `@cline/sdk`，因为它本身就是题目禁止使用的 Agent SDK。
- 不采用 `agents/core/shared/llms` 包布局。
- 不实现 hub、daemon、插件、hooks、团队或计划/执行模式。
- 不复制 Cline 的工具清单、工具名、审批示例或完成工具协议。

### 资料

- [官方仓库](https://github.com/cline/cline)
- [SDK 架构](https://github.com/cline/cline/blob/main/sdk/ARCHITECTURE.md)
- [工具与策略](https://github.com/cline/cline/blob/main/docs/sdk/tools.mdx)
- [权限处理](https://github.com/cline/cline/blob/main/docs/sdk/guides/permission-handling.mdx)

---

## 7. Goose

### 定位与结构

Goose 是 Rust 编写的本地 Agent。它把界面、Agent 和 Extensions 分开；扩展通过工具为 Agent 提供 Shell、文件等能力，并大量使用 MCP。其循环会把工具错误作为结果反馈给模型，也会修订上下文以控制 token。

### 值得学习的原则

- 工具失败应反馈给模型，而不是直接终止整个进程。
- 命令输出需要截断或总结，否则一次长输出就可能挤满上下文。
- 工具可用范围和超时应该显式配置。
- 高风险动作需要平台层确认，处理不受信任仓库时还要考虑 Prompt Injection 与 Git 配置等非模型风险。

### 本项目不采用

- 不实现 Extensions、Profile、Exchange、Notifier 或 MCP。
- 不复制 Goose 的 Developer 扩展和上下文修订流程。
- 不使用多模型 planner/accelerator 结构。
- 不实现桌面端或 ACP。

### 资料

- [官方仓库](https://github.com/aaif-goose/goose)
- [架构说明](https://github.com/aaif-goose/goose/blob/main/documentation/docs/goose-architecture/goose-architecture.md)
- [安全说明](https://github.com/aaif-goose/goose/security)

---

## 8. OpenCode

### 定位与结构

OpenCode 是以 TypeScript/Bun 为主体的终端、桌面和 IDE Coding Agent。主要循环位于 session/prompt 相关模块；工具通过 registry 组织；Agent 的可用工具由权限规则控制；会话压缩负责裁剪工具输出并生成摘要。它还提供 Build/Plan 主 Agent 和多个子 Agent。

### 值得学习的原则

- 最大迭代步数应该是显式配置。
- 工具参数先经过 schema 校验，再进入执行层。
- 权限决定工具能否被模型看到，执行前还可以再次检查。
- 精确文本替换必须处理“旧文本不存在、重复匹配、并发写入”等失败。

### 本项目不采用

- 不采用 `session/prompt.ts` 式大循环文件或 Effect 服务结构。
- 不实现 primary/subagent、Build/Plan、后台任务、LSP、插件或 MCP。
- 不采用 OpenCode 的权限规则语法和 session compaction 结构。
- 不复制 `edit` 工具的 schema、描述或锁实现。

### 资料

- [官方仓库](https://github.com/anomalyco/opencode)
- [主循环入口](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/prompt.ts)
- [Agent 与权限](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/agent/agent.ts)
- [上下文压缩](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/compaction.ts)
- [编辑工具](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/tool/edit.ts)

---

## 9. 跨库汇总结论

七个项目反复出现的通用问题只有六类：

1. 如何把用户任务和有效上下文交给模型。
2. 如何把模型工具调用变成本地、可观察的动作。
3. 如何把环境事实返回给模型。
4. 如何限制路径、命令、费用、时间和循环。
5. 如何在上下文变长时保留关键信息。
6. 如何证明 Agent 真的完成，而不是只声称完成。

这些问题属于 Coding Agent 的功能本质，不属于任何单一仓库。独立性应通过自己的数据模型、控制流、模块边界、错误语义、提示词和测试来体现。
