# 运行只读诊断 Case

在 MiniCode 仓库根目录执行：

```bash
project_root=$PWD
case_name=readonly_pagination_diagnosis
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
```

如果模型提出任何 Approval，回答 `n`。运行结束后执行：

```bash
"$project_root/.venv/bin/python" \
  "$case_root/acceptance.py" \
  "$evaluation_workspace" \
  "$result_directory/answer.txt" \
  "$result_directory/trace.txt"
```
