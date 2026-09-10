# Coding Agent 垂直切片

本文说明 MiniCode 如何把已经独立验证的模型、循环、工具和安全边界组装成一个可从终端运行的 Coding Agent。

## 1. 入口与数据流

`pyproject.toml` 将终端命令 `minicode` 指向 `minicode.cli:main`。执行：

```bash
minicode run "修复失败的测试" --trace
```

会经过：

```text
CLI task
  → DashScopeConfig
  → AsyncOpenAI client
  → OpenAICompatibleModel
  → CodingAgent
  → QueryLoop
  → ModelRequest(instructions, conversation, tool_specs)
  → ToolCall
  → ToolDispatcher
  → Policy / Approval
  → Tool / Workspace / ProcessRunner
  → ToolResult
  → 下一轮 ModelRequest
  → RunResult
```

`CodingAgent.run()` 只负责把一个非空任务字符串转换成首条用户 `Message`。`build_coding_agent()` 是组合根：它注册默认工具、创建 Dispatcher，并把同一组工具的 `ToolSpec` 交给 QueryLoop。没有 `tool_specs`，模型就不知道可以调用哪些工具。

## 2. 默认工具与权限

| 工具 | 作用 | 默认 Policy | 强制边界 |
|---|---|---|---|
| `list_files` | 发现工作区文件结构 | `ALLOW` | Workspace 路径、常见生成目录剪枝和文件数量上限 |
| `read_file` | 读取一个 UTF-8 文件 | `ALLOW` | Workspace 路径和 byte 上限 |
| `search_text` | 搜索文件或目录 | `ALLOW` | Workspace、文件数、文件大小和结果数上限 |
| `edit_file` | 唯一精确替换 | `ASK` | Workspace、源文件和结果大小、原子写入 |
| `run_tests` | 运行限定路径的 pytest | `ASK` | Workspace、固定 argv、无 shell、进程超时 |

模型只能生成 ToolCall，不能直接执行副作用。Dispatcher 先查 Registry 并验证参数，再执行 Policy；`ASK` 只有在 `ConsoleToolApprover` 收到明确的 `y` 或 `yes` 后才继续。每次批准只对应终端展示的那一次工具名称和参数。

## 3. 文件结果的来源标记

`read_file` 返回自描述结果：

```text
File "src/example.py":
<原始文件正文>
```

路径使用 JSON 字符串表示，保留中文并转义引号等特殊字符。这样同一轮读取多个文件时，每份正文自身携带来源，降低模型混淆文件内容的概率。它是辅助模型正确归因的结构化提示，不是安全边界；真正的路径限制仍由 Workspace 实施。

## 4. ToolResult、Event 与 Artifact

一个工具输出有两个消费者：

```text
tool output
  ├─ ToolResult.output → 对话历史 → 下一轮模型
  └─ ArtifactStore     → output_artifact 引用 → LedgerEvent
```

ToolResult 保存模型继续推理所需的完整文本。Event 只保存 `call_id`、工具名、结果状态和可选 Artifact 元数据，避免把大段源码、测试日志或潜在秘密直接写进事件。

启用 `--trace` 时，CLI 创建 `InMemoryArtifactStore`。Dispatcher 使用工具输出的 UTF-8 SHA-256 作为内容 ID，并在 `tool_execution_finished` 中记录：

```json
{
  "output_artifact": {
    "artifact_id": "sha256:...",
    "media_type": "text/plain",
    "byte_count": 127
  }
}
```

SHA-256 是内容指纹，不可反向还原正文。当前 Store 只存在于进程内，命令结束后正文丢失；该实现验证了协议和关联关系，不等于持久审计后端。

## 5. Trace 顺序

QueryLoop 与 Dispatcher 共享同一个 `InMemoryEventLedger`，因此模型和工具事件使用一条连续序列：

```text
001 run_started
002 model_call_started
003 model_call_finished
004 tool_policy_decided
005 tool_approval_resolved       # 仅 ASK
006 tool_execution_started
007 tool_execution_finished
008 model_call_started
...
```

Trace 写入 `stderr`，最终模型回答写入 `stdout`。调用者可以分别重定向：

```bash
minicode run "任务" --trace >answer.txt 2>trace.txt
```

Event 的 `succeeded` 表示对应运行步骤成功完成，不保证最终自然语言回答中的每句话都正确。回答质量仍需真实任务评估。

## 6. 错误与资源清理

CLI 将可解释的边界错误转换成稳定消息和退出码：

| 情况 | 终端语义 | 退出码 |
|---|---|---:|
| 配置缺失或错误 | `Configuration error` | 2 |
| 认证、限流、连接、配额、协议或服务错误 | `Model error` | 1 |
| QueryLoop 总超时 | `Task timed out` | 1 |
| 用户按 `Ctrl+C` | `Task cancelled by user` | 130 |
| 正常完成 | 最终回答 | 0 |

未知程序异常不会被 `except Exception` 吞掉，仍保留 traceback。外层 `finally` 会在 `--trace` 模式下打印已经产生的事件；内层 `finally` 无论成功或失败都会关闭 AsyncOpenAI 客户端。

## 7. 当前限制

- CLI 使用 `Model.complete()`，还没有实时消费模型流式事件。
- EventLedger 和 ArtifactStore 没有磁盘实现，进程退出后不能按 ID 读取历史内容。
- Trace 默认不记录完整工具参数或输出正文，避免无界日志和秘密泄漏；因此只凭事件不能还原每个读取路径。
- Console Approval 是当前进程内的一次性确认，没有持久授权、过期或外部身份认证。
- Workspace 是应用层路径边界，不是容器或操作系统沙箱，仍存在 TOCTOU 和子进程继承环境等限制。
- 路径标签和基础指令可以改善模型归因与重复读取，但不能确定性保证模型回答正确。

这些限制应由后续 Benchmark、持久存储和安全加固阶段分别处理，不应通过扩大 Prompt 或默认记录敏感正文来掩盖。
