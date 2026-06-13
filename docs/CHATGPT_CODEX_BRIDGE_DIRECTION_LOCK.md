# ChatGPT Codex Bridge Direction Lock

## Document Identity

title: ChatGPT Codex Bridge Direction Lock
version: v1.1
status: Active
owner: 駿弘
scope: Future ChatGPT-Codex bridge, relay, runner, operator, and connector workflow work in this repository.

## Primary Goal

The target workflow is a ChatGPT-centered bridge:

1. The user primarily interfaces with ChatGPT.
2. ChatGPT prepares or writes a task packet into a shared auditable place, such as a GitHub issue body or issue comment.
3. A local relay, runner, operator, or Codex-side process reads that task packet.
4. Codex executes the task in the local repo environment.
5. Codex or the local bridge writes the execution result back to a ChatGPT-readable place, such as a GitHub issue body or issue comment.
6. ChatGPT reads and reviews the result.
7. The user only makes key direction and high-risk approval decisions through ChatGPT.

The strategic goal is not merely safer manual copying. The strategic goal is ChatGPT dispatching work to Codex and reading Codex results back through an auditable bridge.

## Approved Operator Strategy

The approved implementation direction is:

1. **Phase B first:** a bounded local Bridge Operator automatically detects explicit GitHub dispatch requests while ChatGPT remains the primary user interface.
2. **Phase C later:** after Phase B is stable, evaluate a ChatGPT App / MCP connector to reduce the remaining local trigger gap.
3. **No replacement chat product:** do not build a separate local OpenAI API chat UI as the primary workflow interface.
4. **Manual PollOnce is recovery only:** it remains a supported fallback, not the target daily workflow.

The detailed source of truth for this approved strategy is:

```text
docs/BRIDGE_OPERATOR_V0_SPEC.md
```

## Non-Goal And Fallback Rule

A workflow where the user manually copies ChatGPT instructions into Codex and manually copies Codex results back into ChatGPT is only a temporary fallback.

Manual copy/paste relay must not be described as the target workflow. It may be used only when the direct bridge is missing, blocked, or intentionally paused. When used, it must be named as fallback and the remaining bridge gap must stay visible.

manual_copy_paste_is_target=false

Manual foreground `PollOnce` is also a recovery path once Bridge Operator Phase B becomes operational. It must not be presented as the final daily experience.

## Source-Of-Truth Rule

This document is the source of truth for the bridge direction.

Before producing Codex execution instructions for bridge-related work, the task must read this plan and emit a PLAN-READ-AUDIT. If the proposed work does not align with the primary goal, it must identify whether the work is support, fallback, or drift_detected before continuing.

For any task involving Bridge Operator behavior, automatic polling, Bridge Inbox semantics, Windows startup, local operator UX, or MCP / ChatGPT App integration, the task must also read `docs/BRIDGE_OPERATOR_V0_SPEC.md` and emit its required `BRIDGE-OPERATOR-SPEC-READ-AUDIT`.

GitHub issues, runner packets, ReviewBundles, audit headers, and implementation notes may carry task-specific detail, but they must not override this plan or the approved Bridge Operator specification unless the user explicitly updates the governing document.

## PLAN-READ-AUDIT Format

Future bridge-related tasks must emit this audit shape after reading the plan:

```text
PLAN-READ-AUDIT protocol=lawb.direction_lock_plan_read.v1
plan_path=docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md
plan_version=v1.1
primary_goal_read=<true|false>
task_alignment=<core|support|fallback|drift_detected>
manual_copy_paste_is_target=false
user_only_interfaces_with_chatgpt_goal=<true|false>
chatgpt_dispatches_to_codex_goal=<true|false>
codex_result_readback_to_chatgpt_goal=<true|false>
failure_reason=<none or exact reason>
```

## Task Role Definitions

core = directly advances ChatGPT-to-Codex dispatch and Codex result readback to ChatGPT.

support = improves safety, auditability, runner stability, documentation, operator reliability, or prerequisites needed for the core goal.

fallback = still requires user manual relay or per-task manual trigger and must be explicitly temporary.

drift_detected = incorrectly treats manual relay as the target, hides that the user is still acting as the relay, replaces ChatGPT with another required chat surface, or expands automation authority without explicit approval.

## Future Issue Binding Block

Future bridge-related issues should include this binding block:

```text
Direction Lock Binding
plan_path=docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md
plan_version=v1.1
primary_goal=chatgpt_dispatches_to_codex_and_reads_results_back
issue_role=<core|support|fallback>
manual_copy_paste_is_target=false
must_emit_plan_read_audit=true
```

