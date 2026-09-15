# Context Projection 真实模型小样本协议

状态：已预注册，尚未运行真实模型。

机器可读配置见 `real_model_protocol.json`。本协议先固定问题、样本、指标、预算和停止条件，
再实现运行入口；不能根据跑出的结果事后更换有利口径。

## 1. 要回答的问题

在相同模型、任务、初始工作区、工具权限和轮次预算下，把较老的大型成功 ToolResult 替换为
可回读引用，是否能在不降低 Safe Task Success 的前提下减少 Provider 报告的输入 Token？

当前离线 bytes 实验只能证明结构变化。真实模型实验必须同时测量：

1. 任务是否通过隐藏验收及 Trace、安全、预算门禁；
2. Provider 返回的 input/output Token；
3. 投影次数、投影 bytes 和历史回读结果；
4. 模型调用与工具执行是否因回读增加。

## 2. 固定对照

两个 Arm 的唯一预期差异是上下文投影闭环：

| Arm | `max_inline_tool_result_bytes` | 模型工具集合 |
|---|---:|---|
| baseline | `None` | 默认七个工具 |
| projection | `500` | 默认工具加 `read_tool_result` |

额外 Tool Spec 是完整策略的一部分，其 Token 成本必须计入 projection，不能从结果中扣除。
两个 Arm 均使用 `qwen3.7-flash-2026-07-15`、`enable_thinking=false`；MiniCode 当前没有设置
temperature，所以协议如实记录为 Provider 默认值，不能写成 temperature=0。

每次运行必须使用从同一 Case 快照创建的新临时工作区、相同任务文本、相同 max turns/tool
calls、相同 Policy 和 Approval 规则。每个 Case 的运行顺序交替为 `A B / B A / A B`，降低
服务时间漂移总是偏向同一 Arm 的风险。

## 3. 样本与规模

首批只选择：

- `multi_file_inventory_contract`：已有一次运行使用 5 次模型调用、8527 input Token；
- `search_driven_retry_schedule`：已有一次运行使用 6 次模型调用、10882 input Token。

它们比只读诊断更长，也覆盖跨文件契约和搜索驱动修复。历史数字只用于选择样本和估算预算，
不能与新版本结果直接合并。

正式实验为 `2 cases × 2 arms × 3 repetitions = 12 runs`。在此之前最多运行一对 2-run
Preflight，只验证配置、Trace 和结果记录，不进入正式统计。

## 4. 预注册指标与门禁

主要质量指标是 Safe Task Success，即隐藏验收、运行结局、预算和 Trace 四个维度全部通过。
主要效率指标是两个 Case 汇总的 input Token；output Token、总 Token、模型调用、工具执行、
回读数和投影 bytes 为辅助诊断。

只有同时满足以下条件才进入“可以考虑产品入口”的下一阶段：

1. baseline 和 projection 都是 6/6 Safe Task Success；若 baseline 自己不稳定，结论记为无效，
   不把 projection 的差异解释为压缩效果；
2. projection 汇总 input Token 至少降低 5%；
3. 任一 Case 的 projection input Token 总和相对 baseline 增长不超过 5%，避免汇总掩盖退化；
4. 未授权副作用为 0，失败或取消的 `read_tool_result` 为 0；
5. 全部原始 answer、trace、patch、result 和协议快照均保留，失败样本不得删除。

12 次运行只是工程小样本，不足以声称统计显著性或通用成功率。即使通过，也只能描述固定
模型、固定 Case 和固定版本上的消融结果。

## 5. 预算与停止条件

Preflight 上限：2 runs、30000 input Token、5000 output Token。正式阶段上限：12 runs、
180000 input Token、30000 output Token。达到任一上限就停止，不用“已经快跑完了”为理由超支。

发生以下情况也立即停止，并保存已经产生的失败记录：

- 出现未授权副作用或跨 Run 历史读取；
- 回读失败或取消，说明压缩闭环本身不可靠；
- 结果记录缺少 Arm、阈值、协议版本或上下文统计；
- 无法固定模型名称、初始 Case 或 MiniCode 版本；
- Provider Usage 缺失，导致主要效率指标无法计算。

普通任务失败不应被悄悄重跑替换；它属于正式样本。Provider 基础设施故障应单独标记，是否
补跑必须按同一规则处理两个 Arm，并在汇总中公开。

## 6. 开跑前工程能力

离线工具链已经补齐：

1. 已完成：`evaluation_run --arm baseline|projection` 能把 `None|500` 传到 Agent 组装；
2. 已完成：`evaluation_result` 保存协议 ID、Arm、阈值及投影/回读汇总，并校验声明与 Trace；
3. 已完成：汇总器按协议、Case、Arm 和重复次数对齐结果，并检查质量、Token 与回读门禁。

Arm 参数只存在于 Benchmark 入口，普通 `minicode run` 没有公开压缩选项。Scripted Model
测试已经从最终 ModelRequest 验证 baseline 为七个工具、projection 额外包含
`read_tool_result`，整个过程没有调用真实 Provider。

每个 `MODEL_CALL_STARTED.context_projection` 现在同时保存 strategy 和配置阈值，因此即使某次
运行没有实际压缩任何结果，也能区分“projection 已启用但没有命中”和“baseline 未启用”。

Preflight 与正式结果必须放在不同目录，汇总器只接收正式目录，避免两次 Preflight 被误算进
12 次正式样本。例如：

```bash
.venv/bin/python -m minicode.evaluation_summary \
  benchmarks/context_projection/results/formal \
  --context-protocol benchmarks/context_projection/real_model_protocol.json
```

它会拒绝协议、模型、阈值或 commit 混杂的结果，也会拒绝 dirty 运行、重复 Run ID、缺少
Provider input Token 或上下文指标自相矛盾的记录。正式样本次数不足、Safe Task Success 不足、
Token 门禁不达标或回读失败时，报告的 `Advancement gate` 为 `FAIL`。

至此可以进入一对 2-run Preflight，但它会产生真实 Provider 调用和费用，必须单独获得同意后
才执行；当前仍未调用真实模型。Preflight 通过也不能进入正式统计，只用于验证端到端记录。
