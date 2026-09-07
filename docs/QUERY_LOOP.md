# MiniCode Query Loop

状态：M2 基础循环已实现；M3 接入 Tool Runtime，M4 接入真实 Model Adapter 和总时限

## 1. 目标

Query Loop 负责协调 Model、ToolRuntime 和对话历史。Model 只产生文本或 ToolCall，不直接执行工具；实际执行被委托给 ToolRuntime。Query Loop 同时管理模型轮次、工具数量和整次运行的总时限。M5 的真实 ToolDispatcher 已在 ToolRuntime 边界内实施 Policy 与 Approval；OS Sandbox 仍属于后续里程碑。

## 2. 当前组件

- Model
  - Provider 无关的模型调用协议，接收 `ModelRequest` 并返回 `ModelResponse`。
- ModelRequest
  - 包含当前结构化历史和稳定有序的 `ToolSpec` 快照。
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

## 3. 一次运行的数据流

1. `run()` 进入 `asyncio.timeout(total_timeout_seconds)` 管理的整次运行边界；`None` 表示不设截止时间。
2. Query Loop 从当前历史和 `tool_specs` 创建不可变 `ModelRequest`，再调用 `Model.complete()`。
3. 模型返回不含 `ToolCall` 的文本时，Query Loop 返回 `StopReason.COMPLETED` 的 `RunResult`。
4. 模型返回 `ToolCall` 时，Query Loop 依次检查是否配置 ToolRuntime、是否到达模型轮次上限，以及整批调用是否超过工具预算。
5. 检查通过后，Query Loop 先按顺序写入整批 `ToolCall`，再调用 ToolRuntime 并写入对应 `ToolResult`。
6. 更新后的历史进入下一轮 `ModelRequest`，直到完成、预算停止、总超时或异常中断。
7. 正常停止时返回 `RunResult`，最后一次模型响应保存在 `RunResult.response` 中；超时或异常中断时不构造伪造的最终响应。

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

## 8. 当前限制

- 已通过 `ModelRequest` 接入真实 Model Adapter；Query Loop 本身仍保持 Provider 无关。
- M5 已在 Dispatcher 后接入 Policy、Approval，以及受 Workspace 和资源限制的 search、edit、test Coding Tools；Query Loop 仍只依赖 ToolRuntime Protocol。
- 工具调用仍然顺序执行。
- Query Loop 当前使用 `Model.complete()`；Model Adapter 虽已支持流式事件，但尚未接入 Query Loop 的实时消费路径或 CLI/UI。
- `asyncio.timeout()` 是协作式取消边界；如果某段同步代码长时间不交还事件循环，超时不能在其执行中途强制中断它。
- 尚未实现 Policy/Approval 的持久事件记录和 OS Sandbox；应用层路径与 argv 规则不能提供宿主机级隔离。
