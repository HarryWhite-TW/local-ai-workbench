# Local Runner Result Packet v1

## Purpose

This document defines Local Runner Result Packet v1.

A result packet is the structured output that a local relay, local runner, or Codex-side process writes after executing one bounded task packet.

The purpose is to let ChatGPT read and review execution results without the user manually pasting long Codex output.

Result Packet v1 is a schema and protocol document.

This document does not implement a runner.

This document does not authorize runner code.

This document does not authorize automatic commit.

This document does not authorize automatic push.

This document does not authorize automatic issue close.

This document does not authorize automatic PR creation.

This document does not authorize automatic merge.

This document does not authorize background watcher behavior.

This document does not authorize always-on polling.

This document does not authorize Lv5 full automation.

## Direction Lock Binding

```text
Direction Lock Binding
plan_path=docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md
plan_version=v1
rebaseline_path=docs/BRIDGE_DIRECTION_REBASELINE_126.md
primary_goal=chatgpt_dispatches_to_codex_and_reads_results_back
issue_role=core
manual_copy_paste_is_target=false
must_emit_plan_read_audit=true
```

## Relationship to bridge direction

Result Packet v1 supports the bridge target:

```text
User
-> ChatGPT
-> auditable task surface
-> local relay / runner / Codex-side process
-> bounded Codex or bounded executor action
-> auditable result surface
-> ChatGPT readback and review
-> user key approval decisions through ChatGPT
```

The user should not be the long-form result relay.

The user should not manually copy Codex output back into ChatGPT as the target workflow.

Manual result relay is fallback.

Result Packet v1 must make that fallback less necessary.

## Relationship to Task Packet v1

Task Packet v1 defines the structured input.

Result Packet v1 defines the structured output.

Each result packet should reference exactly one task packet.

The result packet must not broaden the authority granted by the task packet.

Natural language in the result packet must not create new authority.

A successful result packet is evidence.

A successful result packet is not approval for a later high-risk phase.

## Design goals

Result Packet v1 should make each execution result:

* explicit
* bounded
* auditable
* compact
* machine-readable
* ChatGPT-readable
* failure-aware
* evidence-first
* safe against approval chaining
* safe against result ambiguity
* easy to verify against repository state

The packet should reduce manual result copy/paste.

The packet should not reduce user approval for high-risk phases.

## Non-goals

Result Packet v1 is not an approval token.

Result Packet v1 is not a commit approval.

Result Packet v1 is not a push approval.

Result Packet v1 is not an issue close approval.

Result Packet v1 is not a PR creation approval.

Result Packet v1 is not a merge approval.

Result Packet v1 is not a free-form transcript.

Result Packet v1 is not a replacement for ChatGPT review.

Result Packet v1 is not a replacement for user approval.

Result Packet v1 does not authorize chained high-risk actions.

## Packet boundary markers

A result packet should be embedded in a GitHub issue, GitHub comment, local fallback output, or another approved result surface using clear boundary markers.

Required outer markers:

```text
LOCAL-RUNNER-RESULT-PACKET-V1
BEGIN_RESULT_PACKET
...
END_RESULT_PACKET
```

The reader should only parse content between BEGIN_RESULT_PACKET and END_RESULT_PACKET.

The reader must reject a packet if more than one active result packet is found in the selected result surface.

The reader must reject a packet if boundary markers are missing or malformed.

The reader must reject a packet if the protocol marker is missing.

## Recommended format

Result Packet v1 should use YAML inside the packet boundary.

Recommended structure:

