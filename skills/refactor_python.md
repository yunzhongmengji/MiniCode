---
name: refactor_python
description: Safely refactor Python modules to improve clarity, typing, and maintainability without changing behavior.
trigger_keywords: refactor, cleanup, simplify, typing, structure, readability
---
# Refactor Python Strategy

1. Establish behavioral baseline with existing tests before changing any code.
2. Keep public function signatures and return types backward-compatible unless explicitly asked to change them.
3. Prefer small, cohesive functions with explicit type annotations and clear error messages.
4. Re-run tests and static checks after refactoring to guarantee zero behavioral regression.
