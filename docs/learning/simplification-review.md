# MiniCode 全局复杂度审查与精简建议

日期：2026-09-16。性质：基于当前工作树的审查与建议；各项是否已经实施以小节中的状态为准。

## 1. 结论与范围

项目值得精简。重点是减少重复维护的规则、提前增加的配置，以及同一事实的多份可矛盾状态。
文件数和代码行数不是单独的删除依据。检查覆盖入口与组装、核心循环、模型适配、上下文处理、
工具与工作区、Checkpoint/Event/Artifact、Skill，以及离线/真实运行评测的主要调用链。
本次没有逐个穷举所有异常分支，不应将这份审查理解成完整正确性或安全性证明。

当前 `src/minicode` 的 Python 文件合计 9,809 行，包含注释和空行；六个 `evaluation_*.py` 与
`context_comparison.py` 合计 2,781 行，约占 28%。`evaluation_summary.py` 单独有 1,237 行。
这些数字用来定位阅读和维护负担，不能据此认定评测无用。

## 2. 主链路应保持清楚

```text
CLI → build_coding_agent → QueryLoop
                            ├─ 上下文投影 → Model Adapter → 模型响应
                            ├─ Dispatcher → 参数校验 → Policy/Approval → Tool
                            │                                         └─ Workspace / ProcessRunner
                            └─ EventLedger / Checkpoint

Skill：选择元数据 → 只读取选中的正文 → instructions
评测：准备独立工作区 → 运行 Agent → 隐藏验收与 Trace 检查 → 汇总
```

这些分工有实际用途。Model 和 ToolRuntime 的小 Protocol 允许真实实现与 Scripted 替身互换；
Checkpoint、事件日志和 Artifact 分别回答“怎样继续”“发生了什么”“输出内容是什么”，不能因为都有
存储行为就合并成一种数据。

## 3. 具体发现

### 3.1 普通与流式请求转换已经出现分歧：优先修复

实施状态：2026-09-16 已完成。

位置：`src/minicode/models/openai_compatible.py:450` 与 `:486`。

`complete()` 调用 `model_request_to_openai_messages(request)`，包含 `instructions`；
`stream()` 调用 `conversation_to_openai_messages(request.conversation)`，只包含对话。
同一个带指令的请求，本地假客户端捕获的角色列表分别为 `['system', 'user']` 和 `['user']`。

影响：直接调用 stream 时，系统指令和放在 instructions 中的 Skill 会丢失。当前 QueryLoop 调用
complete，因此这不是已经证实的当前 CLI 故障。

建议：两条路径共用已有的完整请求转换函数。先补一个带 instructions 的流式回归测试；再按需要合并
重复的请求参数组装。无需为这个问题另建一套 Provider 框架。流式增量解析与完整响应解析仍各自保留。

实际调整：`stream()` 现在和 `complete()` 一样调用 `model_request_to_openai_messages(request)`；
流式回归测试给请求加入 system instruction，并验证假客户端依次收到 system 与 user 消息。
工具定义、额外请求参数和流式响应解析没有变化。

### 3.2 上一小步的预算模块提前抽象过多：优先精简

实施状态：2026-09-16 已完成。

位置：`src/minicode/core/context_editing.py:19`、`:83`、`:108`。

这是上一小步新增的 140 行模块。当前只有测试调用它，未接入 QueryLoop。

- `assess_context_pressure()` 只使用 `max_request_bytes`。最近保护批数、最小收益、排除工具等字段
  目前只被保存、校验和序列化，没有参与运行决策。
- `preserve_tool_calls` 接受一个布尔配置，但 False 必然被拒绝；它目前是一条固定规则，不是真正的选项。
- `ContextPressureDecision` 同时保存大小、预算、超出量和状态，后两项可以由前两项推导。
  本地构造已确认：允许创建 request=100、budget=10、overflow=90、status=within_budget 的矛盾对象。
  正常工厂函数目前计算一致，这个复现证明的是数据结构允许矛盾，并非已发现真实运行算错。

建议的下一次精简：先保留实际使用的预算输入；结果至多存请求大小和预算，其他值用 property 推导。
固定的“保留 ToolCall”写在实现与行为测试里。暂未生效的选项留在设计文档，等消费者实现时再加入代码。
trace payload 可以保留需要的输出字段，但不必为输出方便而重复存储状态。