```yaml
protocol: lawb.local_runner.result_packet.v1
packet_id: string
task_packet_id: string
logical_issue: integer
phase: string
action_type: string
risk_level: low | medium | high
result: success | failure | blocked | stopped | partial
repository: string
branch: string
head: string
origin_master: string | null
executor:
  kind: local_runner | relay | codex_side_process | bounded_executor
  name: string
  version: string | null
task_surface:
  kind: github_issue | github_comment | local_file | unknown
  url: string | null
  issue: integer | null
  comment_id: integer | null
result_surface:
  kind: github_issue | github_comment | local_stdout | local_file | unknown
  url: string | null
  issue: integer | null
  comment_id: integer | null
changed_files:
  - string
staged_changes_present: boolean
commit_created: boolean
commit_hash: string | null
push_performed: boolean
pushed_commit: string | null
pr_created: boolean
pr_url: string | null
merge_performed: boolean
issue_closed: boolean
label_changed: boolean
runtime_behavior_changed: boolean
runner_behavior_changed: boolean
dispatcher_behavior_changed: boolean
automation_authority_expanded: boolean
approval:
  required: boolean
  consumed: boolean
  phrase: string | null
  scope: string | null
evidence:
  summary: string
  checks:
    - name: string
      passed: boolean
      detail: string | null
  artifacts:
    - kind: diff | file | commit | comment | log | other
      path: string | null
      url: string | null
      sha: string | null
failure:
  reason: string | null
  failed_check: string | null
  recoverable: boolean
remaining_bridge_gaps:
  - string
next_recommended_action: string
stop_condition_reached: boolean
```

The runner or relay should emit YAML strictly.

Unknown top-level fields should be rejected in v1 unless explicitly allowed by a future schema version.

Missing required fields must fail result validation.

Conflicting fields must fail result validation.

## Required fields

The following fields are required for every result packet:

* protocol
* packet_id
* task_packet_id
* logical_issue
* phase
* action_type
* risk_level
* result
* repository
* branch
* head
* executor.kind
* task_surface.kind
* result_surface.kind
* changed_files
* staged_changes_present
* commit_created
* push_performed
* pr_created
* merge_performed
* issue_closed
* label_changed
* runtime_behavior_changed
* runner_behavior_changed
* dispatcher_behavior_changed
* automation_authority_expanded
* approval.required
* approval.consumed
* evidence.summary
* evidence.checks
* failure.reason
* next_recommended_action
* stop_condition_reached

The following fields are conditionally required:

* origin_master is required when remote state matters.
* commit_hash is required when commit_created is true.
* pushed_commit is required when push_performed is true.
* pr_url is required when pr_created is true.
* approval.phrase is required when approval.consumed is true.
* approval.scope is required when approval.consumed is true.
* result_surface.url is required when GitHub writeback succeeds.
* result_surface.comment_id is required when the result is written to a GitHub comment.
* failure.failed_check is required when result is failure due to a check failure.
* remaining_bridge_gaps is required when manual foreground start or manual fallback relay remains involved.

## Protocol field

The protocol field must be exactly:

lawb.local_runner.result_packet.v1

Readers must reject unknown protocols.

Readers must reject missing protocols.

Readers must reject future protocol versions unless explicitly supported.

## Packet ID field

packet_id identifies a single result packet.

Recommended format:

result-<logical_issue>-<phase>-<short_slug>

Example:

result-127-reviewbundle-result-packet-schema

The result packet should include packet_id in GitHub writeback comments and local fallback output.

## Task packet ID field

task_packet_id identifies the task packet that caused this result.

The result packet must reference exactly one task packet.

The runner must not infer the task packet from natural language.

If the task packet ID is unknown, the result must be failure or partial with a clear failure.reason.

## Logical issue field

logical_issue identifies the task number.

Example:

logical_issue: 127

The logical issue must match the task packet.

If logical_issue conflicts with the task packet, result validation must fail.

## Phase field

phase identifies the workflow phase.

Examples:

* reviewbundle
* result_packet_schema_reviewbundle
* readonly_audit
* docs_only_apply_candidate
* commit_approved
* push_once
* final_audit

The phase must match the task packet phase.

A result packet phase must not authorize the next phase.

## Action type field

action_type identifies the action that was executed or attempted.

Examples:

* read_only_audit
* docs_only_apply_candidate
* local_commit
* push_once
* final_audit
* result_packet_schema_reviewbundle

The action_type must match the task packet action_type.

Unsupported action types must result in failure or blocked.

## Risk level field

risk_level must be one of:

* low
* medium
* high

Risk level describes the executed or attempted action.

Risk level must not reduce required approval.

