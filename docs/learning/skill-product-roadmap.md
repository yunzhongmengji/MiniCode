# MiniCode Skill 产品化路线

规划基线：2026-09-22。S1 实施核对：2026-09-30（当时尚未调用真实模型）。
前半部分保留规划时的缺口描述；后半部分逐步记录已完成的变更，应以最新记录判断当前状态。

当前状态（2026-10-05）：S4 的显式 CLI 接入与已列分支验收已完成，S5a 已增加漏选/多选诊断，
S5b 已固定 v1 合成评测草案，S5c 已提供离线报告命令（标签仍待负责人审核）。
S6a 已验证 Skill 不能越过 edit_file 的策略拒绝或审批拒绝；S6b 已准备任务级开关对照夹具，
S6c 已用脚本模型运行两组 Agent 并生成独立验收记录。
S6d 已接入评测命令的显式 Skill 目录，并离线验证了命令到模型请求的传递。
S6e 已让结果 JSON 明确记录 Skill 组别和选择/加载名称，并在写结果前与 Trace 核对。
S6f 已完成真实 Preflight 前的预算/可比性离线审计（当时尚无付费运行授权；费用硬上限仍未具备）。
S6g 已把评测入口的 SDK 自动重试固定为 0；普通 CLI 仍用原默认值 2，费用硬上限仍未具备。
S6h 已让结果记录显式区分 Token usage 完整与缺失；它是观测字段，不是费用停止器。
S6i 已让普通汇总读取 usage 完整性，并提供可返回失败退出码的完整 usage 检查。
S6j/S6k 已接入 fresh-run 的缺失 usage/累计 Token 停止规则及冻结的两组批次入口。
S6l 的旧快照模型被服务端额度拒绝；S6m 按用户要求统一当前配置为 qwen3.7-flash，
用新协议、新目录完成真实两组对照：两组均通过隐藏验收，11 次模型请求均有完整 usage。
开启 Skill 本次增加了 Token 和一轮模型调用，没有观察到任务结果改善；仅证明个案链路可用。
S6n 已完成证据收尾与第 7 节验收核对：前六项有工程证据，第七项用户理解待复述确认。
本地、显式 Skill v1 的工程范围可收尾，不再自动扩大付费样本；完整流程和简历口径见
[Skill v1 阶段收尾](skill-stage-closeout.md)。
这不代表所有生产边界都已解决：默认 CLI 尚无模型请求总预算；关键词路由的合成标签仍待审核，
其他权限场景、通用效果也不能由这条测试推断。
完整阶段结束仍以第 7 节的标准为准；S4 阶段验收证据见文末 S4f。

## 1. 这一阶段要达到什么目标

当前 Skill 不是空白模块：Manifest、Catalog、磁盘发现、关键词路由、延迟加载、上下文渲染、QueryLoop 注入、事件和
离线路由评测都已经存在。真正缺少的是默认产品链路。

本阶段目标是：

> 用户显式提供一个受信任的本地 Skill 目录后，CodingAgent 能够有边界地发现、选择和加载相关说明；选择过程可以观察，
> 中断恢复继续使用原 Run 的同一份 Skill 指令；不开启 Skill 时，现有 CLI 行为完全不变。

这是一项“把已有组件接入产品并补齐生命周期”的工作，不是重新发明路由算法。

## 2. 先理解现有调用链

```text
<skill-name>/manifest.json
            │ 只读取轻量元数据
            ▼
FileSkillCatalogLoader
            ▼
       SkillCatalog
            ▼
KeywordSkillRetriever  ── 共享关键词大于 0 才召回
            ▼
KeywordSkillRanker     ── 按共享唯一词数量排序
            ▼
KeywordSkillRouter     ── 最多保留 max_skills 个
            ▼
FileSkillLoader        ── 只读取被选中的 SKILL.md
            ▼
SkillContextBuilder    ── 记录选择/加载事件并组合正文
            ▼
QueryLoop              ── 放入 ModelRequest.instructions
            ▼
Model Adapter          ── 转成模型可见的 system 指令
```

各文件职责：

| 文件 | 当前职责 | 不是它负责的事 |
|---|---|---|
| `manifest.py` | 一张 Skill 元数据卡片 | 不读正文、不执行 Skill |
| `catalog.py` | 有序保存 Manifest，拒绝重名 | 不搜索磁盘、不路由 |
| `discovery.py` | 从 Skill 根目录发现并解析 `manifest.json` | 不读取 `SKILL.md` |
| `retrieval.py` | 关键词召回与打分 | 不决定文件权限 |
| `router.py` | 组合召回、排序和 top-k 截断 | 不加载正文 |
| `loader.py` | 在独立 Skill 目录和 byte 上限内读取正文 | 不判断相关性 |
| `context.py` | 选择、加载、记录事件、渲染模型指令 | 不赋予工具权限 |
| `evaluation.py` | 比较“期望 Skill 名称”和“实际选择名称” | 不运行模型，也不判断代码任务是否成功 |

`evaluation.py` 目前只是路由分类器的离线评测。它能发现选错、漏选和过度召回，但即使路由名字全部正确，也不能证明
Skill 真的提高了 Coding Agent 的任务成功率。

## 3. 当前已经具备的能力

1. Manifest 会校验非空名称、描述、入口和唯一标签。
2. Catalog 保持注册顺序，使同分结果可复现。
3. Discovery 只接受两层路径中的顶层 `manifest.json`，并要求目录名与 Skill 名相同。
4. Loader 使用该 Skill 自己的 Workspace，拒绝 `..` 越界、外部符号链接、超大、缺失、目录、非法 UTF-8 和空正文。
5. 未选中的 Skill 正文不会读取；集成测试用非法 UTF-8 的未选中正文证明了这一点。
6. QueryLoop 根据最近一条用户消息只构建一次 SkillContext，后续工具轮次复用，不受 ToolResult 偶然关键词影响。
7. Skill 正文进入 `ModelRequest.instructions`，不污染结构化 conversation。
8. 选择、加载开始、成功、失败和取消都有事件；事件只记录名称、分数、结果和 byte 数，不复制完整正文。
9. Skill 只能影响模型建议，真正的文件修改和测试仍经过 Dispatcher、Policy、Approval 与 Workspace。

当前基线验证：`tests/skills` 与 `tests/core/test_query_loop.py` 共 70 条测试通过，Skill 源码 Ruff 和 Mypy 通过。

## 4. 当前产品缺口

### 4.1 默认 CodingAgent 已有可选 Provider 接口，CLI 仍未接入

S1 已让 `build_coding_agent()` 接收并转交可选的 `skill_context_provider`。CLI 仍没有 Skill 目录参数，默认不启用；
因此还不能描述成 `minicode run` 的产品能力。

### 4.2 恢复时可能换成另一份 Skill

当前 `_run()` 开始时会重新调用 Skill Provider。`resume()` 最终也会进入新的 `_run()`。如果新旧进程之间：

- `SKILL.md` 被修改；
- Manifest 路由字段被修改；
- Skill 目录被删除或替换；

同一个 Run 就可能在恢复后使用不同指令。Checkpoint 目前只保存对话、轮次、工具调用和完成状态，没有保存 Skill 选择
或正文快照。这是 CLI 接入前必须解决的正确性问题。

### 4.3 外部格式还不是稳定协议

规划时 `manifest.json` 没有 `schema_version`，解析器也不拒绝未知字段。S2g/S2h 已补齐基本输入合同：
允许字段固定，未知字段立即报错；新文件可写 `schema_version: 1`，旧文件缺省时仍按 v1 读取；
显式写错版本或类型会失败。公开 CLI 输入前仍须提供清楚的示例和错误提示。

### 4.4 只有单文件上限，没有组合预算

Loader 默认限制每个 Skill 最多 50,000 bytes，Router 默认最多选择 3 个 Skill。理论上可向 instructions 加入接近
150,000 bytes，尚未计算标题和分隔符。产品接入前需要限制渲染后的总 byte 数，而不能只依赖单文件上限。

### 4.5 信任边界必须显式

Skill 正文虽然不能直接绕过工具 Policy，但它作为 system instructions 会强烈影响模型。第一版不能自动加载当前仓库
随附的任意 `.skills`，否则不可信仓库内容会被提升成高优先级指令。应只加载用户显式指定的本地受信任目录，并在文档
中说明“路径安全”不等于“内容可信”。

### 4.6 当前评测太小

现有离线基线只有少量英文正例和负例。关键词算法不能可靠处理同义词、跨语言请求和相似 Skill 冲突。还缺少：

- 相关 Skill 没选到；
- 两个 Skill 共享大量词时选错；
- 无关任务误选；
- Skill 选对但任务结果没有改善；
- Skill 指令试图建议越权动作但仍被 Policy 拦截。

## 5. 后续实施顺序

每个编号是一小步。上一项没有达到标准，不进入下一项。

### S1：只打通产品组装接口

修改范围：`build_coding_agent()` 增加可选 `skill_context_provider` 参数，并原样交给 QueryLoop。

本步不做：

- 不增加 CLI 参数；
- 不发现磁盘目录；
- 不修改 Checkpoint；
- 不运行真实模型。

完成标准：

1. 不传 Provider 时，请求 instructions、事件和现有 CodingAgent 行为完全不变。
2. 传入假 Provider 时，只调用一次，Skill 指令进入每轮 ModelRequest，但不进入 message history。
3. Provider 失败和取消继续由 QueryLoop 的现有运行边界记录并传播。
4. 完整测试、Ruff、Mypy、diff check 通过。

为什么先做这一步：它只是把已有、已经测试的 QueryLoop 能力开放给产品组装，建立最小依赖注入边界，不提前绑定文件
格式或 CLI 设计。

### S1b：先用真实本地文件贯通 Skill 链路

在不开放 CLI 的前提下，用一条集成测试证明：磁盘 Manifest → Catalog → 关键词选择 → 仅读取选中的 `SKILL.md` →
`SkillContextBuilder` → `build_coding_agent()` → `ModelRequest.instructions`。这样先确认组件之间确实接得上，
然后再处理恢复和外部输入合同。

完成标准：相关 Skill 正文进入模型指令，无关 Skill 正文不读取，Skill 选择与加载事件能定位；不调用真实模型。

### S2：保存可恢复的 Skill 指令

优先采用最小状态：在新版本 Checkpoint 中保存本 Run 实际使用的渲染后 Skill 指令文本。恢复时直接使用这段文本，
不重新路由、不重新读取当前磁盘。暂不保存选中 Skill 的名称、逐项 hash，也不为这一段文本单独建立对象层。
名称和选择分数已有事件可观察；如果将来确实需要跨重启审计逐项正文，再根据实际需求增加字段。

完成标准：

1. 建立 Checkpoint 后修改或删除 `SKILL.md`，恢复请求仍使用原快照。
2. 空选择和“没有配置 Skill”能够区分；旧 schema 1/2 的恢复行为明确，不能静默重新路由。
3. 保存的指令大小受明确上限控制，Checkpoint 文件权限仍由现有 0700 状态目录保护。
4. Event 不记录完整正文，只记录必要的选择、加载结果和 byte 数。
5. 编解码往返、旧 schema 读取、文件存储和恢复集成测试通过。

