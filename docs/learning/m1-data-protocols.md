# M1：数据协议与 Fake Model

状态：学习中

## 当前文件地图

- `src/minicode/core/messages.py`：定义组件间交换的消息类型。
- `tests/core/test_messages.py`：记录消息类型的行为契约。
- `src/minicode/core/tool_calls.py`：定义 ToolCall、ToolResult、JSON 校验和递归冻结。
- `tests/core/test_tool_calls.py`：验证候选工具调用的字段、JSON 边界和深层不可变性。
- `tests/core/test_tool_results.py`：验证成功结果、错误结果和字段约束。

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

## 当前测试证据

- Message 保存、不可变、非法角色和非法内容测试。
- ToolCall 外层/嵌套直接修改与调用者别名修改测试。
- 非 JSON 值、非字符串键、非有限浮点数、非 Mapping 根参数测试。
- call_id、name 的类型与空白测试。
- ToolResult 成功、错误、空输出、字段类型测试。

## 已知限制

- 当前不可变对象仍是 Python 应用层约束，不是安全沙箱。
- `call_id` 只能验证格式非空，唯一性由后续创建边界负责。
- Tool 名称的字符集和是否注册由后续 Tool Registry 负责。
- Tool output 目前只保存字符串；大结果与 Artifact 在 M6 设计。
- 尚未实现序列化/反序列化边界和深层数据的标准 JSON 输出。

## 复习题

1. 为什么 `frozen=True` 不能自动冻结字段中的字典？
2. 为什么要组合防御性复制与 `MappingProxyType`？
3. 为什么最外层 arguments 规则放在 ToolCall，而嵌套值规则放在递归函数？
4. 类型别名、类型检查器和运行时校验分别解决什么问题？
5. 为什么 ToolResult 的 output 允许为空，而 call_id 不允许？

## 待补内容

- ModelResponse
- Model Protocol 与 Scripted Fake Model
- 完整调用链、失败模式和复习题
