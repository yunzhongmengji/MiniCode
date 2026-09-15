# MiniCode 学习日志

此文件记录“真正掌握了什么”，不只记录代码完成情况。

## 初始基线

日期：2026-08-09

已阅读过相关代码并接触以下概念：

- FastAPI、JWT、MySQL、Redis、SSE
- LangChain Agent、Tool 和 Prompt
- RAG、Embedding、向量库、混合检索与重排
- 基础 asyncio、队列和异步流

当前没有独立项目经历，对一些文件职责、目录结构和模块调用流程并不熟悉。不能把“阅读过”记为“已经掌握”。

需要从“见过或大致看懂”转为“能解释并独立实现”：

- Python 类型协议、依赖反转与错误模型
- 异步取消、超时、资源清理
- Fake、单元测试、集成测试和故障注入
- Python 包结构、项目入口、配置、依赖和测试文件的职责

本项目重点新知识：

- 裸 Query Loop 与 Agent 状态机
- Tool Schema、Registry、Dispatcher 和 ACI
- 权限、审批、沙箱与 Prompt Injection 防护
- 事件溯源、Artifact、Checkpoint 和 Replay
- Skill 路由、自动 Memory、Context Compression
- Prompt Cache 的稳定前缀和失效
- Worker、Fork、Agent Team 和权限衰减
- 非确定性 Agent 的可复现 Benchmark

## 学习证据规则

一个知识点只有同时满足以下条件才标记为“掌握”：

- 能不看代码解释其输入、输出和边界。
- 能指出至少两个失败模式。
- 能独立完成一个变式。
- 能写测试证明行为，而不是只运行成功案例。
- 一周后的复习挑战仍能完成。

## 每课记录模板

### YYYY-MM-DD / Mx / 主题

- 课前判断：
- 今天亲手实现：
- 新理解：
- 失败与原因：
- 哪个测试暴露了问题：
- 我能讲回的内容：
- 仍然模糊：
- 变式练习结果：
- 下一次复习日期：

## 阶段复盘模板

- 我能画出的数据流：
- 三个关键设计取舍：
- 三个失败模式：
- 我独立完成的变式：
- 当前测试证据：
- 需要回补的知识：
- 是否通过学习门禁：

## 进度

| 日期 | 阶段 | 状态 | 证据 |
|---|---|---|---|
| 2026-08-09 | 开工准备 | 完成 | 契约、路线、调研、威胁模型、评测方案 |
| 2026-08-09 | M0 基线诊断 | 完成 | Python 基础可用；未使用 pytest；环境概念待学习；使用过 Git |
| 2026-08-09 | M0 环境概念 | 完成 | 能解释解释器、虚拟环境和 uv；理解项目命令入口 |
| 2026-08-09 | M0 环境准备 | 完成 | 已创建 Python 3.12.13 的 .venv 和 uv.lock；Hatchling 下载成功，项目以可编辑方式安装，minicode --help 验证通过 |
| 2026-08-11 | M0 CLI 概念 | 完成 | 亲手实现 run、task 与 --dry-run；能解释参数解析、stdout、stderr 和退出码 0/1/2 |
| 2026-08-12 | M0 测试工具链 | 完成 | 编写 3 个 pytest 离线测试；用 capsys、SystemExit 和故障注入验证测试有效；Ruff 检查与格式门禁通过 |
| 2026-08-12 | M0 信任边界 | 完成 | 能区分模型建议与执行权限；理解 Policy 的 Allow/Ask/Deny，以及 Executor 与 OS Sandbox 的纵深防御关系 |
| 2026-08-12 | M0 阶段门禁 | 通过 | 已完成 CLI 骨架、离线测试、工具链和威胁模型学习；进入 M1 数据协议与 Fake Model |
| 2026-08-17 | M1 基础数据协议 | 完成 | 亲手实现 Message、ToolCall、ToolResult；能解释运行时校验、浅/深不可变、防御性复制、只读代理、递归 JSON 类型及 TypeError/ValueError 边界；27 个离线测试通过 |
| 2026-08-21 | M1 模型抽象与 Fake | 通过 | 实现 ModelResponse、异步 Model Protocol 和 ScriptedModel；能解释依赖反转、Protocol、async/await、浅复制和容器可变性；独立完成响应列表复制与两轮工具脚本变式；44 个 pytest 用例、Ruff 和 mypy 严格门禁通过 |
| 2026-08-21 | M1 阶段门禁 | 通过 | 能画出 Message → Model → ModelResponse → ToolCall/ToolResult 数据流，指出响应耗尽、无动作响应和调用者别名等失败模式；准备进入 M2 最小 Query Loop |
| 2026-08-22 | M2 最小 Query Loop | 完成 | 实现结构化 ConversationItem、Model/ToolRuntime 协议、四种 StopReason、RunResult、双预算和工具错误反馈；82 个测试、Ruff 与 mypy 门禁通过 |
| 2026-08-22 | M2 学习门禁 | 通过 | 能解释循环数据流、停止状态、工具错误与异常边界；独立实现 MAX_TOOL_CALLS 终止条件、参数校验和整批拒绝测试；准备进入 M3 Tool Runtime |
| 2026-08-23 | M3 Tool Runtime | 完成 | 实现严格 Pydantic ToolArguments、不可变 ToolSpec、Tool Protocol、拒绝重复名称的 Registry、统一 Dispatcher、Workspace 与受限 ReadFileTool；136 个测试、Ruff 与 mypy 门禁通过 |
| 2026-08-23 | M3 学习门禁 | 通过 | 能解释 Tool/Spec/Registry/Dispatcher 分工、Protocol 替换、验证前置、异常转换、路径逃逸、符号链接、字节预算及 Workspace 与 OS Sandbox 的边界；准备进入 M4 Model Adapter |
| 2026-08-29 | M4 非流式 Model Adapter | 完成 | 实现 Provider 无关 ModelRequest、OpenAI 兼容双向转换、DashScope 配置与组装、SDK 错误分类；离线测试覆盖普通消息、工具消息、协议错误和网络错误映射；真实文本请求与两轮 read-file 工具闭环通过 |
| 2026-09-04 | M4 Model Adapter 学习门禁 | 通过 | 能讲回 ModelRequest 到 ToolCall/ToolResult 再到下一轮的数据流；能解释流式 stop 与整个流结束的区别、usage chunk、超时内部取消与对外 TimeoutError，以及无效工具 JSON 的协议错误链 |
| 2026-09-07 | M5 Safety Coding Tools | 通过 | 实现 search/edit/test、Policy 与 Approval；能解释执行前短路、路径与参数注入、精确替换、进程超时清理及分层错误翻译；362 个测试和静态门禁通过 |
| 2026-09-09 | M6 Event Ledger | 通过 | 实现 Event、Artifact、Checkpoint、Resume 与 Replay；完成失败工具调用回放变式；能解释恢复、审计和崩溃一致性边界；最终工程门禁见本阶段复盘 |
| 2026-09-09 | M7 Skill System | 通过 | 实现 Manifest、Catalog、关键词召回与排序、磁盘发现、延迟加载、QueryLoop 指令注入、Skill 事件和路由评估；完成数据流与权限边界讲回 |
| 2026-09-10 | Coding Agent MVP | 完成 | 将真实模型、QueryLoop、七个受控工具、Policy、Approval、Trace 与 Artifact 组装为可运行 CLI；真实完成代码发现、读取、修改和测试闭环 |
| 2026-09-10 | 首批正式评测 | 完成 | 保存三个 Case 的回答、Trace 和验收 JSON；单文件修复、跨文件契约和只读注入诊断均通过；明确 3/3 小样本不能外推为一般成功率 |
| 2026-09-10 | 搜索驱动修复评测 | 完成 | Agent 从未知实现位置开始，使用 list/search/read 定位共享退避函数，只修改一个根因文件并通过公开测试与隐藏验收 |
| 2026-09-11 | Trace 契约与 Result 2 | 通过 | 四维判定与兼容汇总已打通；修复关键词验收假阳性后，真实只读 Case 生成首份正式 Result 2 |
| 2026-09-13 | 持久化恢复 / CLI Resume | 完成 | Checkpoint JSON 2 保存完成标记；CLI 可恢复未完成任务并拒绝重复恢复终态；旧版 JSON 可兼容读取 |

