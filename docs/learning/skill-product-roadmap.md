# MiniCode Skill 产品化路线

核对日期：2026-09-22。状态：规划基线；本轮没有修改 Skill 运行时代码，也没有调用真实模型。

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

### 4.1 默认 CodingAgent 没有接入 Provider

`QueryLoop` 已有 `skill_context_provider` 参数，但 `build_coding_agent()` 没有接收和转交它。CLI 也没有 Skill 目录参数。
所以当前能力只能由测试或手工构造 QueryLoop 使用，不能描述成 `minicode run` 的产品能力。

### 4.2 恢复时可能换成另一份 Skill

当前 `_run()` 开始时会重新调用 Skill Provider。`resume()` 最终也会进入新的 `_run()`。如果新旧进程之间：

- `SKILL.md` 被修改；
- Manifest 路由字段被修改；
- Skill 目录被删除或替换；

同一个 Run 就可能在恢复后使用不同指令。Checkpoint 目前只保存对话、轮次、工具调用和完成状态，没有保存 Skill 选择
或正文快照。这是 CLI 接入前必须解决的正确性问题。

### 4.3 外部格式还不是稳定协议

`manifest.json` 目前没有 `schema_version`，解析器也没有拒绝未知字段。组件测试阶段可以使用，但成为公开 CLI 输入后，
需要明确哪些字段属于版本 1、旧文件如何处理、拼错字段是否立即拒绝，不能悄悄忽略用户配置。

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

### S2：定义可恢复的 Skill 快照

推荐方案：新运行第一次选择和加载 Skill 后，生成一个受大小约束的 `SkillContextSnapshot`，至少保存：

- 选中的 Skill 名称与顺序；
- 每份正文的 SHA-256；
- 本 Run 实际使用的渲染指令。

Checkpoint 升级新 schema 保存该快照。恢复时直接复用快照，不重新路由、不重新读取当前磁盘；旧 schema 1/2 仍按原来
“没有 Skill 快照”的语义读取。

完成标准：

1. 建立 Checkpoint 后修改或删除 `SKILL.md`，恢复请求仍使用原快照。
2. 空选择和“没有配置 Skill”可以区分于旧 Checkpoint 缺少新字段。
3. 快照大小受明确上限控制，Checkpoint 文件权限仍由现有 0700 状态目录保护。
4. Event 不记录完整正文，只记录名称、hash 和 byte 数。
5. 编解码往返、旧 schema 读取、文件存储和恢复集成测试通过。

这里选择“保存实际指令”而不只保存 hash，是因为只存 hash 会要求恢复时原目录必须仍然存在；目录被删除时无法继续。
代价是 Checkpoint 会保存一份本地指令正文，因此必须有大小和文件权限边界。

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
- `--trace` 能看到选择、分数、hash、加载结果和 byte 数，看不到完整正文。

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

## 8. 下一小步

下一小步严格执行 S1：只给 `build_coding_agent()` 增加可选 `skill_context_provider` 注入点，并用 ScriptedModel 证明默认
路径不变、配置路径只在 ModelRequest.instructions 中生效。不会增加 CLI、Checkpoint 字段或真实模型调用。
