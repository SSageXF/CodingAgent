项目名：EvidenceCoder
公开仓库：https://github.com/SSageXF/CodingAgent

EvidenceCoder 是 Python 3.11+ 本地 Coding Agent，通过 OpenAI-compatible Chat Completions API 使用模型原生 tool calling。项目未使用 Agent 框架或 SDK，自行实现六阶段循环、历史压缩、工具解析与执行、审批、错误恢复和终止条件。

核心特色是“完成声明有凭证”：每次本地操作生成 OperationRecord；submit_result 必须引用真实成功的操作。文件声明对应最新写入，检查声明对应修改后退出码为 0 的命令。交互模式中每条指令使用独立 RunBook，旧凭证不能证明新任务。

安装：python -m pip install -e .
配置：复制 .env.example 为 .env 并填写模型、API 地址和 Key；.env 已被 Git 忽略。
交互运行：evidencecoder --workspace <项目目录>
一次性运行：evidencecoder --workspace <项目目录> "任务描述"
测试：python -m pytest

CLI 提供彩色状态、写入前 diff、调用/token/耗时统计，以及 /history、/resume、/retry、/export 等命令；/resume 会列出对话供选择，/resume latest 仍可直接恢复最近对话。固定工具支持目录、单个或批量读取、搜索、精确写入、命令执行和只读 Git 状态/diff。默认写入和命令需确认；--yes 不能绕过 git push、git reset --hard、系统关机、磁盘格式化和工作区整体递归删除等硬拒绝规则。本项目不是操作系统沙箱，不应以高权限处理不可信项目。
