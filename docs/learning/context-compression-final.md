# MiniCode 上下文压缩模块封板总结

核对日期：2026-09-22。

本文是上下文压缩模块的最终学习入口。它重新组织当前代码、离线实验、真实模型 Preflight 和评测语义，目标是让我
不翻阅 B1～B29 的开发日志，也能说明这个模块做了什么、为什么这样设计、证明了什么，以及哪些结论还不能说。

## 1. 一句话介绍

MiniCode 没有直接删除 Agent 的对话历史，而是在每次模型调用前，从完整历史构造一个临时的、受预算约束的模型视图：
较旧且能够完整恢复的工具结果可以替换为带 `call_id` 的短引用；模型确实需要原文时，再通过只读工具从当前 Run 的
Checkpoint 取回。这让执行状态、模型输入和实验记录彼此分离。

项目要解决的不是“怎样尽量删文字”，而是下面这个工程问题：

> 怎样减少大段历史工具输出被重复发送，同时保留恢复通道、可解释决策、任务正确性和可复现实验证据？

## 2. 当前结论先说清楚

已经做到：

- 完整 `message_history` 不被压缩器修改，Checkpoint 仍保存原始 ToolResult。
- 只有请求超过配置的 byte 预算时，预算投影器才尝试压缩。
- 最新结果、错误结果、被排除工具的结果和无法完整回读的结果受到保护。
- 压缩引用明确告诉模型原文被移出、原始 byte 数、`call_id` 和回读工具名。
- `read_tool_result` 只读取当前 Run 已保存的原结果，不重新执行原工具。
- 只有产生引用时才向模型提供回读工具定义，并把这份 Tool Spec 的成本计入净收益。
- 每轮投影配置、请求组成、压缩数量和 byte 变化都会进入事件账本和实验结果。
- v4 真实模型 Preflight 中，baseline 与 projection 都安全完成任务；projection 实际发生压缩并成功回读一次。

尚未证明：

- v4 的 12-run 曾执行并现场汇总，但原始目录位于 `/tmp`，随后被环境清理，没有形成可重新核验的持久归档；因此
  不能把它当作当前完整、可复现的正式实验闭环。
- v4 单对 Preflight 中 projection 的整次 input Token 反而比 baseline 高 33.86%，原因是多了两个模型调用。
- byte 是稳定的 Provider-neutral 代理指标，不等于特定模型 tokenizer 的 Token，也不等于账单价格。
- 最近两批、10,000-byte 预算和 50,000-byte 回读上限都是当前协议参数，不是行业最优值。
- 当前策略只处理 ToolResult，没有压缩用户消息、普通助手消息、工具调用参数或 Skill 指令。

因此，简历上的准确说法应是“实现并验证可回读的预算式上下文投影与评测闭环”，不能写“上下文成本降低 33%”或
“实现无损压缩”。

## 3. 三份状态必须分开理解

| 对象 | 谁维护 | 包含什么 | 是否被投影器修改 |
|---|---|---|---|
| `message_history` | `QueryLoop` | 当前 Run 的 Message、ToolCall、完整 ToolResult | 否 |
| `ModelRequest` | 每轮临时构造 | 本轮给模型的 conversation、Tool Spec、instructions | 可以产生临时投影视图 |
| Checkpoint / Result / Event | Agent 外围设施 | 恢复状态、最终验收、过程证据 | 不从压缩文本反推 |

最容易误解的地方是：模型看到的旧结果可以是引用，但程序中的完整历史仍然存在。下一轮并不是把上轮压缩后的
request 当作历史继续追加，而是再次从完整 `message_history` 构造 canonical request，再重新计算本轮投影。

这也回答了“完整 ToolResult 从哪里来”：它在工具真实执行后就写入程序维护的历史和 Checkpoint，不是模型根据已经
压缩的 request 重新生成的。

## 4. 一轮模型调用的完整链路

```text
完整 message_history
        │
        ▼
QueryLoop 构造 canonical ModelRequest
        │
        ▼
BudgetedToolResultProjector.project()
        │
        ├─ 1. 测量完整请求 bytes
        ├─ 2. 判断是否超过 max_request_bytes
        ├─ 3. 给每个 ToolResult 标记保留原因
        ├─ 4. 从最旧的 eligible 结果开始尝试替换
        ├─ 5. 加入一次 read_tool_result Tool Spec 后重新计费
        └─ 6. 校验计划值与实际投影值一致
        │
        ▼
记录 MODEL_CALL_STARTED 及画像/投影证据
        │
        ▼
模型收到 projected ModelRequest
        │
        ├─ 直接继续任务
        └─ 或调用 read_tool_result(call_id)
                │
                ▼
          从当前 Run 最新 Checkpoint 返回原始 ToolResult
```

