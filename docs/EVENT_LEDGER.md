# MiniCode Event Ledger

本文记录 M6 的事件账本、Artifact、Checkpoint、恢复执行和审计回放边界。目标是让一次 Query Loop 可以被观察、调查，并从已确认状态继续执行，而不是把所有运行数据混入非结构化日志字符串。

## 1. 完整数据流

~~~text
用户消息
   ↓
QueryLoop.run(...)
   │
   ├─ RUN_STARTED
   ├─ MODEL_CALL_STARTED
   │        ↓
   │      Model
   │        ↓
   ├─ MODEL_CALL_FINISHED
   │
   │   ModelResponse.tool_calls
   │        ↓
   │   ToolDispatcher
   │        ├─ TOOL_POLICY_DECIDED
   │        ├─ TOOL_APPROVAL_RESOLVED（可选）
   │        ├─ TOOL_EXECUTION_STARTED
   │        └─ TOOL_EXECUTION_FINISHED
   │                 │
   │                 └─ output_artifact → ArtifactStore
   │
   ├─ ToolResult 加入 message_history
   ├─ CheckpointStore.save(...)
   ├─ CHECKPOINT_SAVED
   │
   ├─ 下一轮模型调用
   └─ RUN_FINISHED
            ↓
       Event Ledger
            ↓
        RunReplay
~~~

Event Ledger 保存“发生过什么”，ArtifactStore 保存可能较大的工具输出，CheckpointStore 保存“从哪里继续”。三个存储承担不同职责。

## 2. 组件职责

| 组件 | 保存内容 | 主要用途 | 不负责 |
|---|---|---|---|
| `LedgerEvent` | run ID、连续序号、事件类型、JSON 兼容 payload | 记录一项已发生事实 | 执行模型或工具 |
| `EventLedger` | 一次运行的有序事件 | 审计和时序观察 | 保存完整工具输出 |
| `ArtifactStore` | 按内容寻址的文本 | 保存并读取工具输出 | 判断工具是否已经执行 |
| `RunCheckpoint` | 对话历史和已消耗预算 | 恢复真实执行 | 保存完整审计时间线 |
| `CheckpointStore` | 每个 run 的 checkpoint 序列 | 找到最新可恢复状态 | 解释事件含义 |
| `QueryLoop.resume()` | checkpoint 输入 | 补完 pending 工具并继续模型调用 | 审计回放 |
| `RunReplay` | LedgerEvent 快照 | 验证并解释历史事件 | 再次产生副作用 |

`resume()` 与 Replay 不相同：

~~~text
resume
    读取 Checkpoint
    可能调用工具和模型
    会产生新事件和副作用

Replay
    只读取 LedgerEvent
    不调用模型
    不执行工具
    不修改工作区
~~~

## 3. LedgerEvent 与顺序

每个事件包含：

~~~python
LedgerEvent(
    run_id="run_001",
    sequence=1,
    kind=EventKind.RUN_STARTED,
    payload={
        "max_turns": 3,
    },
)
~~~

`run_id` 将同一次运行的事件关联起来。`sequence` 从 1 开始连续增加，用来表达确定性的先后关系，而不依赖时间戳精度。

事件 payload 只允许 JSON 兼容值。映射和列表会递归转换为只读快照，调用者之后修改原始容器不会改变已经记录的事实。

当前稳定事件类型包括：

| EventKind | 含义 |
|---|---|
| `RUN_STARTED` | 一次新运行开始 |
| `RUN_RESUMED` | 从 checkpoint 开始恢复 |
| `SKILL_SELECTION_FINISHED` | 完成候选选择并记录 Skill 名称与分数 |
| `SKILL_LOAD_STARTED` | 开始读取一份已选 Skill 正文 |
| `SKILL_LOAD_FINISHED` | Skill 加载成功、失败或取消 |
| `MODEL_CALL_STARTED` | 发起一次模型调用；记录模型可见画像及投影前后 byte 差异 |
| `MODEL_CALL_FINISHED` | 模型调用成功、失败或取消 |
| `TOOL_POLICY_DECIDED` | Policy 返回 Allow、Ask 或 Deny |
| `TOOL_APPROVAL_RESOLVED` | 人工审批返回批准或拒绝 |
| `TOOL_EXECUTION_STARTED` | 工具通过前置检查并开始执行 |
| `TOOL_EXECUTION_FINISHED` | 工具成功、失败或取消 |
| `CHECKPOINT_SAVED` | 已完成工具结果被保存为恢复点 |
| `RUN_FINISHED` | 当前运行段结束 |

多个组件必须共享同一个 EventLedger，才能得到全局顺序。QueryLoop 记录运行和模型事件，Dispatcher 记录策略、审批和工具事件。

