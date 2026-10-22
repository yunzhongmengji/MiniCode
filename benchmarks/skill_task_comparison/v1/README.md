# Skill 任务级开关对照 v1（离线验证）

本实验复用 `benchmarks/coding_agent/cases/multi_file_inventory_contract`，不改它的任务、初始工作区、
`case.json` 或隐藏 `acceptance.py`。任务是修复跨文件公开字段契约；Skill 只提供检查跨文件契约的工作方法，
不提供具体字段替换答案。隐藏验收独立检查最终行为和修改范围，不能用“Skill 被选中”代替任务成功。

| Arm | 输入任务 | Skill 根目录 | 验收 |
|---|---|---|---|
| baseline | 原 `task.txt` | 不传 `--skills-root` | 原 `acceptance.py` |
| treatment | 同一份 `task.txt` | 本目录的 `skills/` | 同一份 `acceptance.py` |

每个 Arm 必须由 `evaluation_prepare` 从同一 Case 各生成一份**独立**临时工作区；Skill 根目录留在
评测工作区外。固定同一模型版本、模型参数、代码版本、Policy、审批规则、`max_turns=8` 和
`max_tool_calls=8`，并保留两边原始回答、Trace、补丁与验收记录。对照只改变 Skill 开关，不能让
baseline 看到 Skill 正文，也不能在看过结果后调整 Skill 或验收规则。

用 `readonly_pagination_diagnosis` 作无关任务检查：treatment 开启相同 Skill 根目录时，期望选中数为零；
这只是误选/成本检查，不与库存任务的成功率合并。

目前已完成夹具准备、ScriptedModel 的两组端到端验证、`evaluation_run --skills-root` 的命令接线，
以及 `evaluation_result --skill-arm` 的结果记录与 Trace 核对。当前两组编排由下面的集成测试完成。
现已有冻结预算的批次入口（见末节），付费执行仍需要对具体计划获得授权。一对 Preflight 只能证明端到端
链路可用，不能证明 Skill 普遍提高成功率。

从仓库根目录验证这份离线夹具：

```bash
.venv/bin/pytest tests/benchmarks/test_skill_task_comparison.py -q
```

## 评测命令的 Skill 目录参数

`evaluation_run` 从原 Case 读取任务和预算，追加显式提供的 `--skills-root`，再交给普通 `minicode run`
解析与执行。未传目录时参数列表保持原样。相对目录按运行命令时的当前目录解析，与普通 CLI 一致；
评测通常先进入隔离工作区，因此建议使用工作区外的绝对 Skill 目录。含空格的路径仍作为一个参数传递。

以下是准备好隔离工作区后，开启组的命令形式；它会使用配置的真实模型，本步只离线验证了接线：

```bash
"$project_root/.venv/bin/python" -m minicode.evaluation_run \
  --case-root "$project_root/benchmarks/coding_agent/cases/multi_file_inventory_contract" \
  --skills-root "$project_root/benchmarks/skill_task_comparison/v1/skills"
```

`project_root` 和当前工作区按 `benchmarks/coding_agent/README.md` 的准备步骤设置；关闭组省略
`--skills-root`，并使用另一份独立工作区。该命令只启动 Agent，生成 `result.json` 仍由原结果记录器完成。
`--arm` 仍专用于上下文压缩配置，不表示 Skill 的 baseline/treatment。

`--skills-root` 与冻结的 `--context-protocol` 同时出现会在进入普通 CLI 前返回参数错误（退出码 2）。
现有上下文协议没有登记 Skill 指令，不能在原协议下临时增加这项实验变量。

## 在结果中记录 Skill 开关

运行阶段的开关是 `evaluation_run --skills-root`：baseline 不传，treatment 传本实验的 Skill 目录。
结果阶段必须向 `evaluation_result` 显式声明对应组别，沿用 `benchmarks/coding_agent/README.md` 中的
其他记录参数，并在末尾分别追加：

```bash
--skill-arm baseline
# 或
--skill-arm treatment
```

`result.json` 的 `skill_experiment` 会明确写入 `arm`、`selected_skill_names` 和
`loaded_skill_names`。baseline 的两个列表为空；treatment 从 Trace 的选择/加载事件提取名称，
不是从目录名推断。开启但没有匹配 Skill 时，`arm` 仍是 `treatment`、列表为空；加载失败时，
选中名称仍保留，加载成功列表不含失败的名称，任务失败仍可留下记录。

记录器在写补丁或 JSON 之前核对 Trace：baseline 不能出现 Skill 事件；treatment 必须有一次选择
事件，加载名称要与选中名称一致。把开启组误标成 baseline、把关闭组误标成 treatment，或给含
Skill 事件的 Trace 不传 `--skill-arm`，都会拒绝记录。普通非 Skill 实验结果仍可不传此参数，
不会新增 `skill_experiment` 字段。`--skill-arm` 不能和上下文实验协议组合；它与运行阶段的
上下文 `--arm`、结果阶段的 `--context-arm` 不是同一个开关。

命令接线的离线验证：

```bash
.venv/bin/pytest tests/benchmarks/test_evaluation_run.py -q
```

