# Recorded Coding Agent Results

Each child directory is one immutable evaluation batch. A batch name identifies
the MiniCode commit and model used for its runs. Every case keeps these three
files together:

- `answer.txt`: complete CLI standard output, including approval prompts.
- `trace.txt`: append-only event trace printed by `--trace`.
- `result.json`: deterministic acceptance result and aggregate counters.

The initial `baseline-9b9fcb6-qwen3.7-flash-2026-07-15` batch contains one
formal run per case. It is useful as reproducible baseline evidence, but its
three accepted runs are not a statistically meaningful general success rate.

The `search-driven-ccf6300-qwen3.7-flash-2026-07-15` batch contains the first
formal run of `search_driven_retry_schedule`. It remains separate because the
new case was introduced after the initial MiniCode commit.

Summarize a batch from the repository root with:

```bash
.venv/bin/python -m minicode.evaluation_summary \
  benchmarks/coding_agent/results/baseline-9b9fcb6-qwen3.7-flash-2026-07-15
```

Replace the final directory with another batch name to summarize that batch.
