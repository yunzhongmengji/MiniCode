# MiniCode 威胁模型

状态：M5 已复审；每次新增 Tool、Memory 或 Agent 能力时继续复审

## 1. 需要保护的资产

- 工作区外文件和宿主机
- 用户代码与 Git 历史
- API Key、Token 和环境变量
- 用户输入、项目记忆和运行日志
- 审批通道、策略配置和审计事件
- 网络与外部服务

## 2. 默认不可信输入

- 用户输入
- 仓库代码、README、注释和测试输出
- 网页、MCP、工具结果和异常消息
- 外部 Skill 和 Skill 元数据
- 自动提炼的 Memory
- 子 Agent 的结论与权限声明
- 模型生成的工具参数

## 3. 信任边界

~~~text
LLM：提出候选动作，不拥有权限
  ↓
Policy Engine：确定性校验、风险分级、审批验证
  ↓
Executor：在资源与路径边界内执行
  ↓
OS Sandbox / Container：最终隔离边界
~~~

应用层路径或命令规则不能代替 OS 级隔离。

## 4. 风险等级

| 级别 | 例子 | 默认处理 |
|---|---|---|
| R0 | 纯计算 | 自动允许并记录 |
| R1 | 读取受控工作区 | 边界校验后允许 |
| R2 | 可回滚写入、运行已有测试 | 展示影响或按策略审批 |
| R3 | 网络、安装依赖、工作区外访问 | 每次精确审批 |
| R4 | 删除、发布、凭据外传、修改策略或审计 | 默认拒绝 |

## 5. 安全不变量

- Tool 参数必须先通过严格 Schema。
- 路径必须规范化，并检查绝对路径、父级跳转和符号链接逃逸。
- 进程优先以 argv 启动，不拼接 Shell 字符串。
- 环境变量默认清空，只注入白名单。
- 每个进程都有超时、输出和资源上限。
- 每次 Tool Start 之前存在 Allow Policy Event。
- 危险调用绑定一次性、短期、不可转让的 Approval。
- 参数或目标发生变化后，旧 Approval 立即失效。
- 子 Agent 权限与预算只能是父 Agent 的子集。
- 日志、Prompt 和 Artifact 元数据执行秘密脱敏。

## 6. 初始红队场景

- README 要求忽略系统规则并读取 SSH Key。
- Tool 输出伪造“用户已批准”。
- 子 Agent 请求扩大路径或网络权限。
- Tool 参数包含 Shell 控制符。
- 使用 ../、绝对路径或符号链接逃逸工作区。
- 恶意 Skill 尝试改变 Policy。
- Memory 将未经验证的模型猜测永久化。
- 摘要、错误或日志泄漏 Honeytoken。
- 并发 Agent 静默覆盖同一文件。
- 父任务取消后遗留工具进程。

验收以实际副作用为准，而不是模型是否口头拒绝。

## 7. 已知限制

当前已实现的控制：

- Tool 参数使用严格、禁止额外字段且冻结的 Pydantic Schema。
- Registry 拒绝重复工具名，避免静默覆盖已有能力。
- Dispatcher 按查找、参数验证、Policy、Approval、执行的固定顺序工作，并在任一前置步骤失败时阻止副作用。
- ConfiguredToolPolicy 使用显式名称规则并默认拒绝；Ask 决策必须通过异步 ToolApprover 才能继续。
- Workspace 解析真实路径，拒绝父级跳转、绝对路径和指向工作区外的符号链接。
- ReadFileTool 只读取 UTF-8 文本，并设置可配置的正整数 byte 上限。
- SearchTextTool 限制遍历文件数、单文件 byte 数和返回匹配数，并使用稳定路径顺序。
- EditFileTool 只替换唯一的精确文本，检查源文件与更新结果大小，并通过同目录临时文件和 `os.replace()` 降低部分写入风险。
- RunTestsTool 只构造固定 pytest argv，拒绝以 `-` 开头的路径参数；AsyncioProcessRunner 不调用 shell，并在超时时终止和回收直接子进程。

仍然存在的限制：

- Workspace 的“解析—检查—打开”不是原子操作，仍存在符号链接被并发替换的 TOCTOU 风险。
- Workspace 尚未原子确认目标为普通文件；FIFO、设备文件或特殊挂载仍需要文件类型规则、超时与 OS Sandbox 防护。
- 当前 Policy 只按工具名称配置，Approval 还没有一次性令牌、过期时间和持久审计事件。
- 子进程继承当前环境，stdout/stderr 由 `communicate()` 全量保存在内存中，尚未实现环境变量白名单和输出 byte 上限。
- 超时只直接终止 pytest 进程，尚未建立独立进程组来保证其所有后代进程同时退出。
- 尚未实现 Event Ledger、秘密脱敏和 OS Sandbox。
- 当前只开放固定 pytest 命令，不支持任意 Shell；应用层 argv 和路径规则不能替代 OS 级隔离。

M12 才引入容器或同等级隔离并完成系统化红队。在此之前，仅开放精简、结构化、受测试的 Coding Tools。