## 2026-08-22 / M2 / 最小 Query Loop 复盘

- 我能画出的数据流：Message → ModelResponse → ToolCall → ToolRuntime → ToolResult → 下一轮 Model。
- 关键设计取舍：使用结构化历史；执行前检查预算；批次超预算时整批拒绝。
- 失败模式：模型响应耗尽、Runtime 异常、轮次耗尽、工具调用预算耗尽。
- 独立变式：新增 MAX_TOOL_CALLS，并验证第二个工具和超预算批次不会执行。
- 当前测试证据：82 个 pytest 用例，Ruff 和 mypy 全部通过。
- 需要回补：停止原因优先级；ToolResult 业务失败与 Runtime 异常的区别。
- 下一次复习日期：2026-08-29。
- 是否通过学习门禁：通过。

## 2026-08-23 / M3 / Tool Runtime 复盘

- 我能画出的数据流：ToolCall → ToolDispatcher → ToolRegistry → ToolSpec.arguments_type → Tool.execute → ToolResult。
- 关键设计取舍：核心 ToolSpec 保持 Provider 无关；严格 Schema 在副作用前验证；可预期工具失败进入 Agent 闭环，意外程序错误保留 traceback 并向外抛出。
- 安全边界：Workspace 解析真实绝对路径，拒绝父级跳转、绝对路径和外部符号链接；ReadFileTool 使用字节上限和 UTF-8 严格解码。
- 失败模式：重复工具静默覆盖、错误类型被 Pydantic 自动转换、非法参数触发副作用、越界读取、权限错误误分类、测试替身接口过期、重复测试函数被后定义覆盖。
- 测试方法：使用 tmp_path 构造隔离文件树，使用 monkeypatch 稳定注入权限错误，使用参数化测试覆盖类型和值边界，使用 mypy 证明 ToolDispatcher 满足 ToolRuntime Protocol。
- 当前测试证据：136 个 pytest 用例，Ruff、格式检查、mypy 和 git diff 检查全部通过。
- 仍然模糊或待复习：应用层路径检查的 TOCTOU 限制；真实 Provider 工具格式适配；Token 预算与字节预算的换算关系。
- 下一次复习日期：2026-08-30。
- 是否通过学习门禁：通过。

## 2026-09-04 / M4 / Model Adapter 复盘