保存实际指令而不只保存 hash，是因为 hash 不能还原正文；目录被删除时，只有原指令文本才能让同一个 Run
继续使用原来的说明。代价是 Checkpoint 会保存一份本地指令正文，因此必须有大小和文件权限边界。

### S3：稳定 Manifest 与总预算合同

内容：

1. 给磁盘 Manifest 增加明确的 schema version；
2. 拒绝未知字段、错误版本和拼错字段；
3. 保留单 Skill byte 上限；
4. 增加渲染后 Skill Context 总 byte 上限；
5. 在超预算时明确失败，不静默截断一份 Skill 正文。

完成标准：合法 v1、未知版本、额外字段、单文件超限和组合超限都有测试；未选中正文仍不读取；目录与符号链接边界不变。

是否兼容无版本 Manifest 必须在实现前明确决定，不能一边把它当公开协议、一边靠猜测自动升级。当前仓库没有默认产品
Skill 目录，因此可以优先采用严格、简单的 v1 合同，但需在改动说明中明确这是一次外部格式建立，而不是无感重构。

### S4：增加显式、默认关闭的 CLI 接入

建议第一版只增加一个入口：

```text
minicode run "..." --skills-root /absolute/or/explicit/path
```

策略：

- 未提供参数：完全不扫描、不选择、不加载 Skill；
- 提供参数：把它视为用户显式信任的本地指令目录；
- 新运行从目录构建 Provider；
- 恢复使用 Checkpoint 快照，不要求再次传目录；
- 目录或 Manifest 配置错误在第一次 Provider 调用前失败；
- `--trace` 能看到选择、分数、加载结果和 byte 数，看不到完整正文。

完成标准：CLI 默认回归不变；显式启用链路从磁盘走到模型 instructions；无匹配时正常运行且注入为空；错误目录不会发起
模型调用；恢复使用原快照。

第一版不开放十几个调参开关。`max_skills`、单文件上限和总上限先由一个经过测试的产品配置固定，等评测显示需要时再
决定是否暴露给用户。

### S5：扩充路由评测，但不急着换算法

固定一组版本化 Case，至少覆盖：

1. 明确正例；
2. 无适用 Skill；
3. 两个相似 Skill 冲突；
4. 同分时稳定顺序；
5. 当前算法明确不支持的同义改写/跨语言样本。

先把失败记录下来，不为了让四个例子全绿立即加入 Embedding 或模型路由。只有错误样本足以说明关键词基线成为主要瓶颈，
才比较规则扩展、Embedding 召回或模型重排，并计算新增延迟与 Token 成本。

完成标准：报告同时给出 exact match、漏选、误选和具体失败 Case；评测数据版本、Catalog 和参数可复现。

### S6：做一次任务级 Skill 开关对照

路由准确率不等于项目效果。最后选择一个 Skill 确实可能帮助的 Coding Case，固定模型、工具、Policy、预算和验收，比较：

- baseline：Skill 关闭；
- treatment：Skill 开启。

同时加入一个无关任务，检查开启 Skill 后是否误选和增加无效成本。先做 Scripted/离线编排验证，再决定是否授权真实模型
Preflight。

完成标准：

- 最终任务由隐藏验收判断，不用“选中了正确名字”代替任务成功；
- 分别报告结果、模型调用、工具调用、Token、选择与加载成本；
- Skill 建议不能绕过 Policy 和 Approval；
- 一对 Preflight 只证明链路可用，不直接宣称成功率提升。

## 6. 暂时不做什么

- 不做 Skill 市场、远程下载、签名中心或热更新服务。
- 不做 RPC、进程池和注册中心。
- 不自动把仓库里的文本提升成 Skill。
- 不同时引入 Embedding、模型重排和多 Agent。
- 不让 Skill 定义新工具权限。
- 不把路由准确率包装成 Coding Agent 成功率。

这些功能只有在本地显式 Skill 的使用数据暴露实际需求以后才有依据。

## 7. 整个阶段什么时候结束

达到下面标准后，Skill 模块才可以从“组件已实现”升级为“产品可选能力”：

1. `minicode run` 能显式启用一个受信任 Skill 根目录，默认仍关闭。
2. 未选中正文不读取，组合 instructions 有总预算。
3. 选择、加载、失败和注入可观察，但事件不泄露完整正文。
4. 恢复使用同一份快照，不因磁盘变化静默换指令。
5. 无 Skill、选中一个、无匹配、误选、加载失败和越权建议都有测试。
6. 至少完成一个任务级开关对照，诚实报告收益与成本。
7. 能在面试中解释 Skill 是“方法说明”而不是 Tool、权限或新 Agent。

满足这些标准后再进入 Memory；否则 Skill 与 Memory 同时注入会让效果和失败来源无法归因。

## 8. S1 实施记录：产品组装接口

本步只改了产品组装入口：`build_coding_agent(..., skill_context_provider=provider)` 把传入的对象原样交给 `QueryLoop`。
这里的 Provider 是一个接口约定：它提供 `async build(query)`，返回 `SkillContext`。本步没有创建实际的磁盘 Provider；
测试使用假 Provider，目的是单独验证“接线”是否正确。

以用户请求 `Inspect README.md.` 为例，一次运行的数据流是：

```text
用户请求 → CodingAgent.run() → QueryLoop → provider.build(用户请求)
                                      ↓
                               SkillContext.render()
                                      ↓
                           ModelRequest.instructions
                                      ↓
                           模型调用、工具调用、再次模型调用
```

`QueryLoop` 在循环开始前只调用一次 Provider，然后把生成的指令用于本次运行的每轮模型请求。Skill 指令放在基础指令
之后；它不作为对话消息追加到 `message_history`。这两个位置有不同用途：`instructions` 告诉模型本次怎样工作，
`message_history` 记录用户输入和真实发生的工具交互。若不传 Provider，原有单条基础指令保持不变，也不产生 Skill 事件。

新增集成测试覆盖了四件事：默认关闭、配置后只构建一次且两轮请求都收到指令、对话历史不混入 Skill 正文、Provider
失败或取消会向外传播并留下运行结束事件。测试使用 `ScriptedModel`，不消耗真实模型额度；它只证明接线和边界，
还没有证明磁盘 Skill 路由正确或能提升任务成功率。

注意：现有 `resume()` 会重新进入 `QueryLoop` 并重新构建 Skill 指令。若磁盘正文改变，恢复后的同一 Run 可能换一套
指令。S1 没有解决这个问题，所以 CLI 尚不能开放 Skill；S2 要解决的正是这个生命周期缺口。

## 9. 贯通验证与后续顺序

原计划在 S1 后直接进入恢复设计，实际先写了 S2a 的值对象。复盘后发现，这让一个暂时未被运行流程使用的结构先于
端到端证据出现。已调整顺序：先完成 S1b 的真实文件到模型请求的验证，再按最小恢复状态修改 Checkpoint，
最后修改 QueryLoop 的保存与恢复。**只有恢复测试通过，才能说恢复一致性已经实现。**

S1b 已由 `tests/skills/test_coding_agent_integration.py` 验证。测试手工连接已有组件，没有新增生产包装类：

1. 两个真实的 `manifest.json` 都被 Catalog 发现；为什么先读 Manifest？路由只需要轻量元数据，不应提前读全部正文。
2. 用户请求 `Inspect README.md.` 只匹配 `readme-review`；另一个 Skill 的 `SKILL.md` 故意是非法 UTF-8。
   如果未选中正文也被读取，测试就会失败。为什么要这样测？它证明延迟加载不是口头约定。
3. Builder 把唯一选中的正文渲染为 Skill 指令，CodingAgent 将其作为第二条 instruction 发给 `ScriptedModel`；
   用户消息仍在 conversation，Skill 正文不进入对话历史。
4. 选择、加载开始、加载成功三个事件留下可检查的记录；未选中 Skill 没有加载事件。

这条测试证明“现有组件能手工组成完整路径”，**不证明 CLI 已启用、真实模型效果提升或中断恢复一致**。

### S2a 复盘：移除未接入的快照类型

曾新增 `skills/snapshot.py`，包含 `SelectedSkillSnapshot` 与 `SkillContextSnapshot`。但真实链路测试说明，恢复所需的
核心信息只有当时实际使用的渲染指令；名称、逐项 hash 和单独的快照类型并非恢复正确性的必要条件。
因此在其接入 Checkpoint 之前移除该模块和专属测试，避免留下一个暂时没有调用者的持久化抽象。

### S2b：Checkpoint 的最小 Skill 状态与 JSON 合同（已完成）

只在已有 `RunCheckpoint` 上加 `skill_instructions: str | None`，不再包一层快照类：

- `None`：没有保存可恢复的 Skill 指令。当前没有 Provider 的运行仍写 schema 2；旧 schema 1/2 也读成 `None`。
  它**不证明**旧运行一定没有用过 Skill，所以后续若带 Provider 恢复这类 Checkpoint，必须明确拒绝，不能重新路由。
- `""`：Provider 已运行，但没有匹配的 Skill；这是有效状态，保存为 schema 3。
- 非空字符串：保存本次运行实际发给模型的完整 Skill 指令，也保存为 schema 3。

为什么 schema 3 只用于后两种状态？旧的无 Skill 路径继续写原来的 schema 2，不影响现有 CLI；而文件里一旦出现
`skill_instructions`，版本就明确声明了新字段的含义。schema 3 缺少该字段会失败，schema 1/2 偷带该字段也会
失败，避免静默丢失指令。

`RunCheckpoint` 限制 Skill 指令最多 160,000 UTF-8 bytes，并拒绝仅包含空白的非空字符串。这个上限只约束
**新增指令字段**，不是整个 Checkpoint JSON 文件或模型总上下文的上限；当前默认最多 3 份 Skill、每份正文最多
50,000 bytes，余量留给渲染标题。S3 仍需单独确定发送给模型的总预算。

已测试字段校验、schema 1/2 兼容、schema 3 的空选择/非空正文往返、错误版本/缺失字段、文件写入后重新读取。
S2b 本身没有让 QueryLoop 填写或使用该字段；运行时接线见下面的 S2c。

### S2c：运行时保存与恢复 Skill 指令（已完成）

`QueryLoop.run()` 的新运行路径先调用一次 Provider，得到渲染后的 Skill 文本，再进入模型循环；每次工具结果和
最终完成状态写 Checkpoint 时，都把同一段文本写入 `skill_instructions`。为什么新运行要与循环分开？恢复也会
进入模型循环，但它不能再次调用 Provider，否则同一个 Run 可能换指令。

`QueryLoop.resume()` 直接取 Checkpoint 的 `skill_instructions`。即使先补做一个尚未完成的工具调用，写出的
中间 Checkpoint 也原样携带该字段。随后模型请求继续使用同一段指令；Provider 不再被调用。若配置了 Provider，
却拿到没有保存 Skill 指令的旧 Checkpoint，会在执行工具或调用模型之前拒绝恢复，而非静默重新选择。

