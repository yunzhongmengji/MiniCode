# Architecture Decision Records

ADR 用于记录对系统边界有长期影响的决定。

每份 ADR 至少包含：

- 状态与日期
- 背景
- 决策
- 备选方案
- 正面与负面后果
- 何时需要重新评估

已记录：

- [ADR-0001：从基础协议构建 Agent Runtime](0001-build-agent-runtime-from-primitives.md)
- [ADR-0002：使用结构化历史与执行前预算](0002-structured-query-loop-and-budgets.md)
- [ADR-0003：使用集中式工具分发与 Workspace 文件边界](0003-centralized-tool-dispatch-and-workspace-boundary.md)
- [ADR-0004：使用 Provider 无关的模型边界与 OpenAI 兼容 Adapter](0004-provider-neutral-model-boundary.md)
- [ADR-0005：分离流式事件、模型调用观测与 Query Loop 总时限](0005-stream-events-observation-and-total-timeout.md)
- [ADR-0006：集中实施工具策略并使用受限 argv 子进程](0006-centralized-tool-policy-and-bounded-process.md)