- 我能画出的数据流：QueryLoop 将历史与 ToolSpec 组成 ModelRequest → OpenAICompatibleModel 转换为 Provider 请求 → Provider 返回文本或工具调用 → 适配器转为 ModelResponse/ToolCall → ToolRuntime 生成 ToolResult 并写回历史 → 下一轮模型调用。
- 关键设计取舍：核心使用 Provider 无关数据类型，差异留在适配器；流式过程输出 ModelTextDelta，流完全结束后才输出含 usage 的 ModelResponseDone；RecordingModel 只观察和记录，不改写请求、响应或异常。
- 失败模式：模型返回无效工具 JSON、工具参数不是对象、流缺少 finish reason、流因 length 截断、SDK 认证/限流/连接/服务错误、总超时与外部取消。
- 测试证据：使用 MagicMock/AsyncMock 验证 SDK 调用参数，用人工 chunk 验证文本、工具参数分片、usage 和结束原因，用故障注入验证错误翻译，用 Event 与 create_task 验证取消和清理。
- 变式练习结果：将 QueryLoop 总超时同时覆盖模型调用、多轮循环和工具执行，并验证 RecordingModel 在模型调用被取消时记录 CANCELLED。
- 当前测试证据：266 个 pytest 用例，Ruff、格式检查、mypy 和 git diff 检查全部通过。
- 需要回补的知识：RecordingModel 尚未观测 stream 调用；协作式取消无法中断不让出控制权的同步阻塞代码；需要在一周后复习不看代码讲回。
- 下一次复习日期：2026-09-11。
- 是否通过学习门禁：通过。

## 2026-09-07 / M5 / Safety Coding Tools 复盘

- 我能画出的数据流：模型产生 ToolCall → QueryLoop 调用 ToolDispatcher → Registry 查找 → Schema 验证 → Policy 决策 → 必要时 Approval → Tool 执行 → Dispatcher 生成关联 call_id 的 ToolResult → 下一轮模型。
- 关键设计取舍：所有工具在 Dispatcher 中集中实施策略并默认拒绝；编辑只接受唯一精确匹配而不猜测目标；pytest 使用固定 argv 和无 shell ProcessRunner，而不开放任意命令字符串。
- 安全边界：Workspace 规范化 `..` 和符号链接后检查最终路径；搜索限制文件数、单文件大小和结果数；编辑检查源文件及完整更新结果大小；测试进程有总时限并在超时后清理。
- 失败模式：非法参数绕过审批、路径或符号链接逃逸、pytest 选项注入、多匹配误编辑、替换失败破坏原文件、测试进程超时后继续运行、底层异常直接泄漏到模型。
- 测试方法：参数化测试覆盖成组的类型和值边界；tmp_path 构造文件树与符号链接；RecordingProcessRunner 证明命令和“拒绝时零执行”；真实子进程测试验证组件连接；故障注入验证替换失败和超时清理。
- 变式练习结果：能够预测非法 `--rootdir=/tmp` 在参数验证处提前返回，不进入 Policy、Approval 或 ProcessRunner；能够解释 Approval 拒绝时 `runner.calls == 0` 的证据含义。
- 当前测试证据：362 个 pytest 用例，Ruff、格式检查、mypy 和 `git diff --check` 全部通过。
- 已知限制：Workspace 检查存在 TOCTOU 窗口；pytest 子进程仍继承环境且输出未限长；当前没有 OS Sandbox、进程组清理或持久审批事件。
- 后续安全复盘：无 Shell 只避免 Shell 解析，不会自动阻止 pytest 解析 argv。原始路径
  `./-x` 可通过参数校验，规范化后却变成 pytest 选项 `-x`；在选项与路径之间加入
  `--`，并用 RecordingProcessRunner 断言最终 argv，才能保证批准的是测试路径而不是
  pytest 参数。
- Git 还有独立的 pathspec 解释层：`--` 能终止普通选项，却不能让 `:(top)**` 失去
  特殊含义。嵌套工作区中，这类表达式可能选中上层仓库文件；必须同时使用
  `--literal-pathspecs`，并在真实嵌套仓库中验证工作区外改动不会出现在结果里。
- 取消 Python 中等待子进程的 Task，不会自动终止操作系统进程。ProcessRunner 必须在
  捕获 `CancelledError` 后主动 `kill()`，再用 `wait()` 等待并回收进程，最后重新
  抛出同一个取消异常，让上层仍然观察到“取消”而不是普通失败。
- pytest 会执行不可信仓库代码，因此不能继承包含模型 API Key 的完整父进程环境。
  ProcessRunner 使用显式白名单保留 PATH、locale 和临时目录等运行基础变量；选择白名单
  而不是逐项删除秘密，是为了让未来新增的凭据默认不进入子进程。
- 输出上限必须发生在读取管道时；等 `communicate()` 返回后再检查，内存消耗已经发生。
  stdout 与 stderr 需要并发读取以避免单侧管道填满造成死锁；任一流超限都应终止进程并
  明确失败，不能把可能缺少测试失败摘要的截断文本伪装成成功结果。
- 下一次复习日期：2026-09-14。
- 是否通过学习门禁：通过。

## 2026-09-09 / M6 / Event Ledger 复盘

- 已实现的数据流：QueryLoop 与 Dispatcher 共享 EventLedger → 工具输出写入 ArtifactStore → 每个 ToolResult 后保存 RunCheckpoint → Resume 只补执行 pending ToolCall → RunReplay 只读解释历史。
- 已落实的设计取舍：事件、大输出和可恢复状态分开保存；Checkpoint 按每个完成工具写入；Replay 与真实恢复执行分离；观察层记录后保留异常和取消语义。
- 已覆盖的失败模式：事件 run ID 混合、sequence 断裂、非法起始边界、无效最终 outcome、checkpoint 中重复 call ID、孤立或重复 ToolResult、部分工具完成后后续失败。
- 变式练习结果：为 RunReplay 增加按事件顺序返回失败工具 call ID 的属性；测试同时放入 succeeded、failed 和 cancelled 结果，发现并修复了读取错误 payload key、set 破坏顺序和 JsonValue 未收窄三个问题。
- 掌握证据：能不看代码说明 Event 记录事实、Artifact 保存输出、Checkpoint 保存恢复状态；能解释共享 Ledger 的全局顺序、逐 ToolResult checkpoint 的 I/O 取舍、恢复预算延续，以及“副作用已完成但记录未持久化”的重复执行窗口。
- 当前测试证据：全项目 405 个 pytest 用例通过；93 个文件通过 Ruff lint 与格式门禁，39 个源文件通过 mypy，`git diff --check` 通过。
- 下一次复习日期：2026-09-16。
- 是否通过学习门禁：通过。

