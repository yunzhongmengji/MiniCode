# ADR-0003：使用集中式工具分发与 Workspace 文件边界

状态：Accepted
日期：2026-08-23

## 背景

Query Loop 已经能够消费 `ToolCall` 并把 `ToolResult` 返回模型，但 M2 只提供确定性的 `ScriptedToolRuntime`。真实工具系统需要解决以下问题：

1. 模型工具参数是不可信运行时输入，Python 类型注解不会自动验证。
2. 把具体工具写死在 Query Loop 中会让核心循环依赖文件、命令或网络实现。
3. 同名工具静默覆盖可能改变系统真实执行能力。
4. 未知工具、参数错误、预期业务失败和程序缺陷需要不同处理。
5. 模型提供的文件路径可能使用父级跳转、绝对路径或符号链接逃逸工作区。
6. 无限制读取文件会增加内存、上下文和 Token 风险。

## 决策

1. 使用 Pydantic `ToolArguments` 作为所有工具参数的严格基类，并自动生成 JSON Schema。
2. 使用不可变 `ToolSpec` 保存 Provider 无关的名称、描述与参数模型类型。
3. 使用结构化 `Tool` Protocol 定义异步执行能力，不要求名义继承。
4. 使用 `ToolRegistry` 保存名称到 Tool 的映射，拒绝重复名称并保持 Spec 顺序稳定。
5. 使用 `ToolDispatcher` 集中完成查找、参数验证、执行和 `ToolResult` 关联。
6. 只将未知工具、参数验证失败和显式 `ToolExecutionError` 返回 Agent 闭环；意外程序错误当前继续抛出。
7. 文件工具只能通过 Workspace 访问文件。Workspace 解析真实路径并检查最终路径属于根目录。
8. ReadFileTool 使用可配置的正整数 byte 上限、严格 UTF-8 解码和安全异常转换。
9. Workspace 只是应用层边界，不替代 Policy、Approval、Executor 或 OS Sandbox。

## 正面后果

1. Query Loop 不依赖具体 Tool，ScriptedToolRuntime 与 ToolDispatcher 可以互换。
2. 给模型的参数说明与运行时验证来自同一个 Pydantic 模型，降低漂移风险。
3. Registry、Dispatcher、Workspace 与具体工具可以分别进行单元测试和故障注入。
4. 参数失败发生在副作用前，错误 ToolResult 可供模型在下一轮修正。
5. 重复名称、路径逃逸和巨大文件读取拥有明确回归测试。
6. ToolSpec 保持 Provider 无关，为多个 Model Adapter 留出边界。

## 负面后果

1. 同一调用经过 Schema、Dispatcher、Tool 和 Workspace 多层，代码量高于直接函数调用。
2. `Tool.execute(ToolArguments)` 当前较宽泛，具体工具需要运行时缩窄参数类型；未来可能需要泛型重构。
3. byte 上限不能直接等价为 Token 上限，仍需要独立上下文预算。
4. 应用层路径解析存在检查与打开之间的 TOCTOU 窗口。
5. 特殊文件类型尚未被原子拒绝，读取超时仍需后续 Executor 或 OS Sandbox 提供。
6. 当前没有审计事件，意外程序错误也尚未在最外层隔离和脱敏记录。

## 备选方案

1. 在 Query Loop 中按工具名使用 `if/elif` 执行。
   - 初期代码少，但核心循环依赖所有工具细节，新增工具需要修改 Query Loop。

2. 每个工具自行解析原始字典并创建 ToolResult。
   - 会重复 Schema、`call_id` 关联和错误包装，工具间行为容易不一致。

3. 允许后注册工具覆盖同名工具。
   - 支持热替换，但可能静默改变安全关键能力；当前选择显式拒绝。

4. 只使用字符串前缀检查路径。
   - 无法可靠处理 `..`、相似目录前缀和符号链接，不接受。

5. 先读取完整文件，再检查大小。
   - 检查发生时内存和 I/O 成本已经产生，不接受。

6. 捕获所有 `Exception` 并返回模型。
   - 可提高表面可用性，但会隐藏程序缺陷并可能泄漏内部信息；当前只转换明确的可恢复错误。

## 重新评估条件

1. 具体工具类型缩窄导致大量重复检查，需要引入泛型 Tool/ToolSpec。
2. 引入动态 Skill 或插件后，需要工具版本、来源、签名和覆盖策略。
3. 引入写文件和命令工具后，需要 Policy、Approval 与更强 OS 隔离。
4. Benchmark 证明 100,000-byte 默认上限不合适，或需要分页、行范围和二进制摘要。
5. 真实 Provider 对 JSON Schema、工具名称或稳定顺序有额外限制。
6. 安全评审要求使用 `openat`/目录句柄、容器或其他机制消除路径 TOCTOU 风险。
