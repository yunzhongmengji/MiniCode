# MiniCode 学习日志

此文件记录“真正掌握了什么”，不只记录代码完成情况。

## 初始基线

日期：2026-08-09

已阅读过相关代码并接触以下概念：

- FastAPI、JWT、MySQL、Redis、SSE
- LangChain Agent、Tool 和 Prompt
- RAG、Embedding、向量库、混合检索与重排
- 基础 asyncio、队列和异步流

当前没有独立项目经历，对一些文件职责、目录结构和模块调用流程并不熟悉。不能把“阅读过”记为“已经掌握”。

需要从“见过或大致看懂”转为“能解释并独立实现”：

- Python 类型协议、依赖反转与错误模型
- 异步取消、超时、资源清理
- Fake、单元测试、集成测试和故障注入
- Python 包结构、项目入口、配置、依赖和测试文件的职责

本项目重点新知识：

- 裸 Query Loop 与 Agent 状态机
- Tool Schema、Registry、Dispatcher 和 ACI
- 权限、审批、沙箱与 Prompt Injection 防护
- 事件溯源、Artifact、Checkpoint 和 Replay
- Skill 路由、自动 Memory、Context Compression
- Prompt Cache 的稳定前缀和失效
- Worker、Fork、Agent Team 和权限衰减
- 非确定性 Agent 的可复现 Benchmark

## 学习证据规则

一个知识点只有同时满足以下条件才标记为“掌握”：

- 能不看代码解释其输入、输出和边界。
- 能指出至少两个失败模式。
- 能独立完成一个变式。
- 能写测试证明行为，而不是只运行成功案例。
- 一周后的复习挑战仍能完成。

## 每课记录模板

### YYYY-MM-DD / Mx / 主题

- 课前判断：
- 今天亲手实现：
- 新理解：
- 失败与原因：
- 哪个测试暴露了问题：
- 我能讲回的内容：
- 仍然模糊：
- 变式练习结果：
- 下一次复习日期：

## 阶段复盘模板

- 我能画出的数据流：
- 三个关键设计取舍：
- 三个失败模式：
- 我独立完成的变式：
- 当前测试证据：
- 需要回补的知识：
- 是否通过学习门禁：

## 进度

| 日期 | 阶段 | 状态 | 证据 |
|---|---|---|---|
| 2026-08-09 | 开工准备 | 完成 | 契约、路线、调研、威胁模型、评测方案 |
| 2026-08-09 | M0 基线诊断 | 完成 | Python 基础可用；未使用 pytest；环境概念待学习；使用过 Git |
| 2026-08-09 | M0 环境概念 | 完成 | 能解释解释器、虚拟环境和 uv；理解项目命令入口 |
| 2026-08-09 | M0 环境准备 | 完成 | 已创建 Python 3.12.13 的 .venv 和 uv.lock；Hatchling 下载成功，项目以可编辑方式安装，minicode --help 验证通过 |
| 2026-08-11 | M0 CLI 概念 | 完成 | 亲手实现 run、task 与 --dry-run；能解释参数解析、stdout、stderr 和退出码 0/1/2 |
| 2026-08-12 | M0 测试工具链 | 完成 | 编写 3 个 pytest 离线测试；用 capsys、SystemExit 和故障注入验证测试有效；Ruff 检查与格式门禁通过 |
| 2026-08-12 | M0 信任边界 | 完成 | 能区分模型建议与执行权限；理解 Policy 的 Allow/Ask/Deny，以及 Executor 与 OS Sandbox 的纵深防御关系 |
| 2026-08-12 | M0 阶段门禁 | 通过 | 已完成 CLI 骨架、离线测试、工具链和威胁模型学习；进入 M1 数据协议与 Fake Model |
| 2026-08-17 | M1 基础数据协议 | 完成 | 亲手实现 Message、ToolCall、ToolResult；能解释运行时校验、浅/深不可变、防御性复制、只读代理、递归 JSON 类型及 TypeError/ValueError 边界；27 个离线测试通过 |
| 2026-08-21 | M1 模型抽象与 Fake | 通过 | 实现 ModelResponse、异步 Model Protocol 和 ScriptedModel；能解释依赖反转、Protocol、async/await、浅复制和容器可变性；独立完成响应列表复制与两轮工具脚本变式；44 个 pytest 用例、Ruff 和 mypy 严格门禁通过 |
| 2026-08-21 | M1 阶段门禁 | 通过 | 能画出 Message → Model → ModelResponse → ToolCall/ToolResult 数据流，指出响应耗尽、无动作响应和调用者别名等失败模式；准备进入 M2 最小 Query Loop |
| 2026-08-22 | M2 最小 Query Loop | 完成 | 实现结构化 ConversationItem、Model/ToolRuntime 协议、四种 StopReason、RunResult、双预算和工具错误反馈；82 个测试、Ruff 与 mypy 门禁通过 |
| 2026-08-22 | M2 学习门禁 | 通过 | 能解释循环数据流、停止状态、工具错误与异常边界；独立实现 MAX_TOOL_CALLS 终止条件、参数校验和整批拒绝测试；准备进入 M3 Tool Runtime |
| 2026-08-23 | M3 Tool Runtime | 完成 | 实现严格 Pydantic ToolArguments、不可变 ToolSpec、Tool Protocol、拒绝重复名称的 Registry、统一 Dispatcher、Workspace 与受限 ReadFileTool；136 个测试、Ruff 与 mypy 门禁通过 |
| 2026-08-23 | M3 学习门禁 | 通过 | 能解释 Tool/Spec/Registry/Dispatcher 分工、Protocol 替换、验证前置、异常转换、路径逃逸、符号链接、字节预算及 Workspace 与 OS Sandbox 的边界；准备进入 M4 Model Adapter |

