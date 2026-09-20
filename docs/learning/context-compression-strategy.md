# MiniCode 上下文压缩：当前判断与下一步

日期：2026-09-16。性质：设计建议；本次没有修改运行时代码或执行真实模型调用。

## 1. 我们到底要优化什么

目标是：在任务完成质量有保障的前提下，降低整次任务的上下文成本，并让信息丢失能够恢复、能够解释。
单次请求更短不等于整次任务更便宜。额外的模型轮次、工具调用、回读和摘要生成都要计入成本。
目前样本不足以确定最优参数；下面是基于现有证据最值得验证的方案。

“模型看过”只表示原文进入过某次请求，不表示下一次请求删除原文后模型仍然记得它。
关键细节必须仍在本次输入、摘要、可读取的外部记录或其他明确支持的状态中，才能继续使用。

## 2. 当前实现有哪些可靠基础

- `QueryLoop` 保持完整 `message_history`；projector 只改变发给模型的 `ModelRequest`。
- `plan_tool_result_retention` 保护尾部连续的一批 ToolResult，以及所有 `is_error=True` 的结果。
- 旧结果超过单条输出阈值后，才可能替换为包含 call_id 的短引用；原 ToolCall 不变。
- 只有实际生成引用时才加入 `read_tool_result` 的工具定义，并计算包含该定义的完整请求净节省。
- `RunToolResultSource` 从绑定当前 Run 的最新 Checkpoint 的 `message_history` 查找原文。
  当前回读并不直接调用 ArtifactStore；Artifact 是另一个存储/追踪接口。
- 当前 `minimum_net_savings_bytes=1`，没有总上下文压力触发条件。
- 默认 `max_inline_tool_result_bytes=None`，即构建 CodingAgent 时没有默认启用投影。

代码入口：

- [query_loop.py](../../src/minicode/core/query_loop.py)
- [context_retention.py](../../src/minicode/core/context_retention.py)
- [context_projection.py](../../src/minicode/core/context_projection.py)
- [context_retrieval.py](../../src/minicode/core/context_retrieval.py)
- [read_tool_result.py](../../src/minicode/tools/read_tool_result.py)
- [coding_agent.py](../../src/minicode/coding_agent.py)

## 3. v3 证明了什么

baseline 输入 17,489 tokens，任务成功；projection 输入 18,642 tokens，代码修复与测试通过，
但因达到 max_turns 而没有最终答案。projection 相对自己的完整轨迹节省 20,859 bytes，
却比另一条 baseline 轨迹多消耗 6.59% 输入 tokens。

这里的 11 次结果替换是跨请求累计值，不是 11 份不同的工具结果。
真实模型没有调用 read_tool_result；零失败回读不代表它成功使用过恢复能力。
每个实验组只有一条真实轨迹，不能证明压缩导致失败，更不能估计总体成功率。

确定的信息生命周期是：

```text
第 7 轮：模型重新读取注册表
第 8 轮：注册表全文在请求中；模型调用 git_diff
第 9 轮：git_diff 成为最新结果；注册表又被替换为引用
```

“最后一批保留”保证最新结果有机会被使用，但不能让证据跨过下一次工具操作继续可见。
改引用的措辞不能直接解决这个机械问题。

参考：[v3 报告](../../benchmarks/context_projection/results/v3-preflight/REPORT.md)、
[逐轮诊断](../../benchmarks/context_projection/results/v3-preflight/TRACE_DIAGNOSIS.md)。

## 4. 推荐的近期策略

### 4.1 根据需要启动压缩

建议将来增加总请求预算/历史工具结果占比的触发条件，避免短任务为了很小的局部收益承担信息损失。
触发后，优先处理较旧、较大、确实可以恢复的结果，达到目标预算即可停止。
不要机械压缩所有符合单条大小条件的结果。

具体阈值由任务数据和目标模型确定，本笔记不把某个字节数或上下文百分比说成业界标准。
当前 bytes 度量是可复现代理指标，不是 tokenizer 结果，也不是账单。
Provider usage、缓存命中时的实际费用和端到端轮次数需要独立测量。

### 4.2 最近证据保留完整，先验证两批候选

