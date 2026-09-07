# Model Adapter 设计

本文记录 MiniCode M4 当前已经实现的真实模型边界。目标不是让核心代码依赖某一家 SDK，而是让离线 `ScriptedModel` 和真实 Provider 都能满足同一个 `Model` Protocol。

## 1. 为什么需要 Adapter

MiniCode 内部使用自己的稳定数据结构：

- `ModelRequest`：一次模型请求，包含结构化对话历史和有序的 `ToolSpec`。
- `ModelResponse`：一次模型回复，包含文本、零个或多个 `ToolCall` 以及可选的 `ModelUsage`。
- `Message`、`ToolCall`、`ToolResult`：Provider 无关的对话项。

OpenAI 兼容 API 使用另一套消息字典、工具定义和 SDK 响应对象。Adapter 位于两者之间，负责双向转换。如果核心层直接使用 SDK 类型，更换 Provider、升级 SDK 或运行离线测试都会影响 Query Loop。

## 2. 文件与职责

| 组件 | 谁创建或调用 | 输入 | 输出 | 不负责 |
|---|---|---|---|---|
| `ModelRequest` | `QueryLoop` | 对话历史、`ToolSpec` | 不可变请求快照 | Provider 序列化、网络请求 |
| `OpenAICompatibleModel` | Provider 组装函数 | `ModelRequest` | `ModelResponse` | 读取环境变量、执行工具 |
| `conversation_to_openai_messages` | `OpenAICompatibleModel` | MiniCode 对话项 | SDK 消息列表 | 网络请求 |
| `tool_spec_to_openai_tool` | `OpenAICompatibleModel` | `ToolSpec` | OpenAI function tool | 执行工具 |
| `openai_completion_to_model_response` | `OpenAICompatibleModel` | SDK `ChatCompletion` | `ModelResponse` | Query Loop 状态迁移 |
| `openai_completion_stream_to_events` | `OpenAICompatibleModel.stream` | SDK 异步 chunk 流 | `ModelTextDelta` 和 `ModelResponseDone` | 执行工具、渲染 UI |
| `RecordingModel` | 应用组装层 | 任意 `Model` | 原始 `ModelResponse` 和按调用排序的指标记录 | 重试、吞掉异常、记录 Prompt |
| `DashScopeConfig` | 应用入口或测试 | 环境变量映射 | 阿里云配置快照 | 发起网络请求 |
| `build_dashscope_client` | `build_dashscope_model` | `DashScopeConfig` | `AsyncOpenAI` | 对话格式转换 |
| `build_dashscope_model` | 应用入口 | `DashScopeConfig` | 可供 Query Loop 使用的 Model | Query Loop 和工具执行 |

## 3. 完整调用链

```text
Message / ToolCall / ToolResult
              │
              ▼
          QueryLoop
              │ 创建 ModelRequest
              ▼
    RecordingModel（可选）
              │
              ▼
    OpenAICompatibleModel
              │
              ├─ conversation_to_openai_messages
              ├─ tool_spec_to_openai_tool
              │
              ▼
          AsyncOpenAI
              │ HTTPS
              ▼
       Alibaba Model Studio
              │ ChatCompletion
              ▼
openai_completion_to_model_response
              │
              ▼
         ModelResponse
              │
              ▼
          QueryLoop
```

`QueryLoop` 不导入 OpenAI SDK，也不知道请求最终发送给哪家 Provider。它只依赖 `Model` Protocol。

## 4. 对话转换

MiniCode 为了便于状态机处理，将 `ToolCall` 和 `ToolResult` 保存成独立对象：

```text
Message(USER)
ToolCall
ToolResult
```

OpenAI 兼容接口要求工具调用属于一条 assistant 消息，工具结果属于一条 tool 消息。Adapter 因此把上面的历史转换为：

```text
user message
assistant message containing tool_calls
tool message correlated by tool_call_id
```

