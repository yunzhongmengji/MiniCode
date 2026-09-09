# MiniCode Tool Runtime

本文记录 M3 与 M5 的工具协议、注册、分发、参数验证、Policy、Approval、错误分类和 Workspace 文件边界。目标是让 Query Loop 能在不依赖具体工具实现的情况下，执行可测试、可替换且受约束的工具调用。

## 1. 完整数据流

~~~text
ModelResponse.tool_calls
          ↓
       QueryLoop
          ↓ ToolRuntime Protocol
    ToolDispatcher
          ↓ name
     ToolRegistry
          ↓ Tool
       ToolSpec
          ↓ arguments_type.model_validate(...)
   validated ToolArguments
          ↓
       ToolPolicy
     ↙ DENY  ↓ ASK  ↘ ALLOW
  error   ToolApprover   execute
              ↓ approved
          ↓ Tool.execute(...)
       text output
          ↓ Dispatcher 关联 call_id
       ToolResult
          ↓
下一轮 Model 或 RunResult
~~~

QueryLoop 只依赖 `ToolRuntime.execute(ToolCall) -> ToolResult`。测试时使用 `ScriptedToolRuntime`，真实分发时使用 `ToolDispatcher`，二者替换不需要修改 QueryLoop。

## 2. 组件职责

| 组件 | 主要职责 | 不负责 |
|---|---|---|
| `ToolArguments` | 统一严格验证、禁止额外字段、冻结参数并生成 JSON Schema | 查找或执行工具 |
| `ToolSpec` | 保存工具名、模型可读描述和参数模型类型 | Provider 特定序列化和业务执行 |
| `Tool` Protocol | 约束 `spec` 属性与异步 `execute()` 方法 | 保存全局工具集合 |
| `ToolRegistry` | 按名称保存工具、拒绝重复名称、稳定暴露 Spec 快照 | 参数验证和错误包装 |
| `ToolDispatcher` | 查找、验证、实施 Policy/Approval、执行并关联 `call_id` 生成 `ToolResult` | 文件路径安全和具体业务逻辑 |
| `ToolPolicy` | 对一个候选 ToolCall 返回 Allow、Ask 或 Deny 决策 | 执行工具或向用户展示 UI |
| `ToolApprover` | 异步询问一个精确 ToolCall 是否获准 | 决定默认策略或直接执行工具 |
| `Workspace` | 集中处理工作区文件路径、UTF-8 读取与 byte 上限 | OS 级进程隔离 |
| `ReadFileTool` | 声明 read_file Schema，通过 Workspace 读取文本并转换预期错误 | 直接拼接或信任模型路径 |
| `SearchTextTool` | 在受限文件集合中进行 literal search，并限制结果数量 | 正则表达式、索引或工作区外搜索 |
| `EditFileTool` | 唯一精确替换、结果大小检查和受控写入 | 猜测多个匹配中的修改目标 |
| `RunTestsTool` | 验证测试路径、构造固定 pytest argv 并解释进程结果 | 任意命令或 Shell 执行 |
| `ProcessRunner` | 启动无 shell 子进程、收集结果并负责超时清理 | 决定允许运行什么命令 |
| `EventLedger` | 记录 Policy、Approval 和工具执行的全局顺序 | 决定权限或执行工具 |
| `ArtifactStore` | 保存工具输出并向事件返回内容引用 | 将输出反馈给模型 |

## 3. 参数 Schema 与模型工具定义

`ToolSpec` 保持 Provider 无关。当前核心只保存：

~~~python
ToolSpec(
    name="read_file",
    description="Read a UTF-8 text file from the workspace.",
    arguments_type=ReadFileArguments,
)
~~~

`ReadFileArguments.model_json_schema()` 生成参数的 JSON Schema。M4 的 Provider Adapter 再把 `name`、`description` 和参数 Schema 组合为目标 SDK 所需格式，避免核心 Tool Runtime 依赖某一家模型供应商。

`ToolArguments` 的共享策略：

- `extra="forbid"`：拒绝模型生成的未知字段。
- `strict=True`：不把字符串、布尔等输入静默转换为目标类型。
- `frozen=True`：参数通过验证后不能重新给字段赋值。

具体工具可以通过 `Field(description=...)` 和字段验证器增加模型提示与业务约束。

## 4. 错误分类

| 失败 | Dispatcher 行为 | 是否回到模型 |
|---|---|---|
| 工具名未知 | 生成 `ToolResult(is_error=True)` | 是 |
| Pydantic 参数验证失败 | 返回不含原始输入值的结构化错误摘要 | 是 |
| `ToolExecutionError` | 转换为关联原调用的错误 ToolResult | 是 |
| 意外 `TypeError`、`RuntimeError` 等程序错误 | 当前继续抛出并保留 traceback | 否 |

