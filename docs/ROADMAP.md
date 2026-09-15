# 学习与实现路线

状态：M0 至 M7 与 Coding Agent MVP 已完成；文件恢复链路已接入；M9 上下文治理进行中，M8 实验仍暂停在独立 WIP 分支
节奏：按掌握程度推进，而不是机械追赶周数

2026-09-13 核对后的秋招行动顺序见
[Agent 面试考点与秋招发展路线](learning/agent-interview-roadmap.md)。
下方 M0—M13 是主题地图，不要求全部完成才能形成简历项目；当前优先上下文治理，随后
Skill 产品接入和可纠错项目记忆，安全与评测贯穿各阶段。多 Agent 是收益驱动的可选项。

## 1. 教学策略

用户接触过端到端 AI 应用的概念和代码，但没有独立项目经历，不能假设已经理解文件职责和完整执行流程。因此采用以下深度：

- 根据实际掌握情况讲解：RAG、Embedding、向量库、FastAPI、SSE、Tool Calling 的基本概念。
- 从工程使用角度讲清并亲手写：包结构、配置文件、入口、类型、Pydantic、异步生成器、队列/取消、依赖反转、Fake 与测试。
- 重点深入：裸 Query Loop、工具协议、权限、事件溯源、上下文、Memory、Skills、多 Agent 与 Evals。

首次引入一个文件或流程时，必须回答：

1. 为什么需要它？
2. 谁创建、读取或调用它？
3. 输入和输出是什么？
4. 它在完整调用链的哪个位置？
5. 如果删除或设计错误，会发生什么？
6. 有哪些常见替代方案？
7. 它是标准格式、工具生成模板、参考模板修改，还是项目完全手写？
8. 哪些部分可以修改，哪些部分应交给工具维护？

每个单元使用相同闭环：

1. 概念与失败模型
2. 预测程序行为
3. 共同设计接口
4. 用户实现关键部分
5. 运行失败测试并调试
6. 独立完成变式
7. 用自己的话讲回
8. 写入学习日志和必要 ADR

## 2. 里程碑

| 阶段 | 主题 | 核心产物 | 学习验收 |
|---|---|---|---|
| M0 | 契约、环境、威胁模型 | CLI 骨架、测试工具链、文档基线 | 能解释目标、非目标和可信边界 |
| M1 | 数据协议与 Fake Model | Message、ToolCall、ToolResult、Scripted Model | 能解释依赖反转并编写响应脚本 |
| M2 | 最小 Query Loop | 明确状态机、预算、停止与错误反馈 | 能独立补一个新状态和终止条件 |
| M3 | Tool Runtime | Schema、Registry、Dispatcher、统一错误 | 能新增受测 Tool 并处理非法输入 |
| M4 | Model Adapter | 一个真实 Provider、流式、重试与限流 | Fake 与真实模型共用核心循环 |
| M5 | 安全 Coding Tools | read/search/edit/test、Policy、Approval | 能解释并测试路径逃逸和命令注入 |
| M6 | Event Ledger | Trace、Artifact、Checkpoint、Replay | 能从事件流复盘和恢复失败任务 |
| M7 | Skill System | Manifest、Catalog、召回、精排、懒加载 | 能设计正例、反例和路由评测 |
| M8 | Memory | 提炼、证据、作用域、去重、过期与删除 | 能发现并修复错误记忆污染 |
| M9 | Context & Cache | 分层上下文、Repo Map、压缩、稳定前缀 | 能量化 Token 收益与事实丢失 |
| M10 | Worker / Fork | TaskSpec、ResultEnvelope、并发与权限衰减 | 能比较串行和并行的收益与成本 |
| M11 | Agent Team | DAG、取消传播、重试与冲突检测 | 能处理超时、错误结果和孤儿进程 |
| M12 | 红队与加固 | 注入、秘密、沙箱、故障注入 | 高危漏审批与越权副作用为零 |
| M13 | Benchmark 与发布 | 真实仓库验证、报告、容器、CI | 能用数据讲清设计带来的收益 |

## 3. 阶段门禁

每个阶段同时满足两类完成定义。

工程完成：

- 正常和错误路径均有测试。
- 接口、事件或数据格式有文档。
- 可以从 Trace 解释执行过程。
- 不依赖人工观察判断“看起来能跑”。

