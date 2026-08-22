# MiniCode Query Loop

状态：M2 已实现

## 1. 目标

Query Loop 负责协调 Model、ToolRuntime 和对话历史。Model 只产生文本或 ToolCall，不直接执行工具；实际执行被委托给 ToolRuntime。M2 只建立执行边界，Policy、Approval 和 Sandbox 尚未实现。

## 2. 当前组件

- Model
  - Provider 无关的模型调用协议，接收结构化历史并返回 ModelResponse。
- ModelResponse
  - 模型一次响应的统一格式，包含文本和零个或多个 ToolCall。
- ConversationItem
  - 对话历史允许保存的结构化项目：Message、ToolCall 或 ToolResult。
- ToolRuntime
  - 接收 ToolCall 并返回对应 ToolResult 的执行协议。
- QueryLoop
  - 负责模型调用、工具执行、历史更新、预算检查和停止判断。
- RunResult
  - 保存停止原因、最后一次模型响应、历史快照和已使用模型轮次。
- ScriptedModel
  - 脚本模型，用于测试
- ScriptedToolRuntime
  - 无真实副作用的确定性测试替身，记录 ToolCall，并按顺序返回预设 ToolResult。

## 3. 一次运行的数据流

1. QueryLoop 调用 Model。
   1. 用户输入message，从queryloop进入，传给model执行
2. 模型返回普通文本时发生什么。
   1. queryloop从模型回复中检测到只有文本内容，确定任务执行完成，返回任务完成结果。
3. 模型返回 ToolCall 时发生什么。
   1. 模型返回 ToolCall 后，Query Loop 依次检查是否配置 ToolRuntime、是否到达模型轮次上限，以及整批调用是否超过工具预算。只有这些检查都允许时，才保存 ToolCall、调用 ToolRuntime、保存 ToolResult 并进入下一轮。
4. ToolResult 怎样进入下一轮历史。
   1. message_history += (tool_result,)
5. 最终结果怎样返回给调用者。
   1. QueryLoop 返回完整的 RunResult，最后一次模型响应保存在 RunResult.response 中。

## 4. 停止原因

- COMPLETED
  - 模型回复中没有tool_call
- TOOL_CALLS_PENDING
  - 模型返回 ToolCall，但 QueryLoop 没有配置 ToolRuntime。
- MAX_TURNS
  - 模型回复中有tool_call，但当前已经是最后一个loop轮次
- MAX_TOOL_CALLS
  - 已成功执行的工具数量加上当前批次的工具数量，将超过 max_tool_calls。

## 5. 预算语义

- max_turns 统计什么。
  - 一次 run 中允许调用 model.complete() 的最大次数。
- max_tool_calls 统计什么。
  - 一次 run 中允许成功执行的工具调用数量上限。
- 为什么最后一个模型轮次不执行工具。
  - 因为工具执行结果不能返回给模型
- 为什么工具调用批次整体超预算时一个都不执行。
  - 因为一个批次的工具调用会有相关性
- MAX_TURNS 为什么优先于 MAX_TOOL_CALLS。
  - 因为loop预算不够，就不用考虑工具调用了。

## 6. 结构化历史

历史中如果只存在文本内容，就没有办法清晰表明工具的使用，模型也不知道具体使用了哪些工具，得到了什么。同一 ModelResponse 中的全部 ToolCall 是模型在看到任何结果前一次性提出的，
所以先记录全部 ToolCall，再记录 ToolResult，才能保持真实因果顺序。
call_id 用于关联调用和结果。

## 7. 错误边界

- `ToolResult(is_error=True)`
  - 表示可预期的工具业务失败。它仍然会进入历史，模型可以根据错误恢复或解释。
- ScriptedModel 响应耗尽
  - 抛出 RuntimeError，并通过 Query Loop 继续向外传播。
- ToolRuntime 抛出异常
  - 可能来自 Runtime 崩溃、超时或测试结果耗尽。当前 Query Loop 不捕获，会立即中断且不产生 RunResult。
- 当前 QueryLoop 是否捕获这些异常
  - 否

## 8. 当前限制

- 尚未接入真实模型。
- 尚未实现真实工具、Registry 和 Dispatcher。
- 工具调用仍然顺序执行。
- 尚未实现 Policy、Approval 和 Sandbox。