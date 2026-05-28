# ChatGPT Codex Bridge Direction Lock

## Document Identity

title: ChatGPT Codex Bridge Direction Lock
version: v1
status: Active
owner: 駿弘
scope: Future ChatGPT-Codex bridge, relay, runner, and operator workflow work in this repository.

## Primary Goal

The target workflow is a ChatGPT-centered bridge:

1. The user primarily interfaces with ChatGPT.
2. ChatGPT prepares or writes a task packet into a shared auditable place, such as a GitHub issue body or issue comment.
3. A local relay, runner, or Codex-side process reads that task packet.
4. Codex executes the task in the local repo environment.
5. Codex or the relay writes the execution result back to a ChatGPT-readable place, such as a GitHub issue body or issue comment.
6. ChatGPT reads and reviews the result.
7. The user only makes key approval decisions through ChatGPT.

The strategic goal is not merely safer manual copying. The strategic goal is ChatGPT dispatching work to Codex and reading Codex results back through an auditable bridge.

## Non-Goal And Fallback Rule

A workflow where the user manually copies ChatGPT instructions into Codex and manually copies Codex results back into ChatGPT is only a temporary fallback.

Manual copy/paste relay must not be described as the target workflow. It may be used only when the direct bridge is missing, blocked, or intentionally paused. When used, it must be named as fallback and the remaining bridge gap must stay visible.

manual_copy_paste_is_target=false

## Source-Of-Truth Rule

This document is the source of truth for the bridge direction.

Before producing Codex execution instructions for bridge-related work, the task must read this plan and emit a PLAN-READ-AUDIT. If the proposed work does not align with the primary goal, it must identify whether the work is support, fallback, or drift_detected before continuing.

GitHub issues, runner packets, ReviewBundles, and audit headers may carry task-specific detail, but they must not override this plan's target workflow unless the user explicitly updates this plan.

## PLAN-READ-AUDIT Format

Future bridge-related tasks must emit this audit shape after reading the plan:

```text
PLAN-READ-AUDIT protocol=lawb.direction_lock_plan_read.v1
plan_path=docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md
plan_version=v1
primary_goal_read=<true|false>
task_alignment=<core|support|fallback|drift_detected>
manual_copy_paste_is_target=false
user_only_interfaces_with_chatgpt_goal=<true|false>
chatgpt_dispatches_to_codex_goal=<true|false>
codex_result_readback_to_chatgpt_goal=<true|false>
failure_reason=<none or exact reason>
```

## Task Role Definitions

core = directly advances ChatGPT to Codex dispatch and Codex result readback to ChatGPT.

support = improves safety, auditability, runner stability, documentation, or prerequisites needed for the core goal.

fallback = still requires user manual relay and must be explicitly temporary.

drift_detected = incorrectly treats manual relay as the target, or hides that the user is still acting as the relay.

## Future Issue Binding Block

Future bridge-related issues should include this binding block:

```text
Direction Lock Binding
plan_path=docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md
plan_version=v1
primary_goal=chatgpt_dispatches_to_codex_and_reads_results_back
issue_role=<core|support|fallback>
manual_copy_paste_is_target=false
must_emit_plan_read_audit=true
```

## Stop Rule

If the Direction Lock Plan is missing, unreadable, or not acknowledged with PLAN-READ-AUDIT, bridge-related work must stop before producing Codex execution instructions.

Do not continue by silently falling back to manual relay language. Stop, report the missing plan-read condition, and ask for ChatGPT review.

## Drift Examples

These are drift examples and must be flagged:

- Calling a manual relay workflow the final target.
- Saying the user should paste instructions into Codex as if that is the intended end state.
- Claiming that safer manual relay equals direct ChatGPT-Codex bridge.
- Adding more runner safety rails while hiding that the bridge is still missing.
- Optimizing copy/paste format while ignoring the missing direct bridge.

## Correct Next Strategic Target

After this document exists, the next strategic target should be a Bridge Feasibility Probe.

The Bridge Feasibility Probe should test:

1. ChatGPT can write a task packet to GitHub.
2. A local relay can read the task packet.
3. The local relay can invoke Codex or a Codex-side command in a bounded way.
4. Codex or the relay can write a result back to GitHub.
5. ChatGPT can read the result without the user manually pasting Codex output.

The probe must stay bounded, foreground/manual-start where required by current safety rules, and auditable. It must not implement a background watcher, automatic commit, automatic push, automatic close, approval chaining, or a high-risk Release Bundle.

## Lv4.5 Current vs Lv5 Reserved Status Note

Current implemented daily bridge is **Lv4.5**: foreground, explicit, issue-scoped, and manually started.

Current implemented dispatch/result schema pair for Lv4.5 is:

- `CHATGPT-DISPATCH protocol=lawb.dispatch.v1`
- `LAWBRUNNER-RESULT protocol=lawb.runner_result.v1`

`BRIDGE-TASK-PACKET` and `BRIDGE-RESULT-PACKET` remain a higher-level future bridge packet design layer. They must not be mixed with the current Lv4.5 dispatch path unless an explicit adapter is implemented, tested, documented, and approved.

`Lv5-lite` and `Lv5-safe` remain bounded future / higher-level workflow terminology and must not weaken current safety boundaries.
