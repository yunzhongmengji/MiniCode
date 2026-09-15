# Context Projection 自适应策略真实模型协议 v2

状态：真实 Preflight 已完成并判定 FAIL；正式样本未启动，v2 停止。

机器可读协议见 `real_model_protocol_v2.json`。v1 的原始协议、Preflight 和失败结论继续保留，
但不得与 v2 结果合并。

## 1. 为什么必须建立 v2

v1 的 projection 从第一轮起始终向模型发送 `read_tool_result` Tool Spec。真实 Preflight 中，
两次实际引用共缩短 822 bytes，但五轮工具定义固定开销更大，Provider input Token 反而增加
约 5.7%。随后实现改成自适应策略：先构造候选引用并计算完整 ModelRequest，只有净节省至少
1 byte 才采用引用，而且只在该轮加载回读 Tool Spec。

这是观察 v1 结果之后发生的策略修改。继续使用 v1 协议会把两个不同实验条件混在一起，因而
必须换协议 ID、配置 schema 和结果目录。

## 2. v2 唯一实验变量

| 配置 | baseline | projection |
|---|---|---|
| strategy | `identity` | `tool_result_reference` |
| 单结果候选阈值 | `null` | `500 bytes` |
| 完整请求最小净节省 | `null` | `1 byte` |
| 回读 Tool Spec 加载 | `null` | `on_reference` |

两个 Arm 的模型、Case、初始工作区、预算、Policy、Approval 和代码版本必须相同。projection
允许在不划算时退化成与 baseline 相同的完整请求；这是策略行为，不是实验失效。

## 3. Case 与 Preflight

正式 Case 仍是 `multi_file_inventory_contract` 和 `search_driven_retry_schedule`。前者在 v1 中
单次引用的毛节省不足以覆盖回读 Tool Spec，新策略应主动保持完整请求；后者会积累更多历史
工具结果，更适合作为 v2 Preflight 候选。

Preflight 只运行 `search_driven_retry_schedule` 的 baseline、projection 各一次，不进入正式
统计。除了两次 Safe Task Success，还必须至少观察到一个
`changed_tool_result_count > 0`。若没有命中，说明这对运行没有覆盖
新策略核心路径：应停止并重新审视 Case，不能把“两组都成功”当作压缩闭环验证完成。

Preflight 还要求 Provider Usage 存在、失败或取消回读为 0、Answer 不含审批提示，并完整保存
answer、trace、patch、result 和协议快照。

## 4. 正式样本和晋级标准

正式实验仍为 `2 cases × 2 arms × 3 repetitions = 12 runs`，每个 Case 按
`A B / B A / A B` 交替顺序运行。所有结果必须来自同一个干净 MiniCode commit。

只有以下条件全部满足，才进入“可以考虑产品入口”的阶段：

1. 两个 Arm 都达到 6/6 Safe Task Success；
2. projection 汇总 Provider input Token 至少降低 5%；
3. 任一 Case 的 input Token 退化不超过 5%；
4. 未授权副作用、失败或取消回读均为 0；
5. 12 份原始工件全部保留且哈希一致。

这仍是固定模型和固定 Case 上的工程小样本，不能宣传为普遍有效或统计显著。

## 5. 预算和停止条件

Preflight 上限为 2 runs、30000 input Token、5000 output Token；正式实验上限为 12 runs、
180000 input Token、30000 output Token。任一上限触发即停止。

发现跨 Run 读取、配置与 Trace 不一致、Provider Usage 缺失、脏工作区、模型或 commit 混杂、
Artifact 不完整时，也必须保存现状并停止，不能通过删除失败样本或临时放宽规则继续运行。

## 6. 当前阶段边界

协议文件、离线解析、只读就绪审计和两条真实 Provider Preflight 均已完成。原始结果与报告
保存在 `results/v2-preflight/`。门禁确认 baseline Safe Task Success 失败，并且 projection
虽然任务成功，却没有改变任何 ToolResult，因此没有覆盖自适应投影路径。

v2 按预注册停止条件结束，不能进入正式 12-run 实验。后续应先离线构造能稳定触发净收益门槛
的 Case；由于这是观察 v2 之后的实验设计变化，新的真实验证必须使用新的协议 ID。