If action_type and risk_level conflict, result validation must fail.

## Result field

result must be one of:

* success
* failure
* blocked
* stopped
* partial

Definitions:

success means the task completed within scope and all required checks passed.

failure means the task could not complete or a required check failed.

blocked means the task did not run because a required precondition or approval was missing.

stopped means the task intentionally stopped at a required stop condition or risk gate.

partial means part of the task completed, but the result is incomplete and must be reviewed carefully.

A partial result must include failure.reason and remaining_bridge_gaps when applicable.

## Repository and branch fields

repository must identify the expected repository in owner/name format.

branch must identify the expected branch.

The values must match the task packet and actual execution context.

If repository or branch mismatch occurs, the result must be failure and no write action should occur.

## Head and origin_master fields

head records the local HEAD observed after execution or audit.

origin_master records the remote branch state when relevant.

For read-only actions, head should match expected_head.

For push actions, head and origin_master should match after push.

For write actions, head should describe the state after the bounded action.

If HEAD mismatch prevented execution, result must be blocked or failure.

## Executor object

executor identifies the component that produced the result.

Allowed executor kinds:

* local_runner
* relay
* codex_side_process
* bounded_executor

executor.name should be human-readable.

executor.version may be null until implementation versions exist.

## Task surface object

task_surface identifies where the task packet was read from.

Allowed task surface kinds:

* github_issue
* github_comment
* local_file
* unknown

Task surface fields help ChatGPT verify that the task came from the approved task location.

If task surface is unknown, result should be partial or failure unless the action is explicitly local fallback.

## Result surface object

result_surface identifies where the result packet was written.

Allowed result surface kinds:

* github_issue
* github_comment
* local_stdout
* local_file
* unknown

For the target bridge, GitHub or another ChatGPT-readable surface is preferred.

local_stdout is allowed only as fallback when GitHub writeback fails or is not yet implemented.

The result must clearly label local_stdout as fallback.

## Changed files field

changed_files lists repository files changed by the task.

For read-only actions, changed_files must be empty.

For docs-only candidate actions, changed_files must contain only allowed docs files.

For commit actions, changed_files must match committed files.

If files outside allowed scope changed, result must be failure.

## State flags

The following flags must be present:

* staged_changes_present
* commit_created
* push_performed
* pr_created
* merge_performed
* issue_closed
* label_changed
* runtime_behavior_changed
* runner_behavior_changed
* dispatcher_behavior_changed
* automation_authority_expanded

These flags make safety review explicit.

For low-risk and medium-risk ReviewBundle work, all high-risk action flags should usually be false.

If any high-risk flag is true, the result must include evidence and approval information.

## Approval object

approval.required indicates whether approval was required for the action.

approval.consumed indicates whether an approval was consumed.

approval.phrase records the approval phrase when consumed.

approval.scope records the approved scope when consumed.

Approval must be phase-specific.

Approval chaining is forbidden.

Commit approval does not approve push.

Push approval does not approve issue close.

A result packet must not claim approval for a future phase.

## Evidence object

evidence.summary must provide a short human-readable summary.

evidence.checks must list required checks and pass/fail status.

Each check should include:

* name
* passed
* detail

Examples:

* repository_matches
* branch_matches
* head_matches
* changed_files_exact
* git_diff_check_passed
* working_tree_clean
* no_staged_changes
* no_commit_created
* no_push_performed
* no_pr_created
* no_issue_closed
* no_scripts_created
* no_tests_created
* direction_lock_read
* manual_copy_paste_is_target_false

Artifacts may point to diff, file, commit, comment, or log evidence.

Long logs should not be included unless needed for diagnosis.

## Failure object

failure.reason explains failure, blocked, stopped, or partial result.

failure.failed_check identifies the check that failed when applicable.

failure.recoverable indicates whether the task can be retried after correction.

For success, failure.reason should be null.

## Remaining bridge gaps

remaining_bridge_gaps lists remaining manual or technical bridge gaps.

Examples:

* manual_foreground_start_still_required
* github_writeback_unavailable
* chatgpt_direct_task_publication_not_verified
* codex_side_invocation_not_implemented
* result_surface_readback_unstable
* fallback_report_used

