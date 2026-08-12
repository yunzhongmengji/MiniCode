# ADR-0001：从基础协议构建 Agent Runtime

状态：Accepted  
日期：2026-08-09

## 背景

用户已经阅读过一个使用 LangChain AgentExecutor 和 tool 装饰器的完整 RAG 项目。这些框架让应用能够快速运行，但隐藏了本项目最需要学习和证明的部分：

- Query Loop 和状态迁移
- Tool Call 解析、参数校验和统一错误
- 轮次、Token、费用、时间与无进展预算
- 权限审查、审批和副作用治理
- 事件、回放、上下文与多 Agent 协议

如果继续以大型 Agent 框架为核心，本项目容易成为另一层业务封装，无法形成足够的学习深度和简历差异化。

## 决策

- 使用 Python 标准类型、dataclass/Protocol 和边界 Schema 手写核心 Runtime。
- 使用 Scripted Fake Model 建立确定性测试。
- 模型供应商 SDK 仅存在于 Adapter 层。
- 不使用 LangChain、LangGraph 或同类框架实现核心 Query Loop。
- 后期可以增加框架 Adapter 或对照实验，但不能成为核心依赖。

## 正面后果

- 可以观察和测试每个状态转移。
- 权限与执行边界由程序控制。
- Provider、Tool、Skill 和 Memory 可以独立替换。
- 面试时能够解释框架内部机制及设计取舍。
- 能构造精确的故障注入和回放。

## 负面后果

- 初期开发速度较慢。
- 需要自行处理流式、重试、取消和兼容性。
- 不能直接获得框架的生态集成。
- 接口设计错误会带来重构成本。

这些成本正是本项目希望学习的工程问题，因此可以接受。

## 备选方案

1. 继续使用 LangChain AgentExecutor：开发快，但核心机制仍被隐藏。
2. 使用 LangGraph：状态图更清晰，但会把重点变成框架使用。
3. 直接修改现有开源 Coding Agent：真实度高，但不利于形成从零实现能力。

## 重新评估条件

- 核心 Runtime 已完成且通过 Benchmark。
- 需要验证与现有企业 Agent 框架的集成成本。
- 某项非核心协议维护成本明显超过教学收益。

