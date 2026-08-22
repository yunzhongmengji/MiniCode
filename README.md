# MiniCode

MiniCode 是一个从零实现的、本地优先、可审计、可复现的 Coding Agent Runtime。

它不是 LangChain Agent 的再次封装，也不以复刻某个闭源产品为目标。项目重点是亲手实现并验证：

- Query Loop 与结构化 Tool Calling
- 受控代码工具、权限策略与人工审批
- 可回放事件账本、Artifact 与 Checkpoint
- Skill 路由、自动记忆和分层上下文压缩
- 中心化多 Agent 调度与最小权限
- 可执行 Benchmark、故障注入和安全红队

当前状态：M2 最小 Query Loop 已完成，准备进入 M3 Tool Runtime。

## 项目证据

- [项目契约](docs/PROJECT_CHARTER.md)
- [学习与实现路线](docs/ROADMAP.md)
- [同类项目调研](docs/research/landscape.md)
- [评测方案](docs/EVALUATION.md)
- [威胁模型](docs/THREAT_MODEL.md)
- [Query Loop 设计](docs/QUERY_LOOP.md)
- [学习日志](docs/LEARNING_LOG.md)
- [中文学习笔记](docs/learning/README.md)
- [架构决策记录](docs/adr/)

## 项目定位

第一版目标是成为一个能够在真实中型 Python 仓库上安全完成代码问答、局部修改、测试与审计的工程原型。任何效率、成功率或成本收益，都必须来自固定数据集、原始运行记录和可复现实验，未测量前不写入简历。
