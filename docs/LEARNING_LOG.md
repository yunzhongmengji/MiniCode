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

## 2026-09-15 / Context Projection / 真实模型 Preflight

- Preflight 含义：正式实验前的真实系统彩排。它会调用真实 Provider 并完整验证运行、审批、
  Trace、隐藏验收、Result 和 Artifact，但样本不进入正式统计，也不用于证明总体效果。
- 固定对照：在 MiniCode `007d4b9` 上，对 `multi_file_inventory_contract` 分别运行一次
  baseline 和 projection；两次使用独立且相同的初始 Workspace、相同模型和预算。
- 质量结果：两组均为 5 次模型调用、7 次工具执行，Safe Task Success 通过；最终 Patch 哈希
  相同，只修改允许的 `inventory.py` 与 `report.py`，且最后一次修改后测试成功。
- 投影确实命中：projection 在第 4、5 轮各将一个旧 ToolResult 替换为引用，每轮省 411 bytes，
  合计 822 bytes；模型没有调用 `read_tool_result`，因此三类回读错误均为 0。
- 端到端成本结果：baseline 为 8559 input / 419 output Token；projection 为 9047 input /
  422 output Token。projection input 增加 488（约 5.7%），没有得到净 Token 收益。
- 原因解释：projection 的 canonical bytes 比 baseline 多 2486，主要来自五轮都要携带的额外
  回读 Tool Spec；扣除 822-byte 内部压缩后，模型可见 bytes 仍多 1664。局部压缩不等于整次
  运行更省，必须把工具定义和可能增加的轮次一并计算。
- 预算与证据：两次合计 17606 input / 841 output Token，低于 30000/5000 上限。原始 Answer、
  Trace、Patch、Result 和协议快照保存在独立 preflight 批次；正式 12-run 实验尚未开始。
- Preflight 发现的证据缺陷：`ConsoleToolApprover` 的 `input(prompt)` 把人工审批提示写到
  stdout，而评测把 stdout 保存为 `answer.txt`，导致 Answer 混入三段审批文本。隐藏验收、
  Trace 和 Token 未因此改变，原始工件也不能事后清洗；但正式实验必须先将提示分流到 stderr
  并用回归测试证明 Answer 只含模型最终回复。
- 输出分流修复：审批器先用 `print(..., file=sys.stderr, flush=True)` 展示完整调用，再在线程中
  调用无参数 `input()` 读取 stdin。`input_reader` 的测试接口也改为零参数，从类型上避免读取
  函数再次负责展示提示。新测试断言 stdout 为空且 stderr 包含两次完整审批；原 CLI 测试断言
  stdout 只有最终模型回答、Run ID 与 Trace 在 stderr。原始 Preflight Answer 保留污染事实，
  不通过事后清洗伪造当时证据。

## 2026-09-15 / Context Projection / 自适应净收益门槛

- 问题来源：真实 Preflight 中，每轮约 500 bytes 的 `read_tool_result` Tool Spec 从第一轮起
  重复发送，而两个实际投影轮次各只节省 411 bytes，导致工具结果缩短 822 bytes 的同时，
  整次运行模型可见内容仍净增加 1664 bytes，Provider input Token 增加约 5.7%。
- 新决策规则：Projector 先按原 retention 和单结果阈值生成候选引用，再用 Trace 相同的规范化
  JSON 口径比较完整请求。只有 `工具结果毛节省 - 新增回读 Tool Spec bytes > 0` 才采用候选；
  等于 0 也不投影，因为没有实际上下文收益。
- 工具可见性与执行能力分离：`read_tool_result` 仍注册到 Dispatcher，保证引用出现后能够执行；
  QueryLoop 的基础 Tool Specs 不再包含它。Projector 只有采用引用时才把该 Spec 加进本轮
  ModelRequest，所以前置轮次和小结果任务不再无条件付费。
- 状态边界不变：投影只改本轮 ModelRequest；完整 ToolResult 仍保留在 message history 与
  Checkpoint。模型看到引用后仍按 call_id 从绑定当前 Run 的 Checkpoint 回读，恢复安全链路
  没有被收益门槛绕过。
- 新测量口径：`tool_result_bytes_saved` 是引用替换得到的毛节省；`projection_bytes_saved` 是
  再扣除本轮条件式 Tool Spec 后，canonical request 到模型可见 request 的净节省。离线报告
  schema 升至 2，并把条件式工具开销与额外运行形状开销分列，防止再次混淆局部和端到端收益。
- 离线结果：不回读端点为 `4571 = 5071 - 500 - 0`；急切回读端点为
  `-5945 = 10142 - 1000 - 15087`。前者比始终暴露工具时多省 1000 bytes，后者少亏
  1000 bytes；但额外回读轮次依然可能压过局部收益。
- 实验纪律：v1 Preflight 是始终携带回读 Tool Spec 的旧策略证据，原始结果不追溯修改。
  自适应门槛来自观察 Preflight 后的改进，因此 v1 不再运行正式样本；后续真实验证必须新建
  v2 协议和独立结果目录。

## 2026-09-15 / Context Projection / Trace 可审计配置

- 本步没有改变压缩算法；它把算法已经采用的两项关键决策变成 Trace 中可验证的数据。
- `minimum_net_savings_bytes=1` 是“完整 ModelRequest 必须严格变小”的精确表达。代码判断从
  隐含的 `saved <= 0` 改为读取这个具名配置，行为保持一致。
- `retrieval_tool_loading=on_reference` 表示回读工具已在运行时注册，但其 Tool Spec 只在本轮
  真正采用引用时进入模型请求。它不同于始终暴露，也不同于引用出现后临时注册执行器。
- `configuration_schema_version=2` 用来区分历史 v1 工件与新证据。旧结果仍可由汇总器读取；
  新版结果一旦声明 schema 2，缺少或篡改上述字段就会被拒绝。
