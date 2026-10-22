# Skill v1 阶段收尾：验收、简历事实与真实执行链路

核对日期：2026-10-05；真实运行日期：2026-10-03。本页不新增运行功能、不改变评测算法，
也不重新调用真实模型。实现过程见 [产品化路线](skill-product-roadmap.md)。

## 1. 结论：工程范围可收尾，学习理解尚需确认

本阶段交付的是**本地、受信任目录、显式启用、默认关闭的 Skill 可选能力**，
不是语义路由平台、权限系统、远程插件市场或生产级安全沙箱。

产品化路线第 7 节的前六项已有工程证据；第七项“用户能解释设计”不能由助手替用户宣布通过。
因此工程实现可以收尾，不再为追求指标增加功能；接下来先复述与查漏，再进入 Memory 的范围设计。
关键词路由失败、默认 CLI 没有累计 Token 预算等局限保留为后续议题，不伪装成已解决。

## 2. 七项标准对应什么证据

以下测试名称可以在所链接的文件内搜索。通过表示所列合同被验证，不代表所有可能场景均安全。

| 标准 | 核对结果 | 可复核证据与边界 |
|---|---|---|
| 1. CLI 显式启用，默认关闭 | 工程通过 | [CLI 测试](../../tests/test_cli.py)：`test_run_with_explicit_skills_root_handles_skill_selection` 的 matched/unmatched；`test_run_without_skills_root_does_not_load_skill_catalog` 确认未传参数时不会扫描 |
| 2. 未选中正文不读，组合指令有上限 | 工程通过 | [本地集成测试](../../tests/skills/test_coding_agent_integration.py)：`test_local_skill_reaches_model_without_loading_unselected_body`；[循环测试](../../tests/core/test_query_loop.py)：`test_query_loop_rejects_oversized_skill_before_model_call`；单文件默认 50000 bytes、渲染总上限 160000 bytes，不是 Token 或账单预算 |
| 3. 选择/加载/失败/注入可核对，事件不复制正文 | 工程通过 | [Context 测试](../../tests/skills/test_context.py)、CLI 损坏正文测试、循环的 `test_query_loop_records_skill_events_before_model_call`；选择/加载事件只有名称、分数、状态、byte 等元数据，注入由 ModelRequest 检查，真实 Trace 记录 instruction 大小，不提供逐项加载耗时指标 |
| 4. 恢复复用同一份 Skill 指令 | 工程通过 | 集成测试 `test_resume_reuses_original_skill_after_its_file_is_deleted`；CLI 测试 `test_resume_reuses_saved_skill_without_skills_root`；带 Token 预算的 Preflight 是 fresh run，当前不支持 resume，不能把普通恢复能力当作预算评测恢复能力 |
| 5. 默认/命中/无匹配/误选/加载失败/越权建议有测试 | 工程通过，但算法有已知失败 | CLI 测试覆盖默认/命中/无匹配/坏正文；[路由数据测试](../../tests/skills/test_routing_benchmark.py) 及离线报告暴露误选、漏选；集成测试 `test_loaded_skill_cannot_override_edit_permission` 覆盖 Policy 拒绝、审批拒绝。测试通过不等于路由样本全正确 |
| 6. 任务级开关对照，诚实报告结果与成本 | 工程通过，仅限一个 Case | S6m 真实一对：两组隐藏验收通过、usage 完整，开启组 Token 更多；无关任务的 no-match 已离线覆盖，但未做其真实付费开关对照，不能声称多场景效果已验证 |
| 7. 能解释 Skill 与 Tool/权限/Agent 的区别 | 待用户复述确认 | 本页最后六个理解检查；助手讲解和测试绿灯不等于用户已经掌握 |

### 不能遗漏的路由局限

本次重新运行了离线报告：

```bash
.venv/bin/python -m minicode.skill_routing_report benchmarks/skill_routing/v1.json
```

版本 `skill-routing-v1`，4 张卡片、12 个**合成草案**样本、max_skills=3。
按现有草案标签，7/12 完全匹配，2 个样本漏选、3 个样本多选。
标签仍标为 `synthetic draft; pending owner review`，不是经过业务人员审核的生产 Ground Truth。
普通报告命令退出 0 表示报告成功生成，不表示 12 个样本全对。

具体失败不是新的工程异常，而是当前关键词算法的边界：

- 写生日诗与文档 Skill 共享 write，被错误选择。
- pytest/unittest 请求共享 failures，除了正确 Skill 还多选另一个。
- 同义改写、自然中文与英文卡片没有共享词，漏选文档 Skill。