同一次模型响应请求的多个工具及其返回结果算一批。两批不等于两个工具，也不等于两条消息。
最近两批保留，使“读证据 → 检查 diff → 回答”中的证据不会立即消失。
两批是最小候选，不能保证证据在任意长任务中一直保留；三批同样不是普遍最优。

错误结果先沿用现有保护规则。更长任务若出现大量旧错误，后续应区分仍未解决和已解决错误，
但不能仅凭经过几轮就假定错误已经解决。

### 4.3 引用短而明确，不重复整份调用参数

原 ToolCall 已经保存工具名和参数。先利用这一信息，不急着增加复杂的 JSON 和自动摘要。
模型需要知道：这里不是空结果；原文只是从当前输入中移出；call_id 能取回当时的原文。

可验证的候选说明（尚未实现）：

```text
历史工具输出已省略。需要其中的精确内容时，调用 read_tool_result(call_id="...")。
这会返回当时的输出，不会重新执行原工具。
```

统一使用规则可以写在工具说明中，减少每个引用的重复开销。
若仍有理解失败，再评估增加 source_tool 或有界原文片段，不直接增加全部字段。
原文片段必须标明不完整，不能把截断文本当作完整事实摘要。

“没有调用回读工具”不是自动失败：模型可能已有所需事实，或者需要读取工作区最新状态。
读取历史结果用于了解当时输出；read_file 用于了解文件现在是什么样子。二者不应混为一谈。

### 4.4 恢复通道必须与压缩范围一致

read_file 默认允许读取 100,000 bytes 的文件，而 read_tool_result 默认拒绝超过 50,000 bytes
的历史输出。此前 projector 没有检查这个回读上限，所以不能把所有引用一概描述为“保证可恢复”。

现在两者共享 `DEFAULT_TOOL_RESULT_READ_LIMIT_BYTES` 契约。projector 只会引用不超过
50,000 bytes、因而能够被 read_tool_result 完整返回的旧结果；更大的结果继续以内联原文进入模型请求。
在支持分段回读以前，不可完整回读的结果不会进入引用候选。
如果保留它会导致请求超出预算，应明确报告容量不足；不能生成一个实际上无法兑现的恢复引用。
将来再考虑有边界的分段读取，不直接取消所有大小限制。

这属于恢复契约检查，应在下一次真实实验之前单独处理，不与保留窗口同时改动后一起归因。

### 4.5 任务摘要放到更长任务阶段

当旧结果引用仍不断积累、消息本身成为主要负担时，再考虑结构化任务摘要：
目标与约束、已完成动作、关键结论与证据 ID、未解决问题、下一步。
摘要不替代原始历史，也不保证细节无损；需要另外评估遗漏、过时信息和生成摘要的成本。
当前没有证据说明必须马上增加摘要模型、向量数据库、长期记忆或多 Agent。

## 5. 实施顺序与验收

下一小步只做最近一批/两批保留的离线对照，不同时修改提示、max_turns、Case 或默认启用状态。

1. 固定“读注册表 → git_diff → 准备回答”的输入与工具轨迹。
2. 断言两批候选在回答前仍包含注册表全文；一批对照按现有逻辑变为引用。
3. 断言原始历史和 Checkpoint 未被投影覆盖，多工具一批不会被拆坏。
4. 同时统计两种策略的完整请求 bytes，包括引用和回读工具定义；节省不成立时允许退回原请求。
5. 再加一个更老结果，检查两批候选仍能压缩合适历史，而不是意外永久保留一切。

这些断言验证信息通道，不验证模型理解。ScriptedModel 预写正确最终答案不能证明成功率提升。

恢复上限契约已经按独立小步完成。随后再处理回读提示和按预算触发策略。终止预算也独立处理，并对两个实验组
使用相同的约束；不能仅给 projection 增加轮次来掩盖成本。

新的真实模型实验应冻结新协议，保留 v3 失败记录。覆盖短任务、无需回读的大输出任务、
必须引用早期证据的任务，防止只针对 25 个客户端这一题调优。
比较质量、最终证据正确性、整次 input/output tokens、工具与回读次数及延迟。
两三次成功只是可行性信号，不足以宣称总体最优或统计上的质量无退化。

## 6. 外部资料能支持到哪里

