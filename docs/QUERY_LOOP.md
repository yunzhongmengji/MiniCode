# MiniCode Query Loop

状态：M2 基础循环已实现；M3 接入 Tool Runtime，M4 接入真实 Model Adapter 和总时限，M6 接入 Event Ledger 与 Checkpoint 恢复，M7 接入按需 Skill Context

## 1. 目标

Query Loop 负责协调 Model、ToolRuntime 和对话历史。Model 只产生文本或 ToolCall，不直接执行工具；实际执行被委托给 ToolRuntime。Query Loop 同时管理模型轮次、工具数量、整次运行的总时限、运行事件和可恢复 checkpoint。M5 的真实 ToolDispatcher 已在 ToolRuntime 边界内实施 Policy 与 Approval；M6 的 Event Ledger 提供审计但不替代 OS Sandbox。

## 2. 当前组件

- Model
  - Provider 无关的模型调用协议，接收 `ModelRequest` 并返回 `ModelResponse`。
- ModelRequest
  - 包含当前结构化历史、稳定有序的 `ToolSpec` 快照和与历史分离的附加 instructions。
- ModelResponse
  - 模型一次响应的统一格式，包含文本、零个或多个 `ToolCall` 以及可选 Token 用量。
- ConversationItem
  - 对话历史允许保存的结构化项目：Message、ToolCall 或 ToolResult。
- ToolRuntime
  - 接收 ToolCall 并返回对应 ToolResult 的执行协议。
- QueryLoop
  - 负责模型调用、工具执行、历史更新、预算检查、总时限和停止判断。
- RunResult
  - 保存停止原因、最后一次模型响应、历史快照和已使用模型轮次。
- ScriptedModel
  - 脚本模型，用于测试。
- ScriptedToolRuntime
  - 无真实副作用的确定性测试替身，记录 ToolCall，并按顺序返回预设 ToolResult。
- RecordingModel
  - 可选模型包装器，按每次 `complete()` 记录延迟、Token、错误分类和取消，不改变 Query Loop 接口。
- EventLedger
  - 接收 QueryLoop 与 Dispatcher 产生的结构化事件，使模型、工具和运行结果共享一个连续顺序。
- CheckpointStore
  - 在每个 ToolResult 加入历史后保存可恢复状态；QueryLoop 可从最新状态补完 pending 工具。
- RunReplay
  - 只读解释 LedgerEvent，生成运行摘要，不重新执行模型或工具。
- SkillContextProvider
  - 根据最近用户消息选择并加载 Skill，为本次运行生成附加模型指令。

## 3. 一次运行的数据流

1. `run()` 记录 RUN_STARTED，再进入 `asyncio.timeout(total_timeout_seconds)` 管理的整次运行边界；`None` 表示不设截止时间。
2. 配置 SkillContextProvider 时，Query Loop 从历史中提取最近的用户消息，选择并加载一次 Skill Context。
3. Query Loop 从当前历史、`tool_specs` 和本次运行复用的 Skill instructions 创建不可变 `ModelRequest`，再调用 `Model.complete()`。
4. 模型返回不含 `ToolCall` 的文本时，Query Loop 返回 `StopReason.COMPLETED` 的 `RunResult`。
5. 模型返回 `ToolCall` 时，Query Loop 依次检查是否配置 ToolRuntime、是否到达模型轮次上限，以及整批调用是否超过工具预算。
6. 检查通过后，Query Loop 先按顺序写入整批 `ToolCall`，再调用 ToolRuntime 并写入对应 `ToolResult`；每个结果写入后立即保存 checkpoint。
7. 更新后的历史进入下一轮 `ModelRequest`，直到完成、预算停止、总超时或异常中断；Skill instructions 不因工具输出而重新路由。
8. 正常停止时记录 RUN_FINISHED 并返回 `RunResult`；超时、取消或异常中断时先记录对应 outcome，再保留原始控制流，不构造伪造的最终响应。

`resume(checkpoint)` 使用同一运行边界，但从 checkpoint 中保存的回合、工具计数和历史继续。它只执行没有匹配 ToolResult 的 pending ToolCall，再进入下一模型回合。

持久化恢复的第一层是稳定 JSON 编解码。Checkpoint JSON 第 2 版保存 `run_id`、完整
`message_history`、`turns_used`、`tool_calls_used` 和 `is_completed`；历史中的 `Message`、`ToolCall`
和 `ToolResult` 分别携带 `message`、`tool_call`、`tool_result` 类型标签。解码后仍由
`RunCheckpoint` 重新验证历史配对与计数不变量。`FileCheckpointStore` 使用 run ID 的
SHA-256 作为安全文件名，并通过“临时文件写完后原子替换”保存每个 run 的最新 JSON。
Codec 可以把第 1 版 JSON 读取为未完成状态，但旧文件没有最终状态信息，因此不能追溯
判断旧任务是否其实已经完成。
`build_coding_agent()` 已可通过 `CheckpointStore` 协议接收内存或文件实现。CLI 按
Workspace 路径隔离状态目录，为每次 `minicode run` 创建文件 Store 并在开始时输出
Run ID；`minicode resume <run_id>` 会在同一 Workspace 的隔离目录中读取最新状态并调用
`CodingAgent.resume()`。恢复命令创建新的进程内 Ledger，但继续使用原 Run ID；完整的
跨进程事件链目前仍未持久化。