学习完成：

- 能画出本阶段数据流。
- 能解释至少两个设计取舍。
- 能指出至少两个失败模式。
- 能不看答案完成一个变式。
- 能说明测试为何能发现错误。

## 4. 复习机制

每三个里程碑进行一次累计挑战：

- 不提供完整代码，只给需求和验收测试。
- 随机抽取之前的概念进行讲回。
- 将错误记录到学习日志。
- 判断是继续、补课还是重做变式。

## 5. 当前进度与下一步

M7 Skill System 工程完成记录：

1. 已完成：定义不可变 SkillManifest 和稳定有序、拒绝重复名称的 SkillCatalog。
2. 已完成：实现关键词召回、按共享词数量排序、稳定同分顺序和 `max_skills` 截断。
3. 已完成：从本地 `manifest.json` 自动发现 Skill，并要求 Manifest 名称与目录一致。
4. 已完成：使用独立 Workspace 和 byte 上限延迟加载被选中的 `SKILL.md`，未选中正文不会读取。
5. 已完成：SkillContextBuilder 组合指令；QueryLoop 根据最近用户消息构建一次并在多轮模型调用中复用。
6. 已完成：`ModelRequest.instructions` 与真实 conversation 分离，并由 OpenAI Compatible Adapter 转成前置 system messages。
7. 已完成：记录 Skill 选择、加载开始以及成功、失败或取消事件，并保持异常和取消语义。
8. 已完成：建立包含正例、负例、准确率和失败诊断的确定性路由评估；完整磁盘集成测试证明按需加载。

9. 已完成：通过 M7 数据流、延迟加载、上下文分离、工具权限边界和路由评估的学习门禁；全项目 427 个测试以及 Ruff、mypy、格式和 diff 门禁通过。

M7 之后的 Coding Agent MVP 收敛记录：

1. 已完成：把真实模型、QueryLoop、默认工具、Policy、Approval、EventLedger 和
   ArtifactStore 组装为 `minicode run` 垂直切片。
2. 已完成：补齐 `list_files`、`create_file`、`git_diff`，并统一目录剪枝、Workspace
   边界、固定进程参数、超时和输出上限。
3. 已完成：建立单文件修复、跨文件契约和只读注入诊断三个固定 Case，以及模型不可见
   的确定性验收程序。
4. 已完成：保存第一批完整 `answer.txt`、`trace.txt`、`result.json`，并实现批次汇总；
   三次运行全部通过，合计 12 次模型调用、15 次工具执行、20727 输入 Token 和
   1263 输出 Token。
5. 已完成：增加搜索驱动的共享根因修复 Case；首次正式运行通过，证明 Agent 能从
   未知文件位置开始，经发现和调用关系搜索定位共享实现，并精确修改一个文件。

M8 Memory 的实验代码保留在 `wip/m8-memory`，尚未进入主干，也不作为当前产品能力
对外描述。

2026-09-13 当前工作区进度补充：

1. 文件 Checkpoint、`minicode resume`、完成态拒绝恢复和重建 Agent 的恢复集成测试已完成；
   不保证工具副作用恰好一次，Trace/Artifact 仍为进程内实现。
2. Result 2 已实现结果、运行状态、预算与 Trace 四维判断，新增记录支持补丁与工件哈希校验；
   历史证据仅为四个 Case、五次跨版本运行，不能合并成当前版本综合成功率。
3. M9 已有请求组成画像、保留分类、确定性短引用和当前 Run 原文回读；产品组装支持显式
   阈值启用闭环，但默认与 CLI 仍发送完整历史，尚未证明 Token 收益或任务质量不下降。
4. M7 的 Skill 组件虽已完成，但默认 `build_coding_agent()` 尚未传入 Skill Provider；
   接入产品与任务级收益评测是后续独立阶段。