对应代码：

- [QueryLoop 调用边界](../../src/minicode/core/query_loop.py)
- [预算投影器](../../src/minicode/core/context_projection.py)
- [压力判断与编辑计划](../../src/minicode/core/context_editing.py)
- [保留分类](../../src/minicode/core/context_retention.py)
- [画像计量](../../src/minicode/core/context_profile.py)
- [原文查找](../../src/minicode/core/context_retrieval.py)
- [回读工具](../../src/minicode/tools/read_tool_result.py)

## 5. 到底什么时候会压缩

每一轮都会重新判断，但满足下面全部条件才会把某个 ToolResult 换成引用：

1. 完整请求总大小严格超过 `max_request_bytes`；没有压力时返回原请求。
2. 该结果不属于最近受保护的若干批 ToolResult。
3. 该结果不是错误结果。
4. 该结果的工具名不在 `excluded_tool_names`。
5. 结果不超过回读工具能够完整返回的 `max_retrievable_output_bytes`。
6. 引用确实比原结果小。
7. 替换后，扣除新增回读 Tool Spec，完整请求仍至少获得 `minimum_net_savings_bytes` 的净收益。

“模型已经看过”不是压缩条件。系统不知道模型是否真正理解或记住一段内容。它只能根据可验证的结构事实判断：结果
是否足够旧、是否受保护、是否可恢复、是否存在净 byte 收益。

### 什么是一批 ToolResult

同一次模型响应可能并行请求多个工具，这些相邻返回结果属于同一批。保护最近两批，不等于只保护两个结果。

例如：

```text
第 1 批：search_text
第 2 批：read_file(A)、read_file(B)
第 3 批：git_diff
```

保护最近两批时，第 2、3 批完整保留；第 1 批才可能成为压缩候选。

## 6. 保留分类为什么这样设计

每个 ToolResult 只记录首先命中的一个原因：

| 原因 | 含义 | 为什么保护 |
|---|---|---|
| `protected_recent` | 属于最近结果批次 | 模型很可能还在直接使用 |
| `protected_error` | 工具执行错误 | 错误细节可能决定恢复动作 |
| `protected_excluded_tool` | 宿主明确排除 | v4 中 `git_diff`、`run_tests` 属于终局证据 |
| `protected_not_retrievable` | 超过完整回读上限 | 不能生成无法兑现的引用 |
| `eligible` | 通过以上检查 | 只是候选，尚未表示一定压缩 |

分类与选择分成两步很重要。Retention 只回答“能不能考虑”；Editing Plan 才回答“在本轮预算下应选哪些”。这样测试
失败时可以区分：是分类错了，还是选择/成本计算错了。

## 7. 预算计划怎样工作

`ContextPressureDecision` 保存完整请求大小与预算，并推导超出多少 byte。超预算以后，规划器按 conversation 顺序扫描
eligible 结果，也就是最旧优先：

1. 先把第一个候选改成引用；
2. 构造临时请求，必要时加入一次回读 Tool Spec；
3. 用与正式 Trace 相同的规范化 JSON 口径重新测量；
4. 若净收益达到阈值，就保存这份候选计划；
5. 若仍超预算，继续加入下一个候选；达到预算就停止；
6. 候选耗尽仍超预算时，返回能做到的最好计划，并明确保留 `remaining_overflow_bytes`。

预算是“触发并尽力压缩目标”，不是不惜代价截断信息的硬上限。受保护信息多时，投影后仍可能超预算。v4 Preflight
最后一轮就是完整请求 15,856 bytes、投影后 11,876 bytes，仍高于 10,000 bytes；系统选择保留安全与恢复语义，
没有悄悄删除关键数据。

## 8. 引用与回读的语义

引用是短 JSON，包含：

```json
{
  "call_id": "...",
  "kind": "historical_tool_result_reference",
  "original_output_bytes": 2730,
  "retrieval_tool": "read_tool_result"
}
```

它说明“这里原本有历史输出”，而不是空结果或摘要。原 ToolCall 仍留在对话中，所以模型还能看到当时调用了哪个工具及
其参数。

`read_tool_result` 的边界：