连续的 `ToolCall` 会被分组到同一条 assistant 消息中。若 assistant 同时返回文本和工具调用，二者也会合并到同一条消息。末尾仍处于等待状态的 assistant 内容或工具调用必须在循环结束后写入输出，因此转换函数在循环结束时还会执行一次 flush。

工具参数在 MiniCode 内部可能包含只读 `mappingproxy` 和 tuple。发送前会递归转换成普通 dict 和 list，再编码为 JSON 字符串。

## 5. 工具定义

`ToolSpec` 保存 Provider 无关的工具名、描述和 Pydantic 参数类型。Adapter 使用 `model_json_schema()` 生成 OpenAI function tool 的 `parameters`。

这保证了：

1. 给模型看的参数 Schema 与 Dispatcher 的运行时验证来自同一个 Pydantic 类型。
2. 核心 Tool Runtime 不需要导入 OpenAI SDK。
3. Registry 的稳定注册顺序会保留到模型请求中。

## 6. 响应与协议错误

SDK 返回 `ChatCompletion` 后，Adapter 只读取第一个 choice，并将文本与 function tool calls 转成 `ModelResponse`。

下列响应不能安全交给 Query Loop，会转换为 `ModelProtocolError`：

- 没有 choice。
- 不支持的工具调用类型。
- 工具参数不是合法 JSON。
- 工具参数 JSON 解码后不是 object。
- 工具调用缺少有效的 ID、名称或参数。

构造 `ToolCall` 时仍由 `ToolCall` 自己执行字段不变量校验；Adapter 捕获其 `TypeError` 或 `ValueError`，再转换为模型边界统一的 `ModelProtocolError`。这样不会在两个位置重复维护同一套字段规则。

## 7. 流式边界

`OpenAICompatibleModel.stream()` 使用 `stream=True` 请求 SDK 返回异步 chunk 流，并通过 `stream_options={"include_usage": True}` 请求最终 Token 用量。Provider 返回的 chunk 是分片传输对象，不是多个独立完整回复。

Adapter 将 chunk 流转换为两种 Provider 无关事件：

- `ModelTextDelta`：新到达的非空文本分片，立即交给消费者。
- `ModelResponseDone`：该次模型调用的完整结果，包含拼接后的文本、完整 `ToolCall` 和可选 `ModelUsage`。它只表示一次模型调用结束，不必然表示整个 Query Loop 完成。

文本分片在到达时直接 `yield`，同时追加到本地缓冲。工具调用可能把 ID、名称和 JSON 参数拆成多个 chunk，Adapter 按 `index` 分别累积，只在流结束后构造完整 `ToolCall`。

usage chunk 可能没有 `choices`，因此 Adapter 先读取 `chunk.usage`，再判断是否有 choice。最终必须获得 `stop` 或 `tool_calls` 结束原因；缺失结束原因、`length` 截断或无法组装的工具调用都转换为 `ModelProtocolError`。

## 8. SDK 与错误分类

`AsyncOpenAI` 是异步 HTTP SDK 客户端，负责认证头、请求发送、响应解析、超时和 SDK 重试。当前 DashScope client 配置：

- `timeout=60.0`
- `max_retries=2`

MiniCode Adapter 将 SDK 异常转换为稳定的项目异常：

| SDK 异常 | MiniCode 异常 | 含义 |
|---|---|---|
| `AuthenticationError` | `ModelAuthenticationError` | 凭据无效 |
| `PermissionDeniedError` + 免费额度代码 | `ModelQuotaExceededError` | 免费额度耗尽 |
| 其他 `PermissionDeniedError` | `ModelAccessDeniedError` | 无权访问模型资源 |
| `RateLimitError` | `ModelRateLimitError` | 请求频率或并发受限 |
| `APIConnectionError` | `ModelConnectionError` | 无法连接服务 |
| 其他 `APIStatusError` | `ModelServiceError` | Provider 拒绝请求或服务失败 |

异常使用 `raise ... from error` 保留原始 SDK 异常链，同时让核心层只依赖 MiniCode 错误类型。