具体工具使用 `raise ToolExecutionError(...) from error`，既向模型暴露稳定、安全的工具语义，也通过 `__cause__` 为开发者保留底层异常链。M6 的 Dispatcher 在实际执行前后记录 TOOL_EXECUTION_STARTED/FINISHED；预期失败会生成错误 ToolResult 和可选 Artifact，意外异常记录类型后继续抛出。

## 5. Workspace 文件边界

Workspace 初始化时将根目录解析为存在的真实目录。读取文件时：

1. 验证可选 `max_bytes` 的类型和值。
2. 将根目录与模型提供的路径组合。
3. 使用 `resolve(strict=False)` 消除 `..` 并解析已有符号链接。
4. 使用 `is_relative_to(root)` 检查最终路径是否仍位于工作区。
5. 有读取上限时最多读取 `max_bytes + 1` bytes。
6. 未超限后才进行严格 UTF-8 解码。

覆盖的攻击与错误场景：

- `../secret.txt` 父级跳转。
- `/etc/passwd` 等绝对路径。
- 工作区内符号链接指向外部文件。
- 根路径实际是普通文件。
- 系统权限不足、文件不存在、目录读取和非 UTF-8 内容。
- 零、负数、布尔和非整数 byte 限制。

## 6. 为什么 Workspace 不是 Sandbox

Workspace 是应用层文件 API，只能约束经过它的代码。它不能阻止：

- 其他代码绕过 Workspace 直接使用 `Path` 或 `open()`。
- 子进程读取工作区外文件。
- 检查路径后、打开文件前符号链接被并发替换。
- FIFO、设备文件或特殊挂载尚未通过原子文件类型检查排除，读取可能阻塞。
- 网络访问、环境变量读取或系统调用。

因此 Workspace 是纵深防御的一层，不是最终安全边界。后续仍需要 Policy、Approval、受控 Executor 与 OS Sandbox。

## 7. M5 执行前安全顺序

Dispatcher 固定按以下顺序处理调用：

1. Registry 查找工具。
2. 使用工具的 Pydantic Schema 严格验证参数。
3. Policy 返回 Allow、Ask 或 Deny。
4. Ask 决策通过 Approver 获取布尔结果。
5. 只有全部前置条件成功后才调用 `Tool.execute()`。

非法参数会直接返回错误 ToolResult，不会进入 Policy 或打扰用户审批。Deny、缺少 Approver 或审批拒绝也不会调用具体工具，因此文件写入和子进程启动都位于最后一道允许边界之后。

## 8. 当前测试证据

- Schema：合法输入、未知字段、严格类型、冻结和 JSON Schema。
- ToolSpec：元数据、运行时不变量和不可变性。
- Registry：查询、未知名称、重复名称和稳定 Spec 顺序。
- Dispatcher：未知工具、参数失败、Policy 默认拒绝、Ask 审批、非法策略/审批返回值、成功执行、预期执行失败和 QueryLoop 集成。
- Workspace：正常读取、路径穿越、绝对路径、符号链接、根目录类型、byte/file 上限和原子替换失败时保留原文件。
- ReadFileTool：成功读取、异常转换、字段描述、空路径、权限分类和限制配置。
- SearchTextTool：文件和目录搜索、literal 语义、稳定顺序、无匹配、结果/文件限制及路径错误转换。
- EditFileTool：唯一精确替换、源文件与结果大小限制、文件错误转换及审批前禁止写入。
- RunTestsTool/ProcessRunner：固定 argv、参数注入拒绝、真实 pytest 子进程、失败输出、超时终止清理及审批前禁止启动。
- M5 完成时全项目证据：362 个 pytest 用例，Ruff、格式检查、mypy 与 `git diff --check` 全部通过。

## 9. M6 审计接入

Dispatcher 可以与 QueryLoop 共享同一个 EventLedger。合法 PolicyDecision 产生 TOOL_POLICY_DECIDED；Ask 的严格布尔结果产生 TOOL_APPROVAL_RESOLVED；只有进入真实执行路径后才产生 TOOL_EXECUTION_STARTED，随后以 succeeded、failed 或 cancelled 结束。

成功输出和预期 ToolExecutionError 文本可以写入 ArtifactStore，事件保存 artifact ID、媒体类型和 byte 数。ToolResult 仍是反馈给模型的协议，Artifact 是审计存储，二者不能互相替代。

当前 EventLedger 和 ArtifactStore 只有内存实现，尚不提供跨进程持久审计、秘密脱敏或访问控制。完整设计见 [Event Ledger](EVENT_LEDGER.md)。