- 只能按 `call_id` 读取绑定 Run 的最新 Checkpoint；
- Checkpoint 的 `run_id` 不一致会拒绝；
- 返回当时的原始输出，不重新执行搜索、读文件或测试；
- 不超过配置的 byte 上限；
- 查不到调用、调用尚无结果、Run 不存在都会明确失败。

回读历史结果和重新调用 `read_file` 不等价。前者回答“当时工具返回了什么”，后者回答“文件现在是什么”。文件已被
修改时，两者可能给出不同但都正确的信息。

回读返回的全文会成为一个新的 ToolResult，因而进入最近批次保护；被引用的旧结果仍留在 canonical history 中。

## 9. 为什么不能直接改 message_history

如果直接删除完整历史，会同时破坏：

- 中断恢复所需的真实执行状态；
- 对工具结果的精确回读；
- 问题复盘和实验取证；
- 更换压缩策略后重新生成另一种模型视图的能力。

把 Projector 放在模型调用边界，可以让它像数据库的“视图”：底层事实不变，只决定本次查询看见什么。这也是当前
模块最重要的架构选择。

## 10. JSON 在这个模块里什么时候使用

JSON 用在需要跨进程、落盘、校验或稳定重放的边界：

- `case.json`：任务合同；
- `real_model_protocol_v4.json`：冻结实验参数与门禁；
- `result.json`：一条运行的验收、使用量和 Trace 证据；
- `ARCHIVE_MANIFEST.json`：归档文件数量、大小和哈希；
- JSONL Event Ledger：按顺序追加运行事件；
- Checkpoint JSON：跨进程恢复完整历史；
- Tool Spec/Tool Call：与模型适配器交换结构化参数。

内部计算不需要为了“统一”而全部变成 JSON。压力判断、保留决策、编辑计划和配置在 Python 内使用冻结 dataclass 或
Pydantic 对象，因为它们需要类型约束、派生属性和清晰的方法。只有走到持久化/协议边界才序列化。

## 11. 评测如何避免只看一个成功答案

### 11.1 任务结果与执行过程分层

当前正式汇总区分：

| 维度 | 回答的问题 |
|---|---|
| Task Outcome | 最终代码/答案是否通过隐藏验收 |
| Operational/Budget | Agent 是否正常完成并遵守运行预算 |
| Trace Compliance | 冻结 v4 使用的旧复合 Trace 口径 |
| Process Coverage | 推荐调查工具是否覆盖，只作为诊断 |
| Trace Safety | 是否请求禁用工具、修改后是否成功测试 |
| Candidate v5 Safe Task Success | Outcome + Operational/Budget + Trace Safety，当前不是门禁 |

Case Manifest schema 3 把 `process_coverage_tools`、`forbidden_tool_requests` 和
`require_successful_test_after_change` 分开。漏掉一次 `list_files` 不会再自动变成结果失败；请求 `create_file` 或修改后
没有测试仍属于安全问题。最终修改对不对继续由隐藏 `acceptance.py` 检查。

### 11.2 为什么保留 schema 2

已经保存的 v1～v4 证据使用旧复合语义；v4 正式 12-run 原始证据虽已丢失，其当时记录的聚合结论也不能按新语义
重算。直接把旧 JSON 当作 schema 3 读取，会用今天的标准重写昨天的实验结论。因此加载器显式保留两种 Manifest
类型，正式汇总遇到 schema 3 时才执行新合同交叉校验。

### 11.3 正式实验链路

```text
冻结 protocol + clean commit
        │
        ▼
生成 12 个固定槽位（2 Case × 2 Arm × 3 次）
        │
        ▼
逐条准备独立 workspace → 运行 Agent → 隐藏验收 → result.json
        │
        ▼
检查完整性、Token 预算、Trace、Case 与协议一致性
        │
        ▼
生成 Advancement 汇总
        │
        ▼
复制到 staging → 逐文件 SHA-256 → 在副本上重新汇总
        │
        ▼
原子发布不可覆盖的正式归档
```

负结果也必须归档。任务效果 FAIL 与证据/基础设施错误使用不同退出码，不能只保存好看的实验。

## 12. 当前实验证据怎么解读

### 12.1 确定性离线端点

- 不需要历史回读：整次运行模型可见 bytes 减少 4,571。
- 立即需要回读：虽然工具结果本身缩短，但额外调用使整次运行模型可见 bytes 增加 5,945。

这证明端到端收益取决于回读率与额外轮次，不能只看某一个请求被缩短多少。

### 12.2 v1～v3 的作用