所以可以说“建立了能暴露漏选、多选的评测”，不能说“实现了高准确率语义路由”。

## 3. 这次真实对照到底测什么

任务：把库存记录公开字段 quantity 同步改为 stock，只允许编辑 inventory.py、report.py，
不能改测试或新增文件。它检验的是**生产者与消费者的数据契约同时修复**。

baseline 不传 Skill 目录；treatment 显式传冻结目录，选中并加载 inventory-contract-review。
两组模型均 qwen3.7-flash，其他预算、工具、权限和采样设置一致。
Skill 要求先检查跨文件契约、最小修改、运行测试、检查补丁，但并不代替模型完成推理。

| 指标 | 关闭 Skill | 开启 Skill |
|---|---:|---:|
| 隐藏验收与最终 verdict | 通过 | 通过 |
| 模型调用 | 5 | 6 |
| 工具执行 | 7 | 8 |
| Provider 报告输入 Token | 8499 | 11942 |
| Provider 报告输出 Token | 388 | 650 |
| usage 完整性 | 5/5 | 6/6 |

开启组输入多 3443、输出多 262 Token，两组修改完全相同；开启组多调用了一次 git_diff，
随后多一轮模型读取结果并最终回复。不能把总差额只归因于 Skill 正文。
本次没有观察到结果改善或 Token 节省；一个任务各跑一次也不能估计通用成功率。

原始证据：`/home/songshihao/projects/minicode-evaluation-results/skill-preflight-v2.EB5aeh/pair`。
旧额度失败批次仍保留，不能拿它当模型能力失败样本或把它重命名成新模型成功记录。

## 4. 从命令输入到最后生成记录

### 4.1 先准备，再执行，不是一个命令直接开始修代码

历史准备命令为 `python -m minicode.skill_preflight --prepare --results-root 新目录`，
运行时显式设置 DASHSCOPE_MODEL=qwen3.7-flash；`--prepare` **不调用模型**。
它读取 preflight.json，验证模型/组序/权限/预算，将源码、Case、Skill、协议和依赖描述文件
复制到 snapshot，保存 SHA-256、Python/依赖版本到 plan.json。

为什么先做这些？否则两组中间改了 Skill、代码或测试，最后就不知道差别来自什么。

用户授权后才执行 `--execute`。执行前核对实际配置、源文件 hash、快照 hash、依赖与计划一致，
排他写入 execution.started。同一结果目录不能重跑，失败后也不能删标记冒充第一次执行。
本页没有执行该付费命令；后续新付费批次仍要单独确认范围。

### 4.2 每一组从同一份未修复代码重新开始

编排器只复制冻结 Case 的 workspace/，初始化 Git 基线。
baseline 修好的文件不会传给 treatment；两组各有独立工作区、Run ID 和结果目录。
隐藏 acceptance.py 留在冻结 Case 外层，不放进模型操作的工作区。

编排器调用原 CLI 的 main，不另造一套 Agent；传入同一任务、8 轮/8 工具限制、
Token 预算和夹具审批器。treatment 唯一计划差别是多传 skills_root。

### 4.3 CLI 组装，QueryLoop 决定何时构建 Skill

CLI 从环境获取模型配置，创建 Workspace、事件账本、Checkpoint 存储、真实工具、模型适配器。
传 Skill 目录时先发现 manifest.json 元数据，组装 Catalog、Router、Loader、Builder，
这时尚未读取所有 SKILL.md。

QueryLoop 开始本次 run 时，根据最近一条用户输入调用 Builder 一次：

```text
用户任务 → Router 在卡片名称/描述/tags 上匹配关键词
        → 排序、最多取 3 个 → Loader 只读选中正文
        → Builder 记录选择/加载事件 → render 成一段 Skill instructions
```

本次选择分数为 2。任务中的 inventory.py、report.py 提供了与英文卡片共享的词；
这不等于关键词算法已理解自然中文语义。命中名为 inventory-contract-review，正文 619 bytes。
遇到选中正文损坏则在第一次模型调用前停止，不默默丢掉 Skill 继续执行。

### 4.4 每轮请求都有哪些东西

```text
ModelRequest
├─ instructions：基础编码指令 + 本 Run 渲染好的 Skill 指令（开启组）
├─ conversation：用户任务 + 已发生的助手文本/ToolCall/ToolResult
└─ tool_specs：可用工具的名称、描述、参数结构
```