## 4. 停止原因

- `COMPLETED`
  - 模型回复中没有 `ToolCall`。
- `TOOL_CALLS_PENDING`
  - 模型返回 ToolCall，但 QueryLoop 没有配置 ToolRuntime。
- `MAX_TURNS`
  - 模型回复中有 `ToolCall`，但当前已经是最后一个 Query Loop 轮次。
- `MAX_TOOL_CALLS`
  - 已成功执行的工具数量加上当前批次的工具数量，将超过 `max_tool_calls`。

## 5. 预算语义

- `max_turns` 统计什么。
  - 一次 `run()` 中允许调用 `model.complete()` 的最大次数。
- `max_tool_calls` 统计什么。
  - 一次 `run()` 中允许成功执行的工具调用数量上限。
- 为什么最后一个模型轮次不执行工具。
  - 因为工具执行结果已经没有后续模型轮次可以消费。
- 为什么工具调用批次整体超预算时一个都不执行。
  - 因为一个批次的工具调用会有相关性
- `MAX_TURNS` 为什么优先于 `MAX_TOOL_CALLS`。
  - 因为模型轮次已经耗尽时，工具结果无法再返回模型，无需再判断工具预算。
- `total_timeout_seconds` 统计什么。
  - 从 `run()` 进入开始，同时覆盖模型等待、工具执行和后续轮次。`None` 表示不限制；其他值必须是正的有限数，并明确拒绝 `bool`。
- 总时限和 SDK 请求超时有什么不同。
  - SDK 超时约束一次 HTTP 请求；Query Loop 总时限约束完整多轮任务。

## 6. 结构化历史

历史中如果只存在文本内容，就没有办法清晰表明工具的使用，模型也不知道具体使用了哪些工具，得到了什么。同一 `ModelResponse` 中的全部 `ToolCall` 是模型在看到任何结果前一次性提出的，所以先记录全部 `ToolCall`，再记录 `ToolResult`，才能保持真实因果顺序。`call_id` 用于关联调用和结果。

## 7. 错误边界

- `ToolResult(is_error=True)`
  - 表示可预期的工具业务失败。它仍然会进入历史，模型可以根据错误恢复或解释。
- Model 抛出 `ModelError`
  - Provider Adapter 已将 SDK 错误转换为稳定的 MiniCode 异常。Query Loop 不恢复或吞掉它，因为当前没有足够信息决定是否重试。
- Model 或 ToolRuntime 抛出意外异常
  - 立即中断且不产生 `RunResult`，保留 traceback 供调用者处理。
- 总时限到期
  - 内部通过取消停止当前等待，`asyncio.timeout()` 在边界外抛出 `TimeoutError`，不产生 `RunResult`。
- 调用者主动取消
  - `task.cancel()` 产生的 `CancelledError` 继续向外传播；取消不会被误转换为总超时，`finally` 仍可用于资源清理。
- `RecordingModel`
  - 它可以观察并记录模型错误或取消，但记录后仍立即重新抛出，不改变 Query Loop 的错误语义。
- `EventLedger`
  - QueryLoop 在成功、失败、取消和超时路径记录结构化事件，但记录不会把异常转换成成功结果，也不会吞掉取消。

## 8. 当前限制

- 已通过 `ModelRequest` 接入真实 Model Adapter；Query Loop 本身仍保持 Provider 无关。
- M5 已在 Dispatcher 后接入 Policy、Approval，以及受 Workspace 和资源限制的 search、edit、test Coding Tools；Query Loop 仍只依赖 ToolRuntime Protocol。
- 工具调用仍然顺序执行。
- Query Loop 当前使用 `Model.complete()`；Model Adapter 虽已支持流式事件，但尚未接入 Query Loop 的实时消费路径或 CLI/UI。
- `asyncio.timeout()` 是协作式取消边界；如果某段同步代码长时间不交还事件循环，超时不能在其执行中途强制中断它。
- M6 已提供内存 Event、Artifact、Checkpoint 和 Replay；Checkpoint 已有文件后端和 CLI
  恢复入口。Event 与 Artifact 仍无持久后端，也没有事件状态机验证或崩溃时外部副作用的
  事务保证。
- M7 的 Skill 路由使用关键词基线，只在一次运行开始时选择和加载；尚无语义召回、版本解析或组合 Token 预算。
- Event Ledger 只提供观察和恢复证据；应用层路径与 argv 规则仍不能提供宿主机级隔离。