`MODEL_CALL_STARTED.context_profile` 描述真正发送给模型的请求；`context_projection` 对比
canonical request 与模型视图，记录 ToolResult 变化数量、投影前后 ToolResult/总字节及
二者差值，同时记录稳定的 `strategy` 和 `max_inline_tool_result_bytes` 配置。配置字段用于
区分“启用了投影但本轮没有命中”和“使用 Identity”；不能只凭节省值是否为 0 猜测 Arm。
新版配置还记录 `configuration_schema_version=2`、`minimum_net_savings_bytes` 和
`retrieval_tool_loading`。投影 Arm 的后两项分别为 `1` 和 `on_reference`，意思是完整请求
至少净减少 1 byte 才采用引用，并且只在引用实际出现的请求中暴露回读 Tool Spec；Identity
对应 `null`。结果记录器会逐轮核对这些事实，不能只在实验命令中声称采用了新策略。
Identity Projector 的差值为 0。这里仍是规范化 JSON 的 UTF-8 byte，不是供应商 Token。
历史回读次数不重复增加专用计数器，可按 `TOOL_EXECUTION_FINISHED` 中
`tool_name == "read_tool_result"` 和 outcome 汇总。

## 4. outcome 的上下文

`outcome` 不是一个适用于所有事件的全局枚举，它的含义由 EventKind 决定。

| 事件 | outcome 可能值 |
|---|---|
| `TOOL_POLICY_DECIDED` | `allow`、`ask`、`deny` |
| `MODEL_CALL_FINISHED` | `succeeded`、`failed`、`cancelled` |
| `SKILL_LOAD_FINISHED` | `succeeded`、`failed`、`cancelled` |
| `TOOL_EXECUTION_FINISHED` | `succeeded`、`failed`、`cancelled` |
| `RUN_FINISHED` | `succeeded`、`failed`、`cancelled`、`timed_out` |

`TOOL_APPROVAL_RESOLVED` 使用严格布尔字段 `approved`，因为它回答的是一次二选一审批，不是执行结果。`*_STARTED` 事件没有 outcome，因为动作尚未结束。

## 5. Artifact

Dispatcher 可以把成功输出或预期 `ToolExecutionError` 的文本写入 ArtifactStore。事件只保存引用元数据：

~~~python
{
    "output_artifact": {
        "artifact_id": "sha256:...",
        "media_type": "text/plain",
        "byte_count": 25,
    },
}
~~~

完整输出仍通过 ToolResult 交给下一轮模型；Artifact 引用用于审计和以后读取。

当前 `InMemoryArtifactStore` 使用 UTF-8 内容的 SHA-256 作为 ID。相同内容会得到相同 ID，这提供内容寻址和完整性标识，但不是加密，也不会隐藏内容。

意外程序异常会记录错误类型并继续抛出，不保证产生 Artifact，因为这类异常可能发生在安全输出形成之前。

## 6. Checkpoint

RunCheckpoint 保存：

~~~python
RunCheckpoint(
    run_id="run_001",
    message_history=(...),
    turns_used=1,
    tool_calls_used=1,
    is_completed=False,
)
~~~

checkpoint 在每一个 ToolResult 加入历史后立即保存，而不是等一整批工具全部执行完成。
这些中间状态的 `is_completed` 为 `False`。模型返回没有 ToolCall 的最终答复时，再保存一份
`is_completed=True` 的终态；只有这次写入成功，QueryLoop 才向调用者返回 COMPLETED。

假设模型一次返回两个工具调用：

~~~text
ToolCall(call_001)
ToolCall(call_002)
~~~

第一个工具完成、第二个工具崩溃时，最新 checkpoint 是：

~~~text
ToolCall(call_001)
ToolCall(call_002)
ToolResult(call_001)
~~~

恢复时只需执行 `call_002`，不会重复执行已经产生结果或副作用的 `call_001`。

RunCheckpoint 会验证：

1. ToolCall 的 call ID 在一次历史中唯一。
2. ToolResult 必须匹配更早出现的 ToolCall。
3. 每个 ToolCall 最多只有一个 ToolResult。
4. `tool_calls_used` 等于实际 ToolResult 数量。
5. message history 被复制成不可变 tuple。
6. 完成状态不能包含尚无 ToolResult 的 pending ToolCall。

错误 ToolResult 也表示一次工具调用已经完成。恢复时不能因为 `is_error=True` 就自动重试；错误结果应交给模型决定下一步。

## 7. Resume

`QueryLoop.resume(checkpoint)` 执行以下步骤：

