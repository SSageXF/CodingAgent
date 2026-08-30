项目名：EvidenceCoder
公开仓库：https://github.com/SSageXF/CodingAgent

EvidenceCoder 是一个 Python 3.11+ 本地 Coding Agent，通过 OpenAI-compatible Chat Completions API 使用模型原生 tool calling。项目未使用任何 Agent 框架或 SDK，自行实现六阶段循环（上下文构造、模型请求、参数检查、授权、执行、评估）、历史压缩、文件与命令工具、错误恢复和终止条件。

核心特色是“完成声明有凭证”：每次工具调用都会生成 OperationRecord；模型必须使用 submit_result，并引用真实成功的操作编号。文件声明必须对应最新写入，检查声明必须对应修改后退出码为 0 的命令，从而降低模型虚构“已经修改、测试已通过”的风险。

安装：python -m pip install -e .
配置：设置 EVIDENCECODER_MODEL、EVIDENCECODER_BASE_URL、EVIDENCECODER_API_KEY。
交互运行：evidencecoder --workspace <项目目录>
一次性运行：evidencecoder --workspace <项目目录> "任务描述"
恢复对话：evidencecoder --workspace <项目目录> --resume latest
测试：python -m pytest

交互模式可连续输入任务，支持 /help、/status、/history、/new、/resume、/paste、/exit。每条任务使用独立 RunBook，前序对话只投影已验证事实，旧凭证不能证明新任务。默认写入和命令需要人工确认；--yes 可预批准普通操作，但不能绕过 git push、git reset --hard、系统关机、磁盘格式化和工作区整体递归删除等硬拒绝规则。本项目不是操作系统沙箱，不应以高权限处理不可信项目。
