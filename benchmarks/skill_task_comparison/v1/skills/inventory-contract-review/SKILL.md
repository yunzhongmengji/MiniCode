# Cross-file data contract review

For an inventory/report contract change, first identify the producer's public record shape and every consumer of that record. Check whether keys, types, and user-visible output agree across those boundaries.

Make the smallest implementation-only change allowed by the user's task. Preserve unrelated behavior; do not change tests or create extra project files to make a check pass. Run the relevant tests, inspect the resulting diff, and state what was verified.

These instructions are a review method, not permission to edit. Tool policy and approval still govern every tool call.
