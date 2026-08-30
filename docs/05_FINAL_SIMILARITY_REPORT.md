# 最终模块级相似性核查报告

初次核查：2026-08-28；交互式及 `.env` 配置版本复核：2026-08-30

当前自研源码提交：`ea9ee1a2faf0863c43a8e344a40b1caeb0a3e1ad`

结论：**未发现整模块复制、跨语言翻译或仅改名复刻的证据。**

## 1. 固定参考版本

源码压缩包来自 GitHub 官方 codeload；下载后随即通过 GitHub 官方 API 记录对应分支头。
缓存仅用于只读扫描，位于被 Git 忽略的 `.audit-cache/`，不会进入项目提交。

| 仓库 | 分支 | 记录的提交 SHA | 扫描核心源码文件数 |
|---|---|---|---:|
| openai/codex | `main` | `6be2a6ca952ac9f70676ce4dd07fda27175aa9dd` | 458 |
| Aider-AI/aider | `main` | `5dc9490bb35f9729ef2c95d00a19ccd30c26339c` | 88 |
| SWE-agent/mini-swe-agent | `main` | `25941c89cfbc91eb40b3f8756348c91d9977d57e` | 59 |
| OpenHands/OpenHands | `main` | `b50c60c6728e2ce123ccb6e125bee3eb88ac87d1` | 1234 |
| cline/cline | `main` | `aa4753f4abc8303dcecd5d27cde622215047c21b` | 2945 |
| aaif-goose/goose | `main` | `caf59517cc280dd3523a80131f388024eaaede9d` | 552 |
| anomalyco/opencode | `dev` | `19db518e0a851160cc77230320125563f4cb117f` | 365 |

合计扫描 5701 个参考源码文件和 17 个自研运行时源码文件。参考范围选择各仓库的核心
源码目录；排除 `.git`、依赖 vendor、构建产物、快照和测试夹具，单文件上限 1 MB。
扩展名覆盖 `.py`、`.rs`、`.ts`、`.tsx`、`.js`、`.jsx`。

## 2. 自动筛选方法与结果

扫描脚本为 `scripts/similarity_audit.py`，从本项目规格独立编写。原始 JSON 报告保留在
本地忽略缓存，SHA-256 为
最新版本的本地忽略报告为 `.audit-cache/similarity-report-dotenv.json`，SHA-256 为
`5204F8F0EF514EE08B8EBD56B75561A2102264E071246978333F7DD1565E8CD8`。

| 检查 | 规则 | 结果 |
|---|---|---:|
| 连续文本 | 去空行、去纯注释后，连续 10 行完全相同 | 0 |
| 跨语言 token | 规范化 token 5-gram Jaccard；`≥0.30` 人工复核 | 0 |
| 宽松 token 候选 | Jaccard `≥0.10`，用于观察低分候选 | 0 |
| Python AST | 至少 20 个语句节点；匿名化前序结构 4-gram Jaccard `≥0.80` | 0 |

第一次实验性的 AST 节点直方图会把“不相关但都有 if/for/return”的函数误报为相似，
因此没有采用该结果。正式算法保留控制流节点顺序，抹去变量名和字面量，并严格执行预审
规定的“至少 20 个语句节点”；正式结果为 0 个阈值命中。

逐仓库结果均为：连续 10 行命中 0、token `≥0.30` 命中 0、适用的 Python AST
`≥0.80` 命中 0。由于七库汇总在更宽松的 token `≥0.10` 下仍无候选，不存在需要通过
挑选仓库或文件来解释的边缘命中。

## 3. 跨语言人工模块映射

自动文本工具不能排除跨语言重写，因此按状态所有者、阶段顺序、工具分派、审批、历史、
压缩和完成信号逐库复核。详细证据见 `04_IMPLEMENTATION_REVIEW.md`，结论如下：

- **openai/codex（中低）**：共同领域最多，但本项目没有 Session/Turn、Router/Registry、
  app-server、事件协议或 OS 沙箱；同步六阶段 Engine 与操作凭证完成协议没有整模块对应。
- **Aider（低）**：没有 Coder 类族、Repo Map、Git 核心状态和编辑文本协议。
- **mini-SWE-agent（中低）**：同为小型 Python 项目，但没有 Bash-only 动作空间和
  Agent/Environment/Model 驱动；固定 typed tools 与凭证终止显著不同。
- **OpenHands（低）**：没有 Action/Observation 类族、Controller、EventStream 或 Runtime。
- **Cline（中低）**：没有 SDK/Core/IDE/daemon 分层；`submit_result` 是事实核验而非普通完成信号。
- **Goose（低）**：没有 Extension、Profile、Exchange、MCP 或 ACP。
- **OpenCode（中低）**：没有 Session 服务、动态 registry、主/子 Agent、权限规则合并和
  Effect 服务结构。

交互式版本新增的 `InteractiveShell` 只是行输入调度，`DialogueBook` 只是工作区绑定的持久
事实记录；二者没有事件总线、动态路由、插件或第二套 Agent 控制流。新增模块也未触发任一
自动相似性候选。

## 4. 来源与 Git 历史核查

- 首个提交 `45295c5` 只包含调研、设计、预审和忽略规则，发生在任何 Agent 源码之前。
- 第二个提交 `4763060` 从空白目录加入自研实现、测试和审查脚本，没有大块导入后改名历史。
- 提交 `3503f07` 在现有六阶段 Engine 上增加独立的交互层和对话事实层，并同时加入针对凭证
  隔离、恢复和 Windows 行为的测试，没有导入第三方 Agent 代码。
- 提交 `ea9ee1a` 增加小型 `.env` 配置解析和测试；复扫仍未产生任何模块相似性候选。
- 运行时代码未出现七个参考仓库的项目名、专有类名或许可证头；项目名只在研究/审查文档
  和独立性说明中作为来源出现。
- 没有 Git 子模块、vendor 目录、参考仓库依赖或题目禁止的 Agent SDK。

## 5. 局限与最终判断

相似性阈值只能筛选候选，不能在数学或法律意义上证明“绝对无抄袭”；跨语言语义等价也
不能完全自动判定。本报告通过源码扫描、逐模块人工映射、依赖检查和设计先于源码的 Git
历史形成组合证据。

在上述范围内，七个仓库均未发现“整个模块相似”的抄袭嫌疑。保留的中低风险来自 Coding
Agent 必然共享模型循环、工具调用、上下文和审批等通用问题，不来自代码、提示词、数据
模型或组件层级的复制。当前实现可以进入功能演示和最终提交材料准备阶段。
