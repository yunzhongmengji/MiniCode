# Context Projection v2 Preflight 就绪审计

审计日期：2026-09-15  
审计基线：MiniCode `26d10ed`  
结论：环境条件通过；审计发现的离线 Preflight 结果验证器已补齐。随后执行的真实 Preflight
结果见 `results/v2-preflight/REPORT.md`。

本审计没有调用 Provider，没有创建临时评测 Workspace，也没有创建 v2 结果目录。

## 1. 已通过项目

| 检查项 | 结果 | 证据 |
|---|---|---|
| Git 状态 | 通过 | 审计开始时 tracked/untracked 改动均为空 |
| v2 协议解析 | 通过 | 解析为 `context-projection-adaptive-real-model-pilot-v2`，配置 schema 2 |
| Provider 模型 | 通过 | 有效模型名为 `qwen3.7-flash-2026-07-15`，与协议一致 |
| Provider 凭据 | 通过 | `DASHSCOPE_API_KEY` 存在；审计未读取或输出其值 |
| Preflight Case | 通过 | `search_driven_retry_schedule` 的 manifest、task、acceptance、workspace 完整且被 Git 跟踪 |
| 运行预算 | 通过 | Case 为 8 turns / 8 tool calls；协议最多 2 runs、30000 input / 5000 output Token |
| 结果隔离 | 通过 | `results/v2-preflight` 目标尚不存在；历史 v1 Preflight 位于独立目录 |
| Arm 传递 | 通过 | baseline 阈值为 `None`，projection 候选阈值为 `500` |

Case 内容由同一个干净 MiniCode commit 冻结，不依赖目录名猜测。当前审计记录的辅助指纹为：

- `task.txt` SHA-256：`a32fff5632121f2a59c3f6ec66db7b454c9d280ad5a303a6617237dad64b7f02`
- 初始 Workspace 树指纹：`ba981f2631c52d143ac44c338546e7b6f18ce2dfb46fc3a3268937f71671bf7b`

## 2. 输出流与 Trace 的正确边界

CLI 的 stdout 只保存模型最终回答，作为 `answer.txt`。stderr 同时包含：

1. Run ID；
2. 人工 Approval 提示；
3. 运行结束后从 `Trace <run_id>` 开始的规范 Trace。

因此不能把整个 stderr 直接命名为 `trace.txt`。实际运行应先完整保存为
`stderr.raw.txt`，同时通过 `tee` 显示到终端，让操作者看到精确 Tool 名称和参数后逐次批准。
真实 projection Run 还发现：审批提示本身不以换行结束，而终端回显的输入换行不会写进重定向
后的 stderr，所以 Trace header 可能紧接在 `Approve? [y/N]: ` 后面，不能只匹配行首。应确认
全文恰好有一个 `Trace run_` 子串，再从子串位置开始提取：

```bash
awk '
  found { print; next }
  {
    marker = index($0, "Trace run_")
    if (marker) { found = 1; print substr($0, marker) }
  }
  END { if (!found) exit 1 }
' stderr.raw.txt > trace.txt
```

提取前必须确认原始 stderr 中恰好有一个 `Trace run_`；提取后第一行必须以 `Trace run_`
开头。`stderr.raw.txt` 继续保留，不用过滤后的文件覆盖它。不能预先管道输入一串 `y`，因为
Approval 的意义是看到本次具体调用后再批准，而不是盲批未知副作用。

## 3. 审计发现的工程阻塞

v2 协议已经预注册以下 Preflight 条件：

- baseline/projection 恰好各一条；
- 两条都通过 Safe Task Success；
- projection 累计至少改变一个 ToolResult，这也证明至少有一个模型调用实际投影；
- 失败或取消回读为 0；
- Provider Usage 和完整 Artifact 存在；
- 合计 Token 不超过 Preflight 预算。

现有 `evaluation_summary` 面向正式 12-run 批次，会把只有两条的 Preflight 判为重复次数不足；
它也尚未读取 `preflight_plan`。如果现在运行，只能人工检查上述条件，容易漏判或事后改变
口径。

该阻塞随后已解除。离线模式读取 v2 协议和已有 `result.json`，逐项输出 Preflight
PASS/FAIL，并在门禁失败时返回非零退出码：

```bash
.venv/bin/python -m minicode.evaluation_summary \
  benchmarks/context_projection/results/v2-preflight \
  --context-preflight-protocol \
  benchmarks/context_projection/real_model_protocol_v2.json
```

它不会启动模型。缺少或损坏的必要字段和 Artifact 会直接拒绝；证据格式正确但数量不足、
没有真实投影、回读失败或超预算时，会保留逐项报告并把 Preflight gate 标记为 `FAIL`。

## 4. 进入真实 Preflight 的标准

本阶段只有同时满足以下条件才结束：

1. Preflight 验证器对缺 Arm、重复 Arm、协议或模型不一致、脏 commit、Usage 缺失、预算超限、
   Artifact 损坏、无实际投影和回读失败分别有拒绝测试；
2. 能对一对合成的合法结果输出 PASS；
3. Ruff、格式、mypy、全量 pytest 和 `git diff --check` 通过；
4. 最终 commit 干净，凭据与模型只检查存在和名称，不泄露密钥；
5. v2 结果目录仍不存在，避免把工具开发数据混入真实 Preflight。

上述标准已由合成结果测试和全项目门禁验证。下一阶段才是创建隔离目录、保存协议快照并执行
两次真实调用；任何一次结果都必须保留，不能用补跑覆盖失败事实。

## 5. 后续真实执行结果

真实 Preflight 随后在 MiniCode commit `86a3ddc` 上完成。baseline 因实现 off-by-one 且耗尽
工具预算而失败；projection 正确完成任务，但全部模型请求的 `changed_tool_result_count` 都是
0。总 Token 与 Artifact 等其他门禁通过，最终 Preflight gate 为 FAIL。

这证明 Case 没有稳定覆盖自适应投影路径。v2 已停止，不执行正式 12-run；下一阶段先离线设计
新的覆盖 Case，并为后续真实运行预注册新协议 ID。
