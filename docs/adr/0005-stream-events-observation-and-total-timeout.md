# ADR-0005：分离流式事件、模型调用观测与 Query Loop 总时限

状态：Accepted
日期：2026-09-04

## 背景

ADR-0004 建立了 Provider 无关的 `ModelRequest`、`ModelResponse` 和 `Model` Protocol，但非流式边界不足以解决以下问题：

1. Provider 以 chunk 逐段返回文本和工具调用，核心层不应暴露 SDK chunk 类型。
2. 工具调用的 ID、名称和 JSON 参数可能被拆分到多个 chunk，不能将每个 chunk 当作完整 `ToolCall`。
3. 流式 usage 可能位于没有 choice 的末尾 chunk，需要独立累积和转换。
4. 后续 Benchmark 需要按每次模型调用保存延迟、Token 和稳定错误分类，但 Query Loop 不应直接依赖 Provider 或指标实现。
5. SDK 的单次 HTTP 超时不能约束包含多轮模型调用和工具执行的整个 Query Loop。
6. 总超时和调用者主动取消都依赖 asyncio 取消，但它们对外应具有不同语义。

## 决策

1. 保留非流式 `Model.complete()`，另外定义 `StreamingModel.stream()`，不强迫所有 Fake 和核心调用者改用流式接口。
2. 流式边界只暴露 Provider 无关的 `ModelStreamEvent`：`ModelTextDelta` 表示新文本分片，`ModelResponseDone` 表示一次模型调用已组装完成。
3. Adapter 立即 `yield` 非空文本分片，同时在本地累积完整文本。工具调用分片按 Provider 给出的 `index` 独立累积，流结束后才构造经过不变量校验的 `ToolCall`。
4. 流必须提供可接受的结束原因。缺失结束原因、长度截断、非 function 工具或无法组装的参数统一转换为 `ModelProtocolError`。
5. 使用 `ModelUsage` 保存 Provider 无关的输入和输出 Token 数，并将它作为 `ModelResponse` 的可选字段。
6. 使用装饰器式 `RecordingModel` 包装任意 `Model`，不修改 Query Loop 或 Provider Adapter 的公共契约。它使用单调时钟记录每次 `complete()` 的延迟、`ModelUsage`、`ModelErrorKind` 和取消。
7. `RecordingModel` 不保存 Prompt、响应正文、API key 或 SDK request/response 对象。它在记录后使用裸 `raise` 继续传播原异常或取消。
8. `QueryLoop` 接受可选的正的有限数 `total_timeout_seconds`，并使用 `asyncio.timeout()` 包裹整个内部运行，同时覆盖模型等待、工具执行和后续轮次。
9. 总时限到期时，等待链内部观察到 `CancelledError`，`asyncio.timeout()` 边界外的调用者观察到 `TimeoutError`。调用者主动执行 `task.cancel()` 时保留 `CancelledError`，不转换为总超时。
10. 超时、取消或意外异常中断时不构造伪造的 `RunResult`；异常继续交给调用者处理。

## 正面后果

1. 核心层和消费者不依赖 OpenAI SDK chunk 类型，更换 Provider 时修改集中在 Adapter。
2. 消费者可以立即处理文本分片，同时仍能在结束事件中获得经校验的完整响应。
3. 非流式与流式路径共用 `ModelResponse`、`ToolCall`、`ModelUsage` 和错误边界。
4. `RecordingModel` 通过组合而非修改核心循环实现观测，`ScriptedModel` 和真实 Adapter 都能被相同包装器使用。
5. 每轮模型调用产生独立记录，后续 Benchmark 可以从原始记录计算总 Token、失败分布和延迟。
6. Query Loop 总时限不会在每个子步骤重复实现，并确实包含卡住的 ToolRuntime。
7. 外部取消保持 asyncio 原生语义，资源拥有者仍可在 `finally` 中清理。

## 负面后果

1. Adapter 同时维护非流式和流式转换路径，测试数量和协议边界增加。
2. 为了产生最终 `ModelResponseDone`，Adapter 仍需在内存中累积完整文本和工具参数。
3. `RecordingModel` 当前只观测 `complete()`，还不记录流式首 Token 延迟、总延迟或流中途错误。
4. `RecordingModel` 在内层只能看到取消，无法单独判断它是 Query Loop 总超时还是调用者主动取消。
5. `asyncio.timeout()` 依赖协作式调度，无法在不交还事件循环的同步计算或阻塞调用中途强制中断。
6. 超时和取消不产生 `RunResult`，调用者需要通过异常路径记录整次任务结果。
7. 当前 OpenAI SDK/httpcore2 组合的真实流式 smoke test 在进程关闭时曾出现 transport 异步生成器关闭警告；该问题待依赖栈升级后复测，不在业务层屏蔽。

## 备选方案

1. 将 SDK `ChatCompletionChunk` 直接暴露给 Query Loop 和 UI。
   - 转换代码较少，但核心层、测试和消费者都会与 OpenAI SDK 强耦合，不接受。

2. 删除 `complete()`，让所有 Model 和 Fake 只实现流式协议。
   - 可以减少 Provider 的两种入口，但会迫使当前 Query Loop、ScriptedModel 和非流式测试承担不必要的流式复杂度，当前不采用。

3. 在每个 Provider Adapter 内直接记录指标。
   - 可以获得 Provider 细节，但会重复时钟、错误分类和记录存储；当前使用可组合的 `RecordingModel`。

4. 只为每次模型 HTTP 请求设置超时。
   - 无法限制多轮累计时间或卡住的工具执行，因此仍需 Query Loop 总时限。

5. 超时或取消时返回特殊 `RunResult`。
   - 可以统一返回类型，但在没有完整模型回复时需要伪造响应或放宽不变量；当前保留异常语义。

6. 捕获取消并继续运行。
   - 会让调用者失去停止任务的可靠手段，还可能留下孤儿网络流或子进程，不接受。

## 重新评估条件

1. Query Loop 或 CLI/UI 需要实时消费流式事件，需要决定如何将中间文本与最终状态迁移结合。
2. Benchmark 需要首 Token 延迟、流式总延迟、Provider request ID、cache Token 或成本时，扩展观测记录。
3. 需要在指标中区分 Query Loop 总超时和外部取消时，在更高层记录任务结果或向下传递明确的截止原因。
4. 出现长时间同步阻塞、CPU 密集任务或子进程无法协作取消时，引入 Executor、进程级截止或 OS Sandbox。
5. SDK/http transport 升级后，重新运行真实流式关闭测试，确认资源警告是否消失。
