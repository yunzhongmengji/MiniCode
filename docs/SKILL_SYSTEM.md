# MiniCode Skill System

本文记录 M7 的 Skill 发现、路由、延迟加载、模型上下文注入和路由评估边界。

Skill 是供模型遵循的任务方法说明，不是可执行权限。它可以建议模型使用 `run_tests` 或 `edit_file`，但真正的工具调用仍必须经过 ToolDispatcher、Policy 和 Approval。

## 1. 为什么不加载全部 Skill

如果每次请求都把所有 `SKILL.md` 放入模型上下文，会产生三个问题：

- 无关说明消耗 Token，并挤占真实代码和对话的空间。
- 多份方法说明可能互相干扰，使模型更难判断当前任务重点。
- 未选中的外部 Skill 也会进入 Prompt，扩大不可信指令的暴露面。

因此系统把轻量元数据与完整指令分开：启动时只发现 Manifest，收到任务后先路由，再读取少量被选中的正文。

## 2. 磁盘布局

每个 Skill 使用一个独立目录：

~~~text
skills/
├── documentation/
│   ├── manifest.json
│   └── SKILL.md
└── pytest-debugging/
    ├── manifest.json
    └── SKILL.md
~~~

`manifest.json` 是用于发现和路由的轻量清单：

~~~json
{
  "name": "pytest-debugging",
  "description": "Diagnose Python pytest test failures.",
  "entrypoint": "SKILL.md",
  "tags": ["pytest", "testing"]
}
~~~

目录名必须与 `name` 相同。`entrypoint` 相对于该 Skill 自己的目录解析，不能借助 `..` 或符号链接读取其他 Skill 或工作区外文件。

## 3. 完整数据流

~~~text
磁盘中的 manifest.json
          ↓
FileSkillCatalogLoader
          ↓
     SkillCatalog
          ↓
KeywordSkillRetriever     广泛召回共享关键词的候选
          ↓
KeywordSkillRanker        按共享关键词数量排序
          ↓
KeywordSkillRouter        截取 max_skills 个结果
          ↓
FileSkillLoader           只读取被选中的 SKILL.md
          ↓
SkillContextBuilder       渲染为稳定的指令文本
          ↓
QueryLoop                 写入 ModelRequest.instructions
          ↓
Model Adapter             转为模型的 system messages
~~~

真实 `conversation` 不会混入 Skill 文本。这样 ToolCall、ToolResult 和用户消息仍保持原始结构，Skill 只是本次运行的附加指导。

## 4. 组件职责

| 组件 | 输入 | 输出 | 职责 |
|---|---|---|---|
| `SkillManifest` | name、description、entrypoint、tags | 不可变元数据 | 描述 Skill，不读取正文 |
| `SkillCatalog` | Manifest | 稳定有序的 Manifest 集合 | 按名称注册和查找 |
| `FileSkillCatalogLoader` | Skill 根目录 | Catalog | 发现顶层 `manifest.json` |
| `KeywordSkillRetriever` | 请求与 Manifest | 候选 Manifest | 保留存在共享词的候选 |
| `KeywordSkillRanker` | 请求与候选 | `RankedSkill` | 计算共享词数量并稳定排序 |
| `KeywordSkillRouter` | 用户请求 | 有上限的排序结果 | 组合召回、排序和截断 |
| `FileSkillLoader` | 已选 Manifest | `LoadedSkill` | 在独立目录和 byte 上限内读取正文 |
| `SkillContextBuilder` | 用户请求 | `SkillContext` | 选择、加载、记录事件并组合上下文 |
| `QueryLoop` | 对话历史 | `ModelRequest` | 提取最近用户消息，并在一次运行中复用 Skill 指令 |

QueryLoop 在第一次模型调用前只构建一次 SkillContext。后续工具轮次复用相同指令，不会因为 ToolResult 中偶然出现关键词而重新选择 Skill。

## 5. 当前关键词路由

当前基线算法将 Skill 的名称、描述和标签进行 `casefold()`，再按非单词字符切分。请求与 Manifest 的共享词数量就是分数。

例如：

~~~text
请求：Fix the failing pytest test.
Skill：pytest-debugging
元数据：Diagnose Python pytest test failures.
共享词：pytest、test
分数：2
~~~

召回与排序被拆成两个组件，是为了以后可以独立替换：召回可改为倒排索引或 Embedding，排序可改为规则、学习排序或模型重排，而 QueryLoop 和 Loader 不需要变化。

同分结果保持 Catalog 原有顺序，以确保测试、事件和回放结果可复现。

## 6. 延迟加载与边界

`FileSkillCatalogLoader` 只读取 Manifest；`FileSkillLoader` 只读取 Router 选中的入口文件。集成测试为未选中的 Skill 写入非法 UTF-8 正文，而完整运行仍然成功，由此证明未选中正文没有被提前读取。

当前加载边界包括：

- 每个 Skill 使用独立 Workspace 解析入口文件。
- 拒绝跨 Skill 的父级路径和外部符号链接。
- 限制单份指令的 UTF-8 byte 数。
- 拒绝缺失、目录、非 UTF-8 和空白正文。

这些检查限制读取范围和资源消耗，但 Skill 内容本身仍是不可信 Prompt，不能授权副作用。

## 7. 事件

SkillContextBuilder 与 QueryLoop 共享 EventLedger 时，模型调用前会记录：

~~~text
RUN_STARTED
SKILL_SELECTION_FINISHED
SKILL_LOAD_STARTED
SKILL_LOAD_FINISHED
MODEL_CALL_STARTED
MODEL_CALL_FINISHED
RUN_FINISHED
~~~

选择事件记录 Skill 名称和分数；加载完成事件记录 `succeeded`、`failed` 或 `cancelled`，成功时还记录指令 byte 数。失败和取消在记录后继续向外传播，不会被转成成功结果。

## 8. 路由评估

`evaluate_skill_router()` 接受一组 `SkillRoutingCase`。每个案例包含用户请求和期望的 Skill 名称，允许用空元组表达“不应选择任何 Skill”的负例。

报告提供：

- `total_cases`：案例总数。
- `exact_matches`：名称、数量和顺序完全匹配的案例数。
- `accuracy`：精确命中比例。
- `failures`：具体不匹配案例。
- `passed`：是否全部命中。

负例可以发现过度召回；正例可以发现漏选或错序。当前评估是确定性的离线基线，不代表真实仓库任务成功率。

## 9. 已知限制

- 关键词匹配不了同义词、语义改写以及跨语言表达。
- 分数只统计唯一共享词，没有词权重或字段权重。
- Manifest 格式还没有显式 schema version。
- Skill Catalog 和正文来自本地文件，没有签名、来源验证或持久缓存。
- 当前没有为组合后的全部 Skill 指令设置总 Token 预算，只通过数量和单文件 byte 上限间接控制。
- Skill 事件记录选择和加载，不记录完整正文，避免把大量或敏感 Prompt 复制进 Ledger。

后续语义召回或缓存优化必须继续使用现有 SkillRouter、SkillLoader 和 ModelRequest 边界，并以固定评估集证明收益。
