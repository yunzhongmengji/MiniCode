---
name: debug_pytest
description: Diagnose and fix failing pytest test suites and cross-file logic or boundary bugs.
trigger_keywords: pytest, test, failing, assertion, boundary, pagination, pricing, bug, race, concurrency
---
# Debug Pytest Strategy

1. Reproduce the failure first by inspecting the relevant modules and running the targeted test file.
2. Separate root cause from symptoms: trace data flow across module boundaries before editing.
3. Check common failure classes:
   - Duplicate transformations across caller and helper modules (e.g. double discounts or double normalization).
   - Off-by-one slicing and empty/zero boundary inputs in pagination or indexing logic.
   - Missing `asyncio.Lock` around read-modify-write state transitions that yield across `await`.
4. Apply the minimal, cleanest fix and re-run `pytest -q` to confirm all assertions pass.