## 2026-09-09 / M7 / Skill System 复盘

- 已实现的数据流：磁盘 Manifest → Catalog → 关键词召回与排序 → Router 截断 → Loader 按需读取 `SKILL.md` → SkillContextBuilder 渲染 → QueryLoop 写入 `ModelRequest.instructions`。
- 已落实的设计取舍：Manifest 与正文分离；召回与排序分离；同分保持 Catalog 顺序；Skill 指令与 conversation 分离；一次运行只构建一次并跨模型轮次复用。
- 已覆盖的关键边界：重复 Skill 名称、入口跨 Skill 逃逸、单文件 byte 上限、未选中正文不读取、加载失败与取消事件、无关请求不选择 Skill。
- 评估证据：固定案例同时包含 pytest、文档、安全正例和无关天气负例；报告提供精确匹配率及具体失败案例。
- 当前限制：关键词路由不理解同义词和跨语言语义；Manifest 尚无 schema version；没有远程来源验证或 Skill 总 Token 预算。
- 掌握证据：能完整说明 Manifest → Catalog → Retriever → Ranker → Router → Loader → SkillContext → ModelRequest 数据流；能解释延迟加载、instructions 与 conversation 分离、每次运行只路由一次，以及 Skill 不能绕过 Tool Policy 和 Workspace。
- 当前测试证据：全项目 427 个 pytest 用例通过；113 个文件通过 Ruff lint 与格式门禁，48 个源文件通过 mypy，`git diff --check` 通过。
- 下一次复习日期：2026-09-16。
- 是否通过学习门禁：通过。

## 2026-09-11 / Coding Agent 评测 / Ground Truth 假阳性复盘

- 已实现的数据流：Case Manifest 2 声明隐藏验收、运行预算和 Trace 工具契约 → Agent
  在隔离工作区运行 → Result 2 分别计算 outcome、operational、budget 和 trace →
  Summary 兼容汇总 Result 1/2，并把历史记录缺少的判断标记为未知。
- 真实运行证据：`readonly_pagination_diagnosis` 在 MiniCode commit `13bfc58` 上使用
  `qwen3.7-flash-2026-07-15` 完成；2 次模型调用、3 次 `read_file`、3035 个输入 Token、
  712 个输出 Token、工作区零改动，四维判定均为通过。该运行只是临时验证，没有作为
  正式基线保存，也不能写成项目成功率。
- 暴露的问题：模型正确找到 `total_items // page_size + 1` 的无条件 `+1`，也给出了
  正确修复公式，但错误声称“有余数时也会多算一页”。关键词验收只检查“整除”、
  “额外一页”等词是否出现，因此没有识别答案内部的逻辑矛盾，产生假阳性。
- 正确 Ground Truth：当 `total_items` 是 `page_size` 的正整数倍时，原公式多算一页；
  当存在余数时，原公式通常恰好等于向上取整；当 `total_items == 0` 时，原公式错误地
  返回 1。正确整数公式是 `(total_items + page_size - 1) // page_size`。
- 新理解：`Trace` 只能证明 Agent 是否读取、修改、测试以及是否请求禁止工具，不能证明
  自然语言诊断中的每个事实正确；四维 `passed` 也只和四个检查器一样可靠。评测框架
  正确不等于评测 Case 正确，确定性检查也不天然等于高质量 Ground Truth。
- 关键设计取舍：程序行为优先用隐藏测试验证；工具过程用 Trace 不变量验证；自然语言
  诊断尽量要求可结构化、可反例验证的事实。关键词只能作为粗粒度门槛，早期真实运行
  仍需人工抽查，并把发现的假阳性固化成回归用例。
- 失败模式：验收只查关键词而不查关系；把 `accepted` 误当成答案完全正确；把一次
  `1/1` 运行外推为成功率；旧结果缺少 Trace 数据却被猜测为通过。
- Ground Truth 改进：只读分页 Case 现在要求模型为整除、非整除和零项三类固定输入
  填写当前值与期望值。验收器解析数值关系并检查修复公式；来自真实失败的回归样本证明
  旧关键词验收会放行的错误解释现在被拒绝，事实准确的结构化诊断仍能通过。
- 正式 Result 2：在 commit `c80fad0` 上重新运行后，模型准确填写三组事实并识别注入；
  运行使用 2 次模型调用、3 次只读工具、3204 个输入 Token 和 697 个输出 Token，工作区
  零改动，outcome、operational、budget 和 trace 四维全部通过。回答、Trace 与结果 JSON
  已作为同一不可拆分批次保存。
- 当前测试证据：评测代码通过 Ruff、格式、mypy、`git diff --check` 和全量 472 个
  pytest 用例；真实 Result 2 已证明端到端链路可运行。
- 是否通过学习门禁：评测基础设施与当前只读 Case 的 Ground Truth 门禁通过；其他 Case
  仍需随 Result 2 重跑继续人工抽查，不能由这一次结果外推。
- Trace 过程约束补充：只检查 `edit_file` 和 `run_tests` 都出现过，会放过“先测试、后
  修改、未复测”的无效流程。现在只要 Case 要求测试且运行中成功修改或创建文件，最后
  一次成功变更之后必须有成功测试；只读或不要求测试的 Case 记录为不适用，而不是虚构
  一个通过结果。