- `QueryLoop` 无需新增分支：它原本就把 Projector 静态配置与本轮投影统计合并写入
  `MODEL_CALL_STARTED.context_projection`。本步扩展的是静态配置载荷和实验验证契约。
- 为什么重要：只看 `total_bytes_saved` 无法判断“没命中”“净收益不足而主动放弃”还是
  “根本没启用”。面试时应能区分配置事实、执行事实和最终效果，三者不能相互代替。

## 2026-09-15 / Context Projection / v2 实验预注册

- 为什么不能沿用 v1：自适应门槛是看过 v1 Preflight 后才设计的。如果把新实现产生的结果
  放进 v1，就等于实验中途换治疗方案，A/B 结论不可解释。
- v2 协议 schema 2 同时冻结 strategy、500-byte 候选阈值、1-byte 完整请求净收益门槛和
  `on_reference` 工具加载方式。汇总器不仅比较协议 ID 和阈值，还比较结果里的完整配置。
- Preflight Case 不能只看“任务够长”。已知 `multi_file_inventory_contract` 的单次毛节省约
  411 bytes，小于约 500-byte Tool Spec，新策略会合理地不投影。因此 v2 先选择历史工具结果
  更多的 `search_driven_retry_schedule`，并要求至少出现一次真实投影。
- “没有命中”并不说明算法错误，但说明这次 Preflight 没覆盖核心路径。工程验收需要任务成功
  和路径覆盖两个条件；前者回答质量，后者回答我们是否真的测试了新功能。
- 本步只预注册规则并扩展离线协议校验，没有调用 Provider。下一步是只读 Preflight 就绪审计，
  不是直接开始 12 次正式实验。

## 2026-09-15 / Context Projection / v2 Preflight 就绪审计

- 环境检查通过：协议可解析、有效模型名匹配、凭据存在、Case 完整且被 Git 跟踪、历史和 v2
  结果目录隔离。审计只判断密钥是否存在，没有读取或输出密钥值。
- 新输出边界：审批提示修复到 stderr 后，stderr 不再等于纯 Trace。真实运行必须保存原始
  stderr，并从唯一 `Trace run_` 行开始提取规范 Trace；否则结果解析器会把 Run ID 或审批文本
  当成 Trace 语法。stdout 继续只保存最终 Answer。
- 不能盲批 Approval：提前管道输入多个 `y` 虽然方便自动化，却失去了“看到精确 ToolCall 后
  决定是否允许”的安全语义。应使用 `tee` 同时显示并保存 stderr，逐次人工确认。
- 发现的阻塞：v2 JSON 中已经写了 Preflight 成功要求，但正式汇总器只实现 12-run 门禁，尚未
  机器执行两条 Preflight 的路径覆盖和总预算检查。协议里有字段不等于系统会执行它。
- 决策：暂不调用真实 Provider。下一小步先实现只读 Preflight 验证模式，使合法合成结果通过，
  并让缺 Arm、无真实投影、Usage 缺失、超预算或回读失败等情况确定性失败。

## 2026-09-15 / Context Projection / Preflight 离线门禁

- 新的 `--context-preflight-protocol` 与正式 `--context-protocol` 分开：前者期待每 Arm 一条，
  后者期待每 Case/Arm 三条。复用结果解码、Artifact 哈希、协议/模型/commit/配置校验，但采用
  不同的样本数量和晋级条件。
- v2 Loader 现在真正读取 `preflight_plan` 与 `preflight_budget`，并校验 Case、Arm 顺序声明、
  两次运行、每 Arm 成功数、投影活动、回读上限、Usage/Artifact 要求和 Token 预算。JSON 中的
  这些字段不再只是注释。
- 协议字段从 `minimum_projection_model_calls` 改为
  `minimum_changed_tool_result_count`。现有 result 保存的是累计变化 ToolResult 数；门槛为 1 时
  足以证明至少发生一轮投影，但不能伪装成掌握了更细的逐轮计数。
- 结构错误与实验失败分开：缺字段、混入模型、脏 commit、重复 Run ID、Artifact 哈希损坏会
  直接拒绝；两条结果结构可信但缺 Arm、未投影、回读失败或超预算则生成完整 FAIL 报告。
- CLI 在 Preflight gate 为 FAIL 时返回 1，使 CI 不会因为“成功打印了一份失败报告”而误判通过。
  合法合成对照返回 0。整个验证过程只读取已有结果，不调用模型。

## 2026-09-15 / Context Projection / v2 真实 Preflight

- 两条预注册运行均完整保留。baseline 找到了共享根因，却改成
  `range(0, attempts + 1)`，导致三次重试产生四项并耗尽工具预算，Safe Task Success 失败；
  projection 改成正确的 `range(0, attempts)`，测试与隐藏验收通过。
- projection 六轮 `changed_tool_result_count` 均为 0。工具结果不足以覆盖条件式回读 Tool Spec，
  自适应策略保持完整请求属于正确退化；但 Preflight 没有覆盖核心投影路径，因此仍必须 FAIL。
- 两组 Provider input Token 分别为 13571 与 11104，不能把差值归因于压缩：projection 实际零
  投影，而且两次运行的调用轨迹与成败不同。A/B 归因需要相同任务分布、足够重复和路径命中。
- stderr 还有一个容易遗漏的边界：审批提示不以换行结束，stdin 的终端回显不会进入重定向的
  stderr，Trace header 可能接在 `Approve?` 后面。原始 stderr 应保留，提取器必须搜索唯一
  `Trace run_` 子串，而不能假定它位于行首。
- 门禁结果：Run shape、回读、总 Token、Usage、Artifact 与协议快照通过；Safe Task Success 和
  Projection activity 失败。v2 按协议停止，不启动 12-run 正式实验。
