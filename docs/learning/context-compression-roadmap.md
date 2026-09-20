# MiniCode 上下文压缩完整路线

日期：2026-09-16。性质：架构计划与漏洞复盘；本文不代表这些阶段已经实现。

## 1. 最终目标

上下文压缩不是“尽量删文字”，而是同时满足四件事：

1. 任务质量不能因为压缩而失去必要证据。
2. 完整历史可以审计、恢复和重放，模型输入只是它的有界投影视图。
3. 被移出的内容有真实、清楚且有界的恢复方法。
4. 衡量整次任务的 Token、轮次、延迟和成功率，而不是只看某一轮少了多少 bytes。

当前阶段只优化同一个 Run 内的历史 ToolResult。用户目标、系统指令、普通对话消息、长期记忆和
跨 Run 检索不在第一版压缩范围内。

## 2. 不可破坏的系统约束

### 2.1 完整历史和模型视图分离

`message_history`、Checkpoint 和审计记录保存完整事实。Projector 每轮重新构造
`ModelRequest`，不能覆盖原始 ToolResult。恢复、重放和故障诊断必须读取完整历史。

### 2.2 每个引用都必须可兑现

只要模型看到“可以回读”的引用，系统就必须在当前 Run 生命周期内返回对应历史原文。
如果只能返回一部分，响应必须明确标注范围、总长度和下一游标，不能把截断内容冒充完整结果。

### 2.3 新结果必须先完整可见

工具刚返回的结果至少完整进入下一次成功的模型请求。一次模型响应并行请求的多个工具结果算同一批，
不能因为逐条遍历而只保护其中一条。错误结果在第一版继续完整保留。

### 2.4 不制造负收益

引用文本、恢复工具定义和其他新增字段都计入请求成本。完整请求没有变小时，不采用投影。
短任务低于上下文压力阈值时不启动压缩。

### 2.5 无法满足预算时显式失败

若受保护内容本身已经超过目标预算，系统应记录容量不足，而不是悄悄删除、截断或伪造摘要。

### 2.6 所有实验变量可追踪

压缩触发预算、最近保留批数、引用 schema、回读页大小和最小净节省都必须进入 Trace 配置。
未记录的新参数不能进入正式对照实验。

## 3. 之前暴露出的漏洞

### 3.1 先做局部替换，后补端到端契约

最初只验证“长 ToolResult 能否变成短引用”，没有先回答引用能否恢复、何时恢复、恢复会不会再次撑满
上下文。这导致后来才发现 `read_file` 的 100,000-byte 产出范围与 `read_tool_result` 的
50,000-byte 完整回读能力不一致。

### 3.2 把局部 bytes 节省误当成任务收益

真实 v3 中，projection 相对自身完整请求累计减少了历史结果 bytes，但额外轮次、重复读文件和
`git_diff` 使整次输入 Token 反而增加，最终还没有留下回答轮次。压缩器指标和 Agent 成功指标没有同时设计。

### 3.3 最近一批是实现规则，不是完整的信息策略

一批策略保证新结果至少展示一次，却不能覆盖“读取证据 → 检查修改 → 最终回答”的常见链路。
两批离线候选改善了这个场景，但尚未证明是所有任务的最佳参数。

### 3.4 引用面向机器，但对模型说明不足

当前 JSON 能唯一定位结果，却没有用自然语言明确说明“原文仍保存、如何回读、回读不会重新执行工具”。
模型能解析 JSON 不等于它会稳定选择正确恢复动作。

### 3.5 评测前置条件没有一次冻结

恢复能力、保留窗口、最终回答轮次和 Trace schema 分散演进，导致真实实验容易同时受多个变量影响。
以后每个协议只验证一组冻结后的策略，失败记录保留，不在看到结果后补跑到成功。

## 4. 目标工作流

```text
工具执行
  ↓
完整 ToolResult 写入 canonical history / Checkpoint
  ↓
下一次模型请求前建立完整请求画像
  ↓
低于目标预算 ─────────────→ 原样发送
  ↓ 超过预算
保护最近 N 批、错误结果和不可替换内容
  ↓
从最旧的、已经成功展示过的可恢复结果开始清理
  ↓
达到最小净收益且能降低预算压力时才采用投影
  ↓
模型通常直接继续；确需旧证据时按 call_id 定向回读
  ↓
所有新结果仍写入完整历史，下一轮重新投影
```