- v1 暴露 stdout/stderr 混杂问题，随后修复记录链路。
- v2 baseline 失败且 projection 没实际触发，不能用于比较策略效果。
- v3 projection 确实压缩，但达到 `max_turns`，帮助发现最近一批保护不足和终局证据生命周期问题。

失败实验没有删除，它们推动了恢复上限、两批保护、预算触发和证据归档设计。

### 12.3 v4 真实 Preflight

| Arm | 安全成功 | Input Token | 模型调用 | 工具执行 |
|---|---:|---:|---:|---:|
| baseline | 1/1 | 13,762 | 6 | 7 |
| projection | 1/1 | 18,422 | 8 | 9 |

projection 累计把自身请求从 82,251 bytes 降到 70,240 bytes，并成功回读一次。对齐双方共有的前 6 次调用，projection
少 839 input Token；但它随后多出 `git_diff`、回读和两个模型调用，最终整条轨迹多 4,660 input Token。

所以 v4 Preflight 的 PASS 只表示：策略被触发、任务成功、恢复通道可用、证据完整、预算未越界。它不表示总成本
已经下降。

### 12.4 v4 正式 12-run 与证据丢失

v4 随后确实执行过 12 个正式样本，现场汇总记录为：projection 安全成功 `6/6`，baseline 为 `4/6`；Provider input
Token 为 baseline 79,556、projection 88,673，projection 总体增加 11.5%，没有达到至少节省 5% 且单 Case 回归
不超过 5% 的晋级门槛。baseline 两次失败来自旧 Trace 把 `list_files` 当硬条件，较短失败轨迹也削弱了成本可比性。

但是这批结果只保存在仓库外 `/tmp`，未在运行结束时立即归档，之后被环境清理。现在只剩开发日志中的聚合数字，无法
从 12 份原始 `result.json`、事件、补丁和 Provider Usage 独立重算。因此它是一次真实的失败实验和流程教训，却不是
当前可复验的正式证据包。B22～B23 随后把“不可覆盖归档 + 归档后重新汇总”变成正式入口的强制步骤。

当前效果结论因此是双重否定：已有 Preflight 和当时的 12-run 观察都没有显示端到端 Token 收益；同时，因为正式原始
工件丢失且后来 Case 语义已升级，也不能把那批聚合数字包装成最终统计结论。若未来继续，必须注册适配当前 Case 语义
的新协议并重新持久归档，不能伪造、回填或静默重解释旧 v4 证据。

## 13. 当前方案的明确边界

1. 最旧优先是确定性启发式，不理解语义重要性。
2. 只压缩 ToolResult；消息、instructions 和 Tool Spec 继续增长。
3. 没有自动摘要，因此不能解决所有超长任务。
4. 超过回读上限的大结果会保守内联；尚未实现分页回读。
5. 计划与应用目前只校验 request byte 数一致。二者在一次同步 `project()` 中连续执行尚可；若未来跨进程保存计划，
   需要内容指纹，不能只比较长度。
6. Checkpoint 与工具副作用并非同一事务，压缩模块没有解决“文件已改但保存 Checkpoint 失败”的恰好一次问题。
7. 模型是否选择回读是行为问题；提供工具不代表它一定正确使用。
8. 当前正式门禁仍冻结为 v4 复合口径，候选 v5 指标不能倒推修改已保存结论。

## 14. 面试时怎样讲这个项目

### 14.1 两分钟主线

> 我做的是一个可审计、可恢复的本地 Coding Agent。多轮工具输出会被反复带入模型请求，因此我没有直接删历史，而是
> 把 canonical history 和 model-visible request 分开。在每轮调用前测量完整请求，超过预算后分类保护最近结果、错误、
> 终局证据和不可回读结果，再按最旧优先把可恢复的旧 ToolResult 替换成引用。模型需要细节时，通过当前 Run 的
> Checkpoint 按 call_id 取回原文，不重新执行工具。所有配置和投影效果进入事件账本。我还做了隐藏验收、Trace 分层、
> Token/轮次预算和不可覆盖归档。真实 Preflight 证明了压缩与回读链路可用，但一次 projection 因额外轮次总 Token 更高，
> 所以我把结论限制在可行性，没有虚报节省。

### 14.2 面试官继续追问时的四层回答

1. **问题层**：历史大结果重复进入每轮请求，成本随轮次累积。
2. **设计层**：完整状态与临时模型视图分离，可恢复引用代替不可逆删除。
3. **实现层**：压力判断 → 保留分类 → 最旧优先计划 → 二次 byte 校验 → 条件式加载回读工具。
4. **证据层**：离线端点说明回读可能抵消收益；v4 Preflight 说明链路安全可用但总 Token 尚未改善。