历史回读底层现已完成两层：`get_tool_result(history, call_id)` 负责纯查找并区分 pending
与 unknown；`RunToolResultSource` 绑定一个 run_id，只从该 Run 的最新 Checkpoint 查找，
并拒绝 Store 返回的 Run 不匹配。它们只在显式开启引用组装时通过 Tool 暴露给模型。
有输出上限的 `ReadToolResultTool` 契约也已完成：模型参数只包含 call_id，查询失败转为
预期 Tool 错误，宿主固定 UTF-8 byte 上限。默认 Agent 不注册，显式引用组装才注册。
包含 call_id、原始 UTF-8 byte 数和回读工具名的短 JSON 引用及确定性投影已经完成。
投影只处理 retention 判定为 eligible、超过阈值且替换后确实更短的结果；最新批次与错误
结果保留原文。`build_coding_agent()` 现可通过非空阈值同时启用投影器和回读 Tool，并要求
EventLedger 与 CheckpointStore 以绑定当前 Run；脚本模型闭环测试已通过。默认值仍为关闭，
CLI 尚无开关。`MODEL_CALL_STARTED` 现同时记录模型可见画像和 canonical/投影对比：变化的
ToolResult 数、投影前后 ToolResult/总 bytes 及节省值；回读可从已有工具完成事件统计。
固定的 `eager_historical_readback` 离线对照现可通过
`.venv/bin/python -m minicode.context_comparison` 复现：开启组工具结果毛节省 10142 bytes，
按需回读工具定义花费 1000 bytes，但强制回读增加一次模型调用，累计模型可见内容仍比关闭组
多 5945 bytes。该结果证明压缩
不天然降低总成本，不是对真实模型质量的结论。`no_historical_readback` 端点也已完成：两组
都是 3 次模型调用和 2 次工具执行，开启组不回读，工具结果毛节省 5071 bytes；计入新增回读
Tool Spec 的单轮 500-byte 开销后，完整运行仍净少 4571 个模型可见 bytes。两个端点现在分别证明高
回读可能亏损、零回读可以获益。成本分解报告也已完成：不回读端点满足
`4571 = 5071 - 500 - 0`，急切回读端点满足 `-5945 = 10142 - 1000 - 15087`。只按这两个端点
线性混合时，急切回读型任务占比的示意归零点约为 43.47%；报告明确标记它不是生产阈值。
投影器现在会先计算候选工具结果毛节省，只有严格覆盖同一请求新增的回读 Tool Spec 才产生
引用；回读工具也从始终暴露改为随引用按需暴露。下一小步
的真实模型协议已经预注册：选择两个较长 Coding Case、两 Arm 各三次，固定 500-byte 阈值、
交替顺序、质量/Token 门禁及硬预算，共 12 次正式运行，但该 v1 在 Preflight 后已因策略改变
而停止，不能执行正式样本；新策略需要单独的 v2 协议。审查发现正式开跑
前还缺 Benchmark Arm 参数传递、结果配置/上下文字段和分 Arm 汇总。下一小步只实现
Benchmark 配置传递并用 Scripted Model 验证，普通 CLI 继续默认关闭且不调用真实 Provider。
该配置链现已完成：`evaluation_run --arm baseline|projection` 分别传入 `None|500`，Scripted
Model 从最终工具集合验证开关；未知 Arm 会在模型创建前失败。下一小步是扩展结果记录契约，
保存协议 ID、Arm、阈值和 Trace 中的投影/回读汇总，并校验声明与事件一致。该结果契约现已
完成：Trace 明示 Projector strategy/阈值，记录器逐轮核对 Arm 并复算 bytes 与回读 outcome；
普通非实验结果保持兼容。协议化汇总也已完成：它按协议、Case、Arm 和重复次数对齐正式结果，
检查 Safe Task Success、汇总/逐 Case input Token 与回读门禁，并拒绝模型、commit、阈值或
Run ID 不可比的数据。当前仍未调用真实 Provider；下一阶段是经确认后运行一对独立 Preflight，
先验证端到端结果链，Preflight 不进入 12 次正式统计。

2026-09-15 自适应投影补充：v1 Preflight 证明“局部 ToolResult 变短”仍可能被始终携带的
回读 Tool Spec 抵消，因此现实现改为只在完整请求至少净省 1 byte 时采用引用，并只在该请求
暴露 `read_tool_result`。Trace 配置 schema 2 已记录并验证 `minimum_net_savings_bytes=1`
与 `retrieval_tool_loading=on_reference`；旧 v1 结果保持可读，但不能冒充新策略证据。下一小步
是预注册 v2 真实模型协议，不在本步调用 Provider。
