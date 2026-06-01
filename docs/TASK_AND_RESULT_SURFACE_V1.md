Task and Result Surface v1

Purpose

This document defines Task Surface and Result Surface v1.

Task Surface v1 defines where task packets are published or referenced.

Result Surface v1 defines where result packets are written and read back.

The purpose is to support a ChatGPT-centered bridge where the user does not manually copy long task instructions into Codex and does not manually copy long Codex results back into ChatGPT.

This document is a schema and protocol document.

This document does not implement a runner.

This document does not authorize runner code.

This document does not authorize automatic commit.

This document does not authorize automatic push.

This document does not authorize automatic issue close.

This document does not authorize automatic PR creation.

This document does not authorize automatic merge.

This document does not authorize background watcher behavior.

This document does not authorize always-on polling.

This document does not authorize broad issue scanning.

This document does not authorize Lv5 full automation.

Direction Lock Binding

Direction Lock Binding
plan_path=docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md
plan_version=v1
rebaseline_path=docs/BRIDGE_DIRECTION_REBASELINE_126.md
task_packet_path=docs/LOCAL_RUNNER_TASK_PACKET_V1.md
result_packet_path=docs/LOCAL_RUNNER_RESULT_PACKET_V1.md
primary_goal=chatgpt_dispatches_to_codex_and_reads_results_back
issue_role=core
manual_copy_paste_is_target=false
must_emit_plan_read_audit=true

Relationship to the bridge

The intended bridge direction is:

User
-> ChatGPT
-> approved task surface
-> local relay / runner / Codex-side process
-> bounded Codex or bounded executor action
-> approved result surface
-> ChatGPT readback and review
-> user key approval decisions through ChatGPT

The user should not be the long-form task relay.

The user should not be the long-form result relay.

Manual task relay is fallback.

Manual result relay is fallback.

Manual foreground start may remain transitional in early v0 slices.

Manual foreground start must remain visible as a bridge gap.

Relationship to Task Packet v1

Task Packet v1 defines structured task input.

Task Surface v1 defines where that structured task input is located.

A task packet should be retrievable from exactly one approved task surface.

The relay or runner must not infer a task packet from natural language outside the approved task surface.

A task surface can reference an issue, comment, local file, or another approved location.

Task Surface v1 does not broaden the authority granted by Task Packet v1.

Task Surface v1 does not authorize execution by itself.

Relationship to Result Packet v1

Result Packet v1 defines structured task output.

Result Surface v1 defines where that structured output is written.

A result packet should be written to exactly one approved result surface.

ChatGPT should read the result packet from the approved result surface.

Result Surface v1 does not transform evidence into approval.

A successful result packet is evidence.

A successful result packet is not approval for any later high-risk phase.

Surface roles

There are four bridge-facing surface roles:

* roadmap anchor
* task surface
* result surface
* fallback surface

These roles must not be confused.

Roadmap anchor

A roadmap anchor is a long-lived planning issue or document.

Example:

GitHub issue #114

The roadmap anchor can describe the project sequence, current phase, and high-level audit trail.

The roadmap anchor should not be the primary long-term sink for every task packet and result packet.

Large long-lived roadmap issues are poor primary result sinks because they accumulate many comments and become harder to search and read back.

The roadmap anchor may still receive short visible audit markers during transitional phases.

The roadmap anchor may still point to canonical task or result surfaces.

Task surface

A task surface stores or references one active task packet.

A task surface should be scoped to one logical issue, one task packet, or one phase.

A task surface should be short enough for ChatGPT, relay, or runner readback.

A task surface should have a canonical URL.

A task surface should have stable identifiers such as issue number, comment ID, file path, or content hash.

A task surface should not contain multiple active task packets.

A task surface should not contain unrelated discussion that can be mistaken for task instructions.

A task surface should not be a large long-lived roadmap comment thread unless explicitly marked as fallback.

Result surface

A result surface stores or references one active result packet.

A result surface should be scoped to one logical issue, one task packet, or one phase.

A result surface should be short enough for ChatGPT readback.

A result surface should have a canonical URL.

A result surface should have stable identifiers such as issue number, comment ID, file path, or content hash.

A result surface should not contain multiple active result packets.

A result surface should not contain unrelated discussion that can be mistaken for result evidence.

A result surface should not be a large long-lived roadmap comment thread unless explicitly marked as fallback.

Fallback surface

A fallback surface is used when the approved task or result surface is unavailable.

Fallback surfaces may include:

