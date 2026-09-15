# Context Projection v2 真实模型 Preflight 报告

运行日期：2026-09-15  
协议：`context-projection-adaptive-real-model-pilot-v2`  
模型：`qwen3.7-flash-2026-07-15`  
MiniCode commit：`86a3ddcea1e8ad904cad4acb1aab461c82ab4128`  
结论：**FAIL，不进入正式 12-run 实验。**

## 1. 门禁结果

| Arm | Runs | Safe success | Input tokens | Output tokens | Changed ToolResults | Readbacks failed/cancelled |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 1 | 0/1 | 13571 | 551 | 0 | 0/0 |
| projection | 1 | 1/1 | 11104 | 541 | 0 | 0/0 |

- Run shape：PASS
- Safe Task Success：FAIL
- Projection activity：FAIL，`0/1`
- Failed or cancelled readbacks：PASS，`0/0`
- Provider input Token budget：PASS，`24675/30000`
- Provider output Token budget：PASS，`1092/5000`
- Provider Usage、每 Run Artifact、协议快照：PASS
- Preflight gate：**FAIL**，CLI 退出码为 `1`

## 2. baseline 为什么失败

baseline 找到了共享根因，但把循环改成了 `range(0, attempts + 1)`。这虽然让序列从 1 秒开始，
却多生成一项：三次重试得到 `1, 2, 4, 8`，而不是 `1, 2, 4`。相关测试失败后，模型又发起了
一个超过剩余预算的工具请求，最终以 `max_tool_calls` 停止。隐藏验收因此失败。

这不是 Context Projection 故障，而是一次真实的 Agent 任务失败。协议要求保留该样本，不能
删除后补跑以改变 Preflight 结论。

## 3. projection 为什么没有发生投影

projection 正确修复为 `range(0, attempts)`，相关测试和隐藏验收均通过；但六次模型请求的
`changed_tool_result_count` 全部为 0。自适应投影器会先比较完整 ModelRequest：只有候选引用
节省的 ToolResult bytes 足以覆盖本轮新增的 `read_tool_result` Tool Spec，才会采用引用。

本次 Case 的工具结果都不够大，因此保持完整请求是算法的正确行为。但是，这也说明
`search_driven_retry_schedule` 不能覆盖新策略的核心投影路径，不能作为 v2 晋级证据。

## 4. 不能从本结果推出什么

projection 的输入 Token 比 baseline 少 2467，但不能据此声称压缩节省约 18.2%。projection
实际没有改变任何 ToolResult，而且两次运行的模型输出、工具调用数量和成败路径不同。
这个差异只能描述两条独立轨迹，不能归因于 Context Projection。

同理，一次成功、一次失败也不能说明 projection 提高了任务成功率；每个 Arm 只有一个样本。

## 5. 下一步

停止 v2 正式实验。下一阶段先离线设计一个能稳定产生足够大历史 ToolResult、同时仍有真实
Coding 目标的 Case，并用 Scripted Model 证明它会命中投影和可选回读分支。由于该 Case 是在
看过 v2 结果后新增的，后续真实验证必须预注册新协议 ID，不能修改 v2 后冒充原实验。

## 6. 原始证据

每个 Arm 都保存：

- `answer.txt`：模型最终 stdout；baseline 在预算停止前没有最终回答，因此为空文件；
- `stderr.raw.txt`：Run ID、人工审批提示和 Trace 的完整 stderr；
- `trace.txt`：从原始 stderr 提取的规范 Trace；
- `workspace.patch`：隐藏验收前的工作区改动；
- `result.json`：验收、运行、预算、Trace、Usage、投影指标和 Artifact 哈希。

根目录的 `protocol.snapshot.json` 与运行时协议 SHA-256 一致：
`7951199c715bbb7f32459ea1d85e300155c80dffe53e25d6be82f6d69baf9e5e`。