Skill 位于 instructions，不是追加到 message_history 的新消息，也不是新 Tool。
适配器把 instructions 转为服务端 messages 中的 system 消息；因此“它不在我们的
message_history”并不等于“服务端 messages 里没有它”。
tool_specs 转为 tools 参数；conversation 中 ToolCall 转为助手工具请求，ToolResult 转为 tool 消息。

原文指令在本 Run 内每轮复用，不重新扫描磁盘。本次 context_projector 为 identity，
即没有启用上下文压缩；模型从请求看到完整既有历史，不能把这次结果当作压缩实验。
模型适配器发送请求，解析服务端响应为 ModelResponse（文字、工具调用、usage）。

### 4.5 模型提议，程序执行，并不是模型自己打开文件

QueryLoop 收到响应，先累计并检查 usage：缺失或达到阈值就停止本轮工具及下一轮模型请求。
每组累计输入阈值 30000、输出阈值 4096；单次服务端输出参数为 1024，SDK 重试 0。
累计检查发生在响应之后，所以当前请求可能越过阈值，不能声称费用硬上限。

预算检查通过后，若有工具请求，Dispatcher 查找工具、校验参数、检查 Policy。
edit_file/run_tests 的 ASK 还需夹具审批器批准：仅允许两个实现文件和固定测试目标。
读取/列目录/检查 Git 按原默认策略允许，文件工具还受 Workspace 路径约束。
Skill 即使写“已批准修改”，也不会改变这些程序检查。

工具执行得到 ToolResult，其 call_id 对应原 ToolCall；循环将真实结果追加到 message_history。
Dispatcher 把工具输出存到进程内 Artifact，并在事件中记录其引用/大小。
工具结束后保存 Checkpoint：历史、轮次、工具次数、本 Run Skill 指令快照等。
下一轮模型请求包含刚得到的结果，模型据此决定继续读文件、修改、测试或结束。

### 4.6 两组的真实工具轮次

| 模型轮次 | 关闭组 | 开启组 | 目的 |
|---|---|---|---|
| 1 | list_files | list_files | 定位源码和测试目录 |
| 2 | 3 次 read_file | 3 次 read_file | 读取生产者、消费者、公开测试契约 |
| 3 | 2 次 edit_file | 2 次 edit_file | 一处输出 stock，一处读取 stock，保持两端一致 |
| 4 | run_tests | run_tests | 运行公开测试，返回测试结果 |
| 5 | 最终文字回复 | git_diff | 关闭组结束；开启组检查修改范围和补丁 |
| 6 | 已结束 | 最终文字回复 | 开启组读取 diff 后结束 |

多工具可在一个模型响应中提出，由程序逐个执行；所以模型次数不等于工具次数。
当响应没有工具请求时，循环保存 completed Checkpoint 并返回最终回复。
“模型说完成了”只代表循环结束，不代表任务正确。

### 4.7 记录器独立判断任务是否成功

CLI 输出最终回复；评测编排器保存 answer.txt、stderr.txt，并提取 trace.txt。
record_result 再读取实际 Git 补丁，解析 Trace，核对实际 Skill 选择/加载与声明的组别。
接着调用工作区外的 acceptance.py：独立导入修复后的模块，检查输出 stock、消费者渲染、
quantity 已移除、只修改允许的两个文件。公开测试是模型可见的反馈；隐藏验收是记录器的独立判断。

记录器合并 Agent 退出码、运行停止原因、轮次/工具预算、Trace 约束和隐藏验收，写入 result.json。
不仅看最终文字，更不能用“正确加载 Skill”代替代码验收。

编排器检查第一组 completed、usage 完整、实际预算及 Skill 组别一致等，才启动第二组；
如果模型正常完成但隐藏验收失败，仍保留该结果并运行第二组，不挑掉失败样本。
两组最后汇总到 batch.json。pair_complete 表示两份记录可比较，不等于任务都成功。
本次 task_passed 和各组 verdict 也都为 true，属于另一个判断。

### 4.8 各文件与状态的区别

