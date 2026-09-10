# MiniCode Safety Coding Tools

本文记录 M5 的安全 Coding Tools、Policy、Approval 和受限进程执行边界。这里的“安全”表示模型提出的动作必须经过确定性检查，并不表示应用层代码能够替代 OS Sandbox。

## 1. 完整数据流

~~~text
ModelResponse.tool_calls
          ↓
       QueryLoop
          ↓ ToolRuntime
    ToolDispatcher
          ↓
  Registry 查找 Tool
          ↓
 Pydantic 严格验证参数
          ↓
  ToolPolicy.evaluate(...)
      ↙       ↓       ↘
    DENY     ASK     ALLOW
      ↓       ↓       ↓
   错误   ToolApprover 执行 Tool
              ↓批准    ↓
              └──────→ Tool.execute(...)
                         ↓
                    文本或预期错误
                         ↓
             ToolResult(call_id, output, is_error)
                         ↓
                    下一轮模型
~~~

`ToolCall` 只是模型提出的候选动作。只有查找、参数验证、Policy 和必要的 Approval 全部成功，Dispatcher 才会调用具体工具。任何前置步骤失败都会在文件写入或子进程启动之前短路。

## 2. Policy 与 Approval

`PolicyOutcome` 只有三个稳定值：

- `ALLOW`：无需询问即可继续。
- `ASK`：必须由 `ToolApprover` 对本次精确 ToolCall 返回 `True`。
- `DENY`：直接返回错误 ToolResult。

`ConfiguredToolPolicy` 当前按工具名称保存显式规则，没有配置的工具默认拒绝。Policy 决定是否可以尝试动作，Approver 只回答一次具体询问；二者都不负责执行工具。

Dispatcher 先进行工具专属 Schema 验证，再调用 Policy。这样非法参数不会打扰用户，也不会进入副作用路径。例如 `run_tests` 的 `path="--rootdir=/tmp"` 在 Pydantic 验证处直接变成错误 ToolResult，Policy、Approver 和 ProcessRunner 都不会运行。

## 3. 三个 Coding Tools

| 工具 | 行为 | 主要限制 |
|---|---|---|
| `search_text` | 在文件或目录中进行 literal substring search | Workspace 路径、稳定文件顺序、文件数、单文件 bytes、结果数 |
| `create_file` | 创建一个不存在的 UTF-8 文本文件 | Workspace 路径、完整内容 bytes、目标必须不存在、原子创建 |
| `edit_file` | 将一个唯一的 `old_text` 精确替换为 `new_text` | Workspace 路径、UTF-8、源文件/完整结果 bytes、必须恰好匹配一次 |
| `run_tests` | 对一个工作区文件或目录运行固定 pytest 命令 | Workspace 路径、拒绝 `-` 开头参数、固定 argv、正数超时 |

编辑要求 `old_text` 恰好出现一次。出现零次说明模型上下文可能过期，出现多次说明目标有歧义；两种情况都拒绝猜测。写入时先在同一目录生成临时文件、保留原权限，再使用 `os.replace()` 替换，因此替换失败时原文件仍然存在。

## 4. 路径边界

Workspace 将根目录与输入路径组合后调用 `resolve()`，从而规范化父级跳转并解析已有符号链接。只有最终真实路径仍然 `is_relative_to(root)` 时才允许继续。

这会拒绝：

- `../secret.txt`。
- `/etc/passwd` 等绝对路径。
- 工作区内指向外部目标的符号链接。

路径检查发生在读取、写入和启动 pytest 之前。具体工具把 `WorkspacePathError` 等预期底层错误转换为 `ToolExecutionError`，Dispatcher 再将它转换为模型可以处理的错误 ToolResult，同时 `raise ... from error` 为开发者保留异常原因。

## 5. 为什么不用 Shell

RunTestsTool 构造固定参数序列：

~~~python
(
    sys.executable,
    "-m",
    "pytest",
    relative_path,
    "-q",
)
~~~

AsyncioProcessRunner 使用 `create_subprocess_exec(*command)`。每个元素作为单独 argv 传给进程，分号、`&&` 或 `$()` 不会被 shell 解释为新命令。

无 shell 不能自动解决参数注入。如果模型把 `--rootdir=/tmp` 放在 path 位置，pytest 自己仍会把它解释为选项。因此 `RunTestsArguments` 额外拒绝所有以 `-` 开头的路径。

## 6. 超时与错误分层

ProcessRunner 超时时负责：

1. `kill()` 终止直接子进程。
2. 再次 `communicate()` 等待退出并清理管道。
3. 裸 `raise` 保留原始 TimeoutError。

RunTestsTool 捕获该 TimeoutError，将其翻译为包含限制时间的 ToolExecutionError。Dispatcher 最后生成 `ToolResult(is_error=True)`。两层捕获分别负责资源生命周期和工具语义，不是重复处理。

## 7. 已知限制

- Workspace 的路径检查与随后打开之间存在 TOCTOU 窗口。
- 原子替换降低部分写入风险，但不是版本控制、事务或并发冲突检测。
- pytest 子进程继承当前环境，尚未建立环境变量白名单。
- stdout/stderr 由 `communicate()` 全量保存，尚未设置输出 byte 上限。
- 超时只直接终止 pytest 进程，尚未保证其所有后代进程同时退出。
- Policy 当前按工具名配置；Approval 已记录内存事件，但尚无持久审计、一次性令牌或过期机制。
- 没有 OS Sandbox，当前实现不允许任意 Shell，也不应被描述为宿主机隔离。

这些限制将在后续持久事件后端和 M12 红队与加固阶段继续处理。

## 8. 测试证据

- 参数化边界测试覆盖严格类型、空值、正数限制和 pytest 选项注入。
- `tmp_path` 构造隔离文件树、父级跳转和外部符号链接。
- 假 ProcessRunner 验证固定 argv，并用零调用证明 Policy/Approval 在副作用前阻止执行。
- 真实 ProcessRunner 集成测试启动临时 pytest 子进程并捕获结果。
- 故障注入覆盖原子替换失败、测试失败输出和超时后的进程清理。
- M5 完成时全项目 362 个 pytest 用例通过，Ruff、格式检查、mypy 和 `git diff --check` 均通过。