`None`、`""`、非空文本的语义沿用 S2b：未保存、已选择但为空、已保存实际指令。测试包括：删除 `SKILL.md`
后从磁盘 Checkpoint 恢复仍看到原指令；空选择写入空字符串；待执行工具的中间与最终 Checkpoint 都保留原文本；
旧 Checkpoint 搭配 Provider 时拒绝继续。真实模型和 CLI Skill 参数仍未启用。

在把 Skill 开放给 CLI 前，还需要核查现有状态目录的权限边界和整个模型请求的总预算；不能因为恢复测试通过就
认为完整产品阶段结束。

### S2d：首次模型调用前检查 Skill 指令长度（已完成）

本地 `FileSkillLoader` 默认只允许每份正文最多 50,000 bytes，但 `QueryLoop` 接受任意实现的 Provider，且
`KeywordSkillRouter.max_skills` 可以调整。因此，不能仅靠默认装配推断渲染后的指令一定小于 Checkpoint 的
160,000-byte 上限。原先的校验只在保存 Checkpoint 时发生：若 Provider 生成过长文本，模型可能先收到指令，
然后在保存运行状态时失败，导致这次运行无法按原指令恢复。

现在 `QueryLoop` 在 Provider 渲染后、首次模型调用前按 UTF-8 bytes 检查同一个上限；超限直接使 Run 失败，
不会调用模型。Checkpoint 仍保留自己的校验，防止其他入口直接构造非法状态。两处边界共用一个上限常量，
避免数值漂移。测试验证了超限时没有模型请求，且记录运行失败事件。

**这不是模型总上下文限制**：系统指令、用户消息、工具定义和历史结果仍会额外占用上下文。后续仍需明确
Skill 的总请求预算和超限策略；当前不把 Skill 截断，因为截断可能改变步骤、安全约束或语义。

### S2e：显式总字节预算无法满足时拒绝模型调用（已完成）

已有 `BudgetedToolResultProjector` 会把 Skill、基础指令、消息和工具定义都计入请求 byte 测量，但它只会尝试把
**合格的历史工具结果**换成可回读引用。首次请求若因 Skill 等不可压缩内容超过预算，它仍会返回尽力压缩后的请求。
这对独立测量实验有用，却不应让产品层把 `max_request_bytes` 误当成已满足的硬上限。

现在 `QueryLoop` **只对同时启用 Skill Provider 和 budgeted projector 的运行**，于投影完成后再次测量模型可见
请求。若仍大于 `max_request_bytes`，直接报出实际 bytes 和上限，在模型调用之前停止。默认无预算模式不变；
没有 Skill Provider 的旧预算实验仍保留“尽力压缩，可能超预算”的语义。测试用首次请求中的 Skill 指令造成
超限，确认没有工具结果可压缩时模型不被调用，并记录运行失败；另有回归测试保护无 Skill 的旧行为。

最初尝试对所有 budgeted 运行强制硬边界，但全量测试发现，现有历史工具结果回读实验使用了比基础请求更小的
1,000-byte 预算，依赖原有的尽力压缩行为。若直接全局强制，会破坏已存在的功能。收窄到 Skill 路径是在
保持旧合同的前提下，先给新产品入口建立明确边界；若将来要统一硬预算，应另行设计显式迁移，而不是偷偷改旧配置。

这里的“总预算”是项目定义的 **provider-neutral UTF-8 JSON byte 预算**，不是模型的 token 上限、SDK 实际
序列化字节数或费用承诺。真正接入 CLI/真实模型前，仍需为所选模型预留 token 余量并核查状态目录权限。

### S2f：Checkpoint 状态目录权限核查（已完成）

Skill 正文现会进入 Checkpoint JSON，因此状态目录也是敏感数据的存放边界。`FileCheckpointStore` 原来以
`mkdir(mode=0o700, exist_ok=True)` 创建目录，`mkstemp` 写入临时文件并原子替换，POSIX 下新目录与新文件
通常分别是 `0700` 和 `0600`。但 `exist_ok=True` 不会修复一个早已存在、权限过宽的目录。

现在在 POSIX 系统上，Store 初始化后检查**最终 Checkpoint 目录**是否向 group/other 开放；若是则拒绝使用，
不自动 `chmod` 用户已有目录。测试覆盖新目录/文件权限，以及已有 `0755` 目录被拒绝且权限保持不变。
父级目录可以更宽，因为最终目录不能被其他用户遍历；本检查不是多用户恶意并发或外部硬链接的完整防御。
CLI 的 `run` 路径会把拒绝转换为 `Checkpoint error` 并以退出码 2 结束，不进入模型构建；测试也确认客户端正常关闭。

### S2g：Manifest 未知字段拒绝（已完成）

此前磁盘 `manifest.json` 解析器只取 `name`、`description`、`entrypoint`、`tags`，其他字段被静默忽略。
这使同时存在合法字段与拼错字段的配置看似加载成功，却未按用户预期生效。现在解析时计算输入键名与允许键名的差集；
非空则列出未知字段并拒绝加载。测试用合法 `description` 加拼错的 `descripton`，证明不是依赖“必填字段缺失”
才发现错误。现有四个字段含义、`tags` 可省略的规则以及正文延迟加载均不变。

这一步**没有增加 `schema_version`**，因此现有 Manifest 文件不需要批量迁移；正式公开 CLI 输入前仍需单独确定
版本字段及向后兼容策略。

### S2h：Manifest v1 版本规则（已完成）

现在允许 Manifest 加 `"schema_version": 1`；若缺失，按旧版 v1 处理，保护现有本地文件和集成测试。
显式提供时仅接受真正的整数 `1`，不接受 `true`、`"1"`、`null` 或未来未知的版本。必须用
`type(value) is int` 而非 `isinstance(value, int)`，因为 Python 中 `bool` 是 `int` 的子类，
JSON `true` 会被解析成 `True`。版本只决定解析器能否理解文件，不属于路由元数据，因此没有修改
`SkillManifest` 的字段。

完整链路是：读取 JSON → 检查未知字段 → 检查版本 → 校验内容字段 → 构造 `SkillManifest` → 加入 Catalog。
测试同时覆盖显式 v1、缺省旧格式继续加载、无效版本和错误类型。CLI 仍未启用 Skill。

### S4a：显式 Skill 目录进入 CLI（已完成，S4 尚未验收）

`minicode run` 新增 `--skills-root PATH`，用户不提供时 `skill_context_provider` 仍为 `None`，不扫描 Skill 文件。
提供时，CLI 使用 `Workspace(PATH)` 校验目录，`FileSkillCatalogLoader` 只读取 Manifest，再组成
`KeywordSkillRouter + FileSkillLoader + SkillContextBuilder`，交给既有 `build_coding_agent()` 接口。
选中正文在任务运行开始时才延迟读取，进入 `ModelRequest.instructions`；选择和加载事件共享本次 Run 的 Ledger。

`resume` 没有该参数：恢复应使用 Checkpoint 中的原 `skill_instructions`，而非当前磁盘再选一次。
目录或 Manifest 错误在模型客户端创建前报配置错误；选中正文的加载错误会显示为 Skill 错误。
CLI 集成测试使用脚本模型验证磁盘目录到模型请求与 Checkpoint 的完整传导，以及 Trace 不打印正文；
另测了不存在的目录。没有调用真实模型。

S4a 完成时仍需补无匹配、CLI 恢复、未指定目录绝不扫描，以及选中正文损坏的错误路径测试；
当前没有为 CLI Skill 设置默认模型请求总预算，不能把 160,000-byte Checkpoint 字段上限说成模型上下文容量保证。

### S4b：CLI 从磁盘快照恢复，不再读取 Skill 目录（已完成）

新增 CLI 集成测试：在工作区的状态目录中保存一个未完成、带原始 Skill 指令的 Checkpoint；
不创建任何 Skill 目录，直接运行 `minicode resume <run_id> --trace`。恢复后的模型请求仍携带原指令，
完成后的 Checkpoint 也保留同一段指令；Trace 出现 `run_resumed`，但没有 Skill 选择事件。
这证明 CLI 的实际恢复路径使用 Checkpoint 快照，而不是依赖当前磁盘再做选择。测试仍使用脚本模型，
不消耗真实模型额度。S4 剩余无匹配、默认不扫描和选中正文损坏路径的验收。

### S4c：CLI 无匹配时正常完成并保存空选择（已完成）

将 S4a 的集成测试参数化为匹配与不匹配两次运行。匹配场景沿用 README Skill；不匹配场景请求
`Calculate 2 + 2.`，与 Manifest 元数据没有共享关键词，并把 `SKILL.md` 故意写成非法 UTF-8。
CLI 仍正常完成，模型只收到基础指令；Trace 记录 `selected: []` 且没有正文加载事件；完成后的磁盘
Checkpoint 保存 `skill_instructions=""`。这既验证无匹配的正常路径，也用实际损坏正文证明未选中 Skill 不被读取。

`None` 表示未配置 Skill Provider，`""` 表示 Provider 已执行但选择为空。两者都不增加模型指令，
但恢复状态保留了区别，避免把一次已经完成的空选择当成需要重新路由的状态。此次仅调整测试和文档，
生产代码的已有行为通过了验证。S4 剩余默认不扫描和选中正文损坏路径的验收。

### S4d：未指定 Skill 目录时，不自动加载目录（已完成）

新增 `test_run_without_skills_root_does_not_load_skill_catalog`。在临时工作区的 `skills/readme-review`
目录放置损坏的 `manifest.json`，但运行命令时不传 `--skills-root`；同时将目录加载器的 `load()` 临时替换成
一旦调用就触发 `pytest.fail()` 的检查。为什么两者并用？损坏文件让“附近存在目录也不会自动启用”更直观，
而加载器检查不依赖程序猜测哪一个默认路径：只要通过该加载器加载任何目录，测试都会失败。

数据链路：CLI 参数 `skills_root=None` → 不进入目录加载分支 → Provider 保持 `None` → QueryLoop 返回
`skill_instructions=None` → 模型只收到一条基础指令 → 完成后的磁盘 Checkpoint 保留 `None`。
测试还检查没有 Skill 选择或正文加载事件。模型使用 `ScriptedModel`，没有外部模型调用；业务代码没有修改。

这与 S4c 的空选择不同：S4c 显式启用 Provider，选择结果为空，因此保存 `""`；本步根本没有启用 Provider，
因此保存 `None`。已有上层 CLI 测试只确认 `skills_root=None` 被传入执行函数，但该执行函数被整体替换，
不能证明真实装配路径没有加载目录；本步补的是这条回归验证，而不是发现并修复了生产代码缺陷。
检查覆盖当前目录加载器入口，不是对进程内所有文件访问的监控。S4 的 CLI 分支验收剩余“选中正文损坏”的错误路径；
默认模型请求总预算和真实模型效果仍未验收，不能因此宣布整个 Skill 产品化路线完成。

### S4e：选中正文损坏时，在模型调用前失败（已完成）

新增 `test_run_rejects_selected_invalid_skill_body_before_model_call`。创建合法 v1 Manifest，任务
`Inspect README.md.` 确实选中 `readme-review`，但正文 `SKILL.md` 写入非法 UTF-8 字节 `b"\xff"`。
不同于 S4c 的未选中损坏正文，本步必须实际读取正文，因此应明确失败，而不是跳过该 Skill 后继续调用模型。