- 下一方向：先离线设计能稳定产生足够大历史 ToolResult 的真实 Coding Case，并用 Scripted
  Model 验证投影和回读分支。新 Case 来自观察 v2 后的调整，真实实验必须使用新协议 ID。

## 2026-09-15 / Context Projection / 大搜索结果覆盖 Case

- 新 Case `large_search_context_repair` 模拟多个下游客户端共享默认超时配置。任务本身要求先
  搜索共享常量的定义和所有调用方，因此大 ToolResult 来自必要的工程探索，不是与任务无关的
  填充文本。
- Case 的隐藏验收同时检查默认值、25 个客户端的继承结果、唯一允许改动文件，以及
  list/search/read/edit/test 五类成功工具证据。模型不能通过只改测试或注册表绕过共享根因。
- 覆盖测试执行真实 `SearchTextTool`，得到 2730 UTF-8 bytes；再把它放到一条更新 ToolResult
  之前，使其从“最新未见结果”变成可投影历史。引用替换减少 2662 bytes，条件式回读 Tool
  Spec 增加 501 bytes，完整 ModelRequest 净减少 2161 bytes，并且只改变这一条历史结果。
- 本步只证明 Case 数据形状足以触发投影器，还没有证明 Scripted Agent 会按完整工具链完成
  Case，也没有修改真实实验协议或调用 Provider。下一步才做端到端 Scripted Model 闭环。

## 2026-09-15 / Context Projection / 大搜索 Case 的 Scripted 闭环

- `ScriptedModel` 固定执行 list → search → read → edit → test → final answer；其余全部使用产品
  `CodingAgent`、`QueryLoop`、`ToolDispatcher`、真实文件工具、真实 pytest 进程、EventLedger
  和 CheckpointStore，没有手工把 ToolResult 塞进 QueryLoop。
- 六轮投影数量稳定为 `0, 0, 0, 1, 1, 1`。前三轮搜索结果尚未产生或仍是最新未见结果；第四轮
  开始，新的 read/edit/test 结果位于历史尾部，旧搜索结果才转为 eligible。这验证了 retention
  时机，而不只是引用文本格式。
- 第四至第六轮每轮完整请求净省 2162 bytes，并只在这些轮次暴露 `read_tool_result`。上一步
  手工请求测得 2161 bytes，是因为 Tool Spec 列表从空变为一项；产品请求是在已有七项后追加，
  JSON 列表边界相差 1 byte。测量对象不同，不能把这 1 byte 当成算法不稳定。
- 投影只影响 ScriptedModel 收到的请求。最终 RunResult 和完成态 Checkpoint 中仍保存 2730-byte
  搜索原文；修改后的工作区通过真实测试和隐藏验收，证明压缩视图没有破坏权威执行状态。
- 本步仍未调用 Provider，也没有预注册新协议。下一步应冻结新的真实实验协议和 Preflight
  预算；协议一旦提交，才能开始新的付费运行。

## 2026-09-15 / Context Projection / 历史搜索结果回读闭环

- 在同一产品级 Scripted 流程中，测试通过后增加
  `read_tool_result(call_id="call_search")`。Dispatcher 没有重新执行 SearchTextTool，而是让
  `RunToolResultSource` 从绑定当前 Run 的最新 Checkpoint 取回原始 2730-byte 结果。
- 模型请求数变为七轮，投影数为 `0,0,0,1,1,1,1`。最后一轮同时包含旧搜索结果的短引用和
  最新回读结果的完整原文：旧副本仍可压缩，新结果因为位于历史尾部而受到保护。
- EventLedger 证明 `search_text` 只成功执行一次、`read_tool_result` 成功一次；最终 RunResult
  与完成态 Checkpoint 也继续保存原始搜索和回读结果。这排除了“回读其实偷偷重跑搜索”的
  假实现。
- 这仍是机械能力验证：ScriptedModel 是预先指定要回读的，不能证明真实模型会自主意识到信息
  不足。下一步要把“最终答案必须使用早期证据”写进独立 Case 的隐藏验收，再决定真实协议。

## 2026-09-15 / Context Projection / 早期证据语义压力 Case

- 新增 `large_search_context_recall`，与 `large_search_context_repair` 的初始 Workspace 逐文件
  完全一致，只在任务与隐藏验收上增加最终证据要求。这种配对尽量把变量限制为“后续是否需要
  早期搜索细节”。
- 最终回答必须单独给出客户端总数、注册表第一项和最后一项；只修好代码但漏答或答错证据仍
  判失败。隐藏验收还要求 `search_text` 只能成功执行一次，防止模型通过第二次搜索绕开
  历史记忆问题。
- Case 不强制调用 `read_tool_result`：baseline 原本就拥有完整搜索历史，projection 也可能把
  关键事实写进自己的中间消息。验收只规定业务结果与信息结果，不把某种内部实现写死；回读
  次数由实验 Trace 单独观测。
- 本步只完成 Case 和确定性反例，没有声称真实模型会通过。下一步用 baseline/projection 两个
  Scripted 路径验证：前者直接使用完整历史，后者通过引用回读后生成同一答案。

## 2026-09-15 / Context Projection / 早期证据成对路径

- baseline 和 projection 使用相同的初始 Workspace、修复动作和最终答案，两者均通过
  `large_search_context_recall` 隐藏验收，且 `search_text` 都只成功执行一次。
- baseline 的最后一轮模型请求仍直接包含 2730-byte 搜索原文；projection 的旧搜索
  结果是短引用，但最新的 `read_tool_result` 结果恢复了与 baseline 完全相同的原文。
- 测试同时检查作答前的最后 ModelRequest，避免只凭 ScriptedModel 预写答案宣称证据可用。
  它证明两条信息传递路径的机械闭环，仍不证明真实模型会自主选择回读或正确理解证据。