Bridge Operator-related issues must also include:

```text
Bridge Operator Specification Binding
spec_path=docs/BRIDGE_OPERATOR_V0_SPEC.md
spec_version=v0.1
current_phase=<B0|B1|B2|B3|B4|B5|C>
must_emit_bridge_operator_spec_read_audit=true
```

## Stop Rule

If the Direction Lock Plan is missing, unreadable, or not acknowledged with PLAN-READ-AUDIT, bridge-related work must stop before producing Codex execution instructions.

If a Bridge Operator-related task does not read and acknowledge `docs/BRIDGE_OPERATOR_V0_SPEC.md`, it must stop before planning or implementation.

Do not continue by silently falling back to manual relay language. Stop, report the missing plan-read condition, and ask for ChatGPT review.

Any task that expands polling scope, startup behavior, action allowlists, write authority, approval authority, external connectivity, or the primary host model must stop for explicit user approval first.

## Drift Examples

These are drift examples and must be flagged:

- Calling a manual relay workflow the final target.
- Saying the user should paste instructions into Codex as if that is the intended end state.
- Claiming that safer manual relay equals a direct ChatGPT-Codex bridge.
- Adding more runner safety rails while hiding that the bridge trigger is still missing.
- Optimizing copy/paste format while ignoring the missing operator layer.
- Requiring the user to run PollOnce for every normal task and describing that as the final experience.
- Building a second required chat interface instead of keeping ChatGPT primary.
- Adding broad issue scans, hidden services, automatic commits, automatic pushes, automatic issue close, or approval chaining without explicit approval.

## Completed Feasibility Baseline

The bounded bridge feasibility path has been proven on the `workflow-codex-task-discipline` branch:

1. ChatGPT can write a structured request to GitHub.
2. A local Dispatcher can read and validate the explicit request.
3. Dispatcher can invoke Runner v1.
4. Runner v1 can invoke Codex through a compatible Windows launcher.
5. Dispatcher / Runner can write structured results back to GitHub.
6. ChatGPT can read and review those results without the user pasting a long Codex transcript.

The verified current schema pair is:

- `CHATGPT-DISPATCH protocol=lawb.dispatch.v1`
- `LAWBRUNNER-RESULT protocol=lawb.runner_result.v1`

The verified manual recovery path is:

```powershell
.\scripts\local_dispatcher_v1.ps1 -PollOnce -IssueNumber <N> -PostResultComment
```

## Correct Next Strategic Target

The next strategic target is Bridge Operator Phase B, governed by `docs/BRIDGE_OPERATOR_V0_SPEC.md`.

The ordered direction is:

1. Phase B0: specification and documentation reconciliation.
2. Phase B1: fixed Bridge Inbox read-only dry run.
3. Phase B2: one-shot delegation through existing PollOnce.
4. Phase B3: visible foreground bounded loop with lock, idempotency, heartbeat, pause, stop, logs, and bounded retry.
5. Phase B4: optional visible tray/status UX, not a chat interface.
6. Phase B5: separate approval for Windows login startup.
7. Phase C: later ChatGPT App / MCP feasibility and integration review.

This direction must remain bounded and auditable. It must not implement automatic commit, automatic push, automatic close, approval chaining, broad issue scanning, hidden unattended services, or a high-risk Release Bundle.

## Current Level And Terminology

Current implemented bridge baseline is **Lv4.5**: foreground, explicit, issue-scoped, and manually started.

Bridge Operator Phase B is the approved next development workflow layer. It does not replace or weaken Lv4.5 safety semantics; it automates the low-risk trigger path while preserving the existing Dispatcher and Runner authority boundaries.

`BRIDGE-TASK-PACKET` and `BRIDGE-RESULT-PACKET` remain a higher-level future packet design layer. They must not be mixed with the current `CHATGPT-DISPATCH` / `LAWBRUNNER-RESULT` path unless an explicit adapter is implemented, tested, documented, and approved.

`Lv5-lite` and `Lv5-safe` remain bounded historical/future workflow terminology and must not weaken current safety boundaries or override the Bridge Operator specification.

## Product Boundary

The public product mainline remains the Local Document-to-Knowledge Workbench.

Runner, Dispatcher, Task Packet, and Bridge Operator are development workflow tooling and portfolio engineering evidence. They must not be presented as autonomous product runtime features unless the user explicitly changes the product direction.
