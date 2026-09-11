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

## 运行一个 Case

在 MiniCode 仓库根目录执行：

```bash
project_root=$PWD
case_name=single_file_batching
case_root="$project_root/benchmarks/coding_agent/cases/$case_name"
evaluation_workspace=$(mktemp -d "/tmp/minicode-eval-$case_name.XXXXXX")
result_directory=$(mktemp -d "/tmp/minicode-result-$case_name.XXXXXX")

cp -R "$case_root/workspace/." "$evaluation_workspace"

git -C "$evaluation_workspace" init -q
git -C "$evaluation_workspace" add .
git -C "$evaluation_workspace" \
  -c user.name="MiniCode Evaluation" \
  -c user.email="evaluation@example.invalid" \
  commit -q -m "evaluation baseline"

cd "$evaluation_workspace"
"$project_root/.venv/bin/python" -m minicode.evaluation_run \
  --case-root "$case_root" \
  > >(tee "$result_directory/answer.txt") \
  2> >(tee "$result_directory/trace.txt" >&2)
agent_exit_code=$?
```

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

成功时输出：

```text
PASS <case_name>: /tmp/.../result.json
```

运行其他案例时只需把 `case_name` 改为上表中的名称。运行
`readonly_pagination_diagnosis` 时如果出现任何 Approval，应回答 `n`。

不要把 `acceptance.py` 复制进工作区。它代表评测者掌握、模型不可见的检查。

`result.json` 不重复保存回答或 Trace 正文，而是记录文件名和 SHA-256。请将
`answer.txt`、`trace.txt` 和 `result.json` 作为同一个原始结果目录保留。记录器使用
排他创建模式；如果 `result.json` 已存在，会拒绝覆盖历史记录。

## 保存和汇总结果

经过验收的原始结果按批次保存在 `results/`。每个 Case 的 `answer.txt`、
`trace.txt` 和 `result.json` 必须一起保留；JSON 中的 SHA-256 用于确认前两个文件
仍是记录时的原始内容。

汇总器递归读取一个批次中的 `result.json`，只聚合已记录事实，不会再次调用模型或
修改验收结论：

```bash
.venv/bin/python -m minicode.evaluation_summary \
  benchmarks/coding_agent/results/baseline-9b9fcb6-qwen3.7-flash-2026-07-15
```

当前基线每个 Case 只有一次正式运行，因此汇总中的 `3/3` 只能描述这个小样本批次，
不能表述为 MiniCode 的一般任务成功率。
