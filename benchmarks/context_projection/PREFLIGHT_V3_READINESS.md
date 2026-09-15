# Context Projection v3 Preflight 就绪审计

审计日期：2026-09-15

审计基线：MiniCode `bc2aba2`

结论：本地结构与配置已就绪，可以在用户明确授权付费调用后运行一对 v3 Preflight。

本审计没有调用 Provider，没有创建临时评测 Workspace 或 `results/v3-preflight`，也没有读取或
输出密钥内容。

## 1. 已通过项目

| 检查项 | 结果 | 证据 |
|---|---|---|
| Git 状态 | 通过 | 审计开始时 tracked/untracked 改动均为空 |
| v3 协议 | 通过 | 协议被 Git 跟踪，现有 schema 2 Loader 可解析 |
| 本地模型配置 | 通过 | 协议、代码默认值和当前有效环境均为 `qwen3.7-flash-2026-07-15` |
| Base URL | 通过 | 当前有效值为 DashScope OpenAI-compatible 默认入口 |
| 凭据存在性 | 通过 | `DASHSCOPE_API_KEY` 环境变量存在；未读取其值 |
| Preflight Case | 通过 | recall Case 的 manifest/task/acceptance/workspace 完整，8 个文件全部被 Git 跟踪 |
| 配对 Case | 通过 | repair Case 同样有 8 个跟踪文件，与 recall 的初始 Workspace 指纹一致 |
| Case 预算 | 通过 | repair 为 8 turns/8 calls，recall 为 9 turns/9 calls |
| Arm 传递 | 通过 | baseline 映射为 `None`，projection 映射为 `500` |
| 结果隔离 | 通过 | `results/v3-preflight` 不存在，不会混入 v1/v2 结果 |
| 本地评测链 | 通过 | run/result/summary/protocol/recall 五组专项测试共 44 项通过 |

## 2. 冻结指纹

| Case | task.txt SHA-256 | Workspace SHA-256 |
|---|---|---|
| `large_search_context_repair` | `740caa63add647194c6c204b238bd35564c68ceea0fd29b8ec7b53d7e158f431` | `a9523556b00e0756281a60521199c6f75f756a17d42ff5ac0eb57b0205744c87` |
| `large_search_context_recall` | `f4906b0a2770f547926788eeb1041fde5ac37f5772505d8d4ebcb110a862a69d` | `a9523556b00e0756281a60521199c6f75f756a17d42ff5ac0eb57b0205744c87` |

Workspace 指纹按排序后的相对路径、NUL 分隔符和文件原始 bytes 逐项计算。两者相同表明
初始项目是受控变量；task 指纹不同是预期现象，因为 recall 多了最终证据要求。

## 3. 已机器强制的 Preflight 门禁

v3 Preflight 结果汇总器会在落盘后检查：

1. baseline/projection 恰好各一条，Run ID 不重复；
2. 两组都通过 Safe Task Success；
3. projection 累计至少发生一条真实投影；
4. 失败或取消回读为 0；
5. Provider Usage 存在，合计不超过 45,000 input / 5,000 output Token；
6. answer、trace、workspace patch、result 工件齐全且哈希一致；
7. 协议快照、模型名、MiniCode commit、工作区干净状态和 Arm 投影配置一致。

recall 隐藏验收另外要求只成功搜索一次，且最终证据行的数量、首项和末项完全正确。

## 4. 实际执行边界

- 凭据存在不等于凭据有效，本地模型名匹配也不等于 Provider 当前一定接受该模型。只有真实调用
  才能确认这两点。
- 45,000/5,000 Token 是结果记录后的机器晋级门禁，不是发请求前的 Provider 硬限流。超限结果会保留并判定
  FAIL，但调用费用已经发生。
- MiniCode 没有显式设置 temperature，只能保证两个 Arm 使用同一本地配置和运行流程。
- 成功回读数会记录但不强制；模型通过中间消息保留事实同样可以通过。
- 正式 12-run 的总预算和配对顺序尚未机器强制，但不阻塞本次只有两条的 Preflight。正式实验前必须补齐。

## 5. 输出与审批安全

Agent stdout 只保存最终 `answer.txt`。stderr 必须完整保存为 `stderr.raw.txt`，再从全文唯一的
`Trace run_` 标记开始提取规范 `trace.txt`。不能把原始 stderr 直接交给结果解析器。

edit 和 run_tests 的 Approval 必须在看到当次 ToolCall 名称和参数后逐次人工决定。不得提前管道输入
多个 `y`；这会丢失 Approval 对具体副作用的审核语义。工具启动的子进程只继承允许列表中的操作系统变量，
不会把 `DASHSCOPE_API_KEY` 传给测试命令。

## 6. 真实运行时的顺序

只有在用户明确同意付费调用后才执行：

1. 在干净 commit 上于仓库外建立临时 batch 目录，并复制协议快照；
2. 为 baseline 准备独立 Workspace，人工审批调用，保留 answer、原始 stderr、规范 trace 和 patch/result；
3. 保留 baseline 成功或失败的原始结果，不删除、不覆盖；
4. 为 projection 重新准备另一个相同初始 Workspace，按同样流程记录；
5. 如果第一条结果已超过整个 Preflight 预算，则保留该结果并停止，不再运行第二条；
6. 两条完成后再将不可覆盖的原始结果收录到独立 `results/v3-preflight/`，运行 v3 专用汇总门禁。

不能在结果记录前先在 MiniCode 仓库内创建未跟踪的结果目录，否则 `evaluation_result` 会如实把
`minicode_dirty` 记为 true，使实验失去干净 commit 条件。

## 7. 审计结论

本地所有可在不调用 Provider 的前提下检查的 v3 Preflight 条件已通过。剩余不确定性是凭据/模型服务
的实时有效性、真实 Token 用量和模型自主行为，只能通过下一阶段的两次真实调用获得证据。