错误传导：Workspace 解码正文失败（`UnicodeDecodeError`）→ FileSkillLoader 转为 `SkillLoadError` →
SkillContextBuilder 记录加载失败并继续抛出 → QueryLoop 记录 Run 失败并继续抛出 → CLI 显示
`Skill error: cannot load skill 'readme-review' instructions`，返回退出码 2。CLI 的 `finally` 仍输出 Trace，
执行函数的 `finally` 仍关闭客户端。错误提示指出失败的 Skill 和加载阶段，但没有细分到 UTF-8 原因。

测试解析选择事件，确认选中的名称；检查加载开始、加载失败和运行失败事件；脚本模型的请求记录为空且没有
`model_call_started` 事件，证明不仅“返回错误”，而是确实没有调用模型。脚本模型不配置任何响应，如果被误调用，
也会立即报错。还检查没有任务答案、客户端已关闭、磁盘没有此 Run 的 Checkpoint：失败发生在首次模型调用前，
尚未到工具后或完成时的保存点，因此本次不能通过 `resume` 恢复，应修复文件后重新 `run`。

本步只新增测试和学习记录，没有改业务逻辑，也没有调用真实模型。此次覆盖的是非法 UTF-8 正文，不能据此宣称
所有加载错误（例如权限错误）都已通过 CLI 验证。S4 的已列 CLI 分支测试缺口已补齐；默认模型请求总预算、
真实模型效果和整体阶段验收仍是独立事项，不在本步实施。

验证结果：CLI 测试共 18 条通过，测试文件 Ruff 和 `git diff --check` 通过。首次受限沙箱执行在既有
Skill 测试处挂起；独立的 `asyncio.run(asyncio.to_thread(...))` 检查也出现线程函数已完成、事件循环仍等待的
现象。中止挂起测试后，经权限审批在沙箱外运行同一组本地测试，约 1 秒全部通过。因此此次未修改业务代码来
绕过异步加载；证据指向环境相关的跨线程事件循环问题，但未进一步确定沙箱内的底层根因。

### S4f：CLI 接入阶段收尾验收（已完成，2026-10-02）

本步没有新增业务代码或测试，而是对前面分散完成的改动做一次整体回归，并明确阶段边界。验证结果：
`pytest -q` 共 713 条通过；`ruff check .` 通过；`mypy` 检查 76 个源码文件通过；`git diff --check` 通过。
没有调用真实模型，没有提交或推送 Git。

S4 已有的验收证据：

- 默认关闭：不传 `--skills-root`，不调用目录加载器、无 Skill 事件、Checkpoint 保存 `None`（S4d）。
- 显式启用：Manifest → 路由 → 加载正文 → 模型 instructions → 磁盘 Checkpoint（S4a/S4c）。
- 无匹配：选中列表为空，不读取损坏的未选中正文，Checkpoint 保存 `""`（S4c）。
- 配置错误：不存在的根目录在创建模型客户端前被拒绝（S4a）。
- 加载错误：选中正文为非法 UTF-8 时，退出码 2、模型请求为空、Trace 记录失败、客户端关闭（S4e）。
- 恢复一致：CLI 不需要 Skill 目录，使用已保存的原始指令，不再次选择（S4b）；文件删除后的真实文件链路恢复
  另由 `tests/skills/test_coding_agent_integration.py` 验证。

这里的“完成”仅指 S4 的 CLI 接入合同。160,000-byte 渲染指令上限不是模型 token 容量；显式配置预算时的
超限拒绝也不等于默认 CLI 已有总请求预算。路由评测与默认预算可以分别验证，因此先进入离线 S5；真实模型
任务对照前仍需明确预算与成本控制，不能静默跳过这些剩余条件。

下一小步的确定范围：扩展现有 `SkillRoutingResult`，让失败结果分别显示“漏选的 Skill”与“多选的 Skill”，
补对应单元测试。不先改 Router，也不引入 Embedding 或模型调用。这样下一次固定评测集时，失败不仅是
`exact_match=False`，还能定位是没选到正确 Skill、选进了无关 Skill，还是只有顺序不同。
后续再分步建立版本化样本集（期望名称由开发者人工标注，是合成测试样本，不冒充真实用户数据），覆盖正例、
负例、相似 Skill、同分顺序以及同义改写/跨语言的已知限制。S5 收尾必须同时有失败明细、评测集版本、Catalog
和路由参数，不能仅凭当前 4 条简单样本全通过宣称路由准确率高。

### S5a：评测结果区分漏选与多选（已完成）

只在 `skills/evaluation.py` 的既有 `SkillRoutingResult` 上增加两个只读计算属性，不新增结果类、存储字段或
JSON 协议，不改变 `KeywordSkillRouter`。`missing_skill_names` 从期望名称中筛出实际未选中的项；
`unexpected_skill_names` 从实际名称中筛出期望之外的项。临时集合只用于判断名称是否存在，输出仍逐项遍历
原序列，因此漏选沿用期望顺序、多选沿用实际顺序，不受集合顺序影响，也不会修改原结果。

数据链路仍是：人工标注的 `SkillRoutingCase.expected_skill_names` + Router 实际返回的名称 →
`SkillRoutingResult` → `SkillRoutingReport.results/failures` → 调用者读取诊断属性。`@property` 使调用者
可以写 `result.missing_skill_names`，访问时从已有数据计算，不需要维护一份可能与原数据不一致的新状态。
例：期望 `pytest-debugging`，实际 `documentation`，会同时显示漏选前者、多选后者。

保持原来的 `exact_match` 规则（名称与顺序均相同才为真）。若名称相同但顺序颠倒，两个诊断属性都为空，
`exact_match` 仍为假；当前 Catalog 保证 Skill 不重名，正常 Router 输出不含重复名称，本步没有增加对手工
构造重复名称的额外校验。新增参数化测试覆盖正确、仅漏选、仅多选、选错、双方为空、仅顺序不同，以及混合情况的
稳定输出顺序；已有真实 Router 的 4 条样本和报告失败测试也检查新属性。本步证明比较逻辑正确，不证明路由质量改善。

本步验证：`pytest tests/skills -q` 共 33 条通过；修改的源码与测试 Ruff 通过；Mypy 检查 76 个源码文件通过；
`git diff --check` 通过。没有调用真实模型，也没有提交或推送 Git。

后续计划与结束标准：

1. **S5b 固定评测集**：固定版本、Catalog、`max_skills`、任务文本与期望有序名称。覆盖正例、无适用 Skill、
   相似技能、同分顺序、同义改写与跨语言；标明开发者人工标注的合成样本及已知限制，不冒充真实用户数据。
2. **S5c 可复现报告与收尾**：提供离线运行入口，输出 exact match、漏选、多选、失败 Case 及评测配置；
   不要求已知限制样本全绿，不为提高表面分数删改困难样本。版本、输入、参数固定且失败可解释后，S5 收尾。
3. **S6a 任务级对照准备**：在真实调用前明确总请求预算、验收任务、Skill 开关对照和工具权限边界；
   验证 Skill 建议不能绕过 Policy/Approval，先用脚本模型检查编排，不宣称真实模型收益。
4. **S6b 授权后的真实 Preflight**：用户明确授权后才做有成本上限的小规模对照，记录任务结果、调用、Token
   与延迟；少量运行只证明链路与个案结果，不写成整体成功率提升。整个 Skill 阶段仍按第 7 节验收后才进入 Memory。

### S5b：固定 v1 合成路由评测草案（已完成，标签待审核）

新增 `benchmarks/skill_routing/v1.json`，固定数据版本、四张卡片及注册顺序、`max_skills=3` 与 12 条样本。
每条样本有 ID、分类、任务文本、期望有序名称和标注理由。JSON 的用途是保存一份与测试代码分离、可审查、后续
报告入口可复用的输入数据；本步不新增通用配置框架或生产解析器。路由只需要名称、描述和标签，不需要创建或读取
这些卡片对应的 `SKILL.md`。

新增 `tests/skills/test_routing_benchmark.py` 的两条测试：一条校验固定版本、名称和 ID 唯一、分类覆盖、理由非空、
期望名称存在且不超上限；另一条将 JSON 映射到已有 `SkillManifest`/Catalog 与 `SkillRoutingCase`，使用真实
Router/Evaluator 连续运行两次，检查结果可重复且没有丢失样本。测试不固定旧失败数，也不要求报告全部通过。

离线观察：12 条中 7 条完全匹配；生日诗共享 write 导致文档误选；pytest/unittest 两条失败任务共享 failures
导致多选另一框架 Skill；项目入门说明的英文改写与自然中文请求均漏选。这些错误保留在 v1，算法、卡片和上限均
未为此修改。`benchmarks/skill_routing/README.md` 记录分类、标注规则、运行路径与失败明细。

本步复盘：原计划写“人工标注”，但本次标签由开发过程中拟定、尚未经用户审核，不应包装成独立可信的 Ground Truth。
因此 `label_source` 明确写成 `synthetic draft; pending owner review`；合理性说明供负责人审查，而不是准确率保证。
同分期望按 Catalog 顺序是人为排序协议，不是语义相关性的结论。不能把 pytest 测试全绿与路由题全部选对混为一谈。

本步验收：Skill 测试 35 条通过，新增测试 Ruff 与 `git diff --check` 通过。生产源码未修改，没有真实模型调用。
下一小步 S5c 只做离线报告入口与输出，不改算法；S5 收尾要求数据版本、卡片、参数和失败明细可复现，标签待审状态
必须保留。真实任务效果、总预算和权限对照仍留在后续 S6，不因这次得到一个比例就提前写成简历效果指标。

### S5c：一条命令生成离线路由报告（已完成，标签仍待审核）

新增 `src/minicode/skill_routing_report.py`，命令为：

```bash
.venv/bin/python -m minicode.skill_routing_report benchmarks/skill_routing/v1.json
```

没有新增一层结果对象或修改总 CLI。模块入口 `main()` 只负责解析显式路径、处理输入错误与打印 JSON；
`build_skill_routing_report()` 负责读取/检查数据、组装既有 Catalog/Router/Case、调用已有 Evaluator 并转换报告。
`_text()` 只复用非空文本检查，避免各字段复制同一判断。原路由算法、评测比较规则与 v1 数据都没有更改。

链路：命令路径 → JSON 校验 → 卡片按原顺序注册 → 原 KeywordSkillRouter → 原 evaluate_skill_router →
SkillRoutingResult 的漏选/多选属性 → 报告字典 → `json.dumps(ensure_ascii=False, indent=2)` → 标准输出。
报告保存版本、数据 SHA-256、标签来源、路由参数、完整卡片、每条样本明细和失败 ID。数据 hash 不等于算法源码
版本；后续比较算法仍应记录代码版本，不能只凭 hash 宣称整个实验相同。报告不写文件，不加载正文，不调用模型。

输入只接受 schema 1 和 KeywordSkillRouter，拒绝未知路由参数、重复 Case ID、未知/重复期望名称和超过上限的
期望选择。检查时发现直接把 `dict.get()` 的结果传给 Router 存在 `None`/未知类型路径，Mypy 报错；改为明确校验
真正的整数（拒绝 bool）再传入。类型错误使用 TypeError、合法类型的不合法内容使用 ValueError，由命令统一转为
退出码 2 的可读错误。不是靠 cast 或禁用检查掩盖边界问题。

