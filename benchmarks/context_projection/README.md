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

报告单位是规范化 JSON 的 UTF-8 bytes，不是模型 Token。`projection_bytes_saved` 是每轮
canonical request 与 projected request 的内部差值；`model_visible_byte_difference` 则比较
两次完整运行实际发送的累计 bytes，已经包含额外回读轮次。后者为负时，表示该场景虽然
每次投影都缩短了请求，但急切回读带来的额外模型调用使整次运行反而发送更多内容。

当前确定性结果：

- 急切回读场景内部投影累计省 10142 bytes，但额外模型轮次使整次运行净增加 6945 bytes。
- 不回读场景内部投影累计省 5071 bytes；计入额外回读工具定义后，整次运行仍净减少
  3571 bytes。

这两个端点说明收益由“旧结果被压缩后还需不需要取回”决定，但尚未给出真实模型的回读率、
Token 节省或答案质量。

## 成本分解

每个场景都验证下面的恒等式：

```text
净模型可见 bytes 收益
= 投影内部减少的 bytes
- 开启投影后运行形状新增的 canonical bytes
```

“运行形状新增”不是只指回读结果，还包括新增的 `read_tool_result` Tool Spec、额外模型轮次、
回读 ToolCall 和回读 ToolResult。当前事件只能可靠计算这些成本的总和，不把总和伪装成每项
都已单独测量。

- 不回读：`3571 = 5071 - 1500`，得到净收益。
- 急切回读：`-6945 = 10142 - 17087`，出现净亏损。

如果假设一个任务集合只由这两个固定端点按相同比重口径线性混合，并令 `p` 为“急切回读型
任务占比”，则平均净收益为：

```text
(1 - p) * 3571 + p * (-6945) = 3571 - 10516p
```

令平均净收益为 0，得到 `p = 3571 / 10516 ≈ 33.96%`。这只是当前固定输入、输出大小、工具
定义和确定性决策下的**示意盈亏点**，不是单个引用的通用回读概率，也不是生产阈值。

真实模型阶段的预注册样本、指标、预算和停止条件见 `REAL_MODEL_PROTOCOL.md`；机器可读配置
保存在 `real_model_protocol.json`。一对真实 Provider Preflight 已完成，原始证据和报告保存在
`results/preflight-007d4b9-qwen3.7-flash-2026-07-15/`；它不进入正式统计。Preflight 发现审批
提示混入 `answer.txt`；stdout/stderr 分流及回归测试随后已修复，原始 Preflight 工件保留不改。
