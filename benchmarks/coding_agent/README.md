# Coding Agent 小样本评测

这里保存真实模型 Coding Agent 的固定任务。每个 Case 将模型可见的
`workspace/` 与模型不可见的验收程序分开，避免模型读取隐藏断言。

第一阶段只验证任务闭环，不引入自动批量调用模型的框架。每次运行都复制一份
初始工作区，避免不同实验互相污染。

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

cp -R "$case_root/workspace/." "$evaluation_workspace"

git -C "$evaluation_workspace" init -q
git -C "$evaluation_workspace" add .
git -C "$evaluation_workspace" \
  -c user.name="MiniCode Evaluation" \
  -c user.email="evaluation@example.invalid" \
  commit -q -m "evaluation baseline"

cd "$evaluation_workspace"
minicode run "$(<"$case_root/task.txt")" --trace
```

模型运行结束后，执行工作区外的确定性验收：

```bash
"$project_root/.venv/bin/python" \
  "$case_root/acceptance.py" \
  "$evaluation_workspace"
```

成功时输出：

```text
PASS <case_name>
```

运行第二例时只需把 `case_name` 改为 `multi_file_inventory_contract`。

第三例需要额外保存回答和 Trace，具体命令见该 Case 下的 `RUN.md`。

不要把 `acceptance.py` 复制进工作区。它代表评测者掌握、模型不可见的检查。
