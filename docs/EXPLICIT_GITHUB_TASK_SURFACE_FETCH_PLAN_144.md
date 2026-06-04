# Explicit GitHub Task Surface Fetch Plan (#144)

## 1. Purpose

#144 defines a docs-only Fast Lane plan for a future explicit GitHub task surface fetch step.

The value target is to define exactly how a future read-only fetch may accept one explicit GitHub issue comment or URL without scanning.

This document is planning only. It does not implement GitHub fetch, GitHub writeback, Result Packet writeback, Codex-side action, a runner, a dispatcher, an always-on watcher, broad issue scanning, or autonomous execution.

## 2. Issue Classification

```yaml
issue_number: 144
issue_role: support
risk_lane: fast
alignment: core_support
docs_only: true
implementation_allowed: false
```

#144 supports the bridge operator acceleration path by specifying a bounded future fetch boundary. It does not expand the project scope or change the local document workbench positioning.

## 3. Direction Lock

The direction lock remains unchanged:

* explicit user intent remains the source of task authority
* local validation remains evidence only
* ChatGPT readback remains the review surface
* user approval continues to flow through ChatGPT
* Codex must not infer, scan, execute, write, approve, commit, push, merge, close, or label from a fetched task surface

Manual copy/paste is no longer the target for the future fetch shape, but manual copy/paste target drift must be detected and reported as `drift_detected`.

## 4. What This Plan Enables

This plan enables a future #145 Strict Lane implementation proposal for a read-only fetch entry that accepts exactly one explicit task surface reference.

The future step may read only the referenced surface, normalize it into local task surface text, and pass that text into the existing local validation path:

```text
stdin / local surface text -> run_validation_dry_run() -> validate_task_surface() -> extract_task_packet() -> validate_task_packet() -> JSON summary
```

The future output is a bounded read-only fetch summary plus validation summary for ChatGPT review.

## 5. What This Plan Does Not Enable

This plan does not enable:

* GitHub fetch implementation in #144
* GitHub write implementation
* Result Packet writing
* Codex-side action execution
* runner creation
* dispatcher creation
* always-on watcher behavior
* broad issue scan
* next issue inference
* commit, push, PR, merge, issue close, or label changes from a fetched surface
* approval chaining from validation success
* autonomous execution

## 6. Accepted Explicit References For Future #145

A future #145 implementation may accept exactly one of these explicit inputs:

```yaml
accepted_explicit_references:
  - explicit_issue_url
  - explicit_issue_number
  - explicit_issue_comment_url
  - explicit_comment_id
  - explicit_local_text_already_provided_by_chatgpt
```

The input must be supplied directly by the user or ChatGPT task surface. The fetch layer must preserve the original explicit input in its summary.

## 7. Non-Accepted Inputs

A future #145 implementation must reject:

```yaml
non_accepted_inputs:
  - latest_issue
  - next_issue
  - all_open_issues
  - all_recent_comments
  - repository_search
  - broad_repo_state
  - inferred_issue_from_branch
  - inferred_issue_from_commit
  - inferred_issue_from_recent_history
  - ambiguous_url
  - multiple_references
  - missing_reference
```

Ambiguity must fail closed.

## 8. Future #145 Read-Only Fetch Boundary

The earliest possible implementation step is #145 and must use a Strict Lane boundary.

Future #145 may:

* accept exactly one explicit task surface reference
* classify the reference type
* read only the explicit surface
* normalize the content into local task surface text
* invoke the existing local validation dry-run path
* return a bounded read-only summary

Future #145 must not:

* scan all issues
* infer a next issue
* search broad repo state
* write GitHub comments
* write Result Packets
* execute Codex-side actions
* trigger commit, push, PR, merge, issue close, or labels
* convert validation success into approval

## 9. Future #145 Validation Flow

The future #145 flow is:

1. Accept exactly one explicit task surface reference.
2. Classify the reference type.
3. Reject broad or ambiguous references.
4. Fetch or read only that explicit surface.
5. Normalize the result to local task surface text.
6. Run the existing local validation path:

```text
stdin / local surface text -> run_validation_dry_run() -> validate_task_surface() -> extract_task_packet() -> validate_task_packet() -> JSON summary
```

7. Return a read-only fetch summary plus validation summary.
8. Stop without write, execution, or approval chaining.

## 10. Security And Drift Controls

The future #145 implementation must preserve:

* explicit input
* bounded read
* local validation
* auditable output
* ChatGPT readback
* user approval through ChatGPT

The future #145 implementation must report `drift_detected` when:

* the referenced target differs from the expected explicit input
* manual copy/paste content no longer matches the explicit target
* more than one active task surface is found in the provided local text
* the surface requires broad search or inference to resolve

Any drift, ambiguity, or required scan must return a blocked summary.

## 11. Required Result Shape For Future Fetch

A future #145 result should use a bounded shape similar to:

```yaml
explicit_task_surface_fetch_summary:
  protocol: lawb.local_runner.explicit_task_surface_fetch_summary.v1
  result: success | blocked | failure
  explicit_input_preserved: true
  reference_type: issue_url | issue_number | issue_comment_url | comment_id | local_text
  bounded_read_performed: true
  broad_issue_scan_performed: false
  github_write_performed: false
  result_packet_written: false
  codex_side_action_executed: false
  commit_triggered: false
  push_triggered: false
  pr_triggered: false
  issue_closed: false
  label_changed: false
  drift_detected: false
  validation_summary:
    protocol: lawb.local_runner.task_surface_validation_summary.v1
    result: success | blocked | failure
```

The summary is evidence for ChatGPT review. It is not approval.

## 12. Failure Modes

Future #145 must fail closed when:

* no explicit reference is provided
* more than one reference is provided
* the reference type is unsupported
* resolving the reference would require broad scan or inference
* the referenced issue or comment cannot be read
* the fetched surface differs from the explicit target
* the task packet boundary is missing or malformed
* local validation fails
* validation success would be treated as execution approval
* validation success would be treated as commit or push approval

## 13. Acceptance Criteria For #145

A future #145 implementation is acceptable only if:

* it accepts exactly one explicit reference
* it rejects broad and ambiguous references
* it reads only the explicit surface
* it preserves the explicit input in output
* it normalizes content to local task surface text
* it uses the existing local validation dry-run path
* it returns a bounded fetch summary and validation summary
* it performs no GitHub write
* it writes no Result Packet
* it performs no Codex-side action
* it triggers no commit, push, PR, merge, issue close, or label change
* it reports drift as `drift_detected`

## 14. Final Boundary Statement

#144 is a docs-only Fast Lane support plan.

The earliest possible implementation is future #145 under a Strict Lane task.

Future #145 may only read one explicitly provided GitHub task surface reference, or explicit local text already provided by ChatGPT, and return a bounded read-only fetch plus validation summary.

No scan, write, execution, approval chaining, runner, dispatcher, watcher, PR, merge, issue close, label change, commit, or push is authorized by this plan.