## 2026-08-22 / M2 / 最小 Query Loop 复盘

- 我能画出的数据流：Message → ModelResponse → ToolCall → ToolRuntime → ToolResult → 下一轮 Model。
- 关键设计取舍：使用结构化历史；执行前检查预算；批次超预算时整批拒绝。
- 失败模式：模型响应耗尽、Runtime 异常、轮次耗尽、工具调用预算耗尽。
- 独立变式：新增 MAX_TOOL_CALLS，并验证第二个工具和超预算批次不会执行。
- 当前测试证据：82 个 pytest 用例，Ruff 和 mypy 全部通过。
- 需要回补：停止原因优先级；ToolResult 业务失败与 Runtime 异常的区别。
- 下一次复习日期：2026-08-29。
- 是否通过学习门禁：通过。

## 2026-08-23 / M3 / Tool Runtime 复盘

- 我能画出的数据流：ToolCall → ToolDispatcher → ToolRegistry → ToolSpec.arguments_type → Tool.execute → ToolResult。
- 关键设计取舍：核心 ToolSpec 保持 Provider 无关；严格 Schema 在副作用前验证；可预期工具失败进入 Agent 闭环，意外程序错误保留 traceback 并向外抛出。
- 安全边界：Workspace 解析真实绝对路径，拒绝父级跳转、绝对路径和外部符号链接；ReadFileTool 使用字节上限和 UTF-8 严格解码。
- 失败模式：重复工具静默覆盖、错误类型被 Pydantic 自动转换、非法参数触发副作用、越界读取、权限错误误分类、测试替身接口过期、重复测试函数被后定义覆盖。
- 测试方法：使用 tmp_path 构造隔离文件树，使用 monkeypatch 稳定注入权限错误，使用参数化测试覆盖类型和值边界，使用 mypy 证明 ToolDispatcher 满足 ToolRuntime Protocol。
- 当前测试证据：136 个 pytest 用例，Ruff、格式检查、mypy 和 git diff 检查全部通过。
- 仍然模糊或待复习：应用层路径检查的 TOCTOU 限制；真实 Provider 工具格式适配；Token 预算与字节预算的换算关系。
- 下一次复习日期：2026-08-30。
- 是否通过学习门禁：通过。
