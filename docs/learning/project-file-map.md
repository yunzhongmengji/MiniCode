# MiniCode 源码文件地图

核对日期：2026-09-14。本文用于区分“数据结构与接口”“真正执行动作的组件”以及“测试替身”。

## Core：运行协议和调度

| 文件 | 准确职责 | 容易混淆的边界 |
|---|---|---|
| `artifacts.py` | 定义文本 Artifact 的引用、存取接口和内存实现；内容用 SHA-256 标识 | 它是通用存储能力，不主动截断 ToolResult，也不决定何时存；当前 Dispatcher 在配置 Store 时把工具输出另存一份 |
| `checkpoints.py` | 定义可恢复的 `RunCheckpoint`、合法性检查、pending 调用计算、Store 接口及内存实现 | 保存时机由 QueryLoop 决定；Checkpoint 是恢复状态，不是事件日志 |
| `checkpoint_codec.py` | 在 `RunCheckpoint` 与带版本号的 JSON 文本之间转换 | 只编码/解码，不读写磁盘 |
| `context_profile.py` | 把一次 `ModelRequest` 分为指令、消息、工具定义、工具调用、工具结果，并比较 canonical 与模型投影的 UTF-8 字节和变化结果数 | 是测量工具，不执行压缩；byte 不等于模型 Token，变化结果数在当前引用 Projector 下才等于引用数 |
| `context_projection.py` | 定义“完整请求 → 本轮模型可见请求”的投影接口；可把较老、成功且超过阈值的 ToolResult 投影成含 call_id 的短 JSON 引用 | 默认仍使用 Identity Projector；短引用只改变模型视图，不修改完整历史或 Checkpoint |
| `context_retrieval.py` | 按 `call_id` 返回原始 ToolResult；`RunToolResultSource` 固定一个 run_id，并从该 Run 的最新 Checkpoint 查找 | 尚未暴露给模型；Source 的 Run 由宿主组装代码决定，不由模型参数决定 |
| `context_retention.py` | 把 ToolResult 分为 protected 和 eligible | 只分类候选，不修改请求；eligible 不等于一定安全删除 |
| `conversation.py` | 定义 `ConversationItem` 类型别名：`Message | ToolCall | ToolResult` | 不是一个有状态的对话历史类 |
| `events.py` | 定义事件种类、不可变事件、Ledger 接口和内存账本 | 其他组件调用它记录事实；它本身不恢复任务 |
| `file_checkpoint_store.py` | 把 Checkpoint 编码后原子写入文件，并按 Run ID 读取最新状态 | 解决跨进程状态保存，不保证工具副作用恰好执行一次 |
| `messages.py` | 定义普通 `Message` 和角色枚举 | 完整历史还包含结构化 ToolCall/ToolResult，不只包含 Message |
| `model.py` | 定义供应商无关的模型请求、响应、Usage、流事件、异常和 `Model` 接口 | 不是一个真实模型实现 |
| `model_metrics.py` | `RecordingModel` 包装另一个 Model，记录调用耗时、Usage、取消及已知模型异常分类 | 不是单纯数据类，也不是模型适配器 |
| `query_loop.py` | 核心状态机：构造请求、注入 Skill、投影上下文、调用模型、执行工具、累计预算、保存 Checkpoint并决定停止 | 它是核心编排器，但具体工具权限和执行由 Dispatcher 负责 |
| `replay.py` | 校验并只读汇总一段 Event 流，统计结果、模型调用、工具调用和 Checkpoint 次数 | 不读取 Checkpoint，不继续执行；真正恢复在 `QueryLoop.resume()` |
| `tool_approval.py` | 定义人工审批接口 | 审批结果仍由 Dispatcher 使用，接口本身不执行工具 |
| `tool_calls.py` | 定义 JSON 值、`ToolCall` 和 `ToolResult` 协议 | 文件名是复数；它定义格式，不调用工具 |
| `tool_policy.py` | 定义 allow/deny/ask 决策和配置化策略 | Policy 决定权限，Approval 只处理 ask 后的人类选择 |
| `tool_runtime.py` | 定义 QueryLoop 所依赖的最小执行接口：ToolCall → ToolResult | Dispatcher 和 ScriptedToolRuntime 都能实现这个接口 |

### Replay 与 Resume

```text
EventLedger 中的一串事件 ──> RunReplay ──> 只读复盘、统计

RunCheckpoint ──> QueryLoop.resume() ──> 找 pending ToolCall ──> 继续真实执行
```

