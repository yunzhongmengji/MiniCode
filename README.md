# MiniCode

MiniCode 是一个从零实现的、本地优先、可审计、可复现的 Coding Agent Runtime。

它不是 LangChain Agent 的再次封装，也不以复刻某个闭源产品为目标。项目重点是亲手实现并验证：

- Query Loop 与结构化 Tool Calling
- 受控代码工具、权限策略与人工审批
- 可回放事件账本、Artifact 与 Checkpoint
- Skill 路由、自动记忆和分层上下文压缩
- 中心化多 Agent 调度与最小权限
- 可执行 Benchmark、故障注入和安全红队

当前状态：M0 至 M7 的分层组件已经完成；当前开发分支进一步把 DashScope 模型、Query Loop、安全 Coding Tools、默认 Policy、终端 Approval、Event Ledger 和 Artifact 引用组装成可从 CLI 启动的 Coding Agent 垂直切片。

## 快速运行

在准备操作的项目根目录中配置 DashScope API Key：

```bash
read -rsp "DashScope API Key: " DASHSCOPE_API_KEY
echo
export DASHSCOPE_API_KEY
```

运行任务：

```bash
minicode run "检查相关代码并运行测试"
```

输出有序执行事件及工具结果的 Artifact 元数据：

```bash
minicode run "检查相关代码并运行测试" --trace
```

`read_file` 和 `search_text` 默认允许；`edit_file` 和 `run_tests` 每次调用都需要终端确认。命令运行目录是 Workspace 根目录。当前 Trace、Event 和 Artifact 只保存在进程内，尚不提供跨进程恢复或持久审计。

## 项目证据

- [项目契约](docs/PROJECT_CHARTER.md)
- [学习与实现路线](docs/ROADMAP.md)
- [同类项目调研](docs/research/landscape.md)
- [评测方案](docs/EVALUATION.md)
- [威胁模型](docs/THREAT_MODEL.md)
- [Query Loop 设计](docs/QUERY_LOOP.md)
- [Tool Runtime 与 Workspace 设计](docs/TOOL_RUNTIME.md)
- [安全 Coding Tools 设计](docs/SAFETY_TOOLS.md)
- [Model Adapter 设计](docs/MODEL_ADAPTER.md)
- [Event Ledger、Artifact、Checkpoint 与 Replay 设计](docs/EVENT_LEDGER.md)
- [Skill System 设计](docs/SKILL_SYSTEM.md)
- [Coding Agent 垂直切片](docs/CODING_AGENT.md)
- [学习日志](docs/LEARNING_LOG.md)
- [中文学习笔记](docs/learning/README.md)
- [架构决策记录](docs/adr/)

## 项目定位

第一版目标是成为一个能够在真实中型 Python 仓库上安全完成代码问答、局部修改、测试与审计的工程原型。任何效率、成功率或成本收益，都必须来自固定数据集、原始运行记录和可复现实验，未测量前不写入简历。