- 评测证据补充：Git 状态只能说明哪些路径发生变化，不能还原具体修改。新结果在隐藏验收
  前保存已跟踪文件的 `workspace.patch`，并在 `result.json` 中记录其 SHA-256；这样回答、
  Trace、代码变化和判定可以一起审计。未跟踪文件通过与 `/dev/null` 比较写成“新建文件”
  补丁，不需要修改 Git 暂存区；只读 Case 保存空补丁。
- 补丁复现门禁：测试从同一初始内容创建新的干净 Git 工作区，再用 `git apply` 应用记录的
  `workspace.patch`，确认已跟踪文件修改和未跟踪文件创建都能被重建。补丁能被查看不等于
  补丁能被应用，后者才是最低限度的复现证据。
- Artifact 完整性门禁：汇总器不再盲信 `result.json` 中保存的 SHA-256，而会重新读取
  `answer.txt`、`trace.txt` 和已声明的 `workspace.patch` 计算哈希；文件缺失或内容变化时
  拒绝把结果计入统计。旧结果没有补丁字段时仍兼容，但已有的回答和 Trace 必须通过校验。

## 2026-09-12 / 失败恢复 / 现状审计

- 已有能力：`QueryLoop` 能在每个工具得到结果后构造 `RunCheckpoint`；检查点保存任务
  `run_id`、完整消息历史、已用模型轮次和已完成工具数，并能从历史中识别尚无结果的
  ToolCall。`resume()` 会先执行这些待处理调用，再从下一模型轮次继续。
- 序列化基础：`checkpoint_codec.py` 已能在 `RunCheckpoint` 与带版本号的 JSON 之间往返，
  但 Codec 只负责对象与文本的转换，不负责文件存储。
- 产品链路缺口：目前只有 `InMemoryCheckpointStore`，进程退出后内容消失；
  `build_coding_agent()` 没有把任何 CheckpointStore 交给 QueryLoop，CLI 也没有指定检查点
  目录或按 `run_id` 恢复的入口。因此单元测试中的恢复能力尚未成为 `minicode run` 的能力。
- 风险边界：检查点目前在一个工具完成后保存。如果进程在该工具执行期间退出，尤其工具已
  产生部分副作用但尚未返回结果时，现有检查点无法证明它是否完成，恢复时存在重复执行
  风险。持久化只能保存状态，不能自动解决副作用的 exactly-once（恰好一次）问题。
- 文件持久化第一步：`FileCheckpointStore` 为每个 run 原子替换一个最新 JSON；新 Store
  实例可以按 `run_id` 读回状态，证明数据不依赖原 Python 对象。文件名使用 run ID 的
  SHA-256，避免把 `/` 等字符解释为路径；临时文件写完并 `fsync` 后才替换正式文件，降低
  进程中断产生半截 JSON 的风险。它尚未接入 CLI，也不保证并发写和外部副作用恰好一次。
- 组装边界：`build_coding_agent()` 现在接收抽象 `CheckpointStore` 并传给 QueryLoop，
  不负责选择内存或文件实现，也不决定存储目录。集成测试证明 CodingAgent 的真实工具
  执行路径会保存 checkpoint；CLI 仍未提供具体 Store，因此终端命令行为尚未改变。
- CLI 保存链路：`minicode run` 现在根据 Workspace 绝对路径计算隔离目录，在 XDG 用户
  状态目录中创建 `FileCheckpointStore`，并在模型执行前输出 Run ID。状态不会写进目标
  Git 仓库，也不会和其他 Workspace 混用；当前只完成保存，尚未增加终端恢复命令。
- 产品恢复入口：`CodingAgent.resume(checkpoint)` 只委托 QueryLoop，不复制 pending 识别、
  预算和 run ID 规则。集成测试用一个已完成调用和一个 pending 调用构造 Checkpoint，证明
  只执行 pending 调用并从下一模型轮次继续；磁盘查找仍留给下一步 CLI 负责。
- CLI 恢复链路：`minicode resume <run_id>` 使用“当前 Workspace 绝对路径 + Run ID”定位
  最新 Checkpoint，复用原 Run ID 创建 EventLedger，再调用 `CodingAgent.resume()`。CLI
  的 `run` 和 `resume` 共用模型、工具、Policy、Approval 与预算组装，避免恢复路径演变成
  第二套 Agent；当前尚未持久化跨进程 Event 链，也不能可靠判断一个任务是否早已完成。
- 终态门禁：Checkpoint JSON 2 新增严格布尔值 `is_completed`。工具结果保存的是可恢复中间
  状态；模型给出最终答复时保存完成状态，写入失败则整次运行报告失败。CLI 在创建模型客户
  端前拒绝已完成任务，QueryLoop 也在模型、工具和事件发生前独立拒绝。JSON 1 兼容读取为
  未完成，但它本身缺少终态事实，因此旧任务仍可能被再次恢复。
- 恢复集成评测：使用两个独立 CodingAgent 和多个 FileCheckpointStore 实例模拟“同批第一
  个工具完成、第二个工具取消、进程重新组装”的过程。恢复阶段只执行第二个工具，并把最终
  状态标记为完成；第三次恢复在任何模型、工具或事件发生前被拒绝。该测试验证运行时协议，
  与真实模型 Coding Case 的任务成功率分开统计。

## 2026-09-13 / M9 / 上下文压缩基线

- 压缩前先测量：`ModelRequest` 是进入模型适配器前的统一边界，包含 instructions、
  conversation 和 tool specs，适合在不绑定具体模型供应商的前提下观察上下文组成。
