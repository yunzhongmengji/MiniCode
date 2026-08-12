# Coding Agent 项目调研

调研日期：2026-08-09  
原则：借鉴机制和验证方法，不复制产品外壳或不可验证的内部行为。

正式实现对应模块前，应再次核对官方文档，并记录参考仓库的 commit、tag 或文档版本。

## 1. 参考项目与决策

| 项目 | 一手资料 | 借鉴内容 | 不照搬的内容 | 对应阶段 |
|---|---|---|---|---|
| OpenAI Codex | [Repository](https://github.com/openai/codex)、[Security](https://developers.openai.com/codex/security) | 本地优先、模型与执行分层、sandbox、approval policy、项目指令与事件 | Rust/TUI 体量、供应商专有协议和完整产品配置 | M0、M2、M5、M6、M12 |
| Aider | [Repository](https://github.com/Aider-AI/aider)、[Repo Map](https://aider.chat/docs/repomap.html)、[Edit Formats](https://aider.chat/docs/more/edit-formats.html) | Repo Map、Git diff/undo、编辑后 lint/test、多种结构化编辑形式 | 巨大模型兼容矩阵、全部编辑格式、默认自动提交 | M5、M9、M13 |
| OpenHands | [Repository](https://github.com/OpenHands/OpenHands)、[Docs](https://docs.openhands.dev/) | Controller 与 Runtime 隔离、Action/Observation、容器执行、可回放轨迹 | 云平台、复杂前端、分布式运行时 | M2、M6、M10-M12 |
| SWE-agent | [Repository](https://github.com/SWE-agent/SWE-agent)、[Docs](https://swe-agent.com/latest/)、[Paper](https://arxiv.org/abs/2405.15793) | 面向模型设计精简 ACI、History Processor、Patch/Trajectory、容器化评测 | 只面向 SWE-bench 的 issue-to-patch 假设 | M2、M3、M9、M13 |
| Claude Code | [Overview](https://code.claude.com/docs/en/overview)、[Permissions](https://docs.anthropic.com/en/docs/claude-code/permissions)、[Hooks](https://docs.anthropic.com/en/docs/claude-code/hooks)、[Subagents](https://docs.anthropic.com/en/docs/claude-code/sub-agents)、[Memory](https://docs.anthropic.com/en/docs/claude-code/memory) | 分层项目指令、allow/ask/deny、确定性 Hooks、子 Agent 独立上下文和最小权限 | 闭源内部机制；把 Markdown 指令直接当可信长期记忆 | M0、M5、M8、M10、M12 |
| Gemini CLI（备选） | [Repository](https://github.com/google-gemini/gemini-cli)、[Docs](https://geminicli.com/docs/) | Provider、MCP、沙箱、无头模式和结构化输出 | Google 生态耦合与完整扩展平台 | M4、M5、M13 |

## 2. MiniCode 的组合路线

MiniCode 采用以下组合，而不是复刻任一项目：

- Codex 的权限与执行分层
- SWE-agent 的精简 Agent-Computer Interface
- Aider 的 Repo Map、Git diff 和 lint/test 闭环
- OpenHands 的事件流与隔离 Runtime
- Claude Code 的层级指令、Hooks 和子 Agent 最小权限

## 3. 关键差异化

MiniCode 的简历差异化不依赖 UI 或功能数量，而来自：

- 从零实现 Runtime，而不是调用 AgentExecutor。
- 将正确性和安全性合并为 Safe Task Success。
- 每个高级能力都有关闭开关和消融实验。
- Memory 带来源、置信度、作用域、过期和删除机制。
- Approval 绑定精确动作摘要，不能由自然语言伪造。
- 多 Agent 同时量化加速、Token 开销、重复工作和冲突。
- 在真实中型 RAG 仓库上完成安全修复和回放验证。

## 4. 研究纪律

- 不从闭源产品推测未公开实现。
- 不复制大段源码；若参考具体算法，记录许可证、文件和 commit。
- 外部项目只作为设计假设来源，最终以本项目测试验证。
- 任何“更快、更省、更准”的说法必须有同模型、同数据、同预算的对照实验。

