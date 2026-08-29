# ADR-0004：使用 Provider 无关的模型边界与 OpenAI 兼容 Adapter

状态：Accepted
日期：2026-08-29

## 背景

Query Loop 最初只向 `Model.complete()` 传递对话历史。真实 Provider 接入后，一次请求还需要携带有序的工具定义，并处理以下差异：

1. MiniCode 使用独立的 `Message`、`ToolCall` 和 `ToolResult`，SDK 使用角色消息字典。
2. MiniCode `ToolSpec` 使用 Pydantic 类型，SDK 需要 JSON Schema function tool。
3. SDK 工具参数以 JSON 字符串返回，核心层需要结构化且经过不变量校验的 `ToolCall`。
4. SDK 暴露供应商相关异常，Query Loop 不应依赖这些异常类型。
5. 阿里云等兼容 Provider 可能需要额外请求字段和不同配置，但核心循环不应随之变化。

## 决策

1. 将 `Model.complete()` 输入扩展为不可变 `ModelRequest`，同时携带结构化对话和 `ToolSpec` 快照。
2. 核心层只定义 `ModelRequest`、`ModelResponse`、`Model` Protocol 和稳定错误分类，不导入 Provider SDK。
3. 使用 `OpenAICompatibleModel` 作为通用边界 Adapter，集中完成消息、工具定义、工具调用和响应转换。
4. 保留 MiniCode 的扁平结构化历史；只在 Adapter 边界将连续工具调用组合进 assistant 消息。
5. 由核心 `ToolCall` 维护字段不变量，Adapter 将构造失败统一转换为 `ModelProtocolError`。
6. 将 SDK 认证、额度、权限、限流、连接和服务错误转换为 MiniCode 异常，并保留异常链。
7. 使用 `DashScopeConfig`、`build_dashscope_client` 和 `build_dashscope_model` 隔离供应商配置与对象组装。
8. Provider 特有参数通过 Adapter 的 `extra_body` 快照传递，不加入核心 `ModelRequest`。
9. SDK client 当前配置 60 秒超时和 2 次 SDK 重试；MiniCode 暂不叠加第二套自动重试循环。

## 正面后果

1. `ScriptedModel` 和真实 DashScope Model 满足同一个 `Model` Protocol，Query Loop 无需分支。
2. 核心对话和 Tool Runtime 不依赖 OpenAI SDK 类型或版本。
3. 转换逻辑、网络调用和 Provider 配置可以分别进行离线测试。
4. 更换 OpenAI 兼容 Provider 主要改变 client 配置和扩展参数。
5. SDK 异常不会泄漏为核心层的公共契约，调用方可以按稳定类别处理。
6. 真实文本请求和两轮 read-file 工具闭环已在受控临时目录中验证。

## 负面后果

1. 同一份数据在核心格式和 SDK 格式之间转换，代码量与测试数量增加。
2. OpenAI 兼容并不代表行为完全一致，Provider 扩展仍需要显式处理。
3. 扁平历史转角色消息需要暂存和 flush，顺序错误会产生无效对话。
4. 当前只支持非流式 Chat Completions 和第一个 choice。
5. `extra_body` 是弱类型扩展口，拼写或 Provider 不支持的问题只能在请求时发现。
6. SDK 自动重试会增加单次调用的最坏耗时，未来需要结合总时限和可观测数据评估。

## 备选方案

1. 核心层直接采用 OpenAI SDK 请求和响应类型。
   - 初期转换代码较少，但 Query Loop、Fake、工具协议和 Provider SDK 强耦合，不接受。

2. 为 DashScope 单独实现全部消息和工具转换。
   - Provider 身份清晰，但与其他 OpenAI 兼容服务重复大量代码。

3. 让 Query Loop 直接接收 `ToolRegistry`。
   - 可以自动取得 specs，但会把模型请求描述与工具执行生命周期绑定；当前保持 `tool_specs` 和 `tool_runtime` 两个独立依赖。

4. 捕获所有 SDK 或 Python 异常并包装为一个 `ModelError`。
   - 接口简单，但调用方无法区分认证、限流、连接、额度和协议错误，不接受。

5. 在 MiniCode 中再次实现自动重试。
   - 可以自定义策略，但会与 SDK 重试叠加并放大请求次数；在取得延迟和错误率数据前不采用。

## 重新评估条件

1. 接入非 OpenAI 兼容 Provider，需要新的 Adapter 或更通用的中间表示。
2. 实现流式输出后，`Model` Protocol 可能需要事件流或独立 streaming 方法。
3. 指标证明 SDK 默认重试策略不满足总时限、成本或限流要求。
4. Provider 需要大量 `extra_body` 字段，弱类型扩展开始产生维护问题。
5. 支持多候选、结构化输出、图像或其他消息内容后，现有 `Message.content: str` 不再足够。
