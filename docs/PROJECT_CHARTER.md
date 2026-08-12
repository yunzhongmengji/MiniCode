# MiniCode 项目契约

状态：已接受，后续可通过 ADR 修订  
建立日期：2026-08-09

## 1. 用户学习基线

用户阅读过一个 FastAPI + LangChain + RAG 应用，对以下概念有一定了解：

- FastAPI 路由、JWT、MySQL、Redis 与 SSE
- LangChain Agent、Tool Calling 和 Prompt
- 文档切分、Embedding、向量检索、混合检索与重排
- 基础异步任务、队列和流式响应

用户目前没有独立项目经历，尚未从空目录完成过完整项目，对部分文件的职责、目录组织、模块调用流程和工程工具并不熟悉。阅读过代码不等于掌握，因此本项目不能默认用户理解任何文件或流程。

教学会利用已有概念认知减少重复，但在首次出现每种文件、目录、配置、命令和调用链时，必须解释其用途、使用者、输入输出、生命周期以及它与其他模块的关系。随后由用户亲手实现核心部分。

## 2. 产品定位

MiniCode 的准确定位是：

> 可审计、可复现、本地优先的 Coding Agent Runtime 教学与工程项目。

不使用“完全复刻 Claude Code”“企业级通用平台”或“生产就绪”等无法证明的表述。

## 3. 产品目标

第一版必须形成完整运行链路：

1. 用户通过 CLI 创建、观察、取消和恢复任务。
2. Model Adapter 将不同模型响应归一化为统一协议。
3. Query Loop 管理状态、预算、重试和停止条件。
4. 模型提出 Tool Call，由 Tool Registry 校验。
5. Policy Engine 进行确定性的权限判断和精确审批。
6. 隔离 Worker 执行 read、search、edit、test 等受控能力。
7. 所有关键动作写入结构化事件账本，大结果保存为 Artifact。
8. Skill、Memory 和 Context Builder 只注入可追溯的必要信息。
9. 主 Agent 可以派发受限 Worker/Fork，并独立验收结果。
10. Benchmark 输出正确性、安全性、Token、成本和延迟报告。

## 4. 学习目标

项目完成后，用户应能独立：

- 画出 Agent Runtime 的状态机和数据流。
- 新增 Tool，并定义 Schema、错误、幂等性、副作用和权限。
- 接入新的模型 Provider，而不修改核心循环。
- 从 Trace 定位循环失控、工具失败和上下文丢失。
- 解释 Memory 污染、Prompt Injection 和子 Agent 提权风险。
- 设计 Skill 路由、上下文压缩和缓存消融实验。
- 实现子任务取消传播、超时和并发写冲突检测。
- 为新的失败模式补充测试与安全策略。

## 5. 第一版非目标

- IDE 插件和复杂图形界面
- 多租户、高可用的分布式 Agent 平台
- 无限制宿主机 Shell
- 自动推送、发布或生产环境变更
- 一开始引入向量数据库、Redis 或 Kubernetes
- 使用大型 Agent 框架替代核心 Runtime

## 6. 工程不变量

- 模型提出动作，但不拥有权限。
- 所有外部输入、仓库内容、Skill、Memory、工具结果和子 Agent 消息默认不可信。
- 每次 Tool 执行前必须存在可追溯的 Policy Decision。
- 子 Agent 权限、预算和作用域只能收缩，不能扩大。
- 大结果外置，Prompt 中保留摘要、哈希和引用。
- 关键测试默认使用 Scripted Fake Model，不依赖网络。
- 任何简历指标都必须可从原始 Benchmark 结果复算。

## 7. 可交付证据

- 架构图、威胁模型、权限矩阵与 ADR
- 离线确定性测试、真实模型 E2E 与红队用例
- 完整成功 Trace、失败 Trace 和 Checkpoint 恢复演示
- 固定 Benchmark 数据集、原始 JSON 与自动生成报告
- Memory、Compression、Cache、多 Agent 的消融实验
- 一条命令启动、一条命令运行离线评测
- CI 记录、覆盖率、镜像与依赖扫描结果

## 8. 最终真实验证

后期将把上级目录中的 LangChain-RAG-FastAPI-Service 作为只读来源，复制为受控 Fixture 或临时工作区。MiniCode 需要发现并安全修复其中的真实工程问题，生成补丁、测试、审批链和可回放 Trace；不会直接修改原项目。