Replay 回答“之前发生了什么”，Resume 回答“从保存的状态接着做什么”。

## Models：模型实现与供应商适配

| 文件 | 准确职责 |
|---|---|
| `dashscope.py` | 定义 DashScope 配置，从环境读取配置，并创建 `AsyncOpenAI` 客户端和 `OpenAICompatibleModel` |
| `openai_compatible.py` | 将 MiniCode 的请求、消息、工具定义和 ToolCall 转成 OpenAI SDK 格式，再把普通/流式响应和异常转回 MiniCode 协议 |
| `scripted.py` | 测试替身：记录请求，按队列返回预先写好的响应，不访问网络 |

`dashscope.py` 不只是配置文件，它还是 DashScope 的组装入口；真正大量的格式转换位于
`openai_compatible.py`。

## Skills：先选说明，再按需读正文

| 文件 | 准确职责 | 输出 |
|---|---|---|
| `manifest.py` | 定义 Skill 的轻量介绍卡：名称、描述、入口、标签 | `SkillManifest` |
| `catalog.py` | 按名称保存 Manifest，拒绝重复并保持注册顺序 | `SkillCatalog` |
| `discovery.py` | 扫描 Skill 根目录的 `manifest.json`，解析、校验目录名并装入 Catalog | 完整 Catalog |
| `retrieval.py` | 分词；先召回有共享关键词的 Manifest，再按共享词数排序 | 候选与 `RankedSkill` |
| `router.py` | 定义统一选择接口；关键词实现组合 Catalog、Retriever、Ranker，并应用 `max_skills` 截断 | 最终选中的有序 Manifest |
| `loader.py` | 只读取选中 Skill 的入口正文；限制目录边界、编码和 byte 数 | `LoadedSkill` |
| `context.py` | 调用 Router 和 Loader、记录选择/加载事件，并把多份正文稳定渲染为模型指令 | `SkillContext` |
| `evaluation.py` | 用带标签的 query/期望 Skill 名称测试 Router，计算精确匹配数、accuracy 和失败明细 | `SkillRoutingReport` |

完整链路：

```text
磁盘 manifest.json
    ↓ discovery
Catalog
    ↓ router（内部调用 retrieval 的召回与排序）
选中的 RankedSkill
    ↓ loader
LoadedSkill 正文
    ↓ context
合并后的 Skill 指令
    ↓ QueryLoop
ModelRequest.instructions
```

关键区别：

- Retrieval 负责“候选有哪些、候选如何打分”。
- Router 负责“最终选择哪些”，当前实现把检索、排序和数量上限组合起来。
- Loader 只在选定以后读正文，这就是懒加载。
- Skill Evaluation 目前只证明路由名字是否选对，不证明 Coding 任务因此做得更好。
- QueryLoop 已支持 Skill Provider，但默认 `build_coding_agent()` 尚未组装它，所以默认 CLI 还没有使用这套 Skill 链路。

## Tools：能力、中央调度与子进程边界

| 文件 | 准确职责 | 容易混淆的边界 |
|---|---|---|
| `base.py` | 定义可执行 Tool 接口和可安全反馈给模型的预期执行错误 | 不是具体父类实现；这里使用 Protocol |
| `create_file.py` | 在 Workspace 内安全创建新文件，拒绝覆盖 | 具体 Tool |
| `dispatcher.py` | 中央执行管道：查 Registry、校验参数、执行 Policy/Approval、记录事件、调用 Tool、生成相关联结果 | 它才是 QueryLoop 默认使用的 ToolRuntime |
| `edit_file.py` | 在已有文件中做受约束的精确替换 | 具体 Tool |
| `file_selection.py` | 保存多个观察工具共享的默认排除目录名 | 是常量模块，不是完整配置系统 |
| `git_diff.py` | 调用固定 Git 命令，返回工作区变更内容 | 展示差异，不替 Agent 判断修改一定正确 |
| `list_files.py` | 有上限地列出 Workspace 内文件 | 具体 Tool |
| `process.py` | 无 shell 启动受限子进程，处理环境白名单、stdout/stderr、超时、取消和输出上限 | 只被需要子进程的工具使用，目前主要是 `run_tests` 与 `git_diff`；不是所有 Tool 的执行器 |
| `read_file.py` | 有 byte 上限地读取工作区文件 | 具体 Tool |
| `read_tool_result.py` | 按 call_id 从当前 Run 的 Source 回读历史 ToolResult 原文，并限制 UTF-8 byte 数 | Tool 契约已实现但尚未注册；当前默认 Agent 看不到它 |
| `registry.py` | 保存 Tool 对象并按名字查找，同时导出 ToolSpec 列表 | Registry 不主动注册到 Dispatcher；组装代码先填 Registry，再把它交给 Dispatcher |
| `run_tests.py` | 构造受限 pytest 命令并交给 ProcessRunner | 具体 Tool，不直接实现通用 Shell |
| `schema.py` | 定义所有工具参数模型的严格 Pydantic 基类：禁止多余字段、冻结、严格类型 | 定义参数校验约束，不定义完整 ToolCall |
| `scripted.py` | 测试用 ToolRuntime，按队列返回预置 ToolResult并校验 call_id | 不执行真实 Tool |
| `search_text.py` | 在 Workspace 内有范围和数量限制地搜索文本 | 具体 Tool |
| `spec.py` | 定义给模型和 Registry 使用的工具介绍卡：名称、描述、参数类型 | 与 SkillManifest 类似都是元数据，但描述的是可执行能力 |

