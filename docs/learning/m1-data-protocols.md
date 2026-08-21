# M1：数据协议与 Fake Model

状态：已完成

## 当前文件地图

- `src/minicode/core/messages.py`：定义组件间交换的消息类型。
- `tests/core/test_messages.py`：记录消息类型的行为契约。
- `src/minicode/core/tool_calls.py`：定义 ToolCall、ToolResult、JSON 校验和递归冻结。
- `tests/core/test_tool_calls.py`：验证候选工具调用的字段、JSON 边界和深层不可变性。
- `tests/core/test_tool_results.py`：验证成功结果、错误结果和字段约束。
- `src/minicode/core/model.py`：定义供应商无关的 ModelResponse 和 Model Protocol。
- `tests/core/test_model.py`：验证模型响应的字段、组合规则和调用者别名隔离。
- `src/minicode/models/scripted.py`：实现离线、确定、可记录调用轨迹的 ScriptedModel。
- `tests/models/test_scripted_model.py`：验证响应顺序、调用快照、耗尽错误和非法脚本。
- `typechecks/model_contracts.py`：用静态赋值关系证明 ScriptedModel 符合 Model Protocol。
- `pyproject.toml`：声明 pytest-asyncio、mypy 及严格类型检查范围；依赖版本由 uv.lock 锁定。

## 为什么需要数据协议

普通字典允许任意键和值。`{"rol": "user"}` 可以正常创建，直到后续读取 `message["role"]` 才出现错误。数据协议让 Query Loop、Model Adapter 和 Tool Runtime 对字段名称、类型与语义形成共同约定。

第一版 `Message` 包含：

- `role`：消息来源，使用 `MessageRole` 限定为 system、user、assistant 或 tool。
- `content`：消息文本。

## 当前 Python 语法

- `StrEnum`：定义一组有限的、同时具有字符串值的枚举成员。
- `@dataclass`：根据字段声明生成初始化、比较和显示等重复代码。
- `frozen=True`：禁止创建后重新给字段赋值。
- `slots=True`：限制实例只能拥有声明过的字段，并减少对象开销。
- `__post_init__()`：dataclass 自动初始化字段后执行项目自己的运行时校验。

类型标注主要表达接口并帮助静态工具，不会自动完成全部运行时校验。例如 `role: MessageRole` 不会自动拒绝字符串 `"uesr"`。当前 `Message.__post_init__()` 使用 `isinstance()` 强制校验：`role` 必须是 `MessageRole`，`content` 必须是字符串；错误类型抛出 `TypeError`。

`frozen=True` 阻止创建后重新赋值。测试通过 `FrozenInstanceError` 固定这一契约，避免进入历史或审计记录的消息被静默篡改。

## ToolCall 与 ToolResult

`ToolCall` 是模型提出的候选动作，不代表已经获准或执行。它包含非空 `call_id`、非空工具 `name` 和结构化 `arguments`。`ToolResult` 使用同一个 `call_id` 返回字符串 `output`，并用严格布尔值 `is_error` 区分成功与可预期失败。

~~~text
Model → ToolCall(call_id, name, arguments)
  → Policy / Approval
  → Executor
  → ToolResult(call_id, output, is_error)
  → Query Loop
~~~

工具失败被表示成 `is_error=True` 的数据，Query Loop 因此可以让模型重试；未处理异常留给真正的 Runtime 故障。

## 参数快照与递归冻结

普通字典会让调用者与 ToolCall 共享同一对象。只做浅复制会继续共享嵌套容器；只使用 `MappingProxyType(original)` 又会让原字典的修改透过实时只读视图可见。当前实现递归复制每层 Mapping，将其包装为只读代理，并把列表转换为元组。

这形成两类保护：调用者修改原始容器不会影响 ToolCall；通过 ToolCall 直接修改外层或内层参数会抛出 `TypeError`。这是应用层审计不变量，不代替 Policy 或 OS Sandbox。

## JSON 合同