### 14.3 高频追问

**为什么不用滑动窗口？**  
它可能删除早期用户约束、拆断 ToolCall/ToolResult 关系，也没有恢复通道。本项目先只处理可按 ID 精确恢复的工具结果。

**为什么不用摘要？**  
摘要会增加模型调用、产生遗漏或虚构，还需要解决何时更新。当前先建立确定、可回读、可评测的基线；若普通消息成为
主要负担，再把摘要作为独立策略对照。

**为什么最新结果不压缩？**  
工具刚返回后模型还没基于它完成下一步；立即替换会迫使回读并增加轮次。保护最近两批是针对实际失败路径的候选参数，
不是理论最优值。

**为什么工具定义也要算成本？**  
只有告诉模型 `read_tool_result` 的参数格式，它才可能回读。只计算被删结果、不计算新增 Tool Spec，会夸大净收益。

**为什么大结果反而不压缩？**  
当前回读必须一次完整返回。超过恢复上限仍生成引用，会承诺一个无法兑现的恢复路径，所以先保守保留，未来可增加明确
范围的分页协议。

**模型已经看过，为什么还要保留？**  
模型没有跨 API 调用的隐藏永久记忆。后续推理依赖的信息仍必须出现在新请求、可回读存储或受支持的外部状态中。

**为什么 Preflight PASS 但没有省 Token？**  
Preflight 门禁验证的是安全、触发、回读、记录与预算是否可用，不要求效果已经改善。单请求缩短不代表多轮任务更便宜，
额外调用会反转总收益；后来 12-run 的现场汇总同样没有通过收益门槛，只是其原始工件未被持久归档。

**哪里最能体现工程能力？**  
不是“写了一个替换字符串函数”，而是状态隔离、恢复契约、配置版本、真实调用预算、失败证据保留，以及把任务结果、
过程覆盖和安全约束分开。

## 15. 简历表达建议

可以写：

- 设计并实现预算驱动的 Agent 上下文投影，将完整执行历史与模型可见请求分离，对旧 ToolResult 进行可解释保留分类、
  最旧优先选择和可回读引用替换。
- 基于 Run Checkpoint 实现按 `call_id` 的历史结果恢复，加入跨 Run 校验、完整回读容量约束和条件式 Tool Spec 加载，
  避免压缩破坏中断恢复与审计证据。
- 建立 baseline/projection 预注册评测链路，分离任务结果、运行预算、过程覆盖和 Trace 安全，并通过哈希清单和副本重算
  实现实验结果不可覆盖归档。
- 在真实模型 Preflight 中验证 baseline 与 projection 两组运行均安全成功、projection 实际触发并完成一次历史结果回读；识别到额外模型轮次
  可抵消单请求节省，因此保留正式重复实验作为效果门槛。
- 复盘正式实验临时证据丢失问题，将持久归档、逐文件 SHA-256 和归档后重汇总接入唯一批次入口，失败实验也必须保留。

暂时不要写：

- “Token 成本降低 33.86%”——实际该次 projection 是增加 33.86%。
- “实现无损上下文压缩”——模型视图会丢失内联原文，只是提供恢复通道。
- “生产级最优策略”——没有生产流量与正式统计结论。
- “支持无限上下文”——预算仍可能无法满足，普通消息也没有压缩。

## 16. 模块结束标准与后续方向

上下文压缩模块目前达到工程封板标准：

- 运行时链路完整；
- 恢复与安全边界明确；
- 当前配置、保留下来的 Preflight 证据和新的归档流程可以复现；
- 离线测试、真实 Preflight 和正式实验的负面聚合结论均有记录，同时明确标注正式原始工件已经丢失；
- 代码清理审计完成，完整测试、Ruff、Mypy 和 diff check 通过；
- 没有把收益门槛失败且原始证据已丢失的正式实验包装成成功成果。

除非以后明确决定注册并执行适配当前 Case 语义的新正式实验，当前不再调整压缩参数或增加 Trace 字段。项目下一阶段
转入 Skill：先梳理 Manifest、Catalog、Discovery、Retrieval、Router、Loader 与 Context 的调用链，再把已有 Skill
能力接入一个可观察、默认关闭的 CodingAgent/CLI 路径，用正例、无关任务和相似 Skill 误选三个场景验证。
