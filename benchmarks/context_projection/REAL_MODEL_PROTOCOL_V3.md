# Context Projection 早期证据真实模型协议 v3

状态：已预注册，尚未运行真实 Preflight。

机器可读协议见 `real_model_protocol_v3.json`。v1 和 v2 的原始协议、结果与失败结论继续
保留，不得与 v3 结果合并。

## 1. v3 要回答的问题

v2 使用的 Preflight Case 没有稳定产生可投影的大型历史 ToolResult，因此 projection
六轮模型请求的 `changed_tool_result_count` 全部为 0。v3 改用已经离线证明能触发引用的
大搜索 Case，并增加一个真正需要早期搜索证据的最终答案。

它要同时观察三件事：

1. 自适应投影是否真正缩短至少一条历史 ToolResult；
2. 模型在早期证据仍被最终答案需要时，能否保持任务正确；
3. projection 是否自主调用 `read_tool_result`，以及该额外轮次对 Provider input Token 的影响。

第 3 项是观测量，不是强制门禁。如果模型已把关键事实保留在自己的中间消息中，不回读也可以是
合法的成功路径。

## 2. 唯一实验变量

| 配置 | baseline | projection |
|---|---|---|
| strategy | `identity` | `tool_result_reference` |
| 单结果候选阈值 | `null` | `500 bytes` |
| 完整请求最小净节省 | `null` | `1 byte` |
| 回读 Tool Spec 加载 | `null` | `on_reference` |

两个 Arm 继续使用相同模型、Case 初始文件、工具、Policy、Approval、预算和干净 MiniCode
commit。模型为 `qwen3.7-flash-2026-07-15`，关闭 thinking。MiniCode 当前没有为该入口显式传递
temperature，因此协议如实冻结为 Provider 默认值，不宣称 temperature 为 0。

## 3. Case 与 Preflight

正式 Case 是 `large_search_context_repair` 和 `large_search_context_recall`。它们的初始 Workspace
逐文件相同：前者只需修复共享根因，后者还必须在最终答案报告早期搜索中的客户端数量、
首项和末项。这个配对用来观察“后续是否仍需要早期证据”对回读和成本的影响。

Preflight 只运行 `large_search_context_recall` 的 baseline、projection 各一次，顺序固定为
baseline 后 projection，不进入正式统计。只有以下条件全部满足才能进入正式实验：

1. 两个 Arm 都通过 Safe Task Success；
2. projection 累计 `changed_tool_result_count >= 1`；
3. 失败或取消的回读为 0；
4. Provider Usage 和 answer、trace、workspace patch、result 工件完整；
5. 两次合计不超过 45,000 input Token 和 5,000 output Token。

Safe Task Success 已包含隐藏验收：代码必须修好、改动边界正确、只允许一次成功搜索，并且最终
证据行完全正确。

## 4. 预算依据

离线 Scripted 路径的累计模型可见内容为 baseline 45,615 bytes、projection 49,356 bytes。
projection 的每个投影请求更短，但强制回读多出一次请求，所以累计 bytes 反而更高。

这些是规范化 JSON 的 UTF-8 bytes，不是 Provider Token，也不用来预先宣布哪个 Arm 更省。
它们只用于确认 v2 的 30,000 input-token 上限对新路径可能过紧。v3 将两次上限设为
45,000，但这是结果落盘后的机器晋级门禁，不是 Provider 调用前的 input-token 硬限流。它能阻止
超预算的 Preflight 进入正式实验，但不能保证单次调用永远不超出预期消耗。

## 5. 正式样本与晋级标准

若 Preflight 通过，正式实验为 `2 cases × 2 arms × 3 repetitions = 12 runs`。每个 Case
按 `A B / B A / A B` 交替运行，减少固定顺序影响。

进入“可以考虑产品入口”阶段需要：

1. baseline 和 projection 都达到 6/6 Safe Task Success；
2. projection 的汇总 Provider input Token 至少下降 5%；
3. 任一 Case 的 input Token 退化不超过 5%；
4. 未授权副作用、失败或取消回读均为 0；
5. 12 份结果必须来自同一干净 commit，工件完整且哈希一致；
6. 累计不超过 270,000 input Token 和 30,000 output Token。

这仍是固定模型、两个高相似 Case 上的工程小样本，不能宣传为普遍有效或统计显著。

当前汇总器会机器检查正式样本数、Safe Task Success、Token 降幅、逐 Case 退化和回读失败，
但尚未解析 `formal_budget` 和 `paired_arm_order_per_case`。因此 270,000/30,000 Token 上限和
运行顺序目前是已冻结的操作者停止规则，还不是机器门禁；在正式实验前必须单独补齐自动校验。

## 6. 当前边界

本步只创建并校验协议，不创建 v3 结果目录、不复制 Workspace、不读取密钥、不调用 Provider。
下一小步是只读就绪审计：检查协议、Case、模型名、凭据存在性、干净 commit、预算和结果目录隔离，
并明确列出哪些规则已机器强制、哪些仍需在正式运行前补齐；仍不执行真实调用。