工具参数只接受字符串、有限整数/浮点数、布尔值、`None`、字符串键 Mapping，以及递归列表/元组。非字符串键、普通 Python 对象、NaN 和正负无穷会被立即拒绝。`type JsonValue = ...` 表达递归类型合同；`isinstance()`、`math.isfinite()` 和显式异常负责运行时强制。

## 字段校验

- 错误对象类型抛出 `TypeError`。
- 类型正确但空白或非有限等非法值抛出 `ValueError`。
- `_validate_string()` 返回经过验证的字符串，既复用运行时检查，也让类型检查器获得明确的 `str` 返回类型。
- `output` 允许空字符串，因为成功工具可能没有 stdout；`call_id` 和工具名不允许为空。

## ModelResponse

ModelResponse 是不同模型供应商交给 Query Loop 的统一输出。`content` 保存文本；`tool_calls` 保存零个或多个候选工具调用。它接受 list 或 tuple 等 Sequence，运行时逐项验证 ToolCall，然后转换为 tuple 快照，避免调用者后续修改原容器。

响应允许三种有效组合：只有文本、只有工具调用、文本和工具调用同时存在。文本为空白且没有工具调用时，响应既没有答案也没有动作，会让 Query Loop 无法判断下一步，因此立即抛出 ValueError。对象类型错误使用 TypeError，类型正确但组合语义无效使用 ValueError。

## Model Protocol 与依赖反转

Model Protocol 只声明 MiniCode 核心需要的能力：接收 Message 序列，异步返回 ModelResponse。Query Loop 将依赖这个接口，不直接导入某个模型厂商 SDK；OpenAI 等具体 Adapter 和 ScriptedModel 都需要符合核心定义的接口。

~~~text
                     Model Protocol
                    /              \
Query Loop --------/                \-------- Provider Adapter → 外部 SDK
                    \
                     \----------------------- ScriptedModel
~~~

原先若由 Query Loop 直接创建供应商客户端，依赖方向是“核心业务 → 外部技术细节”。现在由核心定义抽象、外部实现适配抽象，再由程序入口注入具体实现。Protocol 表达依赖反转的接口；从外部把实现传给 Query Loop 是依赖注入。

Protocol 使用结构化类型。ScriptedModel 不必继承 Model，只要 complete() 的参数和返回类型兼容，就能在静态检查中赋给 Model。Protocol 不会自动校验网络返回值，运行时数据仍由 dataclass 校验和测试保护。

## 异步接口与 ScriptedModel

`async def complete()` 统一真实网络模型与离线 Fake 的调用方式。调用异步函数先得到协程对象，`await` 才等待其完成。pytest-asyncio 为异步测试提供事件循环；ScriptedModel 虽然没有网络等待，也保留异步签名，使 Query Loop 不需要区分真假模型。

ScriptedModel 构造时验证 ModelResponse 序列并复制到 deque。每次 complete() 先把收到的 Message 序列转换为 tuple 快照并记录到 calls，再用 popleft() 以 O(1) 取出下一条响应。外部看到的 calls 是 tuple 快照，不能直接清空内部记录。

~~~text
预设 [response_1, response_2]
        ↓ 第一次 complete(messages_1)
记录 (messages_1,)；返回 response_1
        ↓ 第二次 complete(messages_2)
记录 (messages_1, messages_2)；返回 response_2
        ↓ 第三次调用
记录调用；抛出“scripted model has no responses remaining”
~~~

Fake 不尝试模拟模型智能。它提供可控制、无网络、无费用且可重复的输出，以便 M2 精确测试 Query Loop 的状态迁移。相比直接使用 AsyncMock，独立 ScriptedModel 把响应脚本和调用轨迹变成可复用的项目级测试协议。

## pytest、Ruff 与 mypy 的分工

- pytest 执行代码并验证运行时行为，包括故意传入错误对象的边界测试。
- Ruff 检查格式、导入和常见代码问题，但不证明对象符合 Protocol。
- mypy 不执行代码，通过 `Model` 返回类型和赋值位置检查结构化接口兼容性。
- `typechecks/model_contracts.py` 是静态契约文件，不是 pytest 运行时测试。