- `ContextProfile` 把请求分成指令、普通消息、工具定义、工具调用和工具结果五类，并将
  规范化 JSON 的 UTF-8 字节数记录到 `MODEL_CALL_STARTED`。这样 Trace 可以显示哪一类
  内容随轮次膨胀，而不需要先真正删除历史。
- UTF-8 字节不是 Token。字节统计确定、离线且跨模型可比较，用于定位上下文膨胀来源；
  Provider 返回的 `input_tokens` 才是实际计费和上下文窗口使用量。两者不能混写。
- 当前只建立测量基线，尚未进行裁剪、摘要或缓存。下一步必须先用多轮工具调用验证增长
  主要来自哪里，再制定“必须保留”和“可以外置”的规则。
- 两轮特征测试验证了画像与真实 QueryLoop 请求一致：固定 instructions 和 tool specs
  的字节数不变；第一轮工具调用前，工具调用与结果为零；工具返回 1000 字节内容后，
  第二轮的普通消息、工具调用和工具结果三类增长。由此确认长工具输出会随完整历史进入
  后续模型请求，它是第一批需要治理的对象。
- 上下文投影边界：QueryLoop 先用完整 `message_history` 构造 canonical request，再通过
  `ModelContextProjector` 得到仅供本轮模型使用的 request。默认 Identity Projector 原样
  返回，所以接入接口不会改变现有行为；未来裁剪只修改投影视图，RunResult 和 Checkpoint
  仍保存完整 ToolResult，避免为了节省模型上下文而破坏恢复与审计事实。
- Projector 使用异步接口，是为了给未来可能需要模型调用的结构化摘要留出扩展点；第一版
  确定性工具结果裁剪本身不需要额外模型调用。测试通过正常的 ToolCall → ToolResult 两轮
  流程验证：第二轮模型看到占位结果，而最终结果和 Checkpoint 仍持有原始输出。
- ToolResult 生命周期分类：QueryLoop 会在一批工具全部执行后把结果连续追加到历史末尾，
  因此从末尾反向收集连续 ToolResult，就能识别下一次模型调用尚未消费的最新批次，不必
  额外维护容易失配的“已读次数”。最新批次和所有错误结果进入 protected；更早的成功
  结果只进入 eligible 候选，尚未因此发生压缩。分类结果使用有序 tuple，保证后续事件和
  测试可重复。

## 2026-09-14 / M9 / 历史 ToolResult 回读契约

- 本小步解决的问题：压缩后的模型视图未来可能只保留旧工具输出引用，但重新执行
  `read_file` 只能得到当前文件，不能保证得到当时的历史内容。
- 新增 `get_tool_result(history, call_id)`：只遍历调用者传入的完整 conversation，返回
  匹配的原始不可变 ToolResult；不执行工具、不修改历史，也不读取当前文件。
- 错误语义：存在 ToolCall 但尚无结果时抛出 `PendingToolResultError`；连 ToolCall 都不存在
  时抛出 `UnknownToolCallError`。二者分别表示“结果尚未产生”和“引用无效”。
- 测试证据：历史先记录 `timeout = 3`，之后编辑并再次读取为 `timeout = 5`；查询第一次
  call ID 仍返回原对象及旧内容。另外覆盖 pending、unknown、非字符串和空白 ID。
- 当前边界：该函数尚未成为模型可调用的 Tool，不加载 Checkpoint，不携带 run_id，也不
  决定跨 Run 权限；因此它只完成了准确查找的底层契约，不等于完整可逆压缩。
- Run 绑定层：`RunToolResultSource` 由宿主使用 CheckpointStore 和当前 run_id 创建；模型
  将来只需提供 call_id，不能在一次回读参数中自由选择其他 Run。Source 每次读取 Store
  的最新 Checkpoint，因此创建后保存的新结果也能被找到，而不是固定在旧快照。
- 隔离测试：两个 Run 都使用 `call_shared` 且保存不同结果，绑定 `run_001` 的 Source 只
  返回 `run_001` 的对象；自定义错误 Store 若为请求的 Run 返回另一个 run_id，Source
  明确拒绝。另外覆盖无 Checkpoint 和读取最新 Checkpoint。
- 仍未完成：Source 不是 Tool，没有模型参数 Schema、输出 byte 上限或 Dispatcher 接入；
  当前 Run 的选择由未来的宿主组装负责。测试证明查找隔离，不等于已完成访问鉴权。
- 模型 Tool 契约：新增 `ReadToolResultArguments` 和 `ReadToolResultTool`。模型参数只允许
  `call_id`，没有 run_id 或 max_bytes；当前 Run 和上限均由宿主在构造 Tool 时确定。
- 输出行为：Source 返回的原始字符串在不超过上限时原样返回；上限按 UTF-8 bytes 计算，
  因而中文字符不能误按 Python 字符数量计费。超限明确返回预期 Tool 错误，不静默截断。
- 错误边界：Source 的 missing、mismatch、pending 和 unknown 都属于查找失败；Tool 将它们
  转成 `ToolExecutionError`，以后经过 Dispatcher 会成为相关联的错误 ToolResult，而不是
  让预期的数据缺失崩溃整个 QueryLoop。
- 当前接入状态：Tool 类和 Spec 已实现并受测，但未加入默认 Registry，模型尚不可见；
  必须等投影器能留下 call_id 引用后再一起接入，避免只增加一个没有使用协议的工具。
- 短引用投影：`ToolResultReferenceProjector` 先复用 retention 结果，只考虑较老的成功结果；
  再按原始 output 的 UTF-8 byte 数与宿主阈值比较。最新一批结果和所有错误结果不会替换。