Claude Code 官方说明接近上下文上限时先清理旧工具输出，再按需总结对话；这支持分阶段、
按压力管理上下文的方向，但没有给出我们项目的最佳参数。
[How Claude Code works](https://code.claude.com/docs/en/how-claude-code-works#when-context-fills-up)

Claude API 的工具结果清理默认保留最近 3 组调用/结果，并保留原工具调用参数；还有触发阈值、
最小清理量和工具豁免。这是 API 配置，不应据此断言 Claude Code 内部必定采用同样参数，
更不能把文档未提及某种回读方式当成产品不存在该能力的证明。
[Context editing](https://platform.claude.com/docs/en/build-with-claude/context-editing)

Anthropic 的工程文章建议控制上下文信息密度、清楚描述工具使用边界，并根据观察到的失败逐步改进。
这些原则支持小步验证，但不能替代 MiniCode 自己的评测。
[Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)

## 7. 面试时应该能解释的问题

- 为什么“看过一次”不等于后续可删除？
- 为什么完整历史与模型输入必须分开？
- 为什么净 bytes 节省为正，端到端 tokens 仍可能增加？
- 为什么回读历史原文和重新读文件不是同一个动作？
- 两批窗口改善了哪个具体场景，又没有解决什么？
- 如何证明回读实际可用，而不是只放一个恢复工具名？
- 哪些结论来自代码与确定性重放，哪些仍需要真实模型实验？

## 8. 2026-09-16：一批/两批离线候选结果

已经给 retention planner 增加 `protected_recent_batch_count`，默认仍是 1。projector 也能直接接收
实验性的保留批数；非默认参数暂时禁止进入带正式 Trace 的 QueryLoop，防止评测协议没有记录新变量。

固定请求包含三批结果：较早搜索、终局注册表证据、最新 `git_diff`。结果如下：

| 候选 | 被替换结果数 | 注册表在回答前是否全文可见 | 完整请求净省 |
|---|---:|---:|---:|
| 最近 1 批 | 2 | 否 | 5,645 bytes |
| 最近 2 批 | 1 | 是 | 3,353 bytes |

两批候选用 2,292 bytes 的额外上下文换取终局证据继续可见，同时仍然压缩更早搜索并保持正净节省。
这只证明固定信息路径符合预期。它没有运行真实模型，也没有证明任务成功率提升或“两批”是全局最优参数。

相关测试同时覆盖：默认一批行为、并行工具结果仍算同一批、原请求对象不被修改、两批下较早结果
仍会被压缩，以及包含条件式回读 Tool Spec 后的完整请求净节省。

恢复契约已经在下一节完成。接下来可以考虑把两批候选升级成可追踪的正式配置。

## 9. 2026-09-16：引用与回读容量契约

问题不是 read_file 和 read_tool_result 的数字必须完全相同，而是 projector 不能生成回读工具无法兑现的
引用。现在默认完整回读能力是 50,000 UTF-8 bytes，并由投影器和回读工具共享同一个常量：

- 历史结果不超过 50,000 bytes：满足其他保留与净节省条件时，可以替换成引用。
- 历史结果超过 50,000 bytes：继续内联原文，不暴露一个注定失败的恢复路径。
- 恰好 50,000 bytes 的边界既可以生成引用，也可以被回读工具完整返回。

这项设计优先保证恢复语义正确，没有声称已经解决超大结果的上下文压力。若超大结果导致请求超过模型
预算，正确的后续方向是实现有界分页或分段回读，并让引用携带明确的范围信息；不能悄悄截断后冒充完整原文，
也不能直接取消回读上限。

本步没有修改默认一批保留窗口、提示、终止轮次或 v3 实验记录，因此测试结果可以单独归因到恢复契约。

## 10. 2026-09-17：A2 可解释保留决策表

现有 retention planner 不再只返回两个缺少原因的 ID 列表。它现在为每个 ToolResult 记录一个当前主原因：

- `protected_recent`：属于最近受保护的结果批次。
- `protected_error`：错误结果继续完整保留。
- `protected_excluded_tool`：宿主明确排除该工具的结果。
- `protected_not_retrievable`：输出超过完整回读容量，不能生成无法兑现的引用。
- `eligible`：通过以上保护规则，可以进入后续预算选择，但尚未决定压缩。

判断顺序固定为最近、错误、排除工具、无法回读、候选。这里记录的是首先命中的原因，例如最新的错误结果
会显示 `protected_recent`；当它离开最近窗口后会重新计算为 `protected_error`，始终不会成为候选。
旧的 protected/eligible ID 列表现在由决策表推导，避免理由和列表分别存储后互相矛盾。

这一步没有实现“从候选里选多少项”，也没有根据总请求预算修改请求。下一步才组合 A1 的压力结果与 A2 的
候选理由，计算最旧优先的预算计划。

## 11. 2026-09-19：A3 最旧优先预算计划

`plan_context_editing()` 现在组合 A1 和 A2，但仍是纯规划函数：

1. 先测量完整请求；未超过预算时返回空选择，完全不承担恢复 Tool Spec 成本。
2. 超预算时按 conversation 顺序查看 `eligible`，因此天然最旧优先。
3. 引用本身不比原文短的候选直接跳过。
4. 对候选前缀构造临时假设请求，加入一次 `read_tool_result` Tool Spec，再使用同一套
   `profile_model_request()` 重新测量完整请求。
5. 达到预算立即停止；全部候选仍不足时，保留最好的正收益计划并明确报告剩余超额。

临时请求只是成本计算材料，不会返回给调用方、写回 canonical history 或发送给模型。计划只保存选择的
call ID 和预计请求 bytes，其余总节省、剩余超额、是否达标都由这两个数字与 A1 压力结果推导。

引用 JSON 的渲染函数已移到 `context_retrieval.py`，让旧投影器与新规划器使用完全相同的引用长度，避免
“规划时一种格式、执行时另一种格式”造成预算估算漂移。

## 12. 2026-09-19：B1 可校验的预算投影边界

`apply_context_editing_plan()` 将 A3 从“预计选择”推进到“构造模型视图”，但仍保持纯函数边界：

- 先重新测量输入请求；若与计划保存的 canonical bytes 不同，拒绝应用。它检查的是成本一致性，不是内容指纹。
- 只允许选择 retention 判定为 `eligible` 的 call ID，并要求每个 ID 在当前请求中确有 ToolResult。
- 仅在存在选择时加入一次 `read_tool_result` Tool Spec。
- 构造后再次测量；实际总 bytes 必须严格等于计划值，否则报错而不是发送不可信的请求。
- 原始 `ModelRequest`、完整 ToolResult 和 tool_specs 保持不变。

`BudgetedToolResultProjector` 目前只在隔离测试中组合 A3 与上述应用函数。它尚未拥有可复现实验所需的正式
Trace 配置，因此 `describe_context_projector()` 主动拒绝它进入 QueryLoop。这个拒绝发生在 QueryLoop
构造阶段、任何模型调用和工具执行之前。

目前计划与应用在同一次 `project()` 调用中连续发生，所以请求不会从外部被换掉。若以后允许计划跨进程保存、
排队或延迟执行，则必须增加稳定请求指纹；两个内容不同但总 bytes 相同的请求，不能仅靠当前 byte 校验区分。

## 13. 2026-09-19：B2 schema 3 配置契约

预算投影不能复用旧 schema 2，因为旧格式只有固定阈值，没有足够字段复现实行的预算决策。新的
`BudgetedContextProjectionConfiguration` 使用 schema 3，完整保存：

- `max_request_bytes`：整个模型请求的 byte 上限。
- `protected_recent_batch_count`：最近多少批 ToolResult 必须保留全文。
- `minimum_net_savings_bytes`：一次编辑至少需要获得多少净收益。
- `excluded_tool_names`：哪些工具结果永不进入压缩候选；写出前去重、排序。
- `max_retrievable_output_bytes`：只有能够被完整回读的结果才能变成引用。
- `retrieval_tool_loading`：当前固定为 `on_reference`，只有产生引用时才承担 Tool Spec 成本。

配置可以在对象与 JSON payload 之间严格往返。解析器拒绝缺字段、多字段、错误版本、错误策略和非法参数，
防止“能读出来但不知道实际用了什么”的宽松记录。`BudgetedToolResultProjector` 保存这份配置并用其中的同一组
值调用 planner。

本步完成时还没有把 schema 3 交给 `describe_context_projector()`；该边界已在下一节接通。

## 14. 2026-09-19：B3 QueryLoop Trace 接入

`describe_context_projector()` 现在可以返回预算 projector 持有的 schema 3 配置。QueryLoop 原有事件路径本来
就会合并“投影器静态配置”和“本轮投影测量”，因此无需增加第二套事件：

```text
schema 3 配置 ─┐
               ├─> MODEL_CALL_STARTED.context_projection
本轮前后 bytes ─┘
```

确定性测试覆盖了真正发生压缩的一轮：ScriptedModel 收到旧 ToolResult 的引用，事件记录一项变化以及正的总
byte 节省，而 `RunResult.message_history` 仍保留原始完整结果。默认 Identity 和旧 schema 2 事件保持不变。

这还不是产品入口。直接向 QueryLoop 注入 projector 时，宿主必须自己保证 `read_tool_result` 在 ToolRuntime 中
真实存在。CLI 和 `build_coding_agent()` 尚未暴露预算配置，正式评测也仍只接受已归档的旧协议。下一步应先复用
现有 CodingAgent 的 EventLedger、Checkpoint 和历史结果工具组装链，避免模型看得到 Tool Spec 却无法调用。

## 15. 2026-09-19：B4 CodingAgent 恢复链组装

`build_coding_agent()` 现在接受完整的 schema 3 预算配置，并与旧阈值参数互斥。两种模式复用同一条恢复链：

```text
EventLedger.run_id
        ↓
RunToolResultSource ──> CheckpointStore 中的完整历史
        ↓
ReadToolResultTool ──> Dispatcher 预注册
        ↑
Projector 只在产生引用时向模型暴露 Tool Spec
```

预算配置的 `max_retrievable_output_bytes` 同时传给回读工具和 projector。这保证了候选分类所承诺的完整回读
容量与工具真正执行时的上限相同。没有 EventLedger 或 CheckpointStore 时拒绝构建；同时传旧阈值和预算配置时
也拒绝，避免两个策略争夺同一轮模型视图。

确定性四轮测试让模型先读旧文件、再读新文件、随后看到旧结果引用并主动调用 `read_tool_result`。测试确认
Dispatcher 成功返回原文、最终 Checkpoint 保存完整历史、Trace 记录 schema 3，同时前两轮没有无条件承担
回读 Tool Spec 成本。该测试与旧阈值策略共用，证明新增入口没有破坏 schema 2 链路。

CLI 和正式评测协议仍未启用预算策略，也没有调用真实模型。

## 16. 2026-09-19：B5 schema 3 离线评测校验

旧 `summarize_context_experiment()` 与已经归档的 v3 协议绑定 schema 2。为了不让历史结果被新规则重新解释，
预算策略使用独立的 `summarize_budgeted_context_experiment()`：调用者必须传入预先登记的
`BudgetedContextProjectionConfiguration`，验证器再从每个 `MODEL_CALL_STARTED` 提取 schema 3 字段。

验证顺序是：

1. 当前轮配置能否按 schema 3 严格解析。
2. 当前轮是否与上一轮完全相同，防止运行中途改预算或保留规则。
3. 当前轮是否等于协议预先登记的配置，防止实际运行与实验声明不一致。
4. 公共 Trace 统计是否满足 `context_profile.total_bytes == total_bytes_after` 和
   `total_bytes_before - total_bytes_after == total_bytes_saved`。

通过后才汇总模型调用数、模型可见与 canonical bytes、净节省、变化结果数和回读成败。测试还把同一份
schema 3 Trace 交给旧入口，确认旧入口继续拒绝，因而 v3/schema 2 证据语义没有被放宽。

本步尚未修改 `record_result` 命令、协议 JSON、CLI 或真实模型流程。

## 17. 2026-09-19：B6 预算实验预注册协议

新增的 `context_experiment_protocol.py` 不压缩上下文，也不启动 Agent；它只把实验前必须固定的决策解析成
不可变对象。v4 JSON 的 baseline 保存完整 schema 2 Identity payload，projection 保存完整 schema 3 payload，
所以两组不是靠一个含糊的 `enabled=true/false` 区分，而是能逐字段复现实际策略。

加载器还检查三组容易发生“看完结果再改规则”的关系：Preflight 的 `runs` 必须同时等于 Arm 顺序长度和预算
最大运行数；正式最大运行数必须等于 `Case 数 × 每 Case 每 Arm 重复数 × 2 个 Arm`；每 Arm 要求的 Safe
Success 必须等于 `Case 数 × 重复数`。任一处漂移都会在模型调用前失败。

`max_request_bytes=10,000` 的依据是 v3 已归档 Trace 的现有范围：启动约 4.9KB，后段约 11～14KB。它让短的
前几轮保持 Identity，让长的后几轮有机会触发预算策略。这个数字只是 v4 Case 的待验证参数，不代表模型 Token
窗口或生产配置。旧 `_load_context_protocol()` 没有扩展 schema 3，避免历史 v1～v3 被新规则重新解释。

本步没有把协议接入 CLI、评测运行器、结果记录器或汇总器，也没有调用真实模型。

## 18. 2026-09-19：B7 协议驱动的运行与记录

旧实验由 `--arm projection` 映射到固定阈值 500，结果阶段再手填协议 ID。这种方式对 v4 不够安全，因为 JSON
里的预算、保护批数、排除工具和回读上限可能与真正运行参数分成两份。新的协议文件路径同时进入
`evaluation_run` 和 `evaluation_result`，schema 3 配置对象只解析一次后沿调用链传递。

运行阶段的链路是：协议 JSON → 不可变协议对象 → 选定 Arm → `cli.main()` → `_execute_coding_task()` →
`build_coding_agent()`。baseline 的预算配置为 `None`，继续得到 Identity；projection 得到协议中的完整
`BudgetedContextProjectionConfiguration`。环境模型不匹配时在 Provider 客户端创建前失败，因此不会产生一条
模型、协议不一致但已经计费的实验。

记录阶段重新加载同一协议，先核对 Case 和模型，再按 Arm 调用旧 schema 2 Identity 校验或 schema 3 预算校验。
最终 `context_experiment` 保存协议 ID、Arm、实际 Trace 配置和统计。旧 v1～v3 参数没有改成新语义。

本步仍不运行真实模型，也未实现 v4 的 Preflight 批次门禁。

## 19. 2026-09-19：B8 schema 3 Preflight 门禁

批次汇总器原先只能把 `context_experiment` 解码成 schema 2 阈值配置。现在结果加载层先看 Trace 配置版本：
baseline 仍按 schema 2 Identity 读取；schema 3 只允许 projection，并要求结果顶层 `max_request_bytes` 与完整
配置对象一致。这样 B7 落盘的字段可以被独立进程重新校验，而不是只在写入时检查一次。

Preflight 的统计与旧 v3 共用同一条门禁：Arm 数量、Safe Task Success、projection activity、回读失败、Token
预算、Provider Usage、工件哈希、单一 commit 和协议快照。不同之处只在配置验证，旧协议加载器没有被放宽。
协议快照必须与登记 JSON 的 bytes 完全相同，看完结果后即使只改一个预算数字也会使门禁失败。

一个重要限制是：结果只记录 Arm 和 Run ID，没有由可信编排器产生的顺序编号。汇总器能证明 baseline/projection
各一条，不能证明谁先运行。目录名称不属于可信证据，因此报告不会宣称已经验证 `arm_order`。下一步应先补编排
边界，再考虑真实模型调用。

## 20. 2026-09-19：B9 Preflight 顺序编排边界

`evaluation_preflight.py` 只负责“按什么顺序运行以及何时停止”，不负责模型、工作区和结果评分的具体命令。
真实执行细节被隔在 `PreflightRunExecutor` 接口后，因此测试可以使用不花 Token 的假执行器验证状态机。

一次编排产生三类不同证据：

- `protocol.snapshot.json`：本次运行真正采用的协议原文，必须与登记文件逐 byte 相同。
- `preflight-plan.json`：开跑前冻结的计划，包含快照哈希、Case、序号、Arm 和目标目录。
- `preflight-events.jsonl`：实际发生的开始/结束事件；JSON Lines 允许每完成一步立即追加和落盘。

编排器先调用 baseline。只有执行器返回成功且该槽位真实存在 `result.json`，才开始 projection。这样“函数返回
True 但忘了记录结果”不能伪装成成功，第一组失败也不会用补跑第二组来掩盖。执行器抛异常时会先写
`run_failed` 和异常类型，然后继续抛出，让自动化任务明确失败。

这里仍有一条证据边界：B9 证明统一编排器能够强制顺序，但尚无真实命令适配器，因此还没有证明 Provider 调用、
Trace 提取和结果记录能完整走通。B10 应只补这层适配，不修改已冻结的实验策略，也不能在适配失败时调用真实模型。

## 21. 2026-09-20：B10 真实命令执行适配器

`ContextPreflightCommandExecutor` 实现了 B9 的小接口，但没有重写现有评测逻辑。一次 Arm 的调用链是：

```text
检查结果目录在仓库外 + 检查 MiniCode Git 干净
  ↓
prepare_evaluation_workspace（复制 Case 工作区并提交初始基线）
  ↓
python -m minicode.evaluation_run（真实 Agent 边界）
  ↓
保存 answer.txt + stderr.raw.txt，并从唯一标记提取 trace.txt
  ↓
python -m minicode.evaluation_result（隐藏验收、Trace 校验、补丁和 result.json）
  ↓
把记录器退出码返回 B9；失败则不开始后续 Arm
```

子进程层继承 stdin，并逐字符把 stderr 转发到当前终端。这一点不是输出美化：`edit_file` 和 `run_tests` 需要人工
Approval，而提示末尾没有换行。如果只用 `capture_output=True`，进程可能在等待输入，但操作者看不到问题。
stdout 则完整保存为 Agent 的 `answer.txt`。

结果目录必须位于 MiniCode 仓库外。否则 B9 刚创建的协议快照和事件文件就会成为未跟踪文件，随后
`evaluation_result` 会正确记录 `minicode_dirty=true`，导致协议要求的干净实现版本无法通过。实验完成并通过门禁
后，才能把不可变结果复制进归档目录。

B10 的假命令执行器没有伪造编排顺序，而是接收并检查未来真实运行会使用的命令参数，再模拟产出 `result.json`。
因此它证明“组装链路正确”，不证明模型任务成功。最终汇总目前尚未读取 B9 的计划和事件证据，这是 B11 必须补齐
的最后一个运行前缺口。

## 22. 2026-09-20：B11 编排证据门禁与批次入口

v4 汇总不再只用 `rglob()` 数出一条 baseline 和一条 projection。它现在建立三组必须一致的事实：

```text
协议 arm_order
      = preflight-plan.json 的序号、Arm 和目录
      = preflight-events.jsonl 的实际开始/完成顺序
      = 对应目录内 result.json 声明的 Arm
```

冻结计划属于实验声明，因此字段、哈希或顺序与协议不一致时直接抛错，不能生成一份貌似可比较的报告。事件流属于
运行结果：格式合法但少了完成事件、包含失败或顺序不完整时，报告 `Orchestration evidence: fail`。结果文件即使
两组数量正确，只要交换目录，也不能通过这一门禁。

这个要求只施加于 schema 3/v4。历史 v1～v3 是在编排事件出现之前完成的实验，继续验证原有 Arm 数量、任务、
Token、回读和工件，不伪造不存在的顺序证据。

新的批次入口是：

```bash
.venv/bin/python -m minicode.evaluation_preflight \
  --protocol benchmarks/context_projection/real_model_protocol_v4.json \
  --results-root /tmp/minicode-context-v4-preflight
```

结果目录必须事先不存在并位于仓库外。命令会依次调用编排器与命令适配器，并在两个单次结果都成功后自动执行最终
门禁。退出码 `0` 表示门禁通过，`1` 表示运行或实验指标未通过，`2` 表示配置、文件或证据结构错误。

代码链路完成不等于已经完成真实实验。当前修改还未形成干净 commit，Provider 环境也未在本步检查，因此命令尚未
执行。下一步应只做只读就绪审计，不能继续边实现边花费实验 Token。