## 2026-09-15 / Context Projection / v3 真实模型协议冻结

- v3 将 `large_search_context_repair` 和 `large_search_context_recall` 设为配对正式 Case，并只用
  recall Case 运行 baseline/projection 各一次的 Preflight。
- 门禁要求两组 Safe Task Success、至少一条真实投影、零失败/取消回读、Provider Usage、
  完整工件与 45,000/5,000 input/output Token 总预算。成功回读数只记录不强制，因为模型
  也可能通过中间消息合法保留关键事实。
- 离线成对路径的累计可见量是 45,615 与 49,356 bytes，只用于判断新 Case 的请求形状。
  bytes 不是 Token，projection 强制回读时总 bytes 更高也说明不能预设压缩必然省钱。
- 协议如实记录当前入口不显式设置 temperature，而不虚构 temperature=0。本步没有检查
  凭据、创建结果目录或调用 Provider。
- 当前程序会在结果落盘后强制 Preflight 预算门禁，但尚不会强制正式样本的总预算和配对顺序。这两项已冻结为操作者
  停止规则，正式实验前还必须将它们变成机器校验，不能把 JSON 中存在的字段等同于系统已执行。

## 2026-09-15 / Context Projection / v3 Preflight 就绪审计

- 协议解析、模型/入口本地配置、凭据变量存在性、Case 完整性与 Git 跟踪、Arm 阈值映射、结果目录隔离均
  通过。凭据内容没有被读取；存在性不证明实时有效性。
- repair/recall 的 Workspace 指纹相同，任务指纹不同，符合“初始代码受控、早期证据要求不同”的配对设计。
- stderr 同时承载 Run ID、Approval 和 Trace，不能整份当成规范 Trace。运行文档现要求保留
  `stderr.raw.txt`，并从唯一 `Trace run_` 标记开始提取 `trace.txt`。
- Preflight Token 预算是落盘后的机器晋级门禁，不是事前 Provider 硬限流。超限会停止后续阶段，
  但已发生的调用费用无法撤回。
- 真实结果应先在仓库外落盘并记录干净 commit，两条都完成后再收录进仓库。提前在仓库内创建未跟踪结果
  会导致 `minicode_dirty=true`。

## 2026-09-15 / Context Projection / v3 真实 Preflight

- v3 的一对付费真实运行已完成。baseline 通过隐藏验收；projection 完成了同样的代码修复与测试，
  但第 9 轮仍请求工具，触发 `max_turns`，没有生成最终回答，因此 Safe Task Success 为 FAIL。
- 压缩路径确实被覆盖：projection 累计替换 11 个历史 ToolResult，相对它自己的规范请求节省
  20,859 bytes。这只能证明机制生效，不能单独证明整次任务更省或质量不受损。
- projection 的完整轨迹反而比 baseline 多 1,153 input tokens（+6.59%）和 2,171 模型可见 bytes
  （+3.28%）。局部请求压缩与端到端成本是两个指标；额外模型轮次、重新读文件和检查 diff 可以
  吃掉局部收益。
- projection 没有使用 `read_tool_result`，而是重新读取 Workspace 文件。零失败/取消回读通过门禁，
  但“没有失败回读”不等于“成功恢复了早期证据”；最终答案为空使信息验收直接失败。
- 一对随机真实轨迹不能建立因果关系，不能说失败必然由压缩导致。能下的结论只有：本次 v3 样本
  未达到预注册晋级标准。因此停止正式 12-run，不删除失败样本，也不补跑到成功为止。
- 下一步先离线逐轮比较 Trace，分析额外工具行为与终止失败。任何观察结果后产生的预算、提示、Case
  或策略修改都必须注册新协议 ID。

## 2026-09-16 / Context Projection / v3 Trace 离线诊断

- 两组前三轮完全相同，第 4 轮第一次投影也是第一次轨迹分叉。projection 此时不使用
  `read_tool_result`，而是直接读取客户端注册表和测试文件。
- Artifact 内容哈希确认 projection 第 4、7 轮读取的是同一份 `client_registry.py`。第 7 轮重新读取后，
  它在第 8 轮属于最新 ToolResult 批次而保留全文；模型随后运行 `git_diff`，第 9 轮注册表不再是最新
  批次，又被替换为引用。
- 当前保留规则保证“最新结果至少完整展示一次”，不保证“终局重要证据一直保留到回答”。这对一般
  工具输出是节省，对必须最终复述的证据可能造成反复读取。
- 本次还暴露了独立的终止预算问题：测试通过后模型继续检查属于合理行为，但 Query Loop 没有预留
  最终回答轮次。证据窗口和终止预算不能一步一起修改，否则后续效果无法归因。
- 下一小步先离线验证配置化的“两批保留窗口”候选，使用 Scripted Model 重放“读证据 → 看 diff →
  最终回答”，同时比较信息可用性和新增 bytes；暂不调用 Provider。

## 2026-09-16 / Context Projection / 两批保留窗口离线候选

- retention planner 现在可配置最近保护批数，默认保持 1；一次模型响应产生的连续并行 ToolResult
  仍按一批计算。非默认 projector 被明确限制为离线候选，尚不能进入正式 Trace/QueryLoop。
- 固定“早期搜索 → 注册表证据 → `git_diff`”请求中，一批策略替换两项并净省 5,645 bytes，
  但回答前注册表只剩引用；两批策略只替换早期搜索、保留注册表全文，仍净省 3,353 bytes。
- 该结果验证信息连续性和 bytes 代价，不验证真实模型理解或任务成功率；默认运行策略、提示、
  max_turns 和 v3 归档协议均未改变，也未调用 Provider。