实际调整：删除尚未生效的 `ContextEditingPolicy`、状态枚举和提前设计的 Trace payload。
`ContextPressureDecision` 现在只保存 `request_bytes` 与 `max_request_bytes`，超出量和是否需要编辑均由
property 推导。`assess_context_pressure()` 直接接收 byte 预算。源文件由 140 行降为 56 行，测试文件
由 195 行降为 120 行；刚好等于预算、超出 1 byte 和 Tool Spec 计入总量的行为保持不变。

后续分类规则继续由现有 `context_retention.py` 承担，`context_projection.py` 负责替换和净收益判断。
不要让 editing 和 retention 再各维护一套最近窗口、错误保护和可恢复性规则。

### 3.3 JSON 容器转换有五份近乎相同的实现

实施状态：2026-09-16 已完成。

位置：`cli.py:146`、`console_approval.py:11`、`core/context_profile.py:160`、
`core/checkpoint_codec.py:121`、`models/openai_compatible.py:115`。

它们都将 Mapping 递归转成普通 dict，将 tuple/list 递归转成 list，方便 JSON 序列化。
建议在定义 JsonValue 的现有模块附近提供一个公共转换函数，五处调用它，保留各处自己的 JSON
格式参数。这个改动不应改变 Checkpoint 格式、工具参数、日志内容或 bytes 的计量结果。

注意：不要把 `_freeze_value()` 一并合并掉。冻结负责输入校验和不可变快照；转为普通容器负责输出序列化，
二者方向与职责不同。

实际调整：在定义 `JsonValue` 的 `core/tool_calls.py` 中增加 `to_plain_json()`，五个调用方删除各自的
递归副本并复用它。各调用方仍自行决定 `indent`、`sort_keys`、`separators` 等输出格式，因此
Checkpoint 文本格式、CLI/审批显示、模型工具参数和上下文 byte 计量口径没有被公共函数接管。
新增行为测试确认只读 Mapping 变回 dict、tuple 变回 list，嵌套内容保持相同。

### 3.4 评测中重复维护了上下文统计

实施状态：2026-09-17 已完成共同事实的提取。

位置：`context_comparison.py:395` 与 `evaluation_result.py:108`。

两处都遍历事件，读取上下文大小，校验 before-after=saved，累计替换项，并统计回读成功/失败/取消。
真实实验还检查协议和 Arm 配置；离线比较还统计毛节省等值。共同部分可以复用，特有校验需保留。

建议：先统一同一份 Trace 的事实统计，再由离线和真实实验各自检查场景条件。验收应要求既有归档结果的
指标与通过/失败结论不变。不要为了减少校验行数取消工件哈希、隐藏验收或旧 schema 的兼容读取。

`evaluation_summary.py` 又同时负责 JSON 读取、schema 兼容、协议校验、Preflight/正式门禁和报告排版。
可以随后把“读取和校验”与“汇总和排版”分离。只是拆文件不会减少规则数量，因此优先于拆文件的是消除
真正重复的统计逻辑。若改用已有 Pydantic 依赖，须先固定旧记录读取行为，不宜全仓一次迁移。

实际调整：新增 `context_trace.py`，集中统计模型调用数、模型可见/原始/节省 bytes、替换结果数和三种
回读结果，同时集中校验 `visible == after` 与 `before - after == saved`。正式评测仍在
`evaluation_result.py` 校验协议 ID、Arm 和 Trace 配置；离线比较仍在 `context_comparison.py` 要求并统计
它独有的 `tool_result_bytes_saved`。后者没有强塞进公共统计器，因为历史正式 Trace 不一定包含该字段。

### 3.5 Skill 关键词召回和排序重复计算

位置：`skills/retrieval.py:50`、`:69`，由 `skills/router.py:43` 创建和调用。

Retriever 对 query 和 manifest 分词，保留有交集者；Ranker 再次分词并计算同一交集的数量。
当前算法可以一遍得到分数，过滤 score=0，再稳定排序和截取 top-k。

建议保留对外 SkillRouter 接口，将当前关键词实现收敛成一个打分流程。无匹配、并列分数顺序和 top-k
行为必须一致。ADR-0008 原来强调独立替换召回与排序；若实施合并，应补充该 ADR 的取舍说明。
Skill 的“元数据发现”和“选中后加载正文”有实际懒加载价值，继续保留。

