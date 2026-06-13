# Task Packet v1.1 Discipline Report

## Purpose

Task Packet v1.1 turns the Codex task discipline described in `AGENTS.md` into verifiable task packet fields.

The goal is to make task boundaries explicit before any later execution layer interprets the packet.

This report records the engineering result, design boundary, and portfolio value of the current `workflow-codex-task-discipline` branch.

## Workflow Positioning

The workflow remains ChatGPT-centered:

```text
ChatGPT coordinates
-> Codex bounded execution
-> Task Packet validation
-> readback
-> user approval
```

Task Packet validation is an evidence and discipline layer in that flow. It helps ChatGPT and the user review whether a task is small, explicit, bounded, and safe to continue.

## v1 / v1.1 Compatibility

Task Packet v1 keeps its original behavior.

Task Packet v1.1 is an accepted protocol for structural validation.

Task Packet v1 does not require the v1.1 discipline fields. This preserves compatibility for existing v1 task packets unless a later task explicitly approves a breaking migration.

## Discipline Fields

Task Packet v1.1 adds these discipline fields:

* `task_mode` records whether the task is plan-only, patch-only, verify-only, or docs-only.
* `objective` keeps the task tied to one explicit goal.
* `max_allowed_files` keeps the task small and reviewable.
* `context_scope` records the allowed inspection context and prevents broad repository exploration.
* `repair_attempt_limit` prevents endless self-repair loops.
* `verification_command_policy` records whether verification is explicit, not required, or forbidden for the task mode.
* `verification_commands` records the exact commands allowed or expected.
* `scope_expansion_allowed` records whether the task may expand scope; for v1.1 discipline this must default to false.

## Validation Rules

Task Packet v1.1 structural validation requires the v1 fields plus all v1.1 discipline fields.

The accepted `task_mode` values are `PLAN_ONLY`, `PATCH_ONLY`, `VERIFY_ONLY`, and `DOCS_ONLY`.

`objective` must be a non-empty string.

`max_allowed_files` must be a positive integer, and the number of `allowed_files` must not exceed it.

`context_scope` must be a non-empty list.

`repair_attempt_limit` must be an integer, currently limited to `0` or `1`.

`verification_command_policy` must be one of `explicit_only`, `not_required`, or `forbidden`.

`verification_commands` must be a list. When the policy is `explicit_only`, the list must be non-empty. When the policy is `not_required` or `forbidden`, the list may be empty.

`scope_expansion_allowed` must be exactly `false`.

## Safety Boundaries

Task Packet v1.1 only strengthens validation and readback discipline.

It does not add runner, dispatcher, watcher, background automation, commit, push, GitHub writeback, PR creation, merge, issue close, or label change authority.

Validation success is not approval for external side effects. User approval remains required for high-risk phases.

## Test Coverage Summary

The focused validator tests cover existing v1 success behavior and v1 unknown top-level field blocking.

They also cover v1.1 success, missing discipline fields, invalid `task_mode`, `allowed_files` exceeding `max_allowed_files`, invalid `context_scope`, `scope_expansion_allowed: true`, and `explicit_only` with empty `verification_commands`.

Focused validator pytest is currently recorded as `23 passed`. This does not claim that the full project test suite has been run.

## Portfolio Value

This work shows a controlled AI-assisted development workflow where task intent becomes structured data instead of free-form authority.

It demonstrates how a local-first project can make AI collaboration safer without jumping to autonomous execution.

The v1.1 discipline fields make review boundaries visible: objective, allowed scope, verification policy, repair limit, and no scope expansion.

That makes the project easier to explain as a portfolio example of practical governance around Codex-assisted implementation.

## Future Backlog

The following are possible future tasks only and are not part of this report task:

* possible integration coverage for `task_surface_validation_flow`
* possible semantic validation for `expected_head` / `risk_level`
* possible guard function consolidation
* possible YAML parser replacement