- 检查中确认下一个独立边界：projector 可以引用超过 50,000 bytes 的结果，但 read_tool_result
  默认拒绝返回超过 50,000 bytes 的原文。下一小步先修复和测试这项恢复契约。

## 2026-09-16 / Context Projection / 可兑现的回读容量契约

- 新增共享的 50,000 UTF-8 byte 完整回读上限，并由 `ReadToolResultTool` 和
  `ToolResultReferenceProjector` 共同使用，避免两个组件各自维护容易漂移的数字。
- projector 现在拒绝把超过回读上限的历史结果替换成引用；结果继续内联，不会向模型提供一个必然失败的
  `read_tool_result` 路径。恰好等于上限的结果仍可引用并完整回读。
- 自定义回读容量暂时只允许离线构造，不能进入正式 Trace；否则 schema 2 没有记录该实验变量，比较结果
  会失去可复现性。
- 相关的投影、回读、检索与 CodingAgent 测试共 46 个通过，Ruff lint 通过。该步骤没有改变一批保留窗口、
  max_turns、模型提示或真实 Provider 实验协议。
- 已知限制：超过 50,000 bytes 的历史结果暂时无法压缩。后续若确有预算压力，应设计带范围信息的分页回读，
  而不是取消上限或把截断结果伪装成完整原文。

## 2026-09-16 / Context Editing v1 / A1 预算入口契约

- 新增尚未接入 QueryLoop 的纯规划模块 `context_editing.py`。`ContextEditingPolicy` 冻结请求 byte 预算、
  最近保护批数、最小净节省、排除工具以及保留 ToolCall 的 v1 约束，并可生成稳定 Trace payload。
- `assess_context_pressure` 只回答完整 `ModelRequest` 是否超过 byte 预算，不修改对话、不选择压缩项、
  不添加恢复工具。刚好等于预算保持原样，超过 1 byte 才进入待编辑状态。
- 完整请求测量包含 instructions、普通消息、ToolCall、ToolResult 和 ToolSpec。因此恢复工具定义带来的
  新增成本不会被遗漏；但 bytes 只是当前确定性代理指标，不能冒充 Provider Token 数。
- v1 明确要求保留 ToolCall。被清理的 ToolResult 仍需看得见原工具名称和参数，避免成为来历不明的引用。
- 新增 14 个测试；上下文编辑、画像、投影与保留规则合计 41 个测试通过，Ruff 和 Mypy 通过。
  当前真实运行行为完全不变。下一小步 A2 才会规划每个 ToolResult 的保护与候选原因。

## 2026-09-16 / 全局精简 / 统一模型请求转换

- 审查发现 `OpenAICompatibleModel.complete()` 使用完整 `ModelRequest` 转换，而 `stream()` 只转换
  `conversation`，会漏掉 `instructions` 中的系统指令和 Skill 正文。
- `stream()` 已改为复用 `model_request_to_openai_messages(request)`。带 instructions 的流式测试验证
  假客户端依次收到 system 与 user 消息；普通与流式模型适配测试共 45 个通过。
- 这次只统一输入转换。完整响应与流式 chunk 的输出解析仍是两种数据形态，应继续分开。
- 学习要点：`conversation` 是完整请求的一部分。Provider 适配器若只读取 conversation，就可能丢失
  instructions 或其他请求级信息。

## 2026-09-16 / 全局精简 / 收缩预算压力对象

- `context_editing.py` 中只有最大请求 bytes 已参与判断，因此删除了暂未生效的 Policy 配置、状态枚举和
  提前设计的 Trace payload。未来选择器真正使用保留批数、最小收益或排除工具时再引入对应输入。
- `ContextPressureDecision` 只保存 `request_bytes` 与 `max_request_bytes`；`overflow_bytes` 和
  `editing_required` 改为 property。调用者无法再单独传入与数字矛盾的状态。
- `assess_context_pressure()` 直接接收 byte 预算。完整请求仍包含 instructions、Message、ToolCall、
  ToolResult 和 ToolSpec，刚好等于预算不编辑，超过 1 byte 才要求后续规划。
- 源文件从 140 行降至 56 行，测试从 195 行降至 120 行；上下文压力与画像相关测试 11 个通过，
  Ruff 和 Mypy 通过。该模块仍未接入 QueryLoop，真实 Agent 行为没有变化。

## 2026-09-16 / 全局精简 / 合并 JSON 容器转换

- CLI Trace、终端审批、上下文画像、Checkpoint 编码和 OpenAI 适配器原来各自递归实现一次
  `Mapping → dict`、`tuple/list → list`。现在统一复用 `core/tool_calls.py` 的 `to_plain_json()`。
- `_freeze_value()` 继续独立存在：它在数据进入核心对象时校验并冻结，`to_plain_json()` 在数据离开核心
  对象、准备序列化时生成普通容器。两者方向相反，不能因为递归结构相似而合并。
- 公共函数只负责容器形态，各调用方自己的 JSON 字段、排序、缩进和紧凑分隔符保持不变。新增测试验证
  嵌套只读容器能恢复为 dict/list；相关测试 69 个、全套测试 591 个通过，Ruff、Mypy 与 diff 检查通过。

## 2026-09-17 / 全局精简 / 共用 Trace 上下文统计

- `context_comparison.py` 与 `evaluation_result.py` 原来各自遍历 Trace，重复计算模型可见 bytes、原始 bytes、
  净节省、替换数和回读成功/失败/取消数，也重复校验 `visible == after` 和
  `before - after == saved`。这些共同事实现在由 `context_trace.py` 统一产生。
- 正式评测的协议 ID、Arm 和配置一致性仍由 `evaluation_result.py` 判断；离线成本模型独有的
  `tool_result_bytes_saved` 仍由 `context_comparison.py` 严格读取。这样共用事实算法，但没有把不同实验规则
  混成一个大函数，也没有要求旧正式 Trace 必须拥有原先不需要的字段。