## 9. DashScope 配置

`DashScopeConfig.from_environment()` 当前读取：

- `DASHSCOPE_API_KEY`：必填凭据。
- `DASHSCOPE_BASE_URL`：可选 API 地址覆盖。
- `DASHSCOPE_MODEL`：可选模型名覆盖。

API key 使用 `field(repr=False)`，避免配置对象的默认 `repr` 直接显示秘密。环境变量仍然只是进程配置，不应写进源码、测试、Git 或聊天记录。

`build_dashscope_model()` 组合 client 和通用 Adapter，并通过 `extra_body` 发送 Provider 扩展参数。当前关闭 thinking，使第一版行为和测试更容易预测。`extra_body` 是兼容层的扩展口，不进入核心 `ModelRequest`。

## 10. 取消与总时限

SDK client 的 `timeout=60.0` 限制单次 HTTP 请求。`QueryLoop(total_timeout_seconds=...)` 使用 `asyncio.timeout()` 限制整次运行，范围包含每轮模型调用、工具执行和后续轮次。

总时限到期时，`asyncio.timeout()` 内部取消当前 Task，等待链上先观察到 `CancelledError`，离开超时上下文后调用者观察到 `TimeoutError`。调用者直接执行 `task.cancel()` 时，外部取消保持为 `CancelledError`，不会被误转换为总超时。

MiniCode 不吞掉取消。模型和工具可以在 `finally` 中释放资源，然后让取消继续向上传播。

## 11. 运行指标

`ModelUsage` 保存一次模型回复的输入和输出 Token 数，`total_tokens` 由两者相加得到。非流式响应从 `ChatCompletion.usage` 转换，流式响应从启用 `include_usage` 后的 usage chunk 转换。

`RecordingModel` 使用装饰器式组合包装任意 `Model`：

```text
QueryLoop → RecordingModel → OpenAICompatibleModel → Provider SDK
```

它使用单调时钟记录每次 `complete()` 的延迟，成功时保存 `ModelUsage`，失败时将 MiniCode 模型异常转换为稳定的 `ModelErrorKind`。取消记录为 `CANCELLED` 后仍立即重新抛出。记录按实际模型调用排序，因此两轮 Query Loop 产生两条 `ModelCallRecord`。

记录不保存 Prompt、响应正文、API key 或 SDK request/response 对象，避免把敏感数据混入指标。

## 12. 测试边界

离线测试使用 `ChatCompletion.model_validate()`、`MagicMock` 和 `AsyncMock` 验证格式转换、参数转发与错误映射，不访问网络，也不消耗额度。

真实 smoke test 已验证三条路径：

1. 单轮文本：真实 Provider 返回预期文本。
2. 两轮工具闭环：模型请求 `read_file`，Dispatcher 读取临时文件，模型根据 `ToolResult` 返回最终答案。
3. 流式文本：逐个消费 `ModelTextDelta`，并验证本地拼接文本与 `ModelResponseDone.response.content` 一致。

真实 smoke test 依赖个人环境变量、网络和免费额度，因此不放入默认离线 pytest 套件。

## 13. 当前限制

- `RecordingModel` 当前只观测 `complete()`；流式调用可以在最终事件中获得 Token，但尚未由该包装器记录流式总延迟和错误分类。
- 尚未记录 Provider 请求 ID、成本和 cache Token 细分。
- Query Loop 已有整次运行的总时限，但尚未对每次模型调用提供独立的动态超时配置。
- CLI 尚未组装真实模型与工具闭环。
- 当前只消费第一个 choice，不支持多候选响应。
- Provider 兼容差异目前只通过 `extra_body` 和 DashScope 组装层处理。
- 在当前 OpenAI SDK/httpcore2 组合下，真实流式 smoke test 内容完整，但进程关闭时曾观察到 transport 异步生成器关闭警告；不在业务层屏蔽该警告。

M4 工程实现已完成；完成数据流、设计取舍和失败模式复盘后通过学习门禁。