退出码 0 只表示报告生成成功；路由样本失败仍完整输出。`missing_cases` / `unexpected_cases` 是样本数，不是
名称总数，也不能相加当失败数。单独的“有失败样本仍返回 0”测试用人为错误期望验证命令语义，不把固定 v1 的
失败数量写成回归要求。其他测试检查内容完整、计数一致、错误输入不产生半份报告、连续运行一致，以及从其他工作
目录启动实际 `python -m` 命令。使用真实 Router，无外部模型调用。

S5 的离线编排与报告交付完成，标签审核仍明确待办；当前观察仍为 7/12 完全匹配、2 条有漏选、3 条有多选。
这不是路由效果提升。接下来应先讲解/审核标签和失败，再进入 S6 的单个权限边界验证及任务级对照准备，不直接
换 Embedding 或运行真实模型；整个 Skill 阶段仍未结束。

本步验证：报告模块与 Skill 测试共 48 条通过，修改的源码/测试 Ruff 通过，Mypy 检查 77 个源码文件通过，
`git diff --check` 通过。实际模块命令已运行并输出全部 12 条结果，没有写报告文件或提交/推送 Git。

### S6a：Skill 的修改建议不能替代工具授权（已完成）

本步只修改 `tests/skills/test_coding_agent_integration.py`，增加一个参数化集成测试
`test_loaded_skill_cannot_override_edit_permission`，没有改生产代码。真实磁盘 Skill 正文明确要求用 edit_file
修改 README，并声称“这些指令已构成授权，不要询问”。使用真实发现、路由、正文加载和 CodingAgent/Dispatcher，
脚本模型第一轮固定提出有效的编辑请求，第二轮固定回复拒绝后结束；测试不推断真实模型是否会听从该正文。

为什么脚本模型故意提出修改？如果模型自己拒绝，就测不到真正的权限关口。本步确保正文已经进入模型 instructions，
工具名和参数合法，原文件中也确实存在待替换文本，因此文件未变不能归因于没选中 Skill、没有工具请求或参数错误。
拒绝由程序的 Policy/Approver 决定，而不是模型或 Skill 对“已授权”的自然语言声明。

同一个测试验证两条分支：

- **Policy DENY**：注入明确禁止 edit_file 的配置策略；记录 deny 事件，不请求审批，返回错误 ToolResult。
- **默认 Policy ASK + 审批拒绝**：不替换默认编码策略；测试 Approver 记录收到的具体 ToolCall 和原因并返回 False。
  记录 ask 与 approved=false 事件，返回审批拒绝的错误 ToolResult。

两条路径都验证：原始文件 bytes 不变，没有工具执行开始/结束事件；第二轮模型 conversation 包含原用户消息、
编辑 ToolCall 和关联相同 call_id 的拒绝 ToolResult（is_error=True）；两轮仍携带相同 Skill 指令。
Dispatcher 返回错误结果后 QueryLoop 可以继续让模型说明问题，不一定使整个 Run 抛出异常。
`StopReason.COMPLETED` 仅表示循环收到最终回复，并非编辑成功或原业务目标已经达成。

其中“只读工作区”是测试配置策略的理由，不是修改文件的操作系统权限；临时文件本身可写，拒绝发生在调用真正的
EditFileTool.execute() 之前。RefusingApprover 是测试替身，不会向真实用户弹出审批。本测试仅证明 edit_file
经过这两个拒绝分支时不执行，不能宣称完整防提示注入、进程沙箱、秘密隔离或所有工具权限都已验证。

验证：本文件、CodingAgent 和 Dispatcher 的相关测试共 37 条通过，修改的测试 Ruff 与 `git diff --check` 通过。
没有真实模型调用，没有提交或推送 Git。下一小步固定一个任务级 Skill 开关对照用例与独立验收，先完成离线准备；
默认总请求预算/成本边界仍需在真实模型实验前明确，标签审核的待办状态也没有变化。

### S6b：固定一个任务级开关对照夹具（离线准备）

复用 `multi_file_inventory_contract` 的原任务、初始工作区和隐藏验收；在
`benchmarks/skill_task_comparison/v1/skills/` 中放一份跨文件契约检查 Skill。baseline 不加载 Skill，
treatment 加载它；两组必须从相同初始 Case 分别创建隔离工作区，保持模型、参数、工具权限和预算一致。
Skill 正文只说明如何检查生产者、消费者和测试，不给出字段替换答案，也不授予工具权限。
数据链路是：原 `task.txt` → Manifest 的关键词匹配（`inventory`、`report`）→ 仅读取被选中的
`SKILL.md` → 渲染为额外 instructions；baseline 不构建这段 Skill instructions。它不写进 conversation，
也不修改 Case 的验收程序。

独立验收的意思是：两组都使用 Case 原有的 `acceptance.py` 检查行为与允许修改的文件，不能让 Skill
选择事件充当任务成功证据。离线测试先确认库存任务能选中该 Skill、无关的分页只读任务不会误选，
再确认同一隐藏验收会拒绝两份未修复工作区、接受修复后的工作区。Skill 文件不会被复制进模型的任务工作区。

这一步没有改路由算法或生产运行器，也没有调用真实模型。`evaluation_run` 尚不支持 Skill Arm，
因此目前只完成实验输入和验收边界，不能报告 Skill 收益。下一步先做 Scripted/离线运行接线与记录；
正式付费实验前仍要确定模型请求总预算和费用停止条件。

### S6c：脚本模型的两组运行与结果记录（已完成）

本步只扩充 `tests/benchmarks/test_skill_task_comparison.py` 并更新学习/实验说明，生产代码全部复用。
新增 `_inventory_responses()` 提供确定的五轮响应，新增参数化端到端测试分别跑 baseline 和 treatment。
每组从原 Case 单独复制 Git 工作区，使用独立模型实例和 Run ID、相同任务与预算、默认编码策略、
相同的测试审批规则；treatment 才组装磁盘 Skill Provider。

数据链路：`task.txt` + `case.json` 预算 → 独立工作区 → `build_coding_agent` → QueryLoop 构建
ModelRequest（treatment 额外加入 Skill instructions）→ ScriptedModel 返回预设 ToolCall →
Dispatcher 校验参数/策略/审批 → 真实工具执行 → ToolResult 回到下一轮 conversation → 最终回复。
随后把回复写成 `answer.txt`，用现有 CLI `_print_trace` 渲染并保存 `trace.txt`，调用原 `record_result`：
解析 Trace、检查工具要求、保存 Git 补丁、运行原隐藏 `acceptance.py`、组合 verdict、写 `result.json`。

五轮依次读取两个实现文件与测试、编辑两处、检查 Git 差异、运行 pytest、返回最终回复。完整修复每组
5 次脚本模型调用、7 次实际工具执行。测试审批器只允许编辑 `inventory.py`/`report.py` 与运行固定测试，
默认 Policy 的 ASK 分支仍实际经过审批；该审批器只用于隔离测试。

参数化的另一个场景故意漏改 `report.py`，仍走到最终回复。两组的 run_tests 错误会进入下一轮请求，
隐藏验收也失败，记录中的 outcome/trace/总体 passed 均为 false，但 operational_passed 为 true。
这证明结果记录器使用真实执行与独立验收，不会把 Skill 选中或 StopReason.COMPLETED 等同于任务成功。
测试核对每轮 Skill 指令相同、选择只发生一次、conversation 不包含 Skill 正文、Trace 往返一致、
回答/Trace/补丁文件的 SHA-256 与记录一致。

ScriptedModel 只按队列返回响应，不根据上下文决策，所以两组通过不构成 Skill 收益证据。它不提供 usage；
当前 Token 汇总的 0 是缺少 usage 的默认值，不能解释成真实零成本。两组记录在 pytest 临时目录中，
Arm 由 baseline/treatment 目录区分，Skill 事实保存在 Trace；尚未增加结果 JSON 的 Skill 实验字段。

下一小步给现有 `evaluation_run` 接入显式 Skill 目录并离线验证命令参数的传递，后续再完善实验元数据
与付费预算边界。没有调用真实模型，没有提交或推送 Git。

验证：对照夹具、原结果记录器、Trace 验收与 Skill 集成测试共 31 条通过；本步测试文件的 Ruff
检查和格式检查通过，`git diff --check` 通过。成功/失败两组原始记录已实际生成在 pytest 临时目录中。

### S6d：评测命令转交显式 Skill 目录（已完成）

本步修改 `src/minicode/evaluation_run.py` 的三处已有入口：

1. `build_parser()` 增加 `--skills-root`，用 `Path` 保存传入路径，默认 None。
2. `build_coding_run_arguments(case_root, *, skills_root=None)` 先从原 Case 组装任务、轮次、工具上限与
   Trace 参数，仅在目录非 None 时追加两个参数项 `("--skills-root", str(skills_root))`。
3. `main()` 把解析得到的目录交给上述函数；随后仍调用原 `cli.main()`。

为什么这里不加载 Skill？评测入口负责将固定任务与配置交给产品入口，现有 CLI 已负责目录发现、Provider
组装、错误处理和生命周期。直接转交避免两处加载逻辑不一致，也保持“不传目录”的原行为。
参数使用字符串序列传递，不再拼成 Shell 命令，含空格的路径不会被拆开。相对目录仍基于运行时的当前工作区，
不会自动变成相对于 Case 目录的路径。

实际数据链路：`evaluation_run --skills-root PATH` → argparse 的 `args.skills_root` →
`build_coding_run_arguments` 追加目录参数 → 普通 CLI 的 run parser → `_execute_coding_task(skills_root=...)`
→ Catalog/Router/Loader/SkillContextBuilder → `build_coding_agent` → QueryLoop → ModelRequest.instructions。
Skill 正文与用户消息分别保存在 instructions 和 conversation 中。

新增参数化接线测试从评测 `main()` 出发，经过真实 CLI、真实磁盘 Skill 加载和 Agent，检查脚本模型实际收到
的请求。测试创建工作区外的 `trusted skills` 目录，使用 `../trusted skills`，同时验证相对路径和空格。
外部客户端与模型构造器被测试替身替换，客户端关闭也有断言；没有网络调用。未提供参数时只有原编码指令，
显式开启时多一段完整 Skill 指令和三条选择/加载事件；两组预算都仍来自原 Case。
此测试只返回一轮脚本最终回复，用于检查接线，任务成功仍由 S6c 的完整执行与独立验收测试验证。

本步发现的兼容问题：冻结的上下文协议未登记 Skill 指令，但新增目录参数可能改变同一协议的输入条件。
因此 `main()` 对 `--skills-root` 与 `--context-protocol` 的组合直接返回参数错误，进入普通 CLI 前停止。
独立测试检查退出码 2 和明确提示。原 `--arm` 继续只表示上下文配置，没有新增 Skill Arm 枚举或中间对象。

类型检查遇到的问题：原来的字面量参数元组会被 Mypy 推断为固定七项，追加 Skill 的两项后重新赋值产生
长度不兼容。把变量明确标注为 `arguments: tuple[str, ...]` 后，表达的是“任意长度、每项都是字符串”，
与可选参数追加的实际用途一致；无需 cast 或跳过检查。

