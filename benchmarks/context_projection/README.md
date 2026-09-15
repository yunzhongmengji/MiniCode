# Context Projection 离线对照

该实验不调用外部模型。它用同一个确定性模型策略分别运行默认上下文和短引用上下文。
目前包含两个端点场景：

1. `eager_historical_readback`：任务仍需要历史原文，看到引用后必须调用
   `read_tool_result`。
2. `no_historical_readback`：任务只需要最新证据，旧结果即使被替换为引用也无需回读。

两个场景都先读取一份较大的历史文件，再读取一份最新文件。每个场景内部的关闭组与
开启组使用同一决策规则，最终报告比较累计模型可见 bytes、投影内部节省、模型调用、
工具调用和回读次数。

运行：

```bash
.venv/bin/python -m minicode.context_comparison
.venv/bin/python -m minicode.context_comparison --scenario no_historical_readback
.venv/bin/python -m minicode.context_comparison --suite
```

报告单位是规范化 JSON 的 UTF-8 bytes，不是模型 Token。`tool_result_bytes_saved` 是工具结果
被短引用替换得到的毛节省；`projection_bytes_saved` 还扣除了引用出现时才加入的
`read_tool_result` Tool Spec，表示同一请求的净节省。`model_visible_byte_difference` 比较两次
完整运行实际发送的累计 bytes，还包含额外回读轮次。后者为负时，表示每个发生投影的请求
虽然都变小了，但急切回读带来的额外模型调用仍使整次运行发送更多内容。

当前确定性结果：

- 急切回读场景工具结果毛节省 10142 bytes，按需工具定义花费 1000 bytes，额外模型轮次等
  运行形状成本为 15087 bytes，整次运行净增加 5945 bytes。
- 不回读场景工具结果毛节省 5071 bytes；只在引用出现的一轮花费 500 bytes 工具定义，整次
  运行净减少 4571 bytes。

这两个端点说明收益由“旧结果被压缩后还需不需要取回”决定，但尚未给出真实模型的回读率、
Token 节省或答案质量。

## 成本分解

每个场景都验证下面的恒等式：

```text
净模型可见 bytes 收益
= 工具结果毛节省
- 按需加入回读工具的开销
- 额外轮次、调用与结果形成的运行形状开销
```

投影器先生成候选引用，再用与 Trace 相同的规范化 JSON 口径计算完整请求。如果工具结果的
毛节省不能严格覆盖本轮新增 Tool Spec，就放弃全部候选引用并保持原请求。回读工具已注册在
运行时中，但只在真正产生引用的模型请求中可见。

该策略不能只存在于代码注释里。每次 `MODEL_CALL_STARTED.context_projection` 都会记录配置
schema 2、`minimum_net_savings_bytes=1` 和 `retrieval_tool_loading=on_reference`；实验结果
记录器逐轮验证，已声明 schema 2 的落盘结果若缺失或篡改这些字段，汇总器也会拒绝。

- 不回读：`4571 = 5071 - 500 - 0`，得到净收益。
- 急切回读：`-5945 = 10142 - 1000 - 15087`，仍因额外回读轮次亏损。

如果假设一个任务集合只由这两个固定端点按相同比重口径线性混合，并令 `p` 为“急切回读型
任务占比”，则平均净收益为：

```text
(1 - p) * 4571 + p * (-5945) = 4571 - 10516p
```

令平均净收益为 0，得到 `p = 4571 / 10516 ≈ 43.47%`。这只是当前固定输入、输出大小、工具
定义和确定性决策下的**示意盈亏点**，不是单个引用的通用回读概率，也不是生产阈值。

优化前真实模型 v1 协议见 `REAL_MODEL_PROTOCOL.md`，机器可读配置保存在
`real_model_protocol.json`。一对真实 Provider Preflight 已完成，原始证据和报告保存在
`results/preflight-007d4b9-qwen3.7-flash-2026-07-15/`；它不进入正式统计。Preflight 发现审批
提示混入 `answer.txt`；stdout/stderr 分流及回归测试随后已修复，原始 Preflight 工件保留不改。
由于本页策略是根据该 Preflight 新增的自适应版本，v1 已停止，后续真实运行必须使用新协议。

自适应策略的预注册协议见 `REAL_MODEL_PROTOCOL_V2.md` 和
`real_model_protocol_v2.json`。v2 尚未运行真实模型；首先只允许一对独立 Preflight，并要求
projection 至少实际命中一次，否则不能证明新路径得到端到端覆盖。

两条 Preflight 结果使用专用门禁，不能交给要求 12 条正式样本的汇总模式：

```bash
.venv/bin/python -m minicode.evaluation_summary \
  benchmarks/context_projection/results/v2-preflight \
  --context-preflight-protocol \
  benchmarks/context_projection/real_model_protocol_v2.json
```