`N` 是需要评测的配置，不预先写死为 `2` 或照搬 Claude 的默认值。第一版不引入模型生成摘要，也不使用
向量数据库；分页同样不是第一版前置条件。先把预算触发、历史保护、确定性清理和可观测性做正确。

## 5. 用 Claude / OpenAI 公开设计校准路线

这里借鉴的是官方公开机制，不把猜测写成事实。

### 5.1 Claude 提供的可迁移原则

Claude Code 接近上下文上限时，先清理旧工具输出，仍然不足时才总结对话。Claude API 的 context editing
还能配置触发阈值、最近保留多少次工具调用、单次至少清掉多少 Token、排除哪些工具；默认保留工具调用参数，
并在响应中报告清除了多少工具结果和输入 Token。

这支持 MiniCode 采用以下原则：

- 预算触发，而不是看到长结果就立即压缩。
- 先处理最旧的历史 ToolResult，保护最近工具交互。
- 工具调用参数继续可见，避免只剩一个来历不明的结果引用。
- 设置最小净收益，防止短任务因引用和恢复工具定义反而更贵。
- 把每次编辑的原因和节省量写入 Trace。
- 工具结果编辑不够时，才进入结构化摘要层。

参考：[Claude Code 工作机制](https://code.claude.com/docs/en/how-claude-code-works)、
[Claude API context editing](https://platform.claude.com/docs/en/build-with-claude/context-editing)。

### 5.2 OpenAI 提供的可迁移原则

OpenAI Responses API 为长时间、工具密集的工作流提供 compaction。官方建议监控上下文增长，并在重要里程碑
之后压缩，而不是机械地每轮压缩。其压缩项是用于继续推理的 opaque item，并提供 Token 用量信息。

MiniCode 借鉴“按压力或里程碑触发”和“端到端计量”，但不把 opaque provider state 作为核心存储格式：
MiniCode 需要兼容多个模型，还要让面试官能检查压缩前后的事实和决策。因此完整 canonical history、Checkpoint
和可解释 Trace 仍由宿主保存。

参考：[OpenAI 长任务 compaction 指南](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.2)、
[OpenAI compact response API](https://developers.openai.com/api/reference/java/resources/responses/methods/compact)。

### 5.3 证据边界

目前没有查到公开的 Codex CLI 内部压缩算法说明。因此本文只能说“借鉴 OpenAI Responses API 的公开设计”，
不能声称 Codex 内部一定使用了某个保留窗口、分页协议或摘要结构。Claude 的默认参数也只是参考，不能直接证明
MiniCode 应保留同样数量的工具调用；最终参数必须由本项目评测决定。

### 5.4 MiniCode 的目标方案

```text
第一层：低于预算，不改变请求
第二层：超预算，确定性清理最旧的可恢复 ToolResult
第三层：仍超预算，在任务里程碑生成结构化继续工作摘要
第四层：只有评测证明模型确实需要旧原文时，才按标识定向回读
```

完整历史始终在模型调用之外保存。这既吸收 Claude 的分层清理思路，也吸收 OpenAI 的预算与里程碑思路，
同时保留 MiniCode 可审计、可重放和跨模型的项目价值。

## 6. 分阶段实施顺序

### 阶段 A：冻结 Context Editing v1 策略

先不继续增加运行功能，只定义并测试一张确定的决策表。至少包含：总请求预算、最近保留批数、单次最小净节省、
排除工具、是否保留 ToolCall、引用说明和 Trace 字段。最近保留 `2` 批只是待验证候选，必须配置化；Claude 的
默认值只能当对照组。

验收标准：

- 同一份历史和配置永远得到同一组 `protected` / `selected` / `unchanged` 决策。
- 低于预算时请求与 baseline 完全相同，不额外加入恢复工具。
- 每个未压缩或被压缩结果都有明确原因。
- 受保护内容本身超预算时报告容量不足，不静默删内容。

### 阶段 B：实现预算驱动的旧结果清理

完整 ToolResult 继续写入 canonical history 和 Checkpoint；只修改发送给模型的投影视图。超过预算后，从最旧的、
模型已经成功看过的、允许恢复的 ToolResult 开始替换，直到满足预算。ToolCall 参数保留，并行返回结果视为同一批。

验收标准：

- 新结果至少完整进入一次成功模型请求，失败或取消的模型调用不算“已经看过”。
- “读证据 → git_diff → 回答”时，保留窗口内的证据仍可见。
- Checkpoint、Replay 和审计历史保持全文，不被投影覆盖。
- Trace 报告触发预算、清理项、清理前后大小、净节省和是否达标。

### 阶段 C：完善可理解引用和定向恢复

现有 `read_tool_result` 先作为可选安全网。引用必须自然语言说明：这是哪个历史工具的输出、为什么被移出当前请求、
原文仍然保存、怎样读取，以及读取不会重新执行原工具。先评测模型能否在需要时正确回读，再决定是否实现分页。

分页不再是默认前置功能。只有包含大于当前 50,000-byte 回读上限的任务确实因无法恢复而失败时，才增加游标、
范围和 UTF-8 安全分页；在此之前继续保留“超过上限不压缩”的安全保护。

验收标准：

- 引用不会被误解为工具执行结果本身，也不会诱导模型重跑原工具。
- 需要旧证据的 Case 能触发正确 `call_id` 回读，不需要时不增加额外轮次。
- 若分页获得证据支持，再单独覆盖页边界、中文多字节、无效游标和精确拼接测试。

### 阶段 D：独立修复最终回答预算

这不是压缩算法，但会直接污染压缩评测。最后一个模型轮次不再继续暴露可执行工具，明确要求生成最终回答；
baseline 与 projection 使用完全相同的轮次规则。若任务确实需要更多工具，应以预算不足结束，不能假装成功。

验收标准：

- 最后一轮不会产生“工具调用无法执行、也没有最终回答”的模糊状态。
- Scripted Model 分别覆盖正常回答、仍企图调工具和工具预算耗尽。
- v3 的失败记录不删除，也不改写为新策略结果。

### 阶段 E：离线端到端评测

至少覆盖：短任务、旧结果无需回读、早期证据必须回读、文件修改后仍需历史版本、超大中文结果、
并行工具、错误结果、`git_diff` 插入终局链路和容量不足。超大结果 Case 用来决定分页是否真的必要，
不能预设结论。

晋级标准：

- canonical history、Checkpoint 和 Replay 全部保持完整。
- 所有引用均可恢复，失败/取消回读为 0。
- 所有需要证据的最终答案都有对应可见原文或成功回读记录。
- 短任务无额外 Tool Spec 和额外轮次；大任务报告端到端累计成本，而非只报单轮节省。

### 阶段 F：真实模型小规模实验

冻结新的协议 ID、commit、模型、Case、顺序、轮次、预算与停止规则后，只运行一对 Preflight。
同时看任务成功、证据正确性、总 input/output tokens、最大单轮输入、模型轮次、恢复次数和延迟。
Preflight 不通过就停止并离线诊断，不直接进入多次正式样本。

### 阶段 G：按证据决定是否增加结构化摘要或历史搜索

只有当引用数量、普通消息或回读轮次成为主要瓶颈时，才考虑结构化任务摘要或
`search_tool_result`。摘要至少包含任务目标、当前状态、重要文件、已做决策、测试结果、未解决阻塞、下一步和
必须保留的用户约束，并保留证据 ID。摘要要单独评测遗漏和过时风险；它不是阶段 A～F 的前置依赖。

## 7. 当前实施位置与下一小步

阶段 A 的 A1～A3 纯规划链路已经完成，并且尚未把预算驱动的计划接入 QueryLoop：

1. `assess_context_pressure` 接收总 byte 预算，并返回请求大小与预算。
2. `overflow_bytes` 和 `editing_required` 由这两个数推导，无法保存互相矛盾的状态。
3. 完整请求测量包含 Tool Spec，因而新增恢复工具的成本不会被忽略。
4. A2 复用 `context_retention.py`，为每项输出 `protected_recent`、`protected_error`、
   `protected_excluded_tool`、`protected_not_retrievable` 或 `eligible`，并由这张表推导受保护/候选 ID。
5. 单一原因按最近批次、错误、排除工具、无法完整回读、候选的顺序判断；它表达当前首先命中的规则，
   不表示后面的安全条件不存在。
6. 可回读性按 UTF-8 bytes 和共享完整回读上限判断；大于上限的结果继续完整保留。
7. A3 只在 A1 判定超预算后，从 `eligible` 中按最旧优先试选；临时假设请求精确计入引用文本和只出现
   一次的回读 Tool Spec，达到预算即停止。
8. A3 输出选中的 call ID、预计请求大小、总节省、剩余超额和预算是否满足；它不返回或发送假设请求。
9. 如果引用不比原文短则跳过；所有候选仍不足时明确保留剩余超额，不静默删除受保护内容。
10. 这些计划尚未写入正式 Trace；默认 Identity 和现有真实实验协议都没有变化。

B1 的隔离投影边界已经完成：

1. `apply_context_editing_plan()` 只替换计划选中的 ToolResult，并按需加入一次回读 Tool Spec。
2. 应用前重新测量 canonical request；若总 bytes 已变化就拒绝应用。应用后再次测量，并要求实际 bytes
   严格等于 A3 的 `planned_request_bytes`。这属于成本一致性校验，不等同于完整的请求身份指纹。
3. `BudgetedToolResultProjector` 组合计划与应用，但 `describe_context_projector()` 明确拒绝把它交给正式
   QueryLoop，因为 schema 2 还不能记录总预算等新变量。
4. 默认 Identity、CLI、旧阈值 projector 和 v3 归档协议都没有变化。

当前预算 projector 在同一次 `project()` 调用中立即完成计划和应用，因此中间没有外部替换请求的入口；若未来
计划需要跨进程保存或延迟执行，必须再增加稳定请求指纹，不能只依赖 byte 数。

B2 已冻结预算投影器的配置契约：

1. 旧 Identity 和阈值 projector 继续使用 schema 2，字段和归档实验含义不变。
2. 预算 projector 使用独立 schema 3，记录总请求预算、最近保护批数、最小净收益、排除工具、完整回读上限
   和恢复工具加载方式。
3. 排除工具名会去重并排序，保证相同语义得到稳定 JSON；解析时要求字段全集、版本和策略均匹配。
4. projector 保存的正是执行时传给 planner 的配置，避免 Trace 写一套、运行用另一套。
5. B2 完成时 schema 3 尚未进入 QueryLoop、CLI 或正式评测，也没有调用真实模型。

B3 已把预算投影器接入通用 QueryLoop 事件边界：

1. `describe_context_projector()` 对预算 projector 返回其 schema 3 配置，不再在构造 QueryLoop 时拒绝。
2. QueryLoop 沿用现有路径，把静态配置与本轮 `changed_tool_result_count`、投影前后 bytes 和节省量合并进
   `MODEL_CALL_STARTED.context_projection`。
3. 离线 ScriptedModel 测试证明：模型收到引用视图、RunResult 仍保存完整历史、同一事件同时含配置和效果。
4. 默认仍是 Identity，旧 schema 2 事件不变；B3 完成时 CLI、CodingAgent 工厂和正式评测尚未启用 schema 3。

B4 已完成产品组合根的安全组装：

1. `build_coding_agent()` 接受完整的 `BudgetedContextProjectionConfiguration`，并与旧
   `max_inline_tool_result_bytes` 明确互斥。
2. 任一引用模式都必须同时提供 EventLedger 与 CheckpointStore；前者绑定 run_id，后者保存可恢复原文。
3. 预算配置的完整回读上限同时配置 `ReadToolResultTool` 和 projector，避免生成无法兑现的引用。
4. `read_tool_result` 预先注册进 Dispatcher，但 Tool Spec 仍只在真正产生引用的轮次向模型暴露。
5. 同一个四轮 ScriptedModel 场景分别验证旧阈值和预算策略：写入引用、模型主动回读、恢复全文、保存完整
   Checkpoint、记录成功工具事件和对应 schema 配置。
6. 默认、CLI 和正式评测仍未改变，也没有调用真实模型。

B5 已增加独立的 schema 3 离线评测入口：

1. `summarize_budgeted_context_experiment()` 接收预先登记的预算配置，并逐个检查模型调用事件。
2. 每轮 schema 3 都必须字段完整、等于登记配置，并与前一轮完全相同；中途改预算会明确拒绝。
3. 配置验证后复用 `summarize_context_trace()`，继续校验模型可见 bytes 与投影后 bytes 一致，以及
   `before - after == saved`，再汇总变化结果和回读成败。
4. 旧 `summarize_context_experiment()` 仍只接受 schema 2；测试明确证明 schema 3 不能通过旧 v3 路径。
5. 新入口尚未接进 `record_result` CLI，也没有注册真实实验协议或调用模型。

B6 已建立预算策略的预注册协议对象和 JSON 加载器：

1. 新的 v4 协议与旧 `_load_context_protocol()` 分开，旧 v1～v3/schema 2 结果不会被 schema 3 规则重新解释。
2. baseline 固定为完整 schema 2 Identity；projection 固定 schema 3 的 10,000-byte 请求预算、最近 2 批保护、
   1-byte 最小净收益、`git_diff`/`run_tests` 排除项和 50,000-byte 完整回读上限。
3. 10,000 bytes 来自旧 Case 启动约 4.9KB、后段约 11～14KB 的已归档范围，只是确保 Preflight 能检验“低压
   不动、高压才压”的实验触发点，不是生产默认值。
4. 协议同时锁死模型、Case、Preflight 两次运行顺序、Provider Token 预算、正式样本数和晋级门槛；加载器
   交叉检查运行数、Arm 数、Case 数、重复数和必需成功数。
5. B6 仍未接入 Agent CLI、评测运行器或结果记录器，也没有调用真实模型。

B7 已把 v4 协议接入单次运行与结果记录边界：

1. `evaluation_run --context-protocol ... --arm ...` 要求显式选择实验 Arm；baseline 传 Identity，projection 直接
   传协议解析出的 schema 3 对象，不再把字段重新手写一遍。
2. CLI 在创建 Provider 客户端前核对 `DASHSCOPE_MODEL` 与协议模型，防止已经花费 Token 后才发现模型跑错。
3. 运行器同时拒绝协议未登记的 Case、当前不支持的 Provider、thinking 模式和非默认 temperature 约定。
4. `evaluation_result --context-protocol ... --context-arm ...` 读取同一协议，按 Arm 分派 schema 2/schema 3
   校验，并核对 Case 与模型；结果保存协议 ID、Arm、Trace 配置和上下文指标。
5. 旧 `--arm projection` 的 500-byte schema 2 路径及 `--context-protocol-id` 记录路径继续保留给 v1～v3。
6. B7 尚未接入批次汇总/Preflight 门禁，也没有调用真实模型。

B8 已为 v4 接入 Preflight 汇总门禁：

1. 结果加载器能严格区分 schema 2 Identity 与 schema 3 budgeted projection；schema 3 的顶层请求预算必须与
   Trace 完整配置一致。
2. 同一个 Preflight 汇总入口按协议 schema 选择旧 v1～v3 或新 v4 校验，不改变历史协议语义。
3. v4 projection 的完整配置必须等于登记对象；baseline 必须无投影变化和 byte 节省。
4. 公共门禁继续检查两组数量、Safe Task Success、projection activity、失败/取消回读、Provider Usage 与
   Token 上限、每 Run 工件、单一 commit 和逐 byte 相同的协议快照。
5. CLI 在门禁失败时返回 1；配置漂移或工件篡改直接拒绝。全部测试使用伪造结果，没有调用模型。
6. 现有结果没有可信实验序号，因此只能验证 Arm 计数，不能证明真实执行先后。文档明确保留该证据边界。

B9 已建立可测试的 Preflight 顺序编排边界：

1. 编排开始前创建全新的结果根目录，逐 byte 复制 `protocol.snapshot.json`，并把快照 SHA-256、Case、
   Run 序号、Arm 和目标目录冻结到 `preflight-plan.json`。
2. 编排器只按协议的 `arm_order` 调用执行器，并把 `run_started` / `run_finished` 依次追加到
   `preflight-events.jsonl`；不再从目录名称推测真实顺序。
3. 执行器报告成功后还必须实际留下 `result.json`，否则本轮仍失败；baseline 失败或缺记录时不会创建、运行
   projection 槽位。
4. 执行器抛异常时先追加失败事件，再把异常继续抛给调用者；已有证据不会静默消失。
5. 结果根目录必须事先不存在，防止旧结果被覆盖、混入或被误当成本次运行。
6. B9 用假执行器验证编排状态机，没有运行 Provider；目前也还没有把真实 CLI 命令包装成执行器。

B10 已完成真实命令执行适配器的离线接线：

1. 每个 Arm 先复用 `prepare_evaluation_workspace()` 创建独立 Git 工作区，不把隐藏验收复制给 Agent。
2. 适配器通过子进程调用已有 `evaluation_run`，保存 `answer.txt` 和完整 `stderr.raw.txt`；stderr 同时流向终端，
   未来真实运行时 Approval 提示不会被捕获层藏起来。
3. 只有原始 stderr 恰好包含一个 `Trace run_` 标记时才生成 `trace.txt`；提示和 Trace 在同一行也能正确切开。
4. 随后通过子进程调用已有 `evaluation_result`，传入同一协议快照、Arm、模型、工作区和 Agent 退出码；不复制
   Trace 校验或隐藏验收逻辑。
5. Adapter 会保存工作区路径、结果记录器 stdout/stderr。记录器退出码非零会返回失败，交给 B9 停止后续 Arm。
6. 在任何 Agent 子进程前，要求 MiniCode 是干净 Git 仓库，并要求结果目录位于仓库外；否则结果文件本身可能让
   `minicode_dirty` 变成 true，污染两组可比性。
7. 离线假命令执行器验证了 baseline/projection 共四条命令、隔离工作区、协议快照传递和全部关键工件；没有调用
   Provider。

B11 已把 B9 证据接入最终门禁，并增加显式批次入口：

1. v4 汇总先严格读取 `preflight-plan.json`，核对字段全集、协议 ID、Case、协议 SHA-256、运行序号、Arm 顺序
   和固定结果目录；计划与注册协议不同会直接拒绝。
2. `preflight-events.jsonl` 必须严格等于两组成功事件序列：baseline started/finished，再 projection
   started/finished；少事件、失败事件或顺序变化都会使 orchestration gate 失败。
3. 结果根下 `result.json` 的路径集合必须恰好是 `01-baseline/result.json` 和
   `02-projection/result.json`，而且每份内容声明的 Arm 必须与对应槽位相同。
4. 汇总新增 `Orchestration evidence`，并把它纳入总 Preflight gate；历史 schema 2/v1～v3 不追溯要求新证据。
5. `python -m minicode.evaluation_preflight` 现在是唯一批次入口：读取协议、调用 B9+B10、成功后自动运行最终门禁，
   分别用退出码 0/1/2 表示通过、实验未通过、配置或证据错误。
6. 所有新增测试仍使用假命令和伪造结果，没有调用 Provider。

至此 v4 的代码链路已经达到“可以准备真实 Preflight”的标准，但当前工作树仍有未提交修改，不能运行。下一步
不再新增压缩功能：先做一次最终只读审计，确认 diff、环境变量、模型名、仓库外结果路径和 Approval 方式；然后由
用户决定是否提交当前实现并授权两次付费模型调用。分页继续留给阶段 C 的超大结果证据决定。

B12 已完成最终就绪审计并修复运行前检查顺序：

1. Provider 配置、登记模型、案例、虚拟环境、仓库外目标和交互式 Approval 均通过只读检查。
2. 批次入口在创建任何结果目录前检查 Git 干净、目标位于仓库外且不存在；失败不再留下半成品证据目录。
3. 每个 Arm 仍在执行前重复检查 Git 与结果路径，覆盖 baseline 和 projection 之间环境被改变的情况。
4. 离线测试覆盖 dirty Git 零副作用、仓库内路径零副作用，以及批次入口成功调用顺序。
5. Provider Token 预算明确为结果落盘后的晋级门禁，不是调用过程中的硬停止器。

下一步只整理可复现提交，不再增加压缩功能。提交后重新确认干净 HEAD，再由用户明确决定是否执行两次真实
Preflight；分页仍留给阶段 C 的超大结果证据决定。

B13 已完成可复现实验提交：预算压缩、v4 协议、批次执行、证据门禁、测试与学习文档已经处于同一个干净 HEAD，
提交后关键 Preflight 定向测试再次通过。当前不再有离线代码门禁；下一步是需要用户明确决定的两次真实 Provider
Preflight。运行时必须在交互式终端审查工具参数，只批准案例允许的 `edit_file` 与 `run_tests`，并将结果保存在
仓库外。正式 12-run 实验仍必须等待 Preflight 门禁通过。

B14 已完成 v4 真实 Preflight：

1. baseline 与 projection 均通过隐藏验收，协议、Provider Usage、Artifact 和编排证据全部 PASS。
2. projection 累计节省 12011 个模型可见 bytes，并成功回读一次被引用的搜索结果，没有失败或取消回读。
3. 对齐共有前 6 次调用时 projection 少 839 input Token，但它多走两个模型轮次，最终总 input 反而增加 33.86%。
4. 这组单样本证明机制安全可运行，不能证明端到端收益，也不能确定额外轨迹由压缩还是模型随机性造成。
5. 原始证据与报告已归档到 `benchmarks/context_projection/results/v4-preflight/`；v4 参数不因结果而回改。

下一步是独立的费用决策：若继续，严格执行已冻结的 12-run 正式实验，并由最终聚合门禁判断效果；若不继续，当前
项目也已经具备“预注册协议、真实 A/B、诚实负面信号与可复核证据”的完整面试故事。分页仍留给超大结果证据。

B15 已建立正式实验控制器的离线边界：

1. 协议中的两个 Case 和每 Case 六个交叉 Arm 顺序被展开为 12 个不可替换的样本槽位。
2. 正式计划在运行前保存协议哈希、Token 上限、全局序号、Case、Arm 和目标目录；已有目录不会被复用。
3. 任务失败且成功生成 `result.json` 时继续后续样本，因为失败也是实验数据；没有记录、记录 Usage 无效或执行器
   异常属于基础设施问题，必须停止。
4. 每次落盘后累计 Provider Usage，超过正式预算后不再发起下一次调用；预算不是单次请求的预测限流器。
5. 当前只用假执行器验证状态机，尚未连接真实命令适配器、正式证据汇总或 Provider。

下一小步只复用 B10 的 prepare/run/result 执行链路接入 `FormalRunRequest`，避免复制一套 Agent 执行代码；随后再
单独将 `formal-plan.json` 和 `formal-events.jsonl` 纳入最终汇总门禁。两步都通过并形成干净 commit 后，才运行已
授权的 12 个真实样本。

B16 已把正式请求接入经过 Preflight 验证的真实命令边界：

1. 公共执行器统一负责 prepare、run、Trace 提取和 result record，Preflight 与 Formal 不再各自复制这条链路。
2. 两个薄执行器只负责各自的计划校验：Preflight 对照两次预检，Formal 对照 Case 优先展开的 12 次正式顺序。
3. 计划位置不一致会在准备 workspace 和执行子进程前拒绝，避免错误调用产生费用后才被发现。
4. 离线假命令测试已经完整穿过 12 个样本、24 条 run/result 命令；没有调用 Provider。

下一小步只把 B15 的正式计划、事件、结果槽位和总 Token 预算纳入最终汇总门禁，并增加一个正式批次 CLI 入口。
完成后还需形成干净 commit，才能真正执行已经授权的 12 个 Provider 样本。