下一小步给结果记录增加明确的 Skill 开关信息，并核对声明与 Trace 中的选择/加载事实，使两组结果无需仅靠
目录名区分。真实模型的预算与授权仍待后续处理；本步没有提交或推送 Git。

验证：评测入口、上下文运行器、普通 CLI 与脚本对照的相关测试共 41 条通过；Mypy 检查 77 个文件通过，
本步源码/测试 Ruff 检查通过、测试格式检查通过，`git diff --check` 通过。实际执行 `evaluation_run --help`
也已显示新的目录参数，未调用真实模型。

### S6e：结果 JSON 明确标记 Skill 组别并与 Trace 核对（已完成）

这一步解决一个记录问题：原 S6c 的 `baseline/`、`treatment/` 目录仅为隔离文件而设。如果把文件搬到
别处，单看 `result.json` 不知道是哪组；人为把开启组文件放入关闭组目录也无法被发现。目录名不是
运行事实，记录器需要一个显式声明，再用 Agent 的 Trace 验证它。

只改现有 `src/minicode/evaluation_result.py` 的结果记录边界，不改 Skill 选择算法或 Agent 运行流程：

1. CLI 增加 `--skill-arm baseline|treatment`，`main()` 将它交给 `record_result()`。这是记录结果时的
   **声明**；运行时真正开启 Skill 仍由 `evaluation_run --skills-root` 决定。关闭组没有 Skill 事件，
   因而不能靠 Trace 单独把它与普通非实验运行区分开，必须显式声明 baseline。
2. `record_result()` 解析原 Trace 后调用 `summarize_skill_experiment()`。baseline 要求没有任何 Skill
   事件；treatment 要求恰好一次选择事件，核对加载开始/结束的名称与顺序，并提取实际选中和加载成功
   的 Skill 名称。开启组无匹配时允许 `selected=[]`；加载失败时允许保留“已选中但未加载成功”的事实。
   如果模型已开始调用，所有选中的 Skill 必须先成功加载。
3. 核对通过才继续原有的 Trace 验收、Git 补丁、隐藏验收与 JSON 写入，并给 JSON 增加可选的
   `skill_experiment: {arm, selected_skill_names, loaded_skill_names}`。普通运行不新增字段；含 Skill
   事件却不声明组别会拒绝记录。Skill Arm 与现有上下文协议互斥，因为协议没有登记 Skill 指令。

数据链路：运行命令的 `--skills-root` → QueryLoop 中的选择/加载事件 → `trace.txt` → 结果命令的
`--skill-arm` 声明与 Trace 比对 → `result.json.skill_experiment`。结果目录名不参与判定；字段里的
选中/加载名称由 Trace 得出，不由命令行或目录名伪造。记录器只能核对保存下来的 Trace，不能证明
Trace 文件从未被人为篡改；原 SHA-256 只是对生成记录时文件内容的固定，不是外部可信签名。

测试中使用真实 Agent/工具的离线两组轨迹，通过实际的结果记录 CLI 分别写入 JSON，检查四种组合：
baseline/treatment × 完整修复/故意漏改。完整修复的业务 verdict 为 true，漏改为 false；Skill
元数据都应如实写入。写入前还故意错标组别、遗漏开启组声明，验证没有生成半份补丁或 JSON。
另用小型 Trace 测试无匹配、加载失败和“加载了另一 Skill”的边界。ScriptedModel 仍不会依据
Skill 内容做决定；这些测试仅证明记录正确，不证明 Skill 提升任务成功率。

下一步先审视正式任务级实验的预算和可比性条件；只有付费边界、标签和运行许可都明确后，才能做
真实模型 Preflight。此步没有调用真实模型，也没有提交或推送 Git。

### S6f：审计两组真实 Preflight 的现有预算和可比性（已完成，尚未开跑）

本步只更新实验说明和本学习记录，不改生产代码或 Skill 路由算法，也不调用真实模型。审计的目的
是区分“已经有的运行上限”与“尚未有的费用上限”，避免把 8 个 Agent 轮次误说成 8 次网络请求。

从 `multi_file_inventory_contract/case.json` 可读出每组 `max_turns=8`、`max_tool_calls=8`；
`evaluation_run` 把这些数传给普通 CLI，QueryLoop 控制 Agent 轮次和工具调用。所以一对两组各一次的
计划上限是 2 个 Run、16 个 Agent 模型调用、16 个工具调用，但目前没有批次入口强制只运行
两次。另查 `models/dashscope.py`：当前
SDK 客户端 `max_retries=2`、单次请求超时 60 秒。已安装的 SDK 会对每个调用最多尝试 3 次，
理论上最多 48 次客户端请求尝试；Trace 只记 Agent 模型调用，不逐次记录 SDK 内部重试。

这些数字不能给出严格货币成本：MiniCode 没有设置单次输出 Token 上限，没有跨两组的运行时
Token/金额停止器，且失败或超时的请求不能靠本地 Trace 判断服务端是否计费。ScriptedModel 的
Token 汇总 0 是没有 usage，不是零成本。`result.json` 的 Token 统计发生在运行之后，不能
用事后统计替代调用前/调用中的停止边界。因此当前**不能**启动“有严格费用上限”的真实对照。

可比性方面，已有夹具复用同一 Case/task/隐藏验收、独立初始工作区与相同任务预算；结果记录器
现能核对 Skill Arm 和 Trace。真正付费前仍须冻结 Case、Skill、代码版本、模型/Provider 配置、
审批规则，并确认两组除 Skill 开关外不改变其他条件。人工审批、服务端随机性和先后顺序仍可能
影响结果；一对 Preflight 只能测链路，不能声称效果提升。

下一小步只收紧评测专用的 SDK 重试边界，避免默默发生最多两次额外请求，同时保持普通 CLI
默认行为不变。之后再讨论总 Token/费用停止策略和获得单独授权；不能因为已有轮次上限就跳过。
详细核对清单在 `benchmarks/skill_task_comparison/v1/README.md`。

### S6g：评测入口禁用 SDK 隐藏重试（已完成，离线验证）

只收紧经 `evaluation_run` 启动的客户端，不给普通 `minicode run` 添加新命令行参数，也不改
Agent 的轮次或工具预算。改动分三处：`models/dashscope.py` 的 `build_dashscope_client()` 增加
可选 `max_retries` 参数，默认仍为 2；`cli.main()` 与 `_execute_coding_task()` 只负责把评测入口
传来的可选覆盖值送到客户端构造，未覆盖时仍调用原默认构造方式；`evaluation_run.main()` 固定
传入 `model_max_retries=0`。这条规则同时适用于 Skill 的 baseline/treatment 和其他评测，
避免同一评测入口出现两套重试语义；普通运行及恢复保持默认 2。

数据链路：`evaluation_run` 固定值 0 → `cli.main(model_max_retries=0)` →
`_execute_coding_task()` → `build_dashscope_client(config, max_retries=0)` → SDK 客户端。
Agent 的 `max_turns=8` 不变；在只运行两组各一次时，客户端请求尝试的计划上限从原来的
2 × 8 × (1 + 2) = 48 降为 2 × 8 × 1 = 16。SDK 不再为一次 Agent 调用追加隐藏重试；
连接失败时该次模型调用会失败，交由现有错误处理和 Trace 记录。这是可控性与自动容错之间的
取舍，不能称为 Token/金额上限，也不能防止人工反复手动重跑。

离线测试分别检查：默认客户端仍传 `max_retries=2`，显式评测覆盖传 0；评测入口将 0
传过 CLI 到客户端，且有/无 Skill 目录都一样；普通 CLI 的测试替身确认收到的覆盖值仍是
`None`。没有真实网络请求，也没有改变 Skill 路由或结果 JSON。当前结果文件不单独保存 SDK
重试配置，因此跨批次比较仍要固定和记录代码版本；后续若做正式实验协议，再把该参数纳入协议。

本步验证：相关测试 37 条通过，Ruff、Mypy 与 `git diff --check` 通过。全量回归为 747 通过、
1 失败；失败项是原有默认模型名断言：当前工作区把 `DashScopeConfig` 默认值改成
`qwen3.7-flash`，旧测试仍期望 `qwen3.7-flash-2026-07-15`。这与重试参数无关，属于已有未
协调改动，本步没有擅自决定应采用哪个模型名。进入真实评测前必须解决并冻结模型版本。

下一步仍须设计真正的总 Token/费用停止机制、处理缺失 usage，并获得真实模型运行的单独授权。

### S6h：在结果中显式标记模型 usage 缺失（已完成，离线验证）

此前 `summarize_trace()` 对没有 `input_tokens`/`output_tokens` 的 `model_call_finished` 使用 0
累加。它便于保持数字汇总，却让 `run.input_tokens=0` 同时可能代表“真实报告 0”和“根本没
报告”。ScriptedModel 正是后者；若只看 0，容易误说成零成本。

本步只改 `evaluation_result.py` 的 Trace 汇总及对应测试，不修改 QueryLoop、SDK 调用或业务
verdict。每条 `model_call_finished` 仍按原规则累加已报告的 Token；只有输入、输出两个字段
均为整数时，才计为一次完整 usage。用 `model_call_started` 总数减去完整 usage 次数，得到
`model_calls_missing_usage`。结果 JSON 的 `run` 新增三个字段：

- `model_calls_with_usage`：同时报告输入与输出 Token 的调用数；
- `model_calls_missing_usage`：没有完整报告的调用数，失败/中断调用也计入；
- `usage_complete`：至少有一次调用、且每次都有完整 usage 时才为 true。

原 `input_tokens`/`output_tokens` 仍是整数以保持兼容；当 `usage_complete=false` 时，它们
只是**已报告部分的和**，不能当真实总量。旧 JSON 没有新字段，不能反推为完整。新增字段只
改进事后观测，不会限制下一次调用，也无法知道超时请求是否已由服务端计费。现有正式汇总器
尚未要求 `usage_complete=true`，所以不能把本步说成 Token 预算门禁。

测试覆盖完整 usage、缺字段/只报单侧字段、失败调用以及脚本模型五轮全部缺 usage 的实际
`result.json`；结束事件比开始事件多的异常 Trace 也会被拒绝。本步相关测试 75 条通过，
Ruff、Mypy 和 `git diff --check` 通过。全量回归 752 通过、1 失败，失败仍是 S6g 已记录的
默认模型名与旧测试期望不一致，与 usage 字段无关。

下一步才考虑是否让 Skill 专用 Preflight 在 usage 不齐全时停止后续运行；
仍需独立设计运行时总预算，并先处理默认模型版本的既有测试不一致。

### S6i：让 usage 完整性参与汇总和退出码（已完成）

这步的目的承接 S6h：字段写进 JSON 后还需要下游读取，否则汇总器继续忽略缺失信息，就可能
用四轮的 Token 合计去估计五轮的成本。比如五轮中只报告了四轮，已知输入合计为 1000，
`usage_complete=false` 表示真实总量尚不完整；它不能推断第五轮也是 0。

