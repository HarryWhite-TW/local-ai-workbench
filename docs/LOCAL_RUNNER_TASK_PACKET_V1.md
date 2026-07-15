# Local Runner Task Packet v1

## Purpose

This document defines Local Runner Task Packet v1.

A task packet is the structured input that ChatGPT prepares and the local runner reads.

The goal is to reduce manual copy and paste while preserving safety boundaries.

Task Packet v1 is a schema and protocol document.

This document does not implement a runner.

This document does not authorize automatic commit.

This document does not authorize automatic push.

This document does not authorize automatic issue close.

This document does not authorize automatic PR creation.

This document does not authorize automatic merge.

This document does not authorize background watcher behavior.

This document does not authorize always-on polling.

This document does not authorize Lv5 full automation.

## Relationship to architecture

This document follows Local Runner Bridge v0 Architecture.

The bridge architecture defines the runner as a bounded, manually triggered task handoff bridge.

Task Packet v1 defines the structured task format that the runner will eventually consume.

The runner must treat task packet fields as structured data.

Natural language inside a task packet must not create new authority.

## Design goals

Task Packet v1 should make each runner task:

* explicit
* bounded
* auditable
* fail-closed
* single-purpose
* easy for ChatGPT to review
* easy for the runner to validate
* safe against accidental authority expansion

The packet should reduce long prompt copy and paste.

The packet should not reduce user approval for high-risk phases.

## Non-goals

Task Packet v1 is not a free-form prompt.

Task Packet v1 is not an agent instruction stream.

Task Packet v1 is not a queue protocol.

Task Packet v1 is not a multi-issue scheduler.

Task Packet v1 is not a background watcher input.

Task Packet v1 is not an approval ledger.

Task Packet v1 is not a replacement for ChatGPT review.

Task Packet v1 is not a replacement for user approval.

Task Packet v1 does not authorize chained high-risk actions.

## Packet boundary markers

A task packet should be embedded in a GitHub issue or GitHub comment using clear boundary markers.

Required outer markers:

```text
LOCAL-RUNNER-TASK-PACKET-V1
BEGIN_TASK_PACKET
...
END_TASK_PACKET
```

The runner should only parse content between BEGIN_TASK_PACKET and END_TASK_PACKET.

The runner must reject a packet if more than one active task packet is found in the selected input.

The runner must reject a packet if boundary markers are missing or malformed.

The runner must reject a packet if the protocol marker is missing.

## Recommended format

Task Packet v1 should use YAML inside the packet boundary.

Recommended structure:

```yaml
protocol: lawb.local_runner.task_packet.v1
packet_id: string
logical_issue: integer
phase: string
action_type: string
risk_level: low | medium | high
repository: string
branch: string
expected_head: string
expected_origin_master: string
allowed_files:
  - string
forbidden_files:
  - string
forbidden_operations:
  - string
approval:
  required: boolean
  phrase: string | null
  scope: string | null
payload:
  kind: none | document | command_plan | audit_request
  target_file: string | null
  content_boundary: string | null
validation:
  required_checks:
    - string
result_target:
  github_issue: integer
  marker: string
stop_condition: string
```

The runner should parse YAML strictly.

Unknown top-level fields should be rejected in v1 unless explicitly allowed by a future schema version.

Missing required fields must fail closed.

Conflicting fields must fail closed.

## Required fields

The following fields are required for every task packet:

* protocol
* packet_id
* logical_issue
* phase
* action_type
* risk_level
* repository
* branch
* expected_head
* allowed_files
* forbidden_operations
* approval.required
* payload.kind
* result_target.github_issue
* result_target.marker
* stop_condition

The following fields are conditionally required:

* expected_origin_master is required for push or remote-state-sensitive actions.
* approval.phrase is required when approval.required is true.
* approval.scope is required when approval.required is true.
* payload.target_file is required when payload.kind is document.
* payload.content_boundary is required when payload.kind is document.
* allowed_files is required and must be non-empty for write actions.
* validation.required_checks is required for write actions.
* result_target.github_issue is required for GitHub writeback.

## Protocol field

The protocol field must be exactly:

```text
lawb.local_runner.task_packet.v1
```

The runner must reject unknown protocols.

The runner must reject missing protocols.

The runner must reject future protocol versions unless explicitly supported.

## Packet ID field

packet_id identifies a single task packet.

packet_id should be stable and unique within the roadmap issue.

Recommended format:

```text
task-<logical_issue>-<phase>-<short_slug>
```

Example:

```text
task-125-reviewbundle-task-packet-schema
```

The runner should include packet_id in the result packet.

## Logical issue field

logical_issue identifies the task number.

Example:

```yaml
logical_issue: 125
```

The runner should not infer issue numbers from natural language.

The runner should use this field for result packet metadata.

## Phase field

phase identifies the workflow phase.

Examples:

* reviewbundle
* commit_approved
* push_once
* final_audit
* readonly_audit
* docs_only_apply_candidate

The runner must not treat phase as approval by itself.

For high-risk phases, approval.required must also be true and approval.phrase must match the approved scope.

## Action type field

