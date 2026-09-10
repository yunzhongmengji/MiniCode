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
minicode run "$(<"$case_root/task.txt")" --trace \
  > >(tee "$result_directory/answer.txt") \
  2> >(tee "$result_directory/trace.txt" >&2)
agent_exit_code=$?
```

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

运行第二例时只需把 `case_name` 改为 `multi_file_inventory_contract`。

运行第三例时改为 `readonly_pagination_diagnosis`；如果出现任何 Approval，回答 `n`。

不要把 `acceptance.py` 复制进工作区。它代表评测者掌握、模型不可见的检查。

`result.json` 不重复保存回答或 Trace 正文，而是记录文件名和 SHA-256。请将
`answer.txt`、`trace.txt` 和 `result.json` 作为同一个原始结果目录保留。记录器使用
排他创建模式；如果 `result.json` 已存在，会拒绝覆盖历史记录。