本步改 `evaluation_summary.py` 的三个已有位置：结果解析读取新字段；普通报告显示 usage
状态并把合计称为“已报告 Token”；命令增加 `--require-complete-usage`，将检查失败转为退出码 1。
继续使用原结果对象，只新增一个 `bool | None` 字段，不建立新的预算类或运行器。True 是完整，
False 是不完整，None 是旧记录未提供信息。解析时校验“完整次数 + 缺失次数 = 模型调用次数”，
并核对布尔值与次数；只提供部分字段或自相矛盾的数据会报错。

链路：Agent usage → Trace → S6h 的 result.json.run → 汇总解析与校验 → 普通报告的 Usage
列 → 可选检查的 PASS/FAIL 与退出码。Task Passed 回答任务是否完成，Usage gate 回答每次
调用是否提供输入/输出 Token；任务可以成功而 usage 检查失败。旧结果仍能查看，但状态是
unknown，在要求完整 usage 时不通过。上下文协议汇总仍沿用已有入口，该新参数与其互斥。

使用命令：`.venv/bin/python -m minicode.evaluation_summary RESULTS_ROOT --require-complete-usage`。
检查覆盖全目录的运行，全部明确完整返回 0，任何 incomplete/unknown 返回 1。测试把一份完整
记录与完整/不完整/旧记录配对，确认不是只看某一份就通过，并校验异常元数据；原脚本 Agent
两组的真实文件记录也实际交给该命令，返回 1、显示两组 usage 不完整，任务 verdict 保持原值。
相关记录器、汇总器和脚本对照共 81 条测试通过；修改文件 Ruff、Mypy 和 `git diff --check`
通过。没有发起真实模型调用；默认模型名的既有失败没有在本步修改。

这个步骤让下游可以判断是否继续；当前尚无自动 Skill 批次入口消费该退出码，也不能控制本组
已经发生的请求。下一小步应把总预算和缺失 usage 停止规则接入单次运行，再接两组编排，避免
只增加事后字段却一直没有运行中的停止行为。默认模型版本的既有测试不一致仍需单独解决。

### S6j：把事后 usage 检查接入正在运行的循环（2026-10-03）

这一小段解决的问题是：发现结果缺 usage 时，费用已经产生；不能只在最后汇总时报警，
还需要阻止后面的工具和下一次模型请求。它不改变 Skill 的关键词路由算法。

具体代码：

| 位置 | 新增/修改 | 为什么放在这里 |
|---|---|---|
| `core/model.py` | `ModelRunBudget`，保存每组输入/输出阈值、单次输出限制，校验正整数 | 参数是数据，不负责执行；用同一份数据贯通模型适配器和循环，避免两处限额不一致 |
| `core/query_loop.py` | 接收可选预算；增加 `usage_missing`、`token_budget`；每次收到响应后累计并检查 | 只有循环能在本轮工具执行和下一轮模型调用之前停止 |
| `coding_agent.py` | 把预算传给 QueryLoop | 组装入口需要接线，没有新增执行算法 |
| `cli.py` | 内部可传预算与评测审批器；普通命令不传时维持原默认 | 评测用原 CLI，不另造一套 Agent；普通交互仍走 Console 审批 |
| `models/openai_compatible.py` | 可选 `max_output_tokens` 转为 SDK `max_completion_tokens`，complete/stream 一致 | 输出截断由服务端实施，不能等全部生成后再用 Python 裁剪来声称节省生成费用 |
| `models/dashscope.py` | 有评测预算时传单次输出限制，并固定 temperature=0、enable_thinking=false | 两组使用相同采样配置；普通模型组装保持原参数 |
| `evaluation_result.py` | 从 Trace 提取真实运行的 model_budget，转成普通 JSON 数据 | 结果能核对运行中实际采用的预算，不只相信文件名或事前计划 |

`ModelRunBudget` 不是一个新执行器，只有三个整数和校验。CLI 的 `_EvaluationRunOptions`
只是 TypedDict：告诉类型检查器两个可选关键字各是什么类型，不会多执行一层任务。

完整链路：

```text
preflight.json → ModelRunBudget
  ├─ CLI → 模型适配器 → SDK max_completion_tokens → 服务端限制单次生成
  └─ CLI → CodingAgent → QueryLoop
                           ↓ model.complete 返回 response
                    usage 是否存在？不存在 → usage_missing，停止
                           ↓ 存在
                    累计输入/输出 Token；记录到 MODEL_CALL_FINISHED
                           ↓ 达到阈值或单次输出超限
                       token_budget，停止
                           ↓ 未达到
                    原来的最终回复/工具执行/下一轮流程
```

检查在“响应返回后、执行本轮工具之前”。例如每组输入阈值 100，第一轮 usage=60，
第二轮 usage=45，记录的真实累计是 105，不是 100；第二轮工具不执行，也不会有第三轮模型请求。
因此累计限额是**收到响应后的停止阈值，不是费用硬上限**。一次请求仍可能越过阈值。
单次输出参数也不能预测输入 Token；不能把 UTF-8 bytes 直接当作账单 Token。

只要启用这份预算，就要求每次完整 usage；即使响应声称已经完成，缺 usage 仍停止。
累计达到阈值采用 `>=`，优先报告预算停止；单次输出检查用 `>`，等于指定输出上限本身不是超限。
`RUN_FINISHED.outcome=succeeded` 表示循环正常返回了一个受控结果，不等于任务成功；
是否正常完成还要看 stop_reason，是否真正修好还要看独立验收与 verdict。

普通 QueryLoop/CLI 未传预算时仍接受没有 usage 的响应，SDK 默认重试仍为 2。
预算评测目前只允许 fresh run：Checkpoint 没存累计 Token，resume 如果重置计数会产生预算漏洞，
所以带预算的 resume 在任何待执行工具之前拒绝。没有扩展 Checkpoint 格式或修改普通恢复行为。