action_type identifies what the runner may do.

Allowed action types for v1 design:

* read_only_audit
* docs_only_apply_candidate
* local_commit
* push_once
* final_audit

Initial implementation should begin with:

* read_only_audit

Then later:

* docs_only_apply_candidate

local_commit, push_once, and final_audit are future rails and must remain separately approved.

Unknown action types must fail closed.

## Risk level field

risk_level must be one of:

* low
* medium
* high

Suggested mapping:

* read_only_audit: low
* docs_only_apply_candidate: medium
* local_commit: high
* push_once: high
* final_audit: low

Risk level must not reduce required approval.

If action_type and risk_level conflict, the runner must fail closed.

## Repository field

repository must identify the expected repository.

Required value format:

```text
owner/name
```

Example:

```text
HarryWhite-TW/local-ai-workbench
```

The runner must verify repository identity before any action.

If repository identity does not match, the runner must fail closed.

## Branch field

branch must identify the expected branch.

Example:

```yaml
branch: master
```

The runner must verify current branch before any action.

If branch does not match, the runner must fail closed.

## Expected HEAD fields

expected_head is required for every task.

expected_origin_master is required when remote state matters.

The runner must verify expected_head before write actions.

The runner must verify expected_origin_master for push and final audit phases.

If HEAD does not match, the runner must fail closed.

The runner must not repair history automatically.

The runner must not pull, merge, rebase, reset, restore, clean, or amend to fix mismatch.

## Allowed files field

`allowed_files` lists the exact normalized repository-worktree paths that are legitimate candidate modifications and eligible for engineering-node review, candidate-acceptance eligibility, and final acceptance.

This is a governance and acceptance scope. It does not mean the local Runner independently proves that the child process was technically incapable of writing any other filesystem path.

For read-only actions, allowed_files may be empty.

For write actions, allowed_files must be non-empty.

The runner must reject absolute paths, drive-qualified paths, traversal, wildcards, directory-only entries, `.git` administration paths, alternate-stream/non-worktree paths, and other entries that do not identify a regular repository-worktree candidate file.

The runner must reject directory-only write permissions in v1.

Every accepted candidate path must be inside `allowed_files`. An observed changed path outside `allowed_files` must block candidate eligibility and acceptance. Natural-language instructions cannot expand this scope.

For docs-only apply candidate, exactly one target file should be allowed unless a task explicitly permits multiple docs files.

## Paths outside the allowlist

Task Packet v1.1 does not define a separate machine-readable `forbidden_files` field. The exact allowlist is sufficient: every repository candidate path outside `allowed_files` is ineligible. A future denylist would require an explicit schema and runtime change rather than documentation-only implication.

## Forbidden operations field

forbidden_operations lists operations that must not happen.

Common forbidden operations:

* stage
* commit
* push
* pull
* merge
* rebase
* amend
* reset
* restore
* clean
* create_branch
* switch_branch
* create_pr
* close_issue
* reopen_issue
* add_label
* remove_label
* modify_assignee
* run_tests
* run_runner
* run_dispatcher
* runtime_smoke

For high-risk phases, only the explicitly approved operation should be removed from forbidden_operations.

`forbidden_operations` records governance authority. A trusted parent may report commands it did not invoke, and named evidence may detect selected outcomes, but the field alone does not prove that an untrusted child was technically prevented from every forbidden or transient action.

Example:

For local_commit, commit may be allowed, but push must remain forbidden.

For push_once, push may be allowed, but commit must remain forbidden.

## Execution assurance and candidate tokens

Runner result evidence must distinguish:

* `detected`: a named evidence source reported a concrete condition;
* `verified`: a predicate was established within a named bounded evidence profile;
* `inferred`: a conclusion was derived but not directly established;
* `unverified`: evidence was absent, failed, or was insufficient;
* `not guaranteed`: the architecture expressly provides no such guarantee.

For the current local Runner, `observable_evidence=verified` means verified only within `local_git_candidate_observation.v1`. Current Codex `workspace-write` execution reports `isolation_guarantee=unverified`; it does not prove universal filesystem, network, process, GitHub, or external-side-effect isolation.

A candidate-review snapshot token may be emitted only when a valid v1.1 governance contract is present, governance passes, observable evidence is verified under a named profile, and all candidate gates pass. The token binds the observed candidate snapshot; it is not human approval, final acceptance, new authority, or proof of universal write prevention. Missing-contract operation is observation-only and cannot produce candidate eligibility or a token. CommitApproved must rebind current contract, scope, full HEAD, and candidate evidence before staging.

## Approval object

approval.required indicates whether user approval is required.

approval.phrase stores the exact approval phrase when required.

approval.scope stores what the approval covers.

Example:

```yaml
approval:
  required: true
  phrase: "APPROVE #125 commit"
  scope: "local commit only"
```

Approval must be phase-specific.

Approval chaining is forbidden.

Commit approval does not approve push.

Push approval does not approve issue close.

A task packet must not use old approval phrases for new phases.

A task packet must not broaden approval scope.

## Payload object

payload.kind defines the task payload type.

