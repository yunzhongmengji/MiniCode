# Context Editing v4 真实模型 Preflight 报告

运行日期：2026-09-20

协议：`context-editing-budget-real-model-pilot-v4`

模型：`qwen3.7-flash-2026-07-15`

MiniCode commit：`b95afeb6fcf78acb9988368ac09ee812b31f90ba`

结论：**PASS，可以决定是否进入预注册的正式 12-run 实验，但尚未证明总 Token 更省。**

## 1. 门禁结果

| Arm | Runs | Safe success | Input tokens | Output tokens | Changed ToolResults | Readbacks failed/cancelled |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 1 | 1/1 | 13762 | 386 | 0 | 0/0 |
| projection | 1 | 1/1 | 18422 | 486 | 7 | 0/0 |

- Run shape、Safe Task Success、Provider Usage、Artifact、协议快照和编排证据：PASS。
- projection activity：`7/1`，PASS。这里的 7 是各轮请求中被替换结果数的累计值，不代表 7 个唯一结果。
- 失败或取消回读：`0/0`，PASS；另有一次成功回读。
- Provider input/output Token：`32184/45000`、`872/5000`，均在 Preflight 预算内。
- Preflight gate：**PASS**，批次 CLI 退出码为 `0`。

## 2. 两条运行分别发生了什么

两组都从相同 Case 创建独立的干净工作区，并成功完成：`list_files`、唯一一次 `search_text`、读取定义与调用方、
把 `service_config/timeouts.py` 的共享默认值从 3 改为 30、运行 `tests/test_timeouts.py`，最后给出要求的 25 个客户端
证据总结。隐藏验收确认只有目标实现文件发生变化，测试、Trace 工具契约和最终回答全部通过。

baseline 使用 6 次模型调用和 7 次工具执行。projection 使用 8 次模型调用和 9 次工具执行；除共同链路外，
它又执行了 `git_diff`，并通过 `read_tool_result` 成功恢复先前 2730-byte 的搜索结果后再提交最终回答。所有人工审批
都只批准了案例允许的 `edit_file` 与 `run_tests`。

## 3. 压缩生效，但本次整条轨迹更贵

projection 自己的 8 个请求累计指标为：

```text
未投影时累计请求：82251 bytes
实际模型可见请求：70240 bytes
投影累计节省：    12011 bytes
```

在双方共有的前 6 次模型调用中，baseline 输入 13762 Token，projection 输入 12923 Token；projection 少 839
Token，约 6.10%。这说明对齐相同调用位置时，引用确实降低了请求成本。

但 projection 随后多出两个模型调用，新增 5499 input Token，最终变成：

```text
整次输入 Token：18422 - 13762 = +4660（+33.86%）
整次输出 Token：  486 -   386 =  +100
```

因此 Preflight PASS 的准确含义是“策略被真实触发、任务仍安全成功、回读可用、证据和预算完整”，不是“已经证明
节省 Token”。单个 Arm 各一条样本，且 Provider 使用默认 temperature，不能把额外 `git_diff`、回读或轮次确定
归因于压缩，也不能忽略它们造成的端到端成本。

最后一轮完整请求为 15856 bytes，投影后为 11876 bytes，仍高于 10000-byte 目标。这不是静默失效：最近两批、
`git_diff`、`run_tests` 和不可牺牲结构受到保护，可压缩候选用完后仍可能无法满足目标。当前预算是触发和尽力压缩
目标，不是通过丢弃受保护信息强制截断的硬上限。

## 4. 决策边界

按照预注册规则，v4 已通过进入正式实验前的安全门槛。正式实验仍是两个 Case、每个 Case 每组 3 次，共 12 次，
总预算为 270000 input / 30000 output Token，最终要求 projection 聚合输入至少降低 5%，且任何单 Case 回归不超过
5%。只有正式重复样本才能判断本次额外轨迹是随机波动还是稳定代价。

本报告不自动启动正式实验，也不根据已观察结果改动 v4 参数。是否承担 12 次真实调用应由用户另行明确决定；若
改变预算、提示、Case 或策略，必须注册新协议，不能与 v4 结果混合。

## 5. 原始证据

归档保留每个 Arm 的 Answer、原始 stderr、规范 Trace、workspace patch 和 `result.json`，以及批次协议快照、冻结
计划和追加事件。运行期临时工作区路径与空记录器 stderr 不作为长期实验工件。

关键 SHA-256：

- baseline 原始 stderr：`31bf6620de0b5b994b5d3ef415add47a20f817c5f39bb4f425c458f0390c4707`
- projection 原始 stderr：`33b386dfe21c6be814e8086a02f64b9d6b8e641bf158ba2da3f9ec02955aa016`
- 协议快照：`18b26a014564764e2e8b8cd32cb8086f8db28e8112ad499c6175dd8ff7402486`
- 冻结计划：`702c9da7f8bd298287745b7046597fe47ee14388616ac1dd5f9b4ffffe6e7e41`
- 编排事件：`3d6c85d22e206935c180fec2c8974438ea88903590120fa0885060bb0daf5998`
