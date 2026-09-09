# M8 Memory 阶段交接记录

更新时间：2026-09-09

## 1. 项目目标

MiniCode 是一个从零实现的、本地优先、安全、可审计、可恢复的
AI Coding Agent Runtime。

秋招目标不是堆叠最多功能，而是完成一条可以深入讲解、真实演示和
量化评测的 Coding Agent 主线。

## 2. 已完成阶段

M0–M7 已完成并推送到 origin/main。

当前稳定基线：

- commit：adb650d
- M0：项目环境、CLI、测试工具链、威胁模型
- M1：Message、ToolCall、ToolResult、Model Protocol、ScriptedModel
- M2：QueryLoop、预算和停止状态
- M3：Tool Registry、Dispatcher、Schema、Workspace
- M4：OpenAI Compatible/DashScope Adapter、流式响应、usage、超时
- M5：search/edit/run-tests、Policy、Approval、ProcessRunner
- M6：Event、Artifact、Checkpoint、Resume、Replay
- M7：Skill Manifest、Catalog、路由、懒加载、Context 和评估

## 3. 当前 M8 状态

M8 尚未完成，当前代码保存在 wip/m8-memory 分支。

已存在的模块：

- records.py
- store.py
- service.py
- extraction.py
- evidence.py
- learning.py
- retrieval.py
- context.py
- admission.py

已经实现或讨论过：

- MemoryScope 支持 PROJECT 和 USER
- MemoryEvidence 支持 USER_MESSAGE、TOOL_RESULT、WORKSPACE_FILE
- MemoryProposal 表示提取器产生的不可信建议
- MemoryCandidate 表示证据来源已经验证
- MemoryRecord 表示正式存储的记忆
- InMemoryMemoryStore
- 去重、TTL、删除
- 关键词检索和 MemoryContext
- QueryLoop 的 MemoryContext 接入
- RunEvidenceVerifier
- MemoryAdmissionOutcome：ADMIT / REJECT
- MemoryAdmissionDecision
- MemoryAdmissionPolicy Protocol

## 4. 当前正在修改的位置

src/minicode/memory/learning.py 中已经增加：

- MemoryLearningItemResult

它用于将一条 Proposal 的完整处理结果放在一起：

- proposal
- candidate
- decision
- write

当前 MemoryLearningResult 和 MemoryLearner 仍然主要使用旧流程，
尚未完成 AdmissionPolicy 接入。

不要继续实现之前对话中那个“固定所有结果为 ADMIT”的临时迁移方案。

## 5. 已确定的 Memory 语义

证据伪造：

- candidate = None
- decision = REJECT
- write = None

证据真实但内容临时：

- candidate 存在
- decision = REJECT
- write = None

内容可靠且第一次保存：

- candidate 存在
- decision = ADMIT
- write.outcome = SAVED

内容可靠但已经存在：

- candidate 存在
- decision = ADMIT
- write.outcome = DUPLICATE

EvidenceVerifier 目前只能证明：

- reference 存在
- excerpt 出现在来源中

它不能证明 MemoryProposal.content 真的被证据支持。

## 6. 当前已知设计问题

- Memory 的语义准入尚未完成
- WORKSPACE_FILE 证据缺少 Artifact 支持
- InMemoryMemoryStore 不能跨进程保存
- 错误记忆目前是硬删除，不可审计
- Memory 内容是不可信数据，不能获得 Tool 权限
- 中文关键词检索能力有限
- Memory 事件类型还不完整
- Store 写入到一半失败时没有事务保证

## 7. 最近验证状态

最近确认：

- src/minicode/memory/learning.py Ruff 检查通过
- tests/memory/test_learning.py：3 passed
- mypy：58 个源文件通过

增加 admission.py 和 MemoryLearningItemResult 后，尚未重新运行完整 pytest。

## 8. 路线调整

发现项目长期偏重 Runtime 基础设施，缺少可见的 Coding Agent 产品闭环。

下一步决定暂停扩展 M8，不删除现有代码。

优先建立 Coding Agent 纵向闭环：

1. 组装正式 CodingAgent/AgentRuntime
2. 接入真实模型和现有 Coding Tools
3. 定义搜索、读取、修改、测试和完成行为
4. 增加仓库结构发现和 diff 检查
5. 完成一个真实 Bug 修复任务
6. 建立最小 Coding Benchmark
7. 再判断是否继续 M8

## 9. 教学协作要求

最重要目标是理解，而不是快速增加代码量。

后续规则：

- 助手先讲清为什么需要新代码
- 说明谁创建、谁调用、输入输出和调用链位置
- 一次只引入一个有独立意义的概念
- 不运行明知必错且没有学习价值的测试
- 不重复大量基础非法输入测试
- 助手在对话中提供代码，由用户复制
- 除非用户明确说“你直接修改”，助手不得修改文件
- 新代码必须说明失败模式和替代设计