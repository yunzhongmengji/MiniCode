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