当前 mypy 只检查 src 和 typechecks。tests 中包含故意违反标注的运行时负例，后续加入明确的 `type: ignore` 后再逐步纳入静态检查。

## M1 完整数据流

~~~text
用户任务
  → Message(role=USER, content=...)
  → Query Loop（M2 实现）
  → await Model.complete(message_history)
       ├─ 测试：ScriptedModel
       └─ 生产：Provider Adapter（M4 实现）
  → ModelResponse(content, tool_calls)
       ├─ 没有 tool_calls：形成最终文本
       └─ 有 ToolCall：Policy / Approval → Executor → ToolResult → 追加历史后再次调用模型
~~~

## 当前测试证据

- Message 保存、不可变、非法角色和非法内容测试。
- ToolCall 外层/嵌套直接修改与调用者别名修改测试。
- 非 JSON 值、非字符串键、非有限浮点数、非 Mapping 根参数测试。
- call_id、name 的类型与空白测试。
- ToolResult 成功、错误、空输出、字段类型测试。
- ModelResponse 文本/工具调用组合、容器快照、非法元素、非法容器和空白响应测试。
- ScriptedModel 响应顺序、消息/响应防御性复制、调用轨迹、耗尽错误和脚本边界测试。
- 44 个 pytest 运行时用例通过，其中 M1 数据协议和 Fake Model 为 41 个。
- Ruff 对 27 个文件的检查与格式门禁通过。
- mypy 严格检查 src 与 typechecks 共 9 个文件，ScriptedModel 的 Protocol 契约通过。
- 独立完成“工具调用 → 追加工具结果历史 → 最终答案”的两轮响应脚本，并验证完整 calls 轨迹。

## 已知限制

- 当前不可变对象仍是 Python 应用层约束，不是安全沙箱。
- `call_id` 只能验证格式非空，唯一性由后续创建边界负责。
- Tool 名称的字符集和是否注册由后续 Tool Registry 负责。
- Tool output 目前只保存字符串；大结果与 Artifact 在 M6 设计。
- 尚未实现序列化/反序列化边界和深层数据的标准 JSON 输出。
- ModelResponse 尚未记录 finish reason、Token 用量、模型名和供应商元数据，M4 接真实 Adapter 时扩展。
- ScriptedModel 是单进程确定性测试工具，尚未设计并发 complete() 的共享队列语义。
- Model Protocol 尚未包含流式响应、超时和取消；这些将在 M4 与多 Agent 阶段补充。
- calls 是应用层只读快照，不是 M6 的持久化 Event Ledger。

## 复习题

1. 为什么 `frozen=True` 不能自动冻结字段中的字典？
2. 为什么要组合防御性复制与 `MappingProxyType`？
3. 为什么最外层 arguments 规则放在 ToolCall，而嵌套值规则放在递归函数？
4. 类型别名、类型检查器和运行时校验分别解决什么问题？
5. 为什么 ToolResult 的 output 允许为空，而 call_id 不允许？
6. ModelResponse 为什么允许空 content，但不允许 content 和 tool_calls 同时为空？
7. 依赖反转和依赖注入有什么区别？
8. 为什么 ScriptedModel 不继承 Model 也能符合 Protocol？
9. 调用 async def 后得到什么，await 又负责什么？
10. 为什么响应队列使用 deque，而调用记录内部使用 list、外部返回 tuple？
11. pytest、Ruff 和 mypy 分别能发现什么、不能发现什么？
12. 为什么 ScriptedModel 的响应耗尽错误不直接暴露 deque 的 IndexError？

## 阶段结论

已能讲回依赖反转、Protocol、异步调用、容器浅复制和 ScriptedModel 的内部/外部可变性取舍；已完成响应列表防御性复制与两轮工具脚本两个变式。M1 工程门禁与学习门禁通过，下一步进入 M2 最小 Query Loop。
