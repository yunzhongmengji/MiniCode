---
name: fix_imports
description: Resolve circular imports, module initialization order issues, and package dependency errors in Python.
trigger_keywords: import, circular, ImportError, partially initialized, module, dependency
---
# Fix Python Imports Strategy

1. Identify the exact import cycle by inspecting top-level `import` and `from ... import ...` statements across the involved modules.
2. Prefer structural decoupling:
   - Move shared types or data models into a leaf module or use `from __future__ import annotations` with `TYPE_CHECKING` guards for type-only imports.
   - Replace eager top-level cross-imports with function-local imports only when runtime coupling is genuinely bidirectional.
3. Verify that every module in the package can be imported independently in any order without `ImportError`.