- 两类报告的 14 个针对性测试保持通过，原有输出字段和数值不变；全套 591 个测试、Ruff、Mypy 和
  diff 检查通过。没有调用真实模型，也没有修改上下文压缩策略。

## 2026-09-17 / Context Editing v1 / A2 ToolResult 决策表

- 复用并扩展 `context_retention.py`，没有新建第二套分类器。每个 ToolResult 现在得到一个稳定原因：
  最近批次、错误、排除工具、超过完整回读上限，或可进入后续选择的 `eligible`。
- 原有 `protected_call_ids` 与 `eligible_call_ids` 改为从决策表推导，避免“理由说受保护、另一个列表却说
  eligible”的重复状态。当前优先级是最近、错误、排除工具、无法回读、候选。
- UTF-8 byte 边界测试使用 4 个汉字（12 bytes）验证超过 10-byte 回读上限时必须保留全文。投影器复用
  同一决策，不再自己重复判断回读容量。
- 相关保留、投影和回读测试 35 个、全套测试 592 个通过，Ruff、Mypy 和 diff 检查通过。A2 不按预算
  选择项目、不改变 canonical history，也未接入新的 QueryLoop 触发流程或调用真实模型。

## 2026-09-19 / Context Editing v1 / A3 预算选择计划

- `plan_context_editing()` 组合 A1 压力结果和 A2 retention 决策。请求未超预算时选择为空；超预算后只从
  `eligible` 中按最旧优先试选，达到预算即停止。
- 规划器用临时假设请求计算真实 provider-neutral bytes：引用 JSON 和条件式 `read_tool_result` Tool Spec
  都计入成本。引用不比原文短时跳过，全部候选仍不足时通过 `remaining_overflow_bytes` 明确报告容量不足。
- 稳定引用渲染移到 `context_retrieval.py`，供旧 projector 与 A3 共用，防止计划成本和执行格式漂移。
  `ContextEditingPlan` 只保存压力、retention、选择 ID 和预计大小；节省量与是否达标均由已有数字推导。
- 测试覆盖预算内零操作、最旧候选刚好达标且计入 Tool Spec、受保护内容导致预算无法满足，以及未达到
  最小净收益时拒绝选择；相关测试 55 个、全套测试 596 个通过，Ruff、Mypy 和 diff 检查通过。
  没有接入 QueryLoop 或调用真实模型。

## 2026-09-19 / Context Editing v1 / B1 预算投影边界

- 新增 `apply_context_editing_plan()`：重新核对计划对应的 canonical request bytes，只替换计划选中的
  eligible ToolResult，按需加入一次恢复 Tool Spec，并要求实际投影 bytes 与 A3 预计值完全相等。
- 新增实验性的 `BudgetedToolResultProjector` 组合“计划 → 应用”。预算内返回原请求对象；超预算时生成
  独立模型视图，canonical request 不变。
- 请求总 bytes 与计划不匹配时立即拒绝；保护项、缺失 call ID 或实际成本漂移也有对应拒绝边界。当前计划
  与应用在一次 `project()` 内连续发生；若未来支持延迟或跨进程应用，还需增加内容指纹，不能只比较 bytes。
- `describe_context_projector()` 暂时拒绝预算 projector 进入 traced QueryLoop，因为现有 schema 2 没有
  记录总预算等变量。默认 Identity、CLI 和旧 v3 协议没有变化，也未调用真实模型。
- 后续精简把“创建一个立即丢弃的 `ContextPressureDecision` 来触发校验”改为显式的
  `validate_max_request_bytes()`。领域对象负责表达压力决策，校验函数负责复用参数规则，避免隐藏副作用和
  无意义的临时对象；投影器测试直接覆盖 `bool` 与零预算边界。
- 相关测试 61 个、全套测试 602 个通过，Ruff、Mypy 和 diff 检查通过。下一步先定义新的 Trace 配置契约，
  再讨论 QueryLoop/CLI 接入。

## 2026-09-19 / Context Editing v1 / B2 schema 3 配置契约

- 新增独立的 `context_projection_config.py`，把配置对象、枚举、稳定 payload 和解析职责从实际投影逻辑中
  分离。旧 projector 的 schema 2 字段保持不变。
- `BudgetedContextProjectionConfiguration` 使用 schema 3，记录总预算、最近保护批数、最小净收益、排除工具、
  完整回读上限和恢复工具加载方式；排除工具名去重、排序后写入，保证稳定可比较。
- `from_payload()` 要求字段全集严格匹配，并验证版本、策略、类型和值边界。缺少任何行为参数都拒绝解析，
  避免不完整 Trace 被当成可复现实验。
- `BudgetedToolResultProjector` 持有配置对象，执行时也从该对象取参数传给 planner，避免“记录值”和“运行值”
  分成两份后漂移。
- 新增 6 个测试；全套 608 个测试、Ruff、Mypy 和 diff 检查通过。预算 projector 仍不能进入 QueryLoop，
  未修改 CLI、默认 Identity 或正式评测，也未调用真实模型。

## 2026-09-19 / Context Editing v1 / B3 QueryLoop Trace 接入

- `describe_context_projector()` 开始返回预算 projector 保存的 schema 3 配置，QueryLoop 因而可以使用现有
  `MODEL_CALL_STARTED` 路径记录配置与每轮实际投影测量，不新增重复事件类型。
- 新增确定性 QueryLoop 测试：较老大结果被替换为引用，ScriptedModel 收到模型视图；事件同时记录 schema 3
  六项行为参数、变化结果数和正 byte 节省；最终 RunResult 仍保存完整 ToolResult。
- 默认 Identity、旧 schema 2、CLI、CodingAgent 工厂和正式评测没有变化，也未调用真实模型。当前直接注入
  QueryLoop 的宿主仍需自行保证回读工具存在，因此下一步先完成产品组装边界，不能直接开放真实实验。