真实工具调用链：

```text
QueryLoop
  ↓ ToolCall
ToolDispatcher
  ↓ Registry 找 Tool
参数 Schema 校验
  ↓ Policy：allow / deny / ask
必要时 Approval
  ↓
具体 Tool.execute()
  ↓（只有 git_diff/run_tests 需要）
ProcessRunner
  ↓
ToolResult 返回 QueryLoop
```

## 外层：产品入口和工作区

| 文件 | 准确职责 |
|---|---|
| `cli.py` | 解析 `run/resume` 参数，读取环境配置，选择 Checkpoint 目录，组装运行依赖，启动异步任务，打印结果和可选 Trace |
| `coding_agent.py` | `CodingAgent` 是面向产品的薄封装；`build_coding_agent()` 是 composition root，默认注册七个工具并组装 Policy、Dispatcher 和 QueryLoop；显式设置上下文阈值时才同时组装短引用投影器与第八个回读工具 |
| `context_comparison.py` | 在临时工作区用同一个确定性条件模型运行关闭/开启两组上下文策略，汇总累计模型可见 bytes、投影节省、调用数和回读结果并输出 JSON | 是离线协议实验，不调用真实模型；bytes 不是 Token，最终答案相同只证明脚本条件一致 |
| `workspace.py` | 将文件解析、读取、创建、替换和遍历限制在一个根目录中，并实施文件/数量/路径边界 |

## Coding Agent 评测：另一套 evaluation

`skills/evaluation.py` 只评测 Skill 路由。仓库外层的 `evaluation_*.py` 评测完整 Coding Agent，二者不要混为一类。

| 文件 | 职责 |
|---|---|
| `evaluation_case.py` | 读取 `case.json`，定义 Ground Truth、允许修改、禁止动作、Trace 期望和预算 |
| `evaluation_prepare.py` | 只复制 Case 的初始 `workspace/` 到临时目录，并创建 Git 基线 |
| `evaluation_run.py` | 读取 `task.txt` 和预算，转成 `minicode run ... --trace` 参数并真正运行 Agent |
| `evaluation_trace.py` | 检查要求的工具是否成功、是否请求禁止工具、最后修改后是否重新测试 |
| `evaluation_result.py` | 解析 Trace、运行模型不可见的 `acceptance.py`、生成补丁，组合 outcome/operational/budget/trace 四维判定并保存哈希记录 |
| `evaluation_summary.py` | 重新校验结果工件哈希，汇总多个 `result.json`；不重新调用模型 |

从任务到记录的流程：

```text
Case：task.txt + case.json + workspace/ + 隐藏 acceptance.py
  ↓ evaluation_prepare
临时 Git 工作区
  ↓ evaluation_run
MiniCode 执行，产生 answer.txt 和 trace.txt
  ↓ evaluation_result
隐藏验收 + Trace 约束 + 预算 + 运行状态
  ↓
workspace.patch + result.json
  ↓ evaluation_summary
批次报告
```

为什么分成多层：

- Agent 不能看到 `acceptance.py`，否则可能针对答案投机。
- “最终代码正确”“程序正常结束”“没有超预算”“过程没有违规”是四个不同问题。
- Trace 证明过程事实，隐藏测试检查最终环境；单看模型最后说“完成了”不可信。
- Summary 只汇总已有记录，不能把四个 Case 的小样本外推成一般成功率。