This field keeps transitional limitations visible.

It prevents fallback or transitional behavior from being mistaken for the target workflow.

## Next recommended action

next_recommended_action tells ChatGPT what should happen next.

Examples:

* chatgpt_review
* chatgpt_review_then_commit_approval_package
* chatgpt_review_then_push_approval_package
* chatgpt_review_then_final_audit_package
* chatgpt_review_then_begin_128_task_result_surface_reviewbundle
* stop_and_investigate

This field is a recommendation only.

It is not approval.

## Stop condition reached

stop_condition_reached indicates whether the runner stopped at the intended boundary.

The result must be failure or partial if the runner continued beyond the stop condition.

The runner must not infer the next task.

## GitHub writeback requirements

When GitHub writeback succeeds, the result packet should include:

* result_surface.kind
* result_surface.url
* result_surface.issue
* result_surface.comment_id
* marker first line in evidence.checks or artifacts

When GitHub writeback fails, the runner should print a local fallback result packet.

Fallback output must include failure.reason or remaining_bridge_gaps.

Fallback output must not be presented as target bridge success.

## Validation rules

A result packet is valid only if:

* protocol is correct
* required fields are present
* task_packet_id is present
* result is one of the allowed values
* safety flags are present
* evidence.summary is present
* evidence.checks is present
* high-risk flags are consistent with approval object
* failure fields are present when result is not success
* next_recommended_action is present
* stop_condition_reached is present

A result packet is invalid if:

* it omits high-risk action flags
* it claims commit approval for push
* it claims push approval for issue close
* it hides changed files
* it hides partial failure
* it hides manual fallback
* it reports success while required checks failed
* it reports success while forbidden operations occurred
* it broadens authority beyond the task packet

## Security notes

Result Packet v1 is intentionally evidence-first.

The packet should not include secret tokens.

The packet should not include credentials.

The packet should not include excessive logs.

The packet should not include unrelated repository content.

The packet should not claim authority.

The packet should not transform evidence into approval.

The packet should not hide manual fallback.

The packet should not hide transitional bridge gaps.

## MVP usage

The first useful implementation should use Result Packet v1 for read-only audit.

The second useful implementation should use Result Packet v1 for GitHub writeback.

The third useful implementation should use Result Packet v1 for docs-only apply candidate results.

The first meaningful bridge milestone is:

```text
ChatGPT creates or writes task packet
-> relay / runner reads task packet
-> bounded action runs
-> relay / runner writes result packet
-> ChatGPT reads result packet
-> user does not paste long Codex output
```

Manual foreground start may remain transitional in early slices.

The result packet must keep that gap visible.

## Future compatibility

Result Packet v1 should preserve future compatibility for:

* task surface v1
* result surface v1
* policy engine v0
* evidence store
* approval ledger
* human approval inbox
* task queue
* queue manager
* bridge smoke tests
* approved commit rail
* approved push rail

These are future-facing extension points.

They are not authorized by Result Packet v1.

Any Lv5 or beyond capability requires separate design, review, and explicit approval.

## Completion criteria

#127 is complete when this document defines:

* result packet purpose
* Direction Lock binding
* relationship to Task Packet v1
* packet boundary markers
* recommended YAML structure
* required fields
* result status values
* repository and branch fields
* executor object
* task surface object
* result surface object
* changed files field
* high-risk state flags
* approval object
* evidence object
* failure object
* remaining bridge gaps
* next recommended action
* stop condition reached
* GitHub writeback requirements
* validation rules
* security notes
* MVP usage
* future compatibility

#127 is not complete if it implements runner code.

#127 is not complete if it creates scripts.

#127 is not complete if it creates tests.

#127 is not complete if it authorizes automatic commit.

#127 is not complete if it authorizes automatic push.

#127 is not complete if it authorizes Lv5 full automation.

## Current status

Local Runner Result Packet v1 is defined as a structured, restrictive, evidence-first result format.

The next recommended step after #127 is #128 Task Surface and Result Surface v1.
