# Context Projection v3 真实模型 Preflight 报告

运行日期：2026-09-15  
协议：`context-projection-evidence-recall-real-model-pilot-v3`  
模型：`qwen3.7-flash-2026-07-15`  
MiniCode commit：`e574fdd82ab676dec994234630282368c5569593`  
结论：**FAIL，不进入正式 12-run 实验。**

## 1. 门禁结果

| Arm | Runs | Safe success | Input tokens | Output tokens | Changed ToolResults | Readbacks failed/cancelled |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 1 | 1/1 | 17489 | 317 | 0 | 0/0 |
| projection | 1 | 0/1 | 18642 | 333 | 11 | 0/0 |

- Run shape：PASS
- Safe Task Success：FAIL
- Projection activity：PASS，`11/1`
- Failed or cancelled readbacks：PASS，`0/0`
- Provider input Token budget：PASS，`36131/45000`
- Provider output Token budget：PASS，`650/5000`
- Provider Usage、每 Run Artifact、协议快照：PASS
- Preflight gate：**FAIL**，CLI 退出码为 `1`

## 2. 两条运行分别发生了什么

baseline 在 8 次模型调用中执行了 6 次工具：`list_files`、`search_text`、两次 `read_file`、
`edit_file` 和 `run_tests`。它把 `service_config/timeouts.py` 中的超时从 3 修复为 30，测试通过，
而且最终回答准确保留了早期搜索证据：

```text
Evidence summary: 25 clients; first=accounting-ledger; last=transaction-journal.
```

隐藏验收通过，运行正常完成。模型一共返回 7 个 ToolCall，其中 6 个进入执行；另一个没有产生
工具策略或执行事件。现有规范 Trace 不保存该未执行调用的内容，因此本报告不推断它为何未执行。

projection 也完成了相同代码修改，测试通过，并且只有目标文件发生变化。它在 9 次模型调用中
执行了 9 次工具：除 baseline 的工具链外，又读取了更多文件并调用了 `git_diff`。第 9 轮模型仍
返回了一个 ToolCall，使模型请求的 ToolCall 总数达到 10；但 Case 只允许 9 轮，因此该调用没有
进入工具策略和执行阶段，运行以 `max_turns` 停止。`answer.txt` 为空，缺少必需的证据总结，隐藏
验收失败。

Trace 没有记录最后一个未执行 ToolCall 的具体工具名。报告不能根据前序行为猜测它是什么。

## 3. 压缩生效了，但整次任务没有更省

projection 的投影机制确实运行了：累计 11 个历史 ToolResult 被替换为短引用。按它自己的完整
历史轨迹计算：

```text
未投影时累计请求：89222 bytes
实际模型可见请求：68363 bytes
投影累计节省：    20859 bytes
```

但是，和另一条独立 baseline 轨迹相比，projection 多走了模型调用和工具调用：

```text
整次输入 Token：18642 - 17489 = +1153（+6.59%）
模型可见 bytes：68363 - 66192 = +2171（+3.28%）
```

因此两句话可以同时为真：

1. 投影让 projection 自己的每个相关请求比“不投影同一份历史”更短；
2. projection 的整次任务仍比 baseline 更贵，因为它形成了更长的执行轨迹。

这正是 Preflight 要检查的区别：局部压缩量不是最终业务收益，最终还要同时看任务成功、总 Token
和额外回读/重试成本。

## 4. 回读和因果边界

两条运行都只成功执行了一次 `search_text`。projection 没有调用 `read_tool_result`，所以成功、失败
和取消回读数都是 0；它选择了重新读取 Workspace 文件，而不是通过 Artifact ID 回读被压缩的
历史搜索结果。

本结果不能证明“压缩导致模型失败”，也不能证明“模型本来就会失败”。每个 Arm 只有一条真实
样本，入口没有显式固定 temperature，而且两条运行已经形成不同的模型输出与工具轨迹。可以确认
的只有：v3 这一次 projection 样本命中了压缩路径，但在轮次耗尽前没有提交最终答案，所以不满足
预注册的晋级标准。

## 5. 决策与下一步

按照预注册规则，v3 在 Preflight 门禁失败后停止：不补跑替换样本，也不执行正式 12-run。若在
看过本结果后调整 Case 预算、提示、回读工具可发现性或投影策略，必须使用新的协议 ID，不能把新
结果并入 v3。

下一小步只做离线失败分析：逐轮比较两条 Trace，定位 projection 为什么增加 `read_file`/
`git_diff` 以及为什么没有在测试成功后结束。分析完成前不修改算法，也不调用 Provider。

该离线分析已完成，详见 `TRACE_DIAGNOSIS.md`。它确认了“注册表回读后又被后续 `git_diff` 挤出
最新结果批次”的机械链路，同时保留了单样本不能证明因果关系的边界。

## 6. 原始证据

每个 Arm 都保存：

- `answer.txt`：模型最终 stdout；projection 在 `max_turns` 停止前没有最终回答，因此为空文件；
- `stderr.raw.txt`：Run ID、人工审批提示和 Trace 的完整 stderr；
- `trace.txt`：从原始 stderr 提取的规范 Trace；
- `workspace.patch`：隐藏验收前的工作区改动；
- `result.json`：验收、运行、预算、Trace、Usage、投影指标和 Artifact 哈希。

原始 stderr SHA-256：

- baseline：`3d48505299c665c2dc1814afa49eef41db15dfc2b79088820499aca3df00bf6c`
- projection：`4b42ed69ba2d4dddbf0df6402cb3ae9d421b01ca627bc5da5528491d2aec1f16`

根目录的 `protocol.snapshot.json` SHA-256 为
`fdf19356c96396eefb2d9a2ad3fa993a1a2ed1c39aab2c738995874f0b9116ae`，与运行时协议一致。