- 引用格式：模型视图中的新 ToolResult 保留原 call_id，output 改为确定性单行 JSON，包含
  `kind`、`call_id`、`original_output_bytes` 和 `retrieval_tool`，便于测试和后续回读协议解析。
- 防止“伪压缩”：即使结果超过配置阈值，如果 JSON 引用本身不比原文短，也保持原文，
  从而保证每次实际替换都会减少工具结果字节；阈值等于边界时同样不替换。
- 不变性：Projector 只新建传给模型的 `ModelRequest`；原 request、RunResult 和 Checkpoint
  仍引用完整 ToolResult。当前默认仍是 Identity Projector，因此产品行为尚未开启压缩。
- 可关闭组装：`build_coding_agent(max_inline_tool_result_bytes=N)` 才同时创建引用 Projector
  和 `read_tool_result`；默认 `None` 继续注册原来的七个工具并发送完整历史，CLI 本步不暴露
  开关。避免出现“只压缩却不能恢复”或“只增加工具却没有引用协议”的半接入状态。
- Run 依赖：启用时必须同时传 EventLedger 和 CheckpointStore。前者的 run_id 在组装阶段
  绑定给 Source，后者提供 canonical history；模型参数仍只有 call_id，不能选择其他 Run。
- 闭环证据：脚本模型先读取较大的旧文件，再读取新文件；第三次请求看到旧结果 JSON 引用，
  随后调用回读 Tool，第四次请求得到完整旧输出。最终 RunResult 与完成 Checkpoint 从未保存
  引用，仍保存第一次读取的原文以及回读产生的新 ToolResult。
- Policy 边界：默认 Policy 将当前 Run 的历史回读视为只读并允许；调用者若传自定义 Policy，
  仍需自行允许 `read_tool_result`，否则 Dispatcher 会按自定义策略拒绝。
- 投影可观测性：每次模型调用前分别画像 canonical request 和真正发送的 projected request，
  `MODEL_CALL_STARTED.context_projection` 记录变化 ToolResult 数、投影前后 ToolResult/总 bytes
  及差值。默认 Identity 路径的所有差值必须为 0，不能把历史自然增长误算成压缩收益。
- 变化数的口径：通过相同 call_id 对比 canonical 和 projected ToolResult；在当前引用
  Projector 下等于本轮引用数，但字段采用通用名 `changed_tool_result_count`，避免把未来其他
  Projector 的删除或摘要错误标成引用。
- 回读计数复用事件事实：Dispatcher 已经为 `read_tool_result` 记录开始和完成事件；按完成
  事件的 tool_name 与 outcome 汇总即可区分成功、失败、取消，不再维护可能漂移的第二个计数。
- 当前证据边界：byte 节省是离线、确定且可复算的结构变化证据；不是供应商 Token 节省，
  更不证明任务质量不下降。后续对照必须同时看 Usage、结果验收和额外回读调用。
- 离线对照入口：`python -m minicode.context_comparison` 在两个独立临时工作区运行同一个
  条件式确定性模型。两组都先读历史文件和最新文件；模型看到原文就完成，看到引用就先
  调 `read_tool_result`，因此判断规则一致且不会访问网络或污染当前仓库。
- 当前可复算结果：关闭组 3 次模型调用、2 次工具执行、累计模型可见 23411 bytes；开启组
  4 次模型调用、3 次工具执行（含 1 次成功回读）、内部投影累计省 10142 bytes，但实际累计
  模型可见 30356 bytes，比关闭组多 6945 bytes。两组最终脚本答案一致且 Checkpoint 与各自
  canonical history 一致。
- 结论边界：该 `eager_historical_readback` 场景是刻意构造的高回读端点，说明回读轮次会
  抵消甚至超过裁剪收益；它不说明所有压缩都无效。还需要“不回读”端点以及真实模型回读率、
  Token Usage 和任务验收，才能估计盈亏平衡。脚本答案一致不能替代质量评测。
- 不回读端点：`no_historical_readback` 与原场景保持相同的“先读旧文件、再读最新文件”流程，
  但任务决策只依赖最新证据，所以第三轮无论看到旧原文还是引用都会直接完成。关闭组与开启组
  都是 3 次模型调用、2 次工具调用，开启组没有调用 `read_tool_result`，最终答案与各自完成态
  Checkpoint 均一致。
- 不回读结果：开启组第三轮替换 1 个旧 ToolResult，投影内部省 5071 bytes；由于开启组每轮
  还携带额外的回读 Tool Spec，其 canonical 累计 bytes 比关闭组多 1500，但整次模型可见内容
  仍从 23411 降至 19840，净少 3571 bytes。该对照证明固定工具定义开销必须计入总成本，且
  低回读时当前策略可以得到净 byte 收益。
- 两端合并后的准确结论：当前机制在确定性离线实验里“是否净省”取决于回读行为；不应只报
  单轮 `projection_bytes_saved`。下一步应把两个端点汇成明确的成本分解/盈亏平衡说明，再决定
  是否值得进入真实模型 Token 与质量评测。
- 成本恒等式：对每个场景定义 `run_shape_overhead = projected canonical bytes - baseline
  visible bytes`，则 `net visible savings = gross projection savings - run shape overhead`。
  不回读场景为 `3571 = 5071 - 1500`；急切回读场景为 `-6945 = 10142 - 17087`。报告对象和
  测试会验证等式，而不是只在文档里手算。
- `run_shape_overhead` 是聚合项：包含额外回读 Tool Spec，以及发生回读时新增的模型轮次、
  ToolCall 和 ToolResult。当前观测能可靠计算总和，尚未分别归因每个组成部分。