- 全套 609 个测试、Ruff、Mypy 和 diff 检查通过。

## 2026-09-19 / Context Editing v1 / B4 CodingAgent 恢复链组装

- `build_coding_agent()` 新增 schema 3 预算配置入口，并与旧单结果阈值参数互斥；默认仍不启用任何投影。
- 预算模式复用现有 Run 绑定恢复链：EventLedger 提供 run_id，CheckpointStore 保存原文，
  `RunToolResultSource` 查找当前 Run，`ReadToolResultTool` 在 Dispatcher 中预注册，Tool Spec 仅按引用出现。
- 回读工具上限直接取自预算配置，projector 再从该工具读取同一个上限，消除“分类器允许引用、执行器却读不回”
  的双配置风险。缺少 EventLedger/CheckpointStore 或同时选择两种投影时会在模型调用前拒绝。
- 原端到端回读测试扩展为旧阈值/schema 2 与预算/schema 3 两种模式，均实际完成四轮工具调用和历史全文恢复；
  新增互斥边界测试。全套 611 个测试、Ruff、Mypy 和 diff 检查通过。
- CLI、正式评测和真实模型调用均未改变。下一步先增加 schema 3 离线评测校验，继续保留旧 v3 证据语义。

## 2026-09-19 / Context Editing v1 / B5 schema 3 离线评测校验

- 新增独立的 `summarize_budgeted_context_experiment()`；它接收预登记的预算配置，逐轮严格解析 schema 3，
  检查轮次间配置不漂移，并要求每轮都等于协议配置。
- 配置通过后复用 `summarize_context_trace()` 的公共事实检查与汇总，不复制 byte 差值或回读结果算法。
  输出包含登记配置、总预算及模型可见/canonical bytes、净节省、变化结果和回读成败。
- 旧 schema 2 汇总入口保持原样；测试明确确认 schema 3 Trace 会被旧 v3 路径拒绝。另有测试覆盖合法两轮
  汇总、第二轮预算被篡改，以及 `before - after != saved` 的伪造测量。
- 新增 4 个测试；全套 615 个测试通过。Ruff、Mypy 和 diff 检查通过；未修改 record_result CLI、协议 JSON、
  Agent CLI 或真实模型流程。

## 2026-09-19 / Context Editing v1 / B6 预算实验预注册协议

- 新增独立 `context_experiment_protocol.py` 和 `real_model_protocol_v4.json`。旧 v1～v3 加载器保持不变，避免
  schema 3 规则改变历史证据语义。
- v4 在结果产生前锁死模型、两个 Case、schema 2 Identity baseline、schema 3 budgeted projection、两次
  Preflight 顺序、正式重复数、Token 预算和晋级门槛；加载器交叉校验相关计数，拒绝被篡改的配置。
- 预算暂定 10,000 bytes：v3 已归档请求启动约 4.9KB、后段约 11～14KB，因此该 Case 前段不压缩、后段能
  进入压力分支。它是待 Preflight 验证的实验触发点，不是生产默认值。
- 新增协议说明与 4 个 v4 注册测试；本阶段不接 CLI、运行器、结果记录或真实模型。下一步只做运行配置与协议
  的单一来源接线，防止手工参数和协议漂移。

## 2026-09-19 / Context Editing v1 / B7 协议驱动的运行与记录

- `evaluation_run` 新增协议文件入口并要求显式 Arm；baseline 保持 Identity，projection 直接传协议解析出的完整
  schema 3 配置，不再从命令参数重复拼装预算字段。
- 通用 CLI 把预算配置传到 CodingAgent composition root，并在创建 Provider 客户端前核对登记模型；Case、
  Provider、thinking 和 temperature 契约也会在运行前检查。
- `evaluation_result` 新增协议文件入口，核对 Case/模型后按 Arm 选择 schema 2 或 schema 3 Trace 校验；结果
  保存协议 ID、Arm、实际配置和上下文指标。旧 v1～v3 路径保持原样。
- 新测试覆盖 v4 两个 Arm、显式 Arm 要求、配置传递、模型漂移提前拒绝、两种 schema 分派和完整结果落盘。
  没有调用真实模型；v4 Preflight 汇总门禁仍待下一步实现。

## 2026-09-19 / Context Editing v1 / B8 schema 3 Preflight 门禁

- `evaluation_summary` 的结果加载层新增 schema 3 严格解析，并保存完整预算配置；schema 3 只允许 projection，
  顶层请求预算必须与 Trace 配置一致。
- Preflight 入口按协议 schema 分派配置校验，再复用原门禁检查 Arm 数、Safe Task Success、projection activity、
  回读、Provider Token、工件、commit 和协议快照；旧 v1～v3 测试保持通过。
- 新测试覆盖 v4 成功对照、配置漂移拒绝、快照改变导致 FAIL 和 CLI PASS。所有结果均为离线构造，没有调用模型。
- 结果尚无可信顺序编号，当前只能证明两个 Arm 各一条，不能证明执行时间顺序；下一步用统一编排边界解决，
  不根据目录名推断。

## 2026-09-19 / Context Editing v1 / B9 Preflight 顺序编排

- 新增 `evaluation_preflight.py`，把“协议顺序与失败停止”同“怎样执行一次真实评测”分开；当前通过
  `PreflightRunExecutor` 注入假执行器，未调用模型。
- 每批创建新的结果根目录，复制不可变协议快照，并写出含 SHA-256、Case、Arm 顺序和运行目录的
  `preflight-plan.json`；已有目录会被拒绝而不是覆盖。
- 每轮开始/结束立即追加到 `preflight-events.jsonl`。只有执行器报告成功且存在 `result.json` 才开始下一 Arm；
  baseline 失败、记录缺失或执行器异常都不会继续 projection。
