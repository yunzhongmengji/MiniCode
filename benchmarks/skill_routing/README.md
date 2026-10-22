# Skill 路由评测 v1

本目录只评测“任务文本是否选中合适的 Skill 名称”，不读取 Skill 正文、不调用模型、不执行代码任务。
固定数据见 [v1.json](v1.json)。当前标签是本次开发过程中拟定的合成草案，**待项目负责人审核**；没有经过
独立专家标注，也不是线上用户数据。`rationale` 给出每条期望的理由，方便逐项审查。

## 固定输入

- 数据集版本：`skill-routing-v1`；数据结构版本：`schema_version=1`。
- 算法：现有 `KeywordSkillRouter`，`max_skills=3`，与当前产品默认上限一致。
- Catalog 注册顺序：`documentation` → `pytest-debugging` → `security-audit` → `unittest-debugging`。
- 四张卡片的描述、标签和顺序均保存在 JSON；没有对应正文文件，因为路由评测不需要正文。
- 覆盖：明确正例、无适用 Skill、相似技能、多 Skill、同分顺序、同义改写、跨语言。

期望名称按任务含义拟定，而非照抄算法输出。pytest 和 unittest 专用方法按框架区分；生日诗不属于项目文档。
同时适用且没有明确优先级时，本评测约定期望顺序遵循 Catalog 顺序，这是排序协议，不是更相关的证明。
改变卡片、顺序、参数、任务或标签会影响可比性，应保留 v1 并建立新数据版本，而不是覆盖困难样本来提高分数。

## 当前基线观察（2026-10-02）

按上述输入运行现有路由器，12 条中 7 条完全匹配。5 条不匹配如下：

| Case ID | 期望 | 实际 | 问题 |
|---|---|---|---|
| negative-shared-write | 无 | documentation | 共享 write 导致误选 |
| similar-pytest-failures | pytest-debugging | pytest-debugging、unittest-debugging | 共享 failures 导致多选 |
| similar-unittest-failures | unittest-debugging | unittest-debugging、pytest-debugging | 共享 failures 导致多选 |
| synonym-onboarding | documentation | 无 | 同义表达没有共享词，漏选 |
| cross-language-documentation | documentation | 无 | 中文请求与英文卡片没有共享词，漏选 |

这只是小规模合成草案的基线观察，不是企业真实准确率，也不是 Coding Agent 任务成功率。不为了得到全绿而修改
期望或减少 `max_skills`；后续算法比较必须使用相同输入和清晰的版本标识。

## 一条命令生成报告

从仓库根目录执行：

```bash
.venv/bin/python -m minicode.skill_routing_report benchmarks/skill_routing/v1.json
```

命令只向标准输出打印 JSON，不自动创建或覆盖文件，也不要求 API Key。输入路径显式传入；在其他目录运行时，
使用已安装 MiniCode 的 Python 和数据集绝对路径即可，不依赖当前目录猜测数据文件位置。

- `dataset_version`、`dataset_sha256`：标识样本版本与读取文件的 SHA-256；hash 只标识数据字节，不标识算法源码版本。
- `label_source`：保留标签待审核声明，不将草案标签升级为已验证的 Ground Truth。
- `router`、`catalog`：保留实际路由参数、卡片及注册顺序。
- `summary`：样本总数、完全匹配数/比例、存在漏选/多选的样本数，以及失败 ID。
- `results`：每个 ID 的分类、任务、标注理由、期望、实际、漏选、多选和完全匹配标志；失败 ID 对应的行即失败明细。

`missing_cases` 和 `unexpected_cases` 统计的是有该问题的**样本数**，不是名称总数；同一条样本可以同时漏选和多选，
两个计数不能简单相加当作失败总数。仅顺序不一致也属于完全匹配失败，此时两个差集可能都为空。

退出码 `0` 表示数据有效且报告生成成功，不承诺全部样本选对；无法读取、非法 JSON、错误版本/参数或不自洽的
期望标签返回 `2`，错误说明写标准错误，不输出半份报告。报告中的 `schema_version=1` 指报告结构版本，
输入数据的 schema-1 合同独立校验。未知路由参数明确拒绝，避免以为设置生效却被静默忽略。

## 如何检查数据与运行路径

从仓库根目录执行：

```bash
.venv/bin/pytest tests/skills/test_routing_benchmark.py -q
```

第一条测试检查版本、名称唯一性、样本 ID、分类覆盖、标注理由，以及期望名称确实存在于 Catalog。
第二条用真实 Catalog、Router、Case、Evaluator 连续运行两次，检查结果一致、样本没有丢失、选择满足上限。
测试不固定 7/12 作为必须维持的成绩，也不要求 `report.passed=True`，因此合法的算法改进不会被旧失败数锁死。
**测试通过表示数据和评测流程满足检查，不表示这 12 道题全部选对。**

报告逐项保留 Case ID、分类、输入、期望、实际、漏选、多选，并记录数据版本、卡片与路由参数。
标签审核或后续真实数据收集应单独记录，不能把本次拟定的草案宣称为已验证的 Ground Truth。
