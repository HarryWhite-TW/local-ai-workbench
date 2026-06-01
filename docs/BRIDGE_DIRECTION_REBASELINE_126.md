# Bridge Direction Rebaseline 126

## Purpose

This document rebaselines the bridge direction after drift was detected in planning language.

The goal is to restore alignment with `docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md`.

The target workflow is not safer manual copy/paste.

The target workflow is not user-managed manual relay.

The target workflow is a ChatGPT-centered bridge where the user primarily interfaces with ChatGPT.

This document is a direction and alignment document only.

This document does not authorize implementation.

This document does not authorize runner code.

This document does not authorize automatic commit.

This document does not authorize automatic push.

This document does not authorize automatic issue close.

This document does not authorize background watcher behavior.

This document does not authorize always-on polling.

This document does not authorize Lv5 full automation.

## Direction Lock Binding

```text
Direction Lock Binding
plan_path=docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md
plan_version=v1
primary_goal=chatgpt_dispatches_to_codex_and_reads_results_back
issue_role=core
manual_copy_paste_is_target=false
must_emit_plan_read_audit=true
```

## Rebaseline result

The active source of truth is `docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md`.

The bridge direction is:

```text
User
-> ChatGPT
-> GitHub task packet or shared auditable task surface
-> local relay / runner / Codex-side process
-> bounded Codex or bounded executor action
-> GitHub result packet or shared auditable result surface
-> ChatGPT readback and review
-> user key approval decisions through ChatGPT
```

The user should not be the long-form task relay.

The user should not be the long-form result relay.

The user should not manually copy ChatGPT instructions into Codex as the target workflow.

The user should not manually copy Codex results back into ChatGPT as the target workflow.

Manual relay may happen only as fallback when the bridge is missing, blocked, or intentionally paused.

## Drift found

A drift risk was found in the wording around Local Runner Bridge v0.

The previous wording could be read as if the target state were:

```text
ChatGPT prepares a prompt
-> user manually triggers or relays the local runner
-> user reports completion
```

That is not the target workflow.

That is at most a transitional implementation constraint.

## Correct interpretation of manual foreground start

Manual foreground start can exist in v0 only as a safety constraint or bridge gap.

Manual foreground start must not be described as the target end state.

Manual foreground start does not mean manual copy/paste is the target.

Manual foreground start does not replace the goal that the user primarily interfaces with ChatGPT.

Manual foreground start should be reduced or abstracted by later approved bridge work.

Any future reduction of manual foreground start must still preserve:

* no background watcher unless separately designed and approved
* no always-on polling unless separately designed and approved
* no broad issue scanning unless separately designed and approved
* no automatic commit
* no automatic push
* no automatic issue close
* no approval chaining
* user approval for high-risk phases

## Bridge states

## Fallback state

Fallback state means:

```text
ChatGPT writes long instructions
-> user copies them to Codex
-> Codex executes
-> user copies Codex result back to ChatGPT
```

Fallback is allowed only when the bridge is missing, blocked, or intentionally paused.

Fallback must be labeled as fallback.

Fallback must not be presented as the target workflow.

## Transitional v0 state

Transitional v0 state means:

```text
ChatGPT writes or references a task packet
-> GitHub or shared surface stores the task packet
-> user may manually start a foreground relay while direct bridge trigger is unavailable
-> relay / runner reads exactly one task packet
-> relay / runner validates schema and policy
-> bounded Codex-side or bounded executor action runs
-> result packet is written back to GitHub or shared result surface
-> ChatGPT reads and reviews result
-> user approves only key high-risk decisions through ChatGPT
```

Transitional v0 still has a bridge gap if the user must manually start the relay.

That gap must remain visible.

The transitional manual start should be treated as a safety and capability limitation, not the target.

## Target bridge state

Target bridge state means:

```text
User communicates with ChatGPT
-> ChatGPT dispatches a scoped task packet to an auditable bridge surface
-> Codex / relay / runner receives the task without user copy-paste
-> Codex / bounded executor performs the scoped task
-> result is written back to a ChatGPT-readable surface
-> ChatGPT reads and reviews the result
-> user only approves or rejects key high-risk decisions through ChatGPT
```

This is the intended direction.

The target still preserves risk gates.

The target still preserves explicit user approval for high-risk phases.

The target does not authorize full autonomous agent behavior.

## Approval model correction

High-risk approval means the user makes a decision through ChatGPT.

High-risk approval does not mean the user must manually relay task text.

High-risk approval does not mean the user must manually relay result text.