- 5 个定向测试覆盖完整顺序、失败即停、假成功但无结果、目录复用保护和异常留痕；Ruff 与该模块 Mypy 通过。
- 这一步没有真实 CLI 执行适配器，也没有 Provider 调用。下一步只接已有 prepare/run/result 流程，并先用假子进程
  做离线验证。

## 2026-09-20 / Context Editing v1 / B10 Preflight 命令执行适配器

- 新增 `evaluation_preflight_executor.py`，按 Arm 复用现有 workspace prepare、`evaluation_run` 和
  `evaluation_result` 边界，不复制 Agent、Trace 评分或隐藏验收实现。
- Agent stdout、原始 stderr、规范 Trace、工作区路径和结果记录器输出分别落盘；stderr 在捕获时仍实时显示，避免
  无换行的 Approval 提示被隐藏后进程等待输入。
- 运行前要求 MiniCode Git 干净，且结果根位于仓库外，防止生成的实验文件反过来污染 `minicode_dirty`。
- Trace 提取要求恰好一个 `Trace run_`，兼容 Approval 提示和 Trace header 同行；零个或多个标记均停止记录。
- 新增 5 个测试（其中一个参数化为两种无效 Trace），与 B9 合计 11 个定向场景通过；全部使用假命令结果，未调用
  Provider。全套 642 个测试、Ruff、Mypy 和 diff 检查通过。下一步让最终门禁验证 B9 计划/事件，并提供显式
  批次入口。

## 2026-09-20 / Context Editing v1 / B11 编排证据门禁与批次入口

- v4 Preflight 汇总开始严格验证冻结计划：协议哈希、ID、Case、运行序号、Arm 和目录必须与注册协议完全一致；
  篡改计划直接拒绝。
- 追加事件必须形成 baseline started/finished → projection started/finished 的完整成功序列，结果路径必须恰好
  对应两个槽位，结果内部 Arm 也不能互换；这些条件统一显示为 `Orchestration evidence`。
- 编排证据加入总门禁，但只适用于拥有该证据契约的 schema 3/v4；历史 v1～v3 汇总语义保持不变。
- `python -m minicode.evaluation_preflight` 成为批次入口，串联协议加载、B9 顺序控制、B10 命令执行和最终汇总；
  已有结果根会在任何模型调用前拒绝。
- 新测试覆盖完整证据、缺事件、结果换位、计划篡改和批次目录复用保护；全部为离线数据。下一步只做真实运行前
  的只读就绪审计，当前脏工作树不能执行 v4。全套 646 个测试、Ruff、Mypy 和 diff 检查通过。

## 2026-09-20 / Context Editing v1 / B12 运行前零副作用门禁

- 只读就绪审计确认 API Key 非空、登记模型一致、默认 Provider 地址、案例工件、虚拟环境、仓库外输出路径和
  Approval 交互方式均已就绪；当前唯一硬阻塞是工作树尚未形成干净 commit。
- 审查发现批次入口原先先创建结果根和计划，再由首个 Arm 检查 Git 与路径。虽然不会误调用模型，但配置失败会
  留下不完整目录，仓库内错误路径还会先污染工作树。
- `ContextPreflightCommandExecutor.validate_environment()` 现在在编排器创建目录前检查 Git 干净、目标位于仓库外
  且尚不存在；每个 Arm 执行前的检查继续保留，用于防止 baseline 之后环境发生变化。
- 新测试证明 dirty Git 和仓库内目标都不会创建结果目录，并覆盖批次入口“前置检查 → baseline → projection →
  汇总”的成功胶水路径。Token 预算注释也更正为运行后的 Provider Usage 晋级门禁，而不是调用中的硬限流。

## 2026-09-20 / Context Editing v1 / B13 可复现实验提交

- 将预算压缩运行时、v4 协议、Preflight 编排与证据门禁、测试和学习文档共 50 个文件整理为一个本地功能提交；
  提交前全套 649 个测试、Ruff、Mypy 与 diff 检查通过。
- 提交后工作树为空，协议、批次入口和命令适配器均能从 HEAD 读取；关键 Preflight 定向测试 50 个再次通过。
- 该提交只建立可复现实验版本，没有运行 Provider。下一步属于会产生外部调用和费用的真实 Preflight，必须由用户
  明确决定，并在可交互终端逐次核对 `edit_file` 与 `run_tests` 审批。

## 2026-09-20 / Context Editing v1 / B14 v4 真实 Preflight

- 用户明确授权后，在干净 commit `b95afeb` 上通过唯一批次入口真实运行 baseline → projection；四次人工审批都只
  涉及目标文件修改和相关测试。两组隐藏验收、运行状态、Trace 工具契约和最终回答全部成功。
- 最终 Preflight gate PASS：两次共 32184 input / 872 output Token，projection 的请求级替换累计为 7，一次历史
  搜索结果回读成功，失败/取消回读为 0，协议快照、计划、事件、结果槽位和 Artifact 全部通过。
- projection 自身从累计 82251 canonical bytes 降至 70240 model-visible bytes，节省 12011 bytes；双方共有的前
  6 次调用中 projection 少 839 input Token（约 6.10%）。
- 但 projection 多执行 `git_diff`、回读和两个模型轮次，整次 input 为 18422，对比 baseline 13762 增加 4660
  （33.86%）。单样本不能把额外轨迹归因于压缩，Preflight PASS 只代表安全性与机制门禁通过，不代表效果已成立。
- 证据归档到 `benchmarks/context_projection/results/v4-preflight/`。正式 12-run 仍需单独授权，并以协议冻结的
  聚合降低至少 5%、单 Case 回归不超过 5%为效果结论；不得看到本结果后改写 v4 参数。
