EvidenceCoder - 本地编程智能体

一、Git 仓库
https://github.com/SSageXF/CodingAgent
公开仓库。

二、安装与配置
要求 Python 3.11+、Git 及支持 tools/tool_calls 的 OpenAI 兼容接口。
git clone <上述仓库地址>
cd CodingAgent
python -m pip install -e .
复制 .env.example 为 .env，填写模型名、接口地址和 API Key。.env 不上传仓库，视频中也不得展示。

三、运行
交互：python -m evidencecoder --workspace <项目目录>
也可在命令末尾直接附加任务。支持历史、恢复、重试和报告导出；写入及命令默认需要人工批准。

视频演示：
$demo = powershell -ExecutionPolicy Bypass -File .\demo\prepare_video_demo.ps1
python -m evidencecoder --workspace $demo
输入：请先读取 VIDEO_TASK.txt，然后严格按照文件中的要求完成任务。

四、特色功能
1. 不使用 Agent 框架/SDK，自行实现上下文管理、工具协议、输出解析、循环终止和错误处理。
2. 10 个固定工具覆盖目录、分段/批量读取、搜索、精确修改、写入、本地命令及只读 Git；文件操作限制在工作区。
3. 本地操作生成不可变凭证；最终声明必须引用本轮成功操作，成功测试必须晚于最新修改，避免无证据完成。
4. 支持写入 diff、人工审批、API 重试、命令超时、卡死检测、用量统计和 JSON 记录。
5. 支持连续对话、上下文压缩、原子保存、列表恢复及报告导出。

五、测试与限制
安装开发依赖：python -m pip install -e ".[dev]"
运行测试：python -m pytest
结果为 47 passed、1 skipped；另通过三个真实 API 案例。设计、开源调研和逐库相似性核查见 docs/。

本地命令不是系统沙箱，可能访问工作区外资源；未知任务勿使用高权限或 --yes。项目不依赖服务端代码执行/Files API，不自动提交或推送 Git。