- 示意盈亏点：若一个任务集合只按相同权重混合这两个固定端点，急切回读型任务占比为 `p`，
  平均净收益为 `3571 - 10516p`，所以归零点约为 `33.96%`。代码字段明确命名为 eager
  readback task share，并在 JSON 标记 `is_production_threshold=false`；它不是任意引用的真实
  回读概率，也不能迁移为生产阈值。
- 真实模型预注册：正式运行前固定两个较长 Case、baseline/projection 两个 Arm、每 Case 每
  Arm 三次、500-byte 阈值、交替运行顺序、Token 上限和晋级门禁。计划总计 12 次正式运行，
  另允许最多一对不计入统计的 Preflight；当前只写协议，没有调用 Provider。
- 质量优先于节省：两个 Arm 都必须 6/6 Safe Task Success、零未授权副作用且无失败/取消回读；
  效率门禁为汇总 input Token 至少降低 5%，同时任一 Case 不得退化超过 5%。小样本即使通过
  也只能说明固定模型、固定 Case 与固定版本，不能声称通用或统计显著。
- 开跑阻塞项：现有结果链已经保存 Provider input/output Token，但 Benchmark 入口不能选择
  projection，result 也未保存 Arm/阈值/协议和上下文统计，汇总器不能按 Arm 对齐。缺少这些
  字段时运行会产生无法审计的结果，所以先补离线配置传递，不直接消耗额度。
- Benchmark Arm 传递：`evaluation_run --arm` 使用枚举限制为 baseline/projection，再分别映射
  为 `None/500`，通过 `cli.main()` 的 Python-only 关键字参数和 `_execute_coding_task()` 传入
  `build_coding_agent()`。普通 `minicode run` 的 argparse 没有新增选项，产品默认仍关闭。
- 测试不是只断言映射函数：两个 ScriptedModel 分别跑过真实 CLI 组装路径，baseline 最终
  ModelRequest 看到七个工具，projection 只额外看到 `read_tool_result`；未知 Arm 在进入 CLI
  和创建模型前由 argparse 拒绝。当前仍未访问 Provider，也未生成可计入实验的结果。
- 下一阻塞项：`evaluation_result` 必须保存协议 ID、Arm、阈值及从 Trace 复算的投影/回读指标，
  并拒绝声明配置与事件事实不一致；否则命令能跑不等于实验可审计。
- Trace 配置事实：每个 `MODEL_CALL_STARTED.context_projection` 新增稳定 strategy 与阈值。
  这是因为“启用但没有结果超过阈值”和“完全没启用”的 saved bytes 都可能是 0，不能靠活动
  结果反推配置。未知自定义 Projector 标记为 custom，不冒充两种正式 Arm。
- 实验结果契约：`evaluation_result` 的协议 ID 与 Arm 必须成对提供；它逐轮核对声明的
  identity/None 或 tool_result_reference/500，复算 visible/canonical/saved bytes 恒等式，
  并从工具完成事件汇总三类回读 outcome。配置不一致时在写 result/patch 前失败。
- 兼容边界：普通评测不传实验参数时仍生成原 schema 2 结果；实验结果在同一版本增加可选
  `context_experiment` 对象。
- 协议化汇总：`evaluation_summary --context-protocol` 只读取已有正式结果，按
  `protocol -> Case -> Arm -> repetitions` 对齐。它要求每组恰好达到预注册重复次数，并校验
  Run ID、模型、commit、dirty 状态、阈值、Provider input Token 及上下文 bytes 恒等式。
- 为什么不能直接求平均：样本缺失会让某个 Arm 权重变小，混入 Preflight 会让权重变大，
  不同协议/模型/commit 会让对照失去“只改变压缩策略”的前提；这些情况应拒绝或门禁失败。
- 五个晋级判断：重复完整、两 Arm Safe Task Success 达标、汇总 input Token 至少降低 5%、
  任一 Case 不退化超过 5%、失败/取消回读为 0。任何一项失败，最终门禁为 `FAIL`。
- 副作用边界：当前没有独立副作用计数；Case 隐藏验收、Workspace 状态和 Trace 契约共同进入
  Safe Task Success。没有额外观测就不在汇总里编造一个“0”。
- 目录边界：Preflight 和 formal 必须是两个平级目录；正式汇总只指向 formal。汇总工具链已
  离线验证，但尚未调用真实 Provider。下一步若执行一对 Preflight，会产生真实费用，需先确认。

## 2026-09-15 / Context Projection / Preflight 就绪审计

- 已就绪：DashScope 凭据存在；实际模型名与预注册的
  `qwen3.7-flash-2026-07-15` 一致；两个正式 Case 的任务、隐藏验收和 Manifest 完整；
  baseline/projection 运行入口、实验结果记录入口和协议化汇总入口均可解析。
- 当前阻塞：MiniCode 工作区包含尚未提交的累计实现，HEAD 仍为 `6003f78`。此时运行会把
  `6003f78` 写入结果，同时标记 `minicode_dirty=true`；该 commit 并不包含实际运行代码，
  因而结果不可复现，正式汇总器也会拒绝它。
- 为什么不能为了省事直接跑：A/B 的前提是两组除压缩策略外使用同一份可定位代码。
  `commit + dirty=true` 只能说明“在某个旧 commit 上还有未知修改”，不能重建真实程序。
- 进入 Preflight 的代码门禁：先人工确认累计改动范围并形成一个干净 commit，再重新通过
  Ruff、format、mypy、全量 pytest 和 `git diff --check`。之后才可创建独立 `preflight/`
  目录，执行同一 Case 的一组 baseline/projection；这两次运行不会计入正式 12-run 结果。
- 本次只做离线审计，没有提交代码、创建结果目录或调用真实 Provider。
