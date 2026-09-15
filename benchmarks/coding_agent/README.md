# Coding Agent 小样本评测

这里保存真实模型 Coding Agent 的固定任务。每个 Case 将模型可见的
`workspace/` 与模型不可见的验收程序分开，避免模型读取隐藏断言。

第一阶段不自动批量调用模型。人负责启动真实模型和处理 Approval，结果记录器负责
确定性验收、统计 Trace 并生成 JSON。每次运行都复制一份初始工作区，避免实验互相污染。

## 当前 Cases

| Case | 能力 | 允许修改 |
|---|---|---|
| `single_file_batching` | 单文件逻辑修复 | `batching.py` |
| `multi_file_inventory_contract` | 跨文件数据契约一致性 | `inventory.py`、`report.py` |
| `readonly_pagination_diagnosis` | 只读诊断和仓库内提示注入 | 不允许修改 |
| `search_driven_retry_schedule` | 文件发现、调用关系搜索和共享根因修复 | `retrying/backoff.py` |
| `large_search_context_repair` | 大搜索结果下的共享配置修复 | `service_config/timeouts.py` |
| `large_search_context_recall` | 修复后报告早期搜索证据 | `service_config/timeouts.py` |

## 运行一个 Case

在 MiniCode 仓库根目录执行：

```bash
project_root=$PWD
case_name=single_file_batching
case_root="$project_root/benchmarks/coding_agent/cases/$case_name"
evaluation_workspace=$(
  "$project_root/.venv/bin/python" -m minicode.evaluation_prepare \
    --case-root "$case_root"
)
result_directory=$(mktemp -d "/tmp/minicode-result-$case_name.XXXXXX")

cd "$evaluation_workspace"
"$project_root/.venv/bin/python" -m minicode.evaluation_run \
  --case-root "$case_root" \
  > >(tee "$result_directory/answer.txt") \
  2> >(tee "$result_directory/trace.txt" >&2)
agent_exit_code=$?
```

上下文投影实验可以在这个 Benchmark 专用入口显式选择 Arm：

```bash
"$project_root/.venv/bin/python" -m minicode.evaluation_run \
  --case-root "$case_root" \
  --arm projection
```

省略 `--arm` 等于 `baseline`。该参数没有加入普通 `minicode run`，projection 当前只用于
预注册实验；在结果记录器能够保存 Arm、阈值和上下文统计之前，不应进行正式付费运行。

`evaluation_prepare` 创建一个新的临时目录，只复制 Case 的 `workspace/`，然后初始化
Git 并提交 `evaluation baseline`。它不会复制 `case.json`、`task.txt` 或隐藏的
`acceptance.py`，输出的唯一一行是临时工作区路径，供 Shell 保存到
`evaluation_workspace`。

`evaluation_run` 从 `task.txt` 读取模型任务，从 `case.json` 读取 `max_turns` 和
`max_tool_calls`，再调用现有的 `minicode run`。它始终以执行命令时的当前目录作为
Agent Workspace，因此上面的 `cd "$evaluation_workspace"` 不能省略。该入口只负责
启动 Agent 和打印 Trace，不复制工作区、不运行隐藏验收，也不生成 `result.json`。

模型运行结束后，返回 MiniCode 仓库并生成结果记录：

```bash
cd "$project_root"
model_name="${DASHSCOPE_MODEL:-qwen3.7-flash-2026-07-15}"

"$project_root/.venv/bin/python" -m minicode.evaluation_result \
  --case-root "$case_root" \
  --workspace "$evaluation_workspace" \
  --answer "$result_directory/answer.txt" \
  --trace "$result_directory/trace.txt" \
  --output "$result_directory/result.json" \
  --model "$model_name" \
  --agent-exit-code "$agent_exit_code"
```

记录 Context Projection 实验时，必须把与运行阶段相同的 Arm 和预注册协议 ID 一起交给
记录器：

```bash
--context-protocol-id context-projection-adaptive-real-model-pilot-v2 \
--context-arm projection
```

记录器不会直接相信这两个参数。它会读取 Trace 中每轮的 Projector strategy 和阈值；声明
为 projection 但 Trace 实际为 identity（反之亦然）时拒绝生成结果。普通非实验结果可省略
这两个参数，但二者不能只提供一个。

成功时输出：

```text
PASS <case_name>: /tmp/.../result.json
```

运行其他案例时只需把 `case_name` 改为上表中的名称。运行
`readonly_pagination_diagnosis` 时如果出现任何 Approval，应回答 `n`。

不要把 `acceptance.py` 复制进工作区。它代表评测者掌握、模型不可见的检查。

`result.json` 不重复保存回答、Trace 或代码补丁正文，而是记录文件名和 SHA-256。
结果记录器会在隐藏验收之前把 Agent 对已跟踪文件的修改保存为 `workspace.patch`。
请将 `answer.txt`、`trace.txt`、`workspace.patch` 和 `result.json` 作为同一个原始
结果目录保留。记录器使用排他创建模式；如果 `result.json` 或 `workspace.patch` 已
存在，会拒绝覆盖历史记录。

## 保存和汇总结果

经过验收的原始结果按批次保存在 `results/`。新记录的每个 Case 必须一起保留
`answer.txt`、`trace.txt`、`workspace.patch` 和 `result.json`；JSON 中的 SHA-256
用于确认前三个文件仍是记录时的原始内容。历史批次不会被追溯补写补丁。

汇总器递归读取一个批次中的 `result.json`，只聚合已记录事实，不会再次调用模型或
修改验收结论：

```bash
.venv/bin/python -m minicode.evaluation_summary \
  benchmarks/coding_agent/results/baseline-9b9fcb6-qwen3.7-flash-2026-07-15
```

当前基线每个 Case 只有一次正式运行，因此汇总中的 `3/3` 只能描述这个小样本批次，
不能表述为 MiniCode 的一般任务成功率。

预注册的 Context Projection A/B 实验使用严格的正式结果目录：

```bash
.venv/bin/python -m minicode.evaluation_summary \
  benchmarks/context_projection/results/formal \
  --context-protocol benchmarks/context_projection/real_model_protocol_v2.json
```

不要把 `preflight/` 放到 `formal/` 下面。该汇总会检查每个 Case/Arm 的重复次数、不同 Run ID、
Safe Task Success、input Token 对比、逐 Case 退化和回读失败；协议、模型、阈值或 commit 混杂
会直接拒绝，而不是生成一个看似可比较的平均数。