| 数据/文件 | 回答什么问题 | 不负责什么 |
|---|---|---|
| plan.json + snapshot/ | 当时打算运行什么，代码/Case/Skill 精确是什么 | 不证明模型已经成功完成 |
| Checkpoint | 本 Run 从哪个已保存状态继续、沿用哪份 Skill 指令 | 不是压缩摘要、不是任务独立验收；当前带 Token 预算的 Preflight 不允许 resume |
| trace.txt | 执行中发生了哪些模型/工具/审批/Skill 事件 | 不含完整 Skill 正文或所有工具输出全文，不能仅靠它还原所有内容 |
| answer.txt | 模型最后说了什么 | 不证明代码行为正确 |
| workspace.patch | 隔离工作区实际修改了什么 | 不证明修改通过了契约验收 |
| result.json | 单组验收、预算/轨迹 verdict、usage、Skill 开关与加载结果 | 不证明 Skill 通用效果 |
| batch.json | 两组是否完整可比较、各自结果和汇总 | 不等于成功率提升报告 |

普通 CLI 的事件/Artifact 在进程内，Checkpoint 写入本地状态目录；本次评测通过捕获 CLI 输出
把 Trace 另存为文件。不要把这些都理解为“所有运行数据已经持久化”。

## 5. 简历可直接使用的事实表述

项目名称建议：**MiniCode：可审计 Coding Agent 运行时**。
其中 Skill 部分可写两条，不必把所有实验数字堆进简历：

- 实现本地 Skill 可选接入，基于 Manifest 关键词路由与正文按需加载，将方法指令注入模型请求；通过 Checkpoint 保存实际指令快照，保证同一 Run 恢复时不受磁盘 Skill 变化影响。
- 构建版本化路由评测与任务级 Skill 开关对照，记录漏选/多选、实际加载、独立验收和 Token usage；冻结代码与任务快照，并在评测循环中加入缺失 usage 停止、累计 Token 阈值及工具审批边界。

这两条描述本模块已验证能力，不表示无人工辅助独立编写所有代码。
结合 AI 协作开发时，应能说明哪些代码由助手辅助生成，自己如何阅读、测试和定位问题。

面试追问数字时再说：一个跨文件契约修复 Case 进行了真实开关对照，各一次、两组通过，
11 次模型调用均有 usage，开启组 Token 更多，因此未声称效果提升。
单文件/总指令 byte 上限也是设计边界，不是实测性能收益。

不要写：Skill 使成功率提高 X%、成本降低 X%、路由准确率达到生产要求、生产级沙箱安全、
多 Agent/长期记忆已实现、预算评测可无损 resume。当前证据不支持这些说法。
路由草案的 7/12 不建议作为简历亮点，更不能去掉“合成且标签待审核”的前提。

## 6. 面试时如何解释，自己如何检查理解

一分钟讲法：

> 我做的是 Coding Agent 运行时。Skill 是可复用的方法说明，不是执行权限。
> 用户显式指定可信目录后，程序根据任务匹配轻量卡片，只加载选中正文，作为模型指令在本 Run 各轮复用。
> 工具仍由程序校验、检查策略并审批；恢复使用 Checkpoint 中的原指令，不重新读取磁盘。
> 我把路由评测和代码任务验收分开，也做了真实开关对照。这一个任务两组都成功，开启组成本更高，
> 所以我只声称链路与边界被验证，没有把它包装成成功率提升。

可以先用自己的话回答下面六问，不需要背源码全部细节：

1. Manifest 与 SKILL.md 为什么分开读？——前者用于选择，后者是选中后才需要的完整方法说明。
2. Skill 放在哪里？——内部 instructions；适配后为 system 消息，不追加到内部 message_history。
3. 写在 Skill 里的“允许编辑”为什么无效？——权限取决于程序 Policy/Approval，而不是模型看到的文本。
4. 恢复时 Skill 文件删除了怎么办？——用 Checkpoint 保存的渲染指令；普通恢复与预算评测支持范围要区分。
5. Skill 名称选对了，任务一定成功吗？——不一定；需要运行工具并由独立代码契约验收判断。
6. 为什么开启组成功也不能说 Skill 更好？——关闭组同样成功，且一个 Case 各一次不足以估计通用效果。

理解检查不是让用户同意助手的结论，而是能指出数据在哪里、哪层作决定、哪种失败会停止。
本阶段可结束的学习标准：能解释上述六问，并跟着第 4 节复述一轮“请求—工具—结果—下一请求”。
若有一项不清楚，下一小步只讲该项；确认后再设计 Memory 的最小需求，不一次实现整个记忆系统。

## 7. 本次收尾验证

2026-10-05 重新检查现有代码/测试、路由报告和真实结果汇总；没有改运行源码、Fixture、
协议、原始结果或历史失败记录，也没有调用模型。当前验证结果见产品化路线 S6n。
