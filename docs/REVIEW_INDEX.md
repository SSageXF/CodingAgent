# EvidenceCoder 方案审查入口

> 状态：**设计及扩展均已审查通过，0.3.1 实现、测试与相似性复核已完成**
> 调研日期：2026-08-28  
> 原始题目：[推免考核题目学生版.pdf](../推免考核题目学生版.pdf)

## 1. 项目边界

设计阶段完成了以下事项：

1. 记录考核题的硬性约束。
2. 调研 7 个开源 Coding Agent 仓库。
3. 逐库总结架构、优点、局限和可借鉴原则。
4. 从调研结论出发，设计一个独立实现的 Coding Agent。
5. 在代码产生前进行模块级相似性预审，并规定实现后的正式核查方法。

设计审查通过后，已从空白目录开始实现 Agent 源码；仍未引入 Agent 框架，也没有把任何参考仓库复制到项目源码。`openai/codex` 的早期浅克隆仅位于系统临时目录，用于只读研究，不属于项目或未来提交物。

## 2. 文档顺序

1. [逐库调研](01_REPOSITORY_REVIEWS.md)
2. [汇总设计](02_PROPOSED_DESIGN.md)
3. [相似性预审](03_SIMILARITY_AUDIT.md)
4. [实现复核与逐库模块映射](04_IMPLEMENTATION_REVIEW.md)
5. [最终模块级相似性核查报告](05_FINAL_SIMILARITY_REPORT.md)
6. [交互式 CLI 与提交完善方案](06_INTERACTIVE_CLI_PROPOSAL.md)
7. [0.3.0 CLI 与工具扩展实施记录](07_CLI_AND_TOOL_EXPANSION.md)

建议先审查汇总设计，再用逐库调研和相似性预审验证设计来源与独立性。

## 3. 考核要求基线

以下要求在后续实现中不可变更：

- 独立实现能够读写文件、执行本地命令并迭代完成编程任务的 Agent。
- 不在现有 Agent 产品上套壳。
- 不使用 LangChain、LlamaIndex、OpenAI Agents SDK、Claude Agent SDK、AutoGen、CrewAI 等 Agent 框架或 SDK。
- 可以使用普通模型 API 客户端、OpenAI 兼容网关和模型原生 tool calling。
- 不使用服务端托管的代码执行、Code Interpreter 或 Files API。
- 自行实现上下文管理、工具定义与本地执行、模型输出解析、循环终止和错误处理。
- API Key 只通过环境变量或未入库配置提供。
- 截止时间为 2026-09-02 24:00（北京时间）。

## 4. 本次选择的参考仓库

| 仓库 | 主要研究价值 | 许可证 |
|---|---|---|
| [openai/codex](https://github.com/openai/codex) | 完整 harness、工具路由、上下文、审批和跨平台沙箱 | Apache-2.0 |
| [Aider-AI/aider](https://github.com/Aider-AI/aider) | Git 感知、仓库地图、编辑格式 | Apache-2.0 |
| [SWE-agent/mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) | 极简循环、环境抽象、轨迹记录 | MIT |
| [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) | Action/Observation、控制器、事件流、隔离运行时 | MIT；`enterprise/` 例外 |
| [cline/cline](https://github.com/cline/cline) | 无状态循环、工具策略、人工审批、会话层 | Apache-2.0 |
| [aaif-goose/goose](https://github.com/aaif-goose/goose) | 扩展工具、错误回灌、上下文修订 | Apache-2.0 |
| [anomalyco/opencode](https://github.com/anomalyco/opencode) | 会话循环、工具权限、压缩和 Plan/Build 模式 | MIT |

许可证只用于识别参考材料边界，不代表法律意见。即使许可证允许复用，本项目也不复制这些仓库的模块或源码。

## 5. 已批准的关键决策

- 项目暂定名：`EvidenceCoder`。
- 使用 Python 3.11，实现单进程、单 Agent、同步 CLI。
- 直接调用一个 OpenAI-compatible API，不支持多模型路由。
- 固定提供 10 个本地工具；新增批量读取和只读 Git 观察，不实现 MCP、插件、浏览器、
  多 Agent、Git 写操作或 GUI。
- 使用“执行凭证”作为特色：Agent 声称完成时必须引用真实工具执行记录。
- 文件工具严格限制在工作区；Shell 默认需要确认，并明确不把“仅设置 cwd”冒充为安全沙箱。
- 上下文采用运行记录簿与活动窗口分离，不复制任何参考库的消息/事件模块。

## 6. 设计审查结果

设计阶段重点检查了：

- 功能范围是否适合剩余时间。
- “执行凭证”是否值得作为核心特色。
- 工具集合是否需要增删。
- 默认审批策略是否合适。
- 是否接受只支持 OpenAI-compatible tool calling。
- 模块结构是否足够独立、可解释。
- 相似性核查门槛是否足够严格。

用户已于 2026-08-28 明确回复“审查通过，可以开始”，随后才进入编码阶段。实现后的
测试结果与正式相似性核查见上述第 4、5 份文档。

用户随后于 2026-08-30 审查通过第 6 份交互式方案；`0.2.0` 按该方案实现，并再次完成
七仓库模块级扫描。真实 API 最终演示仍需用户在其已配置密钥的终端中执行。

同日用户继续审查通过 CLI 美化与工具扩展；`0.3.0` 保持 Engine 单一控制流，引入 Rich
显示、三个固定只读工具、用量统计、重试和报告导出，并完成第三次七仓库复扫。

随后 `0.3.1` 为 `/resume` 增加工作区对话列表和序号选择，同时保留 `latest` 与 ID 恢复；
实现仍是现有行式 InteractiveShell 的小型扩展，并完成复扫。
