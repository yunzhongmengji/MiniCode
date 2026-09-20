# Context Editing v4 预注册协议

状态：**完整批次链路与编排证据门禁均已离线接线；尚未调用真实模型。**

机器可读协议是 `real_model_protocol_v4.json`。它的作用不是启动 Agent，而是在看到实验结果之前，先把
“用什么模型、跑哪些 Case、两组分别使用什么策略、最多花多少 Token、怎样才算通过”锁死。后续运行器只能
读取并遵守这份协议，不能在 projection 失败后临时加轮次、换 Case 或改预算。

## 1. 两个实验组

- baseline：schema 2 的 `identity`，模型看到完整请求。
- projection：schema 3 的 `budgeted_tool_result_reference`。完整历史仍在 Checkpoint 中，只在单轮完整请求
  超过 10,000 bytes 后，才从最旧的可恢复 ToolResult 开始替换。

projection 还固定：保护最近 2 批 ToolResult；`git_diff` 和 `run_tests` 不参加压缩；只有净节省至少 1 byte
才采用引用；单个结果必须能在 50,000 bytes 回读上限内完整恢复。

## 2. 为什么暂定 10,000 bytes

v3 已归档 Trace 的启动请求约为 4.9KB，后段完整请求增长到约 11–14KB。若把预算写成示例里出现过的
120KB，这两个 Case 根本不会触发预算策略，Preflight 无法检验压缩；若预算低于启动请求，则 Agent 从第一轮
就承受压缩压力，也不符合“短任务不增加成本”的目标。

因此 10,000 bytes 是根据现有 Case 请求区间选出的**实验触发点**，不是模型上下文上限，也不是企业生产默认值。
Preflight 要验证它是否既能产生 projection activity，又不损害任务成功；失败就保留结果并注册新协议，不能
改写 v4。

## 3. 运行顺序与停止规则

Preflight 只对 `large_search_context_recall` 各跑一次：先 baseline，后 projection，共 2 次。只有两组都
Safe Task Success、projection 至少改变 1 个历史 ToolResult、没有失败/取消回读、Provider Usage 与工件齐全，
而且总输入/输出不超过 45,000/5,000 Token，才有资格讨论正式实验。

正式实验仍使用两个 Case、每个 Case 每组 3 次，共 12 次；成对顺序和 270,000/30,000 Token 总预算已经写入
JSON。所有运行必须使用同一个干净 MiniCode commit，并记录到每份结果中。

## 4. 当前边界

`load_budgeted_context_experiment_protocol()` 会拒绝 baseline 不是完整 schema 2 Identity、projection 不是完整
schema 3 配置、Preflight 次数与顺序不一致、正式次数与 Case/重复数不一致，以及晋级成功数不一致。

`evaluation_run` 现在能从本协议选择 Arm：baseline 不启用 projector，projection 把协议中的完整配置对象传到
CodingAgent；环境中的模型名不等于登记模型时，会在创建 Provider 客户端前拒绝。`evaluation_result` 读取同一
协议，核对 Case、模型与逐轮 Trace 后才保存协议 ID、Arm 和配置。

`evaluation_summary --context-preflight-protocol real_model_protocol_v4.json` 现在能读取 schema 2 baseline 与
schema 3 projection 结果，并统一检查：两组各一条、Safe Task Success、projection activity、失败/取消回读、
Provider Token 预算、每条工件集合和逐 byte 相同的协议快照。配置与协议不一致会直接拒绝，证据完整但门槛不达标
则报告 `FAIL` 并返回退出码 1。

统一 Preflight 编排器现在会冻结计划，并追加每个 Arm 的开始/结束事件；命令适配器会准备隔离工作区、运行已有
Agent 入口、提取 Trace，再调用已有结果记录器。适配器在模型调用前要求干净 Git 仓库和仓库外结果目录。

汇总门禁现在会交叉校验协议、冻结计划、追加事件、固定结果路径和结果内部 Arm。唯一批次入口是：

```bash
.venv/bin/python -m minicode.evaluation_preflight \
  --protocol benchmarks/context_projection/real_model_protocol_v4.json \
  --results-root /tmp/minicode-context-v4-preflight
```

代码链路已达到准备真实 Preflight 的标准，Provider 环境、模型名、仓库外结果路径和人工 Approval 方式也已完成
只读就绪审计；实现已经形成干净 Git 提交并通过提交后定向测试。本阶段仍没有调用真实模型，不能把离线测试描述成
真实实验结果。下一步必须由用户明确决定是否承担两次真实 Provider 调用并在交互式终端完成工具审批。
