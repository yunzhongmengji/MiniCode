# Context Projection Preflight 报告

状态：两次真实运行完成，但发现 Answer 捕获污染；正式 12-run 实验暂停。

固定条件：`multi_file_inventory_contract`、MiniCode `007d4b9`、
`qwen3.7-flash-2026-07-15`。baseline 与 projection 各运行一次，均从独立的相同 Case
快照开始。预运行协议保存在 `protocol.snapshot.json`。

| 指标 | baseline | projection | 差异 |
|---|---:|---:|---:|
| Safe Task Success | 1/1 | 1/1 | 相同 |
| Model calls | 5 | 5 | 0 |
| Tool executions | 7 | 7 | 0 |
| Provider input Token | 8559 | 9047 | +488（+5.7%） |
| Provider output Token | 419 | 422 | +3 |
| Canonical bytes | 30278 | 32764 | +2486 |
| Model-visible bytes | 30278 | 31942 | +1664 |
| Projection bytes saved | 0 | 822 | +822 |
| Failed/cancelled readbacks | 0 | 0 | 0 |

两次运行都只修改 `inventory.py` 和 `report.py`，修改后公开测试、隐藏验收、运行、预算和
Trace 门禁全部通过；两份 `workspace.patch` 的 SHA-256 相同。

projection 在第 4、5 次模型请求中各缩短 411 bytes，说明投影和引用生成真实生效；模型没有
请求回读。但新增 `read_tool_result` Tool Spec 在五次请求中重复出现，新增运行形状成本大于
822-byte 内部节省，最终模型可见 bytes 增加 1664，Provider input Token 增加 488。

这份 Preflight 证明真实 Provider、投影、Trace、结果记录、工件哈希和隐藏验收链路能够工作，
同时给出一个需要重视的效率警告。它不是正式样本，不能据此估计稳定成功率或断言策略普遍
无效，也不能混入 `formal/` 汇总。

Preflight 还发现 `answer.txt` 混入了人工审批提示。`ConsoleToolApprover` 当前通过
`input(prompt)` 把提示写到 stdout，而评测脚本把 stdout 整体保存为 Answer。隐藏验收不读取
本 Case 的 Answer，所以本次质量判定未被改变；原始文件和哈希也保持不动。但这违反
“Answer Artifact 只表示模型最终回答”的证据语义，必须在正式实验前把审批提示改到 stderr，
并增加回归测试。修复前不进入正式 12-run 阶段。

后续实现已将审批提示与输入读取拆开：提示明确写入 stderr，无提示的 `input()` 只从 stdin
读取答案。回归测试同时断言审批提示不出现在 stdout，原有 CLI 测试继续断言 stdout 只包含
模型最终回答。这里保存的 Preflight 原始文件不追溯修改。

两次运行合计 17606 input Token、841 output Token，低于预注册 Preflight 上限
30000/5000。