Allowed payload kinds:

* none
* document
* command_plan
* audit_request

For v1 MVP, document is used for docs-only apply candidate.

For document payloads, the task packet should point to a content boundary.

Example:

```yaml
payload:
  kind: document
  target_file: docs/LOCAL_RUNNER_TASK_PACKET_V1.md
  content_boundary: DOCUMENT_1
```

The actual document content should be placed outside the YAML using explicit markers.

Example:

```text
BEGIN_DOCUMENT_1
...
END_DOCUMENT_1
```

The runner must only write content inside the matching document boundary.

The runner must not write instruction text into the target file.

## Validation object

validation.required_checks lists checks the runner or executor must perform.

Examples:

* repository_matches
* branch_matches
* head_matches
* changed_files_exact
* diff_check_passed
* final_index_clean
* final_head_matches_initial
* observed_candidate_paths_within_allowed_files
* trusted_parent_push_invoked
* trusted_parent_pr_create_invoked
* trusted_parent_issue_close_invoked

The runner must include check results in the result packet.

If a required check cannot be evaluated, the runner must fail closed.

Validation names and results must preserve their evidence boundary. `final_index_clean=true` means only that the final observed staged area is empty; it does not prove staging never occurred. `final_head_matches_initial=true` means only that the final observed HEAD matches the initial HEAD; it does not prove no transient commit occurred. A `trusted_parent_*_invoked=false` fact describes only the trusted parent action path. It does not prove that child, hook, transient, external, network, process, or GitHub actions were universally absent or impossible. Candidate file-type restrictions must be evaluated through the exact `allowed_files` scope and the named bounded evidence profile rather than expressed as universal no-write claims.

## Result target object

result_target defines where the result packet should be written.

Example:

```yaml
result_target:
  github_issue: 114
  marker: REVIEWBUNDLE-AUDIT-VISIBLE
```

GitHub writeback should include:

* marker first line
* packet_id
* logical_issue
* phase
* action_type
* result
* changed files
* safety flags
* failure reason

If GitHub writeback fails, the runner should print a local fallback result packet.

## Stop condition field

stop_condition defines when the runner must stop.

Recommended values:

* stop_after_result_packet
* stop_after_local_commit_audit
* stop_after_push_audit
* stop_after_final_audit

The runner must stop after the stop condition is reached.

The runner must not continue into the next phase.

The runner must not infer the next task.

## Fail-closed rules

The runner must fail closed if:

* protocol is missing
* protocol is unsupported
* packet boundaries are missing
* YAML cannot be parsed
* required fields are missing
* unknown action_type is used
* risk_level conflicts with action_type
* repository does not match
* branch does not match
* expected_head does not match
* write action has no allowed_files
* write action changes files outside allowed_files
* forbidden files change
* forbidden operations are requested
* approval is required but missing
* approval phrase does not match scope
* payload boundary is missing
* payload target_file is not allowed
* result_target is missing
* stop_condition is missing

Fail-closed means:

* do not modify files
* do not stage
* do not commit
* do not push
* do not close issue
* write or print a failure result packet when possible

## Security notes

Task Packet v1 is intentionally restrictive.

The packet should not support arbitrary shell commands in v1.

The packet should not support free-form execution.

The packet should not support broad issue scanning.

The packet should not support queue processing.

The packet should not support automatic low-risk execution until separately designed.

The packet should not support high-risk approval chaining.

The packet should not support background watcher behavior.

## MVP usage

The first useful implementation should use Task Packet v1 for read-only audit.

The second useful implementation should use Task Packet v1 for docs-only apply candidate.

The first copy-paste reduction milestone is:

```text
ChatGPT creates GitHub task packet
-> user manually triggers runner
-> runner validates task packet
-> runner applies one docs-only candidate
-> runner writes GitHub result packet
-> ChatGPT reviews result
```

This milestone should be reached before commit rail or push rail is implemented.

## Future compatibility

Task Packet v1 should preserve future compatibility for:

* result packet v1
* policy engine v0
* approval ledger
* evidence store
* policy profiles
* human approval inbox
* queue manager
* multi-repo support
* background watcher adapter
* automatic low-risk execution

These are future-facing extension points.

They are not authorized by Task Packet v1.

Any Lv5 or beyond capability requires separate design, review, and explicit approval.

## Completion criteria

#125 is complete when this document defines:

* packet boundary markers
* recommended YAML structure
* required fields
* action_type rules
* risk_level rules
* repository and branch guards
* expected HEAD guards
* allowed_files and forbidden_files rules
* forbidden_operations rules
* approval object
* payload object
* validation object
* result_target object
* stop_condition
* fail-closed rules
* security notes
* MVP usage
* future compatibility

#125 is not complete if it implements runner code.

#125 is not complete if it creates scripts.

#125 is not complete if it creates tests.

#125 is not complete if it authorizes high-risk automation.

#125 is not complete if it authorizes Lv5 full automation.

## Current status

Local Runner Task Packet v1 is defined as a structured, restrictive, fail-closed task format.

The next recommended step after #125 is #126 Local Runner Result Packet v1.