1. 验证输入确实是 RunCheckpoint。
2. 验证 checkpoint run ID 与 EventLedger run ID 一致。
3. 拒绝 `is_completed=True` 的终态 checkpoint。
4. 使用 `pending_tool_calls` 找出没有对应 ToolResult 的调用。
5. 验证剩余回合和工具调用预算。
6. 只执行 pending 工具调用。
7. 每完成一个工具，再保存一个 checkpoint。
8. 从 `turns_used + 1` 开始继续模型循环。

普通运行从 `first_turn = 1`、`tool_calls_used = 0` 开始。恢复运行从 checkpoint 中已有计数继续，不会重置预算。

`run()` 和 `resume()` 共享同一个运行边界，因此具有相同的总超时、取消传播、错误记录和 RUN_FINISHED 行为。

## 8. Replay

RunReplay 接受一次运行的 LedgerEvent 序列，首先验证：

1. 输入是非空事件序列。
2. 所有元素都是 LedgerEvent。
3. 所有事件属于同一个 run ID。
4. sequence 从 1 开始连续递增。
5. 第一条事件是 RUN_STARTED 或 RUN_RESUMED。
6. 最后的 RUN_FINISHED 包含字符串 outcome。

未完成事件流不会被拒绝。例如：

~~~text
RUN_STARTED
MODEL_CALL_STARTED
~~~

这可能表示进程在模型调用期间崩溃。Replay 会报告：

~~~python
is_finished is False
outcome is None
model_call_count == 1
~~~

Replay 当前从事件中推导 run ID、是否已经结束、最新结束 outcome、模型调用尝试次数、工具执行尝试次数、checkpoint 保存次数，以及按事件顺序排列的失败工具 call ID。

调用次数统计 `*_STARTED`，因为一次调用即使没有完成事件，也已经发生过一次尝试。

## 9. 超时、取消与失败

模型或工具内部观察到取消时，先记录对应的 `*_FINISHED`，outcome 为 `cancelled`，然后重新抛出 CancelledError。

如果取消由 QueryLoop 的 `asyncio.timeout()` 发起，离开超时上下文后，外部调用者收到 TimeoutError，RUN_FINISHED 记录 `timed_out`。

如果调用者直接执行 `task.cancel()`，外部仍收到 CancelledError，RUN_FINISHED 记录 `cancelled`。

普通异常记录 `error_type` 后继续抛出。事件记录用于观察，不改变底层控制流。

## 10. 隐私与安全边界

事件默认不保存 API key、完整 Prompt、完整模型响应正文、工具参数全文或完整工具输出。工具输出通过 Artifact 引用保存，降低事件 payload 无限增长的风险，但当前 ArtifactStore 仍是进程内明文存储。

Event Ledger 是审计能力，不是安全执行边界。Policy、Approval、Workspace 和 ProcessRunner 仍负责在副作用发生前限制动作。

## 11. 当前限制

- CLI 已接入保存每个 run 最新 JSON 的 FileCheckpointStore，并能按 Run ID 恢复未完成任务；
  EventLedger 和 ArtifactStore 当前仍只有内存实现，进程退出后数据丢失。
- 尚未提供 Event 的 JSONL、SQLite 或数据库持久化，也没有 Checkpoint 历史版本存储。
- 尚未记录墙上时间、单调时间或跨进程 trace ID。
- RunReplay 只验证基础序号、run ID 和边界，没有实现完整事件状态机校验。
- 事件不能单独重建 message history；真实恢复必须读取 Checkpoint。
- Artifact 使用内容寻址但没有加密、访问控制、过期和垃圾回收。
- 尚未实施事件与 Artifact 的秘密扫描或脱敏。
- 内存 Ledger 不提供线程安全或多进程并发写入保证。
- checkpoint 恢复无法自动判断某个外部副作用是否在进程崩溃前完成、但尚未来得及写入 ToolResult；这需要幂等工具或更强的事务协议。

## 12. 测试证据

- LedgerEvent 测试覆盖字段校验、连续序号和递归不可变 payload。
- QueryLoop 测试覆盖运行、模型调用、成功、失败、取消和超时事件。
- Dispatcher 测试覆盖 Policy、Approval、工具成功、预期失败、意外异常和取消事件。
- Artifact 测试覆盖内容寻址、确定性 ID、读取和缺失引用。
- Checkpoint 测试覆盖快照、最新状态、pending ToolCall 和历史完整性。
- Resume 测试证明已完成工具不会重复执行，pending 工具会补完后进入下一模型回合。
- Replay 测试覆盖正常摘要、损坏事件流和未完成运行。
- Replay 变式覆盖 succeeded、failed 和 cancelled 工具结果的精确筛选、稳定顺序和 JsonValue 到字符串的类型收窄。
- 端到端测试连接真实 ReadFileTool、Dispatcher、Artifact、Checkpoint、Event Ledger 和 Replay。