### 3.6 上下文画像被重复计算

位置：`core/context_projection.py:197`、`core/query_loop.py:455`、`core/context_profile.py:115`。

引用候选路径在 projector 内计算前后画像用于判断净收益；QueryLoop 随后再次计算可见请求画像，
再通过 projection profile 重新计算前后画像。实际走到候选比较的一轮会产生五次 profile_model_request
调用；Identity 路径也会重复测量相同请求。

建议先复用单轮已经得到的画像，避免重复 JSON 序列化。不要为此立刻引入跨轮缓存、缓存失效协议或全局
缓存服务。本次只确认重复计算，未测量其延迟占比，不能宣称它是主要性能瓶颈。

### 3.7 孤立功能和文档也增加理解成本

`RecordingModel` 当前只在测试与类型契约中被引用；QueryLoop 自己记录模型调用事件和 Usage。
RecordingModel 还提供耗时和异常分类，两者并非完全等价。应先决定正式观测入口，再决定接入或归档，
不能仅凭主链路未调用就立即删除。

默认 build_coding_agent 尚未组装 Skill provider，模型 stream 也未接入默认 QueryLoop。学习文档应标明
“可用组件”“默认路径”“实验候选”，减少把所有代码都当成每次必经流程的误解。

当前 ROADMAP、压缩策略、压缩路线和学习日志都有不同时间的“下一步”。建议由路线文档维护当前计划，
学习日志只保留历史证据，旧策略标明日期与替代关系。这样暂停 A2 去做精简时，不会出现多个活跃计划。

## 4. 应当保留的复杂度

- Dispatcher 的参数校验、Policy 和 Approval 分工。
- Workspace 的目录边界、精确编辑、文件与输出大小限制，以及 ProcessRunner 的超时/取消处理。
- Checkpoint 的 Run ID、调用和结果对应关系、完成状态校验，文件存储的原子替换。
- 完整历史与模型投影视图的分离，以及引用必须能兑现的回读边界。
- 不泄露隐藏验收的独立评测、工件哈希、历史失败记录和诚实的统计口径。

这些机制有具体失败场景和测试依据。重复的校验代码可以整理，但外部输入和恢复数据的校验不能只用
类型注解代替。几个重复的小型 `_record_event` 包装也不值得立即引入继承体系去消除。

## 5. 建议的后续顺序和完成标准

| 顺序 | 一小步的范围 | 完成标准 |
|---|---|---|
| 1 | 统一普通/流式请求的指令转换 | 相同 ModelRequest 的 instructions 都能传到假客户端；已有流式解析行为不变 |
| 2 | 精简 A1 预算对象，收回未生效选项 | 边界判断不变；状态只能从实际大小推导；继续不接入真实 QueryLoop |
| 3 | 合并五份 JSON 容器转换 | 嵌套 Mapping/tuple 等价；原有序列化内容、Checkpoint 与 byte 统计不变 |
| 4 | 共用 Trace 上下文统计 | 既有离线 Case 和归档真实实验的指标、门禁结果不变 |
| 5 | 按当前主线需要决定 Skill 与观测整理 | 路由输出稳定；正式观测入口明确；不因“可能以后用”不断增加组件 |

完成前四步后即可回到上下文预算主线，不必把所有整理都做完才开发。恢复 A2 时复用 retention，
避免再平行增加一套分类框架。每一步都先展示删除/合并了哪条重复职责，再解释保留的关键行为。

## 6. 本次验证与边界

- 现有全套测试：591 passed。相对最初审查时，预算模块精简删除了 7 个只验证未生效配置的测试，
  JSON 公共转换新增了 1 个行为测试。
- 本地假客户端复现 stream 丢失 instructions，全程无 Provider 请求。
- 本地构造复现 ContextPressureDecision 可存储矛盾状态。
- 审查后的前四步已完成：统一普通/流式请求转换、精简预算压力对象、合并 JSON 容器转换，并共用
  Trace 上下文事实统计；Skill 与观测等其余问题仍未调整。
- 学习验收：能解释“为什么冻结输入仍有用”“为什么派生状态无需重复存储”“为什么 ToolCall 保留是
  固定规则”“为什么把两个文件合成一个文件不一定降低复杂度”。这些是后续复习题，不表示已经掌握。