新测试从评测命令一直走到 ScriptedModel 收到 ModelRequest，检查默认关闭、显式正文注入、Trace、预算
传递和客户端关闭；只让脚本返回一轮最终回复，因此这条接线测试不判断库存修复是否完成。

## 脚本模型验证的具体过程

`test_scripted_skill_arms_run_tools_and_record_verdicts` 分别组装 baseline 与 treatment，复用产品的
`build_coding_agent`、默认工具策略、真实文件工具、真实子进程执行器和原 `record_result`。
测试审批器只批准这份临时夹具里两个实现文件的编辑，以及固定测试文件的运行；两组审批规则完全相同。

| 模型轮次 | 脚本响应 | 实际工具的目的 |
|---|---|---|
| 1 | 三个 read_file 请求 | 读取生产者、消费者和公开测试契约 |
| 2 | 两个 edit_file 请求 | 同步两处字段使用 |
| 3 | 一个 git_diff 请求 | 检查修改范围及具体补丁 |
| 4 | 一个 run_tests 请求 | 在隔离工作区运行真实 pytest |
| 5 | 最终回复 | 结束循环，交给独立验收判断是否修好 |

完整修复每组使用 5 次脚本模型调用和 7 次工具执行。脚本模型不分析 Skill 或工具结果，它按队列返回预设
响应；测试直接检查它收到的 ModelRequest：baseline 只有原编码指令，treatment 每轮多一段完整 Skill
指令，两组 task 相同且 Skill 不进入 conversation。因此两组都成功只证明编排、注入和记录链路贯通。

测试同时运行一次故意漏改消费者的场景：两组都只修改生产者，run_tests 返回错误，最后仍收到脚本最终回复。
`record_result` 保留失败记录：隐藏验收失败、Trace 要求失败、总体 verdict 为 false，循环运行本身可以正常结束。
该场景用来确认加载 Skill 或完成循环不会被记录器误当作任务成功。

每个参数化测试的 pytest 临时目录中都有独立的 `baseline/` 与 `treatment/`，分别保存 `answer.txt`、
`trace.txt`、`workspace.patch`、`result.json`。模型标识固定为 `scripted-skill-task-v1`，每次运行使用独立
Run ID；测试还核对 Trace 的完整事件和结果记录里三个原始文件的 SHA-256。目录只用于隔离两组文件；
`result.json` 的 `skill_experiment.arm` 明确标记组别，选择和加载名称来自 Trace。测试还尝试把两组
错标和漏标，确认记录器在生成结果前拒绝。

ScriptedModel 不提供真实模型 Token usage。记录器对此输出的 Token 汇总 0 是已知部分的和；
`result.json.run.usage_complete=false`、`model_calls_missing_usage=5` 明确说明五轮均没有 usage，
不能当作测得零 Token 成本，也不能拿这两组比较真实模型效果或费用。

结果目录可以用 `python -m minicode.evaluation_summary RESULTS_ROOT --require-complete-usage`
检查 Token 数据；两组都明确完整时检查通过，有缺失或旧记录缺少完整性字段时返回退出码 1。
本脚本夹具的两组会失败，因为 ScriptedModel 没有 usage；这与库存修复是否成功无关。
该检查尚未接入自动 Skill 批次运行，当前应先读取检查结果，再决定后续运行。

## 真实模型 Preflight 前的预算与可比性核对（S6f 审计）

以下是 S6f 修改重试策略**之前**发现的风险；随后 S6g 已收紧评测入口，见本节末。此处仍是
**离线就绪审计，不是付费运行授权**。当前 Case 的 `case.json` 把每组
限制为最多 8 个 Agent 模型轮次、8 个工具调用；若只运行 baseline 和 treatment 各一次，计划上限是
2 个 Run、合计 16 个 Agent 模型轮次和 16 个工具调用；目前没有批次入口强制只运行两次。
QueryLoop 在开始下一轮前检查轮次，
并在执行工具前检查工具调用数。这个上限属于 Agent 层，不等于网络请求数、Token 数或金额上限。

S6f 审计时 DashScope 客户端默认配置 `max_retries=2`、单次请求 `timeout=60.0`。安装的 SDK 在一次
`model.complete()` 内最多执行初次尝试加两次重试；因此上述计划最坏可触发最多 48 次客户端请求
尝试（2 Run × 8 轮 × 3 次尝试）。Trace 的 `model_call_started` 只记录 Agent 层调用，
不会逐次记录 SDK 的隐藏重试。这个数字仍**不能换算为最高费用**：每次请求的输入长度不同，
MiniCode 未显式设置单次输出 Token 硬上限，失败/超时的服务端计费情况不能从本地 Trace 判定；并且没有跨两组
的运行时 Token/金额停止器。`result.json` 的 Token 是事后统计；新增的 `usage_complete`
与缺失次数能指出数据不完整，但不能补出实际耗用，也不能在调用前停止。当前不能说
“真实 Preflight 已有严格费用上限”。