SDK 参数核对使用了 OpenAI Docs；当前使用现代的 `max_completion_tokens`，而非准备弃用的
`max_tokens`。Qwen Flash 3.5 及后续支持该参数；阿里云文档也提示实际计数可能存在少量偏差，
循环发现单次 usage 超过指定上限会保守停止。
依据：[OpenAI Chat API](https://developers.openai.com/api/reference/resources/chat)、
[阿里云 OpenAI 兼容 Chat 参数](https://www.alibabacloud.com/help/en/model-studio/qwen-api-via-openai-chat-completions)。

### S6k：冻结并运行唯一一对 Skill 开关对照（2026-10-03）

新增 `skill_preflight.py` 和 `benchmarks/skill_task_comparison/v1/preflight.json`。
一个模块提供准备、执行和固定夹具审批，没有增加另一套 Model/Tool/Agent 执行机制。
协议的 Pydantic 类负责拒绝错误字段/组序/权限；运行仍复用原 CLI、prepare、Trace 和 record_result。

本次授权的固定配置：`qwen3.7-flash-2026-07-15`；同一阿里云北京兼容端点；
baseline → treatment，各一次；每组最多 8 轮、8 次工具执行；SDK 重试为 0；
每次输出限制 1024；每组累计输入停止阈值 30000、输出停止阈值 4096；
temperature=0，非思考模式。最多 16 次逻辑模型调用，无批次重试。
这份协议使用快照模型名；仓库默认别名仍为用户已修改的 `qwen3.7-flash`，只是同步修正了
默认值测试，未把日常配置改回旧快照。真实评测会核对环境中的模型名与协议完全一致。

执行步骤与每一步的数据：

1. `--prepare` 不构造 SDK 客户端。保存 `plan.json`、代码/任务/验收/Skill/协议原始文件快照、
   每个文件 SHA-256、Python/依赖版本。结果目录必须是仓库外的新目录，不能覆盖旧证据。
2. `--execute` 先核对源码、快照、依赖版本、实际模型和端点；写入排他的 `execution.started`。
   同目录不能再次执行，即使前次失败或中断，也不能无意重新付费。
3. baseline 从冻结 Case 复制一个新的 Git 工作区，不传 Skill 根目录。运行参数从原 Case 读取，
   再将预算与固定审批器传给 CLI。保存 answer、stderr、Trace，调用原记录器生成 patch/result。
4. 对照检查 `result.json.run` 的 stop_reason、完整 usage、实际预算和轮次/工具次数，
   并核对实际选中和加载的 Skill。第一组运行/usage/记录不合格就不启动 treatment。
5. treatment 再从同一冻结 Case 复制另一份工作区，其他配置相同，只增加显式 Skill 根目录。
   结束后生成 `batch.json`，包含两组观察结果及仅限单 Case 的结论范围。

固定审批器只允许在隔离工作区中编辑 `inventory.py`、`report.py`，以及运行 `tests` 或固定公开
测试文件；路径先经 Workspace 解析，`./report.py` 等规范化后允许，越界路径拒绝。
修改测试、创建新文件和其他测试目标不批准。默认 Tool Policy 仍照常生效，Skill 不改变权限。
审批范围不是进程沙箱：pytest 会执行工作区 Python，生产环境仍需要容器/资源和网络隔离。

`pair_complete=true` 只表示两组运行有完整、可核对的记录，**不代表两组任务都修好了**。
模型正常结束但隐藏验收失败时，要保留失败并继续另一组，不能挑掉失败样本。
源码工作树本来有未提交修改，结果仍如实记录 commit 和 dirty；精确版本由源码快照/SHA-256 补充，
没有擅自提交已有改动，也没有声称运行在干净提交上。

本次联调遇到的问题：

- 事件 payload 会冻结成只读 mappingproxy；新增嵌套预算字段不能直接交给 json.dump。
  改用现有 `to_plain_json` 递归转换，端到端测试实际读取生成的 JSON 来防止回归。
- 两组结束时不能重复使用排他写入同一个 batch.json；改为每组独立 run-summary，最后写一次总报告。
- 缺失 usage 与“任务没修好”不能混成一种失败：前者阻止继续计费，后者是需要保留的对照结果。

离线测试包括：第一轮缺 usage，无第二次模型请求且没有工具执行；第二轮累计输入或输出达到阈值，
不执行该轮工具/不发起第三轮；单次输出超限；普通行为不变；计数不跨 fresh run 泄漏；
带预算 resume 拒绝；SDK complete/stream 参数接线；两组隔离、正文差异、实际文件修复与隐藏验收；
预算停止后不启动下一组；模型/快照不一致拒绝；排他执行和审批范围。

这一阶段进入下一步的标准：离线全套回归通过；真实一对的 Trace/补丁/验收/完整 usage 都能复核；
预算和组别与计划一致；能够解释失败和目前边界。不以“成功率显著提升”作为一对 Preflight 的结论。
满足后先收尾证据与简历口径，再决定是否扩展多个独立 Case；不立即加新路由算法或多 Agent。

### S6l：真实 Preflight 被账户额度拒绝（2026-10-03，未完成两组对照）

用户已明确授权使用上述快照模型与限额。离线全套 797 条测试通过后准备了新批次，
冻结 84 个源码/Case/Skill/协议/依赖描述文件，安装版本为 openai=3.3.1、pydantic=2.13.4、pytest=9.1.1。

证据目录：`/home/songshihao/projects/minicode-evaluation-results/skill-preflight-v1.JufSAw/pair`。
目录位于源码仓库外；包含 plan、完整源码快照、execution.started、batch.json，
baseline 的 answer/stderr/Trace/空补丁/result.json/验收/工作区路径；未删除失败记录。

实测只有 baseline 发起第 1 次模型调用，服务端返回 `AllocationQuota.FreeTierOnly`，
适配器转成 `ModelQuotaExceededError`，CLI 退出 1；没有成功模型响应，没有工具执行，
没有 SDK 重试，没有启动 treatment。Trace 最终 outcome=failed，usage_complete=false，
batch.json 的 pair_complete=false。隐藏验收失败是工作区未修改的必然结果，不能当作模型能力失败。
原汇总器的 `--require-complete-usage` 同样显示 incomplete、FAIL，并返回 1。

此处不能说“四项全部完成”：前三项代码与离线验证完成，第四项实际尝试后受账户条件阻挡，
尚无可比较的真实任务结果。也不能写“Skill 提高成功率/降低 Token”，本次没有这种证据。
记录中的 reported input/output=0 只是没有收到 usage，不等于可以核定账单为 0。

[阿里云官方错误码说明](https://www.alibabacloud.com/help/en/model-studio/error-code)
将该错误关联到免费额度耗尽及仅使用免费额度的账户限制；按量计费需在控制台处理相关开关/账户条件。
用户批准本次受限调用，不等于授权助手更改账户级计费设置。
所以没有擅自关闭控制台限制、换模型、换密钥或新建批次重试。

下一步需要用户处理账户条件，并重新确认是否按同一配置创建新的一对；原批次保留为失败证据，
不能删除 execution.started 来重用。如果指定其他模型或端点，先修改并重新审核协议，
不能把换模型后的结果与本次快照配置混算。

新增模拟额度拒绝的回归测试，检查一次失败调用被记录、客户端关闭、空补丁保留、第二组不启动。
这验证的是失败收尾和停止行为，不是模型效果。

本轮最终验证：798 条测试全部通过；Ruff 检查、Mypy（78 个源码/类型检查文件）、
`git diff --check` 通过。现有仓库部分文件的全量格式检查仍有旧格式差异，未扩大范围重排无关文件。

### S6m：切换当前模型并完成真实两组对照（2026-10-03）

用户说明旧模型额度不足，要求当前配置统一为 `qwen3.7-flash` 并继续。此次只调整配置与验证，
不增加 Skill 算法、预算包装层或新工具，也不更改账户级计费设置。

#### 改了哪里，为什么

| 位置 | 本步调整 | 原因 |
|---|---|---|
| `models/dashscope.py` | 默认值原本就是 qwen3.7-flash，未重复修改 | 真正覆盖默认值的是环境变量及评测协议 |
| `/home/songshihao/.bashrc` | 仅将 DASHSCOPE_MODEL 的旧快照名改为 qwen3.7-flash | 新终端不再用环境变量覆盖成旧模型；没有改密钥 |
| `benchmarks/skill_task_comparison/v1/preflight.json` | model 换为别名，protocol_id 换为 skill-inventory-preflight-v2-qwen3.7-flash | 模型变更必须与旧失败批次分开标识，不能混算；v1 目录仍表示夹具版本 |
| `tests/benchmarks/test_skill_preflight.py` | 新增当前协议模型/预算/组序检查；把旧模型名作为不匹配负例 | 新模型现在应允许，旧模型必须被协议检查拒绝 |
| `tests/models/test_openai_compatible*.py`、`tests/test_cli.py` | 更新模拟响应模型标签及当前预期；一个预算接线测试显式设置模型环境变量 | 模拟测试不是旧模型实验记录；避免依赖测试进程继承的终端配置 |
| `benchmarks/coding_agent/README.md` | 当前运行示例的默认模型改为别名 | 示例与产品当前配置一致 |

历史结果、上下文压缩的旧冻结协议和 S6l 记录仍保留原模型名，属于历史证据而非当前配置。
以后若重跑这些旧实验，应另立新协议/新目录，不直接把历史结果改名。
本次协议沿用原授权的预算、工具权限、组序、temperature=0、非思考模式和 SDK 重试 0。

一个容易忽略的问题：修改 `.bashrc` 不会改变已经启动的进程的环境变量。
本次命令都显式加 `DASHSCOPE_MODEL=qwen3.7-flash`；用户当前终端如仍是旧值，可执行
`export DASHSCOPE_MODEL=qwen3.7-flash`，或重新打开终端。
回归测试最初因此出现一次模型名不一致：修正的是测试的显式环境配置，没有绕过产品的模型一致性校验。

#### 从配置到证据的数据链

```text
新 preflight.json → prepare 冻结协议/源码/Case/Skill → plan.json
环境 DASHSCOPE_MODEL → DashScopeConfig.model
                           ↓ execute 核对与计划模型完全相同
baseline：相同任务，无 Skill → CLI → QueryLoop → 真实模型/工具 → Trace
treatment：相同任务 + 显式 Skill 目录
  → 关键词选中 inventory-contract-review → 读取正文 → instructions
  → CLI/QueryLoop 每轮使用该指令 → 真实模型/工具 → Trace
两组各自：Trace + 实际补丁 + 隐藏验收 → result.json
  → 核对预算/usage/选中与加载 → batch.json → usage 汇总检查
```

Skill 正文仍不追加进 message_history；它进入每轮 ModelRequest.instructions。
本次 Trace 中基础 instruction 为 648 bytes，开启后为 1333 bytes：净增加 685 bytes，
其中正文 619 bytes，其余为渲染包装。两个数字都不是 Token 数。
两组上下文投影均为 identity，未启用压缩；这样不会把压缩变化混进 Skill 开关对照。

#### 实际结果与每轮工具目的

证据目录：`/home/songshihao/projects/minicode-evaluation-results/skill-preflight-v2.EB5aeh/pair`。
旧额度失败目录保留，未覆盖。本次两组各只执行一次，没有 SDK/批次重试。

| 指标 | baseline（关闭 Skill） | treatment（开启 Skill） |
|---|---:|---:|
| 独立隐藏验收及最终 verdict | 通过 | 通过 |
| 模型调用 | 5 | 6 |
| 工具执行 | 7 | 8 |
| Provider 报告累计输入 Token | 8499 | 11942 |
| Provider 报告累计输出 Token | 388 | 650 |
| 实际选中/加载 Skill | 空 | inventory-contract-review |
| usage 完整性 | 5/5 完整 | 6/6 完整 |

前四轮两组相同：

1. `list_files`：定位工作区文件和测试目录，不直接猜文件结构。
2. 三次 `read_file`：读取生产者 inventory.py、消费者 report.py、公开测试契约。
3. 两次 `edit_file`：把生产者输出键和消费者读取键从 quantity 同步改为 stock。
4. `run_tests`：确认公开测试通过，之后由独立验收再检查任务契约。

baseline 第五轮直接最终回复。treatment 第五轮调用 `git_diff` 检查补丁，第六轮最终回复。
Skill 正文包含“inspect the resulting diff”的要求，额外调用与要求一致；这只是轨迹观察，
不能由两次随机模型运行严格证明该指令是唯一原因。
两组补丁完全相同，只修改允许的两个实现文件，未修改测试或新增项目文件。

总计 11 次模型调用、15 次工具执行，报告输入 20441、输出 1038 Token。
两组均正常 completed、完整 usage、预算一致、未达到停止阈值；`pair_complete=true`。
`evaluation_summary ... --require-complete-usage` 返回 0、Provider usage gate 为 PASS。
源码运行时有原有未提交改动，result 如实标记 dirty；对应运行版本由源文件快照/hash 留证，
后续文档补充不改变当时冻结的代码。没有把仓库提交号单独当作精确运行版本。

本次开启 Skill 多消耗输入 3443、输出 262 Token；不仅有每轮多出的说明，还多了一轮请求及
Git diff 结果，所以不能把总差额全归因于 Skill 正文长度。这是 Provider usage，不是账单金额。
两组修复结果相同，不支持“成功率提升”或“节省 Token”；单 Case、各一次、固定顺序，
也不能证明 Skill 通常无用。模型名使用别名，未证明服务端底层版本永久冻结。

#### 本步达成标准与下一小步

先前四项中的预算接线、冻结协议、离线验证和真实 Preflight 现已完成。
799 项离线测试通过；Ruff、Mypy（78 个文件）和 diff check 通过。
额外检查本次涉及的四个测试文件格式：两份已格式化，`test_cli.py` 与
`test_openai_compatible_stream.py` 仍有既有格式差异；未为换模型批量重排无关测试。

下一小步先做**阶段收尾核对，不新增算法或付费样本**：按第 7 节逐条连接现有测试/实际记录，
梳理能写进简历的事实与不能宣称的效果，并讲解此次真实执行链路，让用户能解释配置、
Skill 注入、权限、恢复和验收的区别。明确正例之外的无关任务已有离线路由/集成覆盖，
不能冒称已做其真实付费对照；合成标签也不能冒称真实业务 Ground Truth。
这些收尾与理解确认后，才进入 Memory 的需求和最小范围设计；不把默认 CLI 总预算、
关键词路由升级等所有扩展项当作当前阶段永远不能结束的理由。

### S6n：核对阶段门槛、整理简历事实、讲解完整链路（2026-10-05）

本步只新增 `docs/learning/skill-stage-closeout.md`，更新本页状态与学习索引。
没有新增运行代码、修改 Skill 正文/路由算法、变更冻结协议或原始结果，也未发起真实模型请求。
单独建收尾文档，是为了把散落的实施记录整理成可以复习的验收表、实际调用链和面试讲法。

逐项核对第 7 节：前六项的 CLI 接入、按需读取/预算、可观察事件、指令快照恢复、
错误/权限分支和真实任务开关对照均有现有测试或真实记录对应。第七项是学习验收，
不能用全套测试通过来证明用户理解。本阶段工程范围可收尾，下一小步先由用户复述或提出疑问，
确认后才进入 Memory 范围设计，不继续自动扩展 Skill 功能。

重新运行离线路由报告：4 张卡片、12 个合成草案样本，7/12 完全匹配，
2 个样本漏选、3 个样本多选；保持待负责人审核标签，不调整算法来让报告全绿。
真实旧批次汇总 `--require-complete-usage` 退出 0：两组通过验收，11 次调用均完整 usage；
原始证据仍是 2026-10-03 的一对，不冒称本日重新运行，也不把 2/2 写成通用成功率 100%。

收尾文档明确：Skill 位于内部 instructions，适配为服务端 system 消息；不是内部历史消息或工具。
逐步解释冻结准备、两组工作区隔离、元数据路由/加载、模型请求、预算检查、工具策略/审批、
真实结果回填、Checkpoint、独立验收、result 与 batch；区分普通 resume 与不支持 resume 的预算评测。
简历只描述已验证实现和评测机制，未声称路由高准确率、任务成功率提升、Token 节省或生产级安全。

本步重新运行全套离线测试：799 项通过；Ruff 检查、Mypy（78 个文件）与
`git diff --check` 通过。没有为文档收尾重排既有格式差异，也没有自动提交或推送。