* local stdout
* local file
* copied user message
* roadmap issue comment
* temporary diagnostic comment

Fallback must be labeled as fallback.

Fallback must not be presented as target bridge success.

Fallback must include remaining_bridge_gaps.

Fallback should be reduced by later approved bridge work.

Surface kinds

Allowed task surface kinds in v1:

* github_issue
* github_comment
* github_issue_body
* local_file
* local_stdout
* fallback_user_message
* unknown

Allowed result surface kinds in v1:

* github_issue
* github_comment
* github_issue_body
* local_file
* local_stdout
* fallback_user_message
* unknown

The preferred target surface kind is task-specific GitHub issue or GitHub comment.

A local file may be used during implementation slices.

local_stdout is fallback only.

fallback_user_message is fallback only.

unknown should usually make validation partial, blocked, or failure.

Canonical URL rules

Each GitHub-backed surface should include a canonical URL.

For GitHub issue surfaces, use the issue URL.

For GitHub comment surfaces, use the issue comment URL.

For local file surfaces, use a repository-relative path and optionally a commit SHA when available.

For local stdout fallback, canonical URL should be null and fallback must be explicit.

The canonical URL should be included in both task packet metadata and result packet metadata when available.

Surface identifiers

Each surface should provide stable identifiers.

Recommended identifiers:

surface:
  kind: github_comment
  url: "https://github.com/owner/repo/issues/123#issuecomment-123456789"
  issue: 123
  comment_id: 123456789
  path: null
  sha: null

For local file surfaces:

surface:
  kind: local_file
  url: null
  issue: null
  comment_id: null
  path: "docs/tasks/task-128.example.md"
  sha: "<optional_blob_or_commit_sha>"

Active packet rule

A surface must contain at most one active task packet or at most one active result packet.

If multiple active packets are found, the reader must fail closed.

A surface can include historical packets only if they are clearly archived and outside active packet markers.

The active packet should be delimited by protocol-specific markers.

For task packets, use Task Packet v1 boundary markers.

For result packets, use Result Packet v1 boundary markers.

Surface binding object

Task packets and result packets should reference surfaces using a surface binding object.

Recommended shape:

surface_binding:
  role: task_surface | result_surface | roadmap_anchor | fallback_surface
  kind: github_issue | github_comment | github_issue_body | local_file | local_stdout | fallback_user_message | unknown
  url: string | null
  issue: integer | null
  comment_id: integer | null
  path: string | null
  sha: string | null
  active_packet_count: integer
  fallback: boolean
  fallback_reason: string | null

The reader must reject active_packet_count greater than 1.

The reader must require fallback_reason when fallback is true.

Task surface requirements

A valid task surface must:

* include exactly one active task packet
* expose a canonical URL or fallback identifier
* identify logical_issue
* identify phase
* identify action_type
* identify risk_level
* identify allowed_files when relevant
* identify forbidden_operations
* identify stop_condition
* identify result target expectation
* avoid unrelated executable instructions outside the packet
* preserve Direction Lock constraints
* preserve approval gate constraints

Result surface requirements

A valid result surface must:

* include exactly one active result packet
* expose a canonical URL or fallback identifier
* identify the related task_packet_id
* identify logical_issue
* identify phase
* identify action_type
* identify risk_level
* identify result status
* identify changed_files
* identify high-risk action flags
* include evidence.summary
* include evidence.checks
* include failure fields when needed
* include next_recommended_action
* include stop_condition_reached
* avoid unrelated evidence outside the packet
* preserve evidence-not-approval semantics

Roadmap anchor usage rules

The roadmap anchor may be used for:

* project-level sequence
* short phase-visible audit markers
* pointers to canonical task surfaces
* pointers to canonical result surfaces
* human-readable progress summaries

The roadmap anchor should not be used as:

* the long-term primary task packet sink
* the long-term primary result packet sink
* a broad queue
* an always-on polling source
* a place with many active task packets
* a place with many active result packets

During transition, #114 may still receive short audit markers.

When a dedicated task or result surface exists, #114 should point to it rather than duplicate full packet content.

Preferred v1 topology

Preferred v1 topology:

#114 roadmap anchor
-> task-specific task surface
-> task-specific result surface
-> #114 receives short pointer / marker only during transition

This preserves roadmap visibility while avoiding long-comment readback instability.

Surface lifecycle

A surface lifecycle should follow:

planned
-> active
-> consumed
-> archived

A task surface becomes active when a task packet is published.