两组可比性应逐项核对：同一份 Case/task/隐藏验收和独立复制的相同初始 Git 提交；相同模型名称、
Provider 地址、默认采样设置、`max_turns`/`max_tool_calls`、工具 Policy 与人工审批规则；不同 Run ID
和结果目录。唯一计划差别应为 treatment 显式传入冻结的 Skill 根目录，baseline 完全不传。
`result.json.skill_experiment` 与 Trace 可以核对开关和实际选择/加载；它们不能证明人工审批决定
相同，也不能消除服务端随机性或运行顺序影响。两次 Preflight 只验证链路和个案，不估计成功率。

S6g 已将 `evaluation_run` 创建的模型客户端固定为 `max_retries=0`，baseline 和 treatment
同样生效。现在每个 Agent 模型调用最多对应一次 SDK 请求尝试；普通 `minicode run` 仍默认
`max_retries=2`。因此在**确实只运行两组各一次**的前提下，计划上的客户端请求尝试上限从
48 降为 16。若请求失败，不在 SDK 内偷偷重试；Trace 仍记录 Agent 层的失败。这个设置也适用于
经 `evaluation_run` 启动的其他评测，旧批次不能不看代码版本就与新批次混算。

进入真实模型 Preflight 之前仍须完成：冻结 Case/Skill/代码版本与模型配置；明确两组总请求及
Token/金额停止策略，尤其处理缺失 usage；确定人工审批规则及遇到超限/失败是否停止；
由用户单独授权这次可能产生费用的运行。关闭 SDK 重试只解决请求尝试数的一个边界，
**不是费用硬上限**；S6g 没有发起网络调用。

## 冻结的两组 Preflight 入口（S6j/S6k）

上节保留的是旧预算审计结论。现在可使用 `skill_preflight`：先离线准备，再单独执行已经审核的计划。
不要把下面的执行命令当作普通测试，它会调用真实模型并可能计费。

```bash
DASHSCOPE_MODEL=qwen3.7-flash .venv/bin/python -m minicode.skill_preflight --prepare \
  --results-root /absolute/path/outside-repository/new-skill-pair

# 核对 plan.json；获得这份具体配置的付费授权后再执行：
DASHSCOPE_MODEL=qwen3.7-flash .venv/bin/python -m minicode.skill_preflight --execute \
  --results-root /absolute/path/outside-repository/new-skill-pair
```

协议为本目录 `preflight.json`，当前协议 ID 为 `skill-inventory-preflight-v2-qwen3.7-flash`，
模型为用户指定的 `qwen3.7-flash` 别名（不声称服务端底层版本永久冻结）。
模型更换后使用新协议、新结果目录；历史快照模型失败记录不改名。
SDK 重试 0、temperature=0、非思考模式。
每组最多 8 轮/8 次工具，输入累计停止阈值 30000、输出累计停止阈值 4096，
单次 `max_completion_tokens=1024`；累计阈值在响应后检查，当前轮可能越过，**不是金额硬上限**。
缺 usage 时该轮工具与下一轮请求都停止。普通交互 CLI 默认行为不变。

`--prepare` 保存原始代码/Case/Skill/协议快照和 SHA-256、Python/SDK 版本；`--execute` 前和两组
运行边界都核对，使用冻结 Case/Skill 的副本。工作树的未提交状态如实留在 result.json，源码精确版本
由快照补充。不能在两组之间改源码或 Skill。每组独立复制工作区、Run ID、结果目录。

审批只允许两个实现文件的编辑和固定测试目标；普通 Tool Policy 仍生效。第一组运行异常、预算停止、
usage 不完整或记录不可核对，便不启动第二组。任务正常结束但隐藏验收失败仍保留并对照，不能筛掉失败。
每目录通过 `execution.started` 防重复执行，不会自动恢复、重试或扩大样本。

结果包括 `plan.json`、`snapshot/`、各组 answer/stderr/trace/workspace.patch/result.json，以及
`batch.json`。`pair_complete` 只表示两组记录可比较，任务是否成功另看各组 verdict。
一对结果不能证明通用成功率提升。详细代码、链路、遇到的问题见
`docs/learning/skill-product-roadmap.md` 的 S6j/S6k/S6l/S6m。

2026-10-03 首次真实尝试：baseline 第一次请求被服务端免费额度限制拒绝
（`AllocationQuota.FreeTierOnly`），无成功响应和工具执行；批次停止，未启动 treatment。
当时没有重试/切换模型/更改账户计费设置，该旧批次未完成两组，不能据此声称 Skill 的效果改善。
失败证据位置及后续条件见学习文档 S6l。

2026-10-03 用户随后指定 qwen3.7-flash，新批次两组均通过独立隐藏验收，usage 完整性检查通过。
关闭 Skill：5 次模型调用、7 次工具执行，输入/输出 Token 为 8499/388。
开启 Skill：6 次模型调用、8 次工具执行，输入/输出为 11942/650，实际选中并加载
inventory-contract-review。两组修改相同；开启组额外检查了 Git diff，未观察到任务结果改善或
Token 节省。一对只证明链路可用，不能作为通用成功率证据。
完整证据位于 `/home/songshihao/projects/minicode-evaluation-results/skill-preflight-v2.EB5aeh/pair`，
变更原因、执行流程和后续收尾标准见学习文档 S6m。