High-risk approval does not approve downstream phases.

Commit approval does not approve push.

Push approval does not approve issue close.

Approval chaining remains forbidden.

## Corrected next issue sequence

The corrected next issue sequence should advance both sides of the bridge:

* task dispatch from ChatGPT to Codex / relay
* result readback from Codex / relay to ChatGPT

The corrected sequence is:

## #126 Direction Rebaseline

Restore direction alignment and correct manual relay wording.

Expected files:

* docs/BRIDGE_DIRECTION_REBASELINE_126.md
* docs/LOCAL_RUNNER_BRIDGE_V0_ARCHITECTURE.md

## #127 Local Runner Result Packet v1

Define the result packet schema.

The result packet must support ChatGPT readback without the user manually pasting Codex output.

Expected files:

* docs/LOCAL_RUNNER_RESULT_PACKET_V1.md
* docs/examples/local_runner_result_packet.example.md

## #128 Task Surface and Result Surface v1

Define where task packets and result packets live.

This issue must avoid using a large long-lived roadmap issue as the primary result sink.

Expected output:

* task surface rules
* result surface rules
* short-lived or task-specific result surfaces
* canonical URLs
* issue/comment ID readback
* fallback rules

## #129 ChatGPT Task Packet Publication Proof

Prove that ChatGPT can write or prepare a task packet into the approved task surface.

This is a dispatch-side proof.

It must not rely on the user copying a long prompt into Codex as the target.

## #130 Foreground Relay Task Fetch MVP

Implement or validate a foreground relay that reads exactly one task packet from the approved task surface.

The relay may still require manual start in this transitional slice.

Manual start must be labeled as transitional.

The relay must not run as a background watcher.

## #131 Relay Invokes Bounded Codex-side Action MVP

Implement or validate one bounded Codex-side or bounded executor action.

The action must be harmless, scoped, auditable, and fail-closed.

This issue must prove dispatch from task packet to bounded execution.

## #132 Relay Writes Result Packet MVP

Implement or validate result packet writeback from the relay or Codex-side process to GitHub or another ChatGPT-readable result surface.

This issue must prove result readback without the user manually pasting Codex output.

## #133 No-copy / No-paste Bridge Smoke

Run one controlled bridge smoke:

```text
ChatGPT creates task packet
-> task packet appears on task surface
-> relay reads task packet
-> relay invokes bounded action
-> relay writes result packet
-> ChatGPT reads result packet
-> user does not paste task text
-> user does not paste result text
```

Manual foreground start may remain transitional if required.

The smoke must explicitly report remaining bridge gaps.

## #134 Docs-only Bridge Apply Candidate MVP

Allow one docs-only candidate through the bridge path.

This must still avoid stage, commit, push, PR, merge, issue close, and approval chaining.

## #135 Approved Commit Rail Through Bridge

Allow an explicitly approved local commit through the bridge rail.

The user approves through ChatGPT.

The bridge executes only the approved commit scope.

Commit approval does not approve push.

## #136 Approved Push Rail Through Bridge

Allow an explicitly approved push through the bridge rail.

The user approves through ChatGPT.

The bridge pushes only the approved commit.

Push approval does not approve issue close.

## #137 Approval-only End-to-End Smoke

Run one end-to-end smoke where the user primarily interacts with ChatGPT.

Expected behavior:

* ChatGPT dispatches the task
* bridge executes bounded action
* bridge writes result
* ChatGPT reviews result
* user approves high-risk phase through ChatGPT
* bridge executes only approved high-risk phase
* ChatGPT reads final evidence

This is the first real approval-only bridge smoke.

## Current status after rebaseline

The project is still in transitional bridge construction.

Manual copy/paste remains fallback.

Manual foreground start remains transitional when required by current safety constraints.

The target remains ChatGPT-centered dispatch and readback.

The user should only make key approval decisions through ChatGPT when the bridge reaches the intended target state.

## Completion criteria

#126 is complete when:

* Direction Lock is acknowledged as the source of truth
* manual_copy_paste_is_target=false is preserved
* user_only_interfaces_with_chatgpt_goal=true is preserved
* chatgpt_dispatches_to_codex_goal=true is preserved
* codex_result_readback_to_chatgpt_goal=true is preserved
* manual foreground start is labeled transitional
* manual relay is labeled fallback
* Local Runner Bridge v0 wording is corrected
* corrected next issue sequence is documented
* no runner code is created
* no scripts are created
* no tests are created
* no automation authority is expanded