A task surface becomes consumed when the relay / runner reads and validates the task packet.

A result surface becomes active when a result packet is written.

A result surface becomes consumed when ChatGPT reads and reviews the result packet.

Archived surfaces must not be treated as active.

Readback priority

ChatGPT should prefer readback in this order:

1. canonical result surface URL
2. canonical task surface URL
3. task-specific GitHub issue or comment
4. local file reference when explicitly provided
5. roadmap anchor short marker
6. fallback user-pasted result

Fallback user-pasted result should be used only when bridge readback is unavailable.

Writeback priority

Relay / runner should prefer writeback in this order:

1. approved result surface URL
2. task-specific GitHub comment
3. task-specific GitHub issue body
4. local file result packet
5. local stdout fallback

The runner must not create new GitHub issues unless a future issue explicitly authorizes that behavior.

The runner must not choose a broad issue or roadmap anchor as the primary result surface unless the task packet explicitly allows fallback.

Failure rules

Surface validation must fail closed when:

* active_packet_count is greater than 1
* task surface is missing
* result surface is missing after writeback should have occurred
* protocol marker is missing
* packet boundary markers are missing
* logical_issue mismatches
* phase mismatches
* action_type mismatches
* risk_level mismatches
* fallback is used but not labeled
* fallback_reason is missing when fallback is true
* result surface is a long-lived roadmap issue without explicit fallback permission
* result claims approval instead of evidence
* high-risk action flags are missing
* forbidden operations occurred

Security rules

Surfaces must not include secret tokens.

Surfaces must not include credentials.

Surfaces must not include unrelated private data.

Surfaces must not include excessive logs.

Surfaces must not include broad shell instructions outside the task packet.

Surfaces must not mix active and archived packet content without clear boundaries.

Surfaces must not transform evidence into approval.

Surfaces must not hide manual fallback.

Surfaces must not hide transitional bridge gaps.

Approval boundary

A task surface may contain an approval phrase only when the task packet explicitly requires and scopes it.

A result surface may report approval consumption only for the exact phase that consumed it.

A result surface must not approve future phases.

A result surface must not claim that commit approval approves push.

A result surface must not claim that push approval approves issue close.

Approval chaining remains forbidden.

Transitional behavior

During transitional v0, the user may still paste task or result text when bridge readback is unavailable.

That behavior must be labeled fallback.

During transitional v0, the user may still manually start a foreground relay.

That behavior must be labeled transitional.

Neither fallback copy/paste nor manual foreground start is the target bridge workflow.

MVP usage

The first useful use of this document is to stop treating #114 as the primary result packet sink.

The second useful use is to define a canonical result surface for each task packet.

The third useful use is to enable ChatGPT to read a short, task-specific result surface without requiring the user to paste the result packet.

The fourth useful use is to enable relay / runner task fetch from a canonical task surface.

Future compatibility

Task and Result Surface v1 should preserve future compatibility for:

* ChatGPT task packet publication
* relay task fetch
* GitHub result writeback
* task-specific issue creation
* approval ledger
* evidence store
* task queue
* queue manager
* no-copy / no-paste bridge smoke
* approved commit rail
* approved push rail

These are future-facing extension points.

They are not authorized by this document.

Any Lv5 or beyond capability requires separate design, review, and explicit approval.

Completion criteria

#128 is complete when this document defines:

* Task Surface v1 purpose
* Result Surface v1 purpose
* Direction Lock binding
* relationship to Task Packet v1
* relationship to Result Packet v1
* surface roles
* roadmap anchor role
* task surface role
* result surface role
* fallback surface role
* allowed surface kinds
* canonical URL rules
* surface identifiers
* active packet rule
* surface binding object
* task surface requirements
* result surface requirements
* roadmap anchor usage rules
* preferred v1 topology
* surface lifecycle
* readback priority
* writeback priority
* failure rules
* security rules
* approval boundary
* transitional behavior
* MVP usage
* future compatibility

#128 is not complete if it implements runner code.

#128 is not complete if it creates scripts.

#128 is not complete if it creates tests.

#128 is not complete if it creates GitHub issues.

#128 is not complete if it changes the real result surface.

#128 is not complete if it authorizes automatic commit.

#128 is not complete if it authorizes automatic push.

#128 is not complete if it authorizes Lv5 full automation.

Current status

Task and Result Surface v1 is defined as a restrictive, auditable, task-specific surface protocol.

The next recommended step after #128 is #129 ChatGPT Task Packet Publication Proof.
