# B4-D Fresh-Reboot End-to-End Smoke Test Plan

## Governing-document read audit

```text
PLAN-READ-AUDIT protocol=lawb.direction_lock_plan_read.v1
plan_path=docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md
plan_version=v1.1
primary_goal_read=true
task_alignment=core
manual_copy_paste_is_target=false
user_only_interfaces_with_chatgpt_goal=true
chatgpt_dispatches_to_codex_goal=true
codex_result_readback_to_chatgpt_goal=true
failure_reason=none
```

```text
BRIDGE-OPERATOR-SPEC-READ-AUDIT protocol=lawb.bridge_operator_spec_read.v1
spec_path=docs/BRIDGE_OPERATOR_V0_SPEC.md
spec_version=v0.1
spec_read=true
current_phase=B3
task_alignment=core
authority_change_requested=false
chatgpt_remains_primary_interface=true
manual_pollonce_is_recovery_only=true
high_risk_actions_remain_separate=true
failure_reason=none
```

`B4-D` in this document is the course-computer recovery milestone name. It is
not Bridge Operator specification Phase B4 and does not authorize tray UI,
startup behavior, a service, or any other Phase B4 capability.

## 1. Purpose

Define one future, explicitly authorized, foreground-only end-to-end smoke test:

```text
ChatGPT
-> fixed GitHub Bridge Inbox Issue #147
-> Bridge Operator one-shot delegation
-> Dispatcher PollOnce
-> Runner v1 ReviewBundle
-> Codex
-> target-Issue review bundle and LAWBRUNNER-RESULT
-> ChatGPT readback and review
```

The smoke is intended to prove that a freshly restored course computer can
complete one bounded `run-reviewbundle` request after B4-B diagnostics and B4-C
Bootstrap Audit report readiness.

This document is planning only. It performs none of the future steps.

## 2. Preconditions

All preconditions must be checked immediately before a future smoke:

1. The checkout is the intended `HarryWhite-TW/local-ai-workbench` repository.
2. The current branch is exactly `master`.
3. Local `HEAD` is recorded as a full 40-character SHA and equals the approved
   expected HEAD. `origin/master` is known, reviewed, and equals local `HEAD`.
4. `git status --short` is empty.
5. Bootstrap Audit, without `-Apply`, returns:
   - `mode=AUDIT`;
   - `overall_status=READY`;
   - healthy repository-local venv and pip;
   - ready course dependencies;
   - usable GitHub CLI and authentication;
   - usable expected Codex command.
6. B4-B read-only diagnostics separately return:
   - `protocol=lawb.bridge_operator_diagnostics.v1`;
   - `read_only=true`;
   - `dispatcher_invoked=false`;
   - `runner_invoked=false`;
   - `codex_invoked=false`;
   - `github_write_performed=false`;
   - either `status=READY`; or, for the pristine first-smoke baseline only,
     `status=ATTENTION` with `status_reasons` exactly
     `["no_state_files_present"]`.
7. When the pristine first-smoke `ATTENTION` exception is used, all of these
   additional checks must pass:
   - repository identity is the intended repository;
   - current branch is `master`;
   - local HEAD equals the approved HEAD;
   - `origin/master` is known and equals local HEAD;
   - working tree is clean;
   - no lock, pause, or stop flag is present;
   - repository and Bridge Operator state `read_errors` are empty;
   - `failure_clarity.last_failure_json_status=not_present`;
   - no prior failure reason or request ID is present;
   - all invocation and write flags listed above are false.
   Any additional `ATTENTION` reason or any `BLOCKED` status stops the smoke.
   This exception matches the real clean post-B4-C baseline: no Bridge Operator
   state files exist yet, so diagnostics report only
   `ATTENTION/no_state_files_present` while repository and safety checks pass.
8. The fixed Bridge Inbox remains Issue `#147`.
9. A human explicitly selects one existing open target Issue. It must not be
   inferred from latest, next, open-Issue order, or a broad scan.
10. The target Issue satisfies Runner v1's current eligibility test: the
    case-insensitive combined Issue title and body contain at least one exact
    phrase recognized by the existing regex: `write-capable`, `write capable`,
    `review-bundle`, or `review bundle`. This is text eligibility, not a label,
    new marker, or approval. The Issue also contains a tightly bounded task
    with an exact allowed-file list and final-report requirements.
11. The target task is safe to leave as local unstaged changes for review.
12. The trusted GitHub actor remains `HarryWhite-TW`, unless a separately
    approved authority change has occurred.
13. The Inbox request and target dispatch have unique IDs, exact branch/HEAD
    binding, and an expiry comfortably beyond the bounded run timeout.
14. No matching result already exists for the target dispatch request ID.
15. The human has reviewed the exact planned GitHub writes and execution scope.

## 3. Explicit non-goals

- No runtime implementation or behavior change.
- No Bridge Operator B3 loop, polling service, watcher, daemon, scheduled task,
  login startup, tray UI, or hidden process.
- No broad Issue scan or target selection by ordering.
- No cross-repository execution.
- No automatic retry of Dispatcher, Runner, or Codex.
- No automatic repair, pull, branch switch, reset, clean, stash, or lock removal.
- No commit, push, Issue close, label edit, PR creation, merge, force push, or
  approval consumption.
- No test of `maybe-status-check`; this milestone is specifically the bounded
  Codex path through `run-reviewbundle`.
- No adoption of the separate future `BRIDGE-TASK-PACKET` /
  `BRIDGE-RESULT-PACKET` schema. This smoke uses the current
  `CHATGPT-DISPATCH` / `LAWBRUNNER-RESULT` contract.

## 4. Safety boundaries

The smoke uses existing authority only:

- fixed repository: `HarryWhite-TW/local-ai-workbench`;
- fixed Inbox: Issue `#147`;
- one human-selected target Issue;
- one current Inbox request;
- one current target dispatch marker;
- action exactly `run-reviewbundle`;
- one foreground Bridge Operator B2 invocation;
- Dispatcher `PollOnce` for only the explicit target Issue;
- Runner v1 `ReviewBundle` only;
- Codex workspace writes limited by the target Issue's exact allowed paths;
- local changes remain unstaged;
- no continuation after result publication;
- no retry.

Bridge Operator must not call Runner or Codex directly. It delegates once to
Dispatcher. Dispatcher remains responsible for dispatch validation and invokes
Runner v1. Runner v1 remains responsible for bounded Codex execution.

The future approval to execute this smoke is not approval to commit, push,
close, label, create a PR, merge, run another request, or begin another phase.

## 5. Fixed surfaces and allowed inputs

| Surface | Fixed or explicit value | Role |
|---|---|---|
| Repository | `HarryWhite-TW/local-ai-workbench` | Only allowed repository |
| Local checkout | Human-confirmed course-computer checkout | Execution location |
| Branch | `master` | Exact branch binding |
| HEAD | Full SHA captured and approved immediately before request publication | Exact state binding |
| Bridge Inbox | GitHub Issue `#147` | Only wake-up/control surface |
| Target Issue | One positive integer explicitly selected by the human | Task and result surface |
| Inbox author | Trusted GitHub metadata actor | Request identity |
| Dispatch author | Trusted GitHub metadata actor | Dispatch identity |
| Requested by | `chatgpt` | Required marker field |
| Action | `run-reviewbundle` | Only executable action for this smoke |
| Operator | Bridge Operator B2 one-shot CLI | No loop or retry |
| Result readback | Explicit target Issue comments | ChatGPT review surface |

Allowed dynamic inputs are only:

- `<TARGET_ISSUE>`;
- `<MASTER_HEAD_40_SHA>`;
- `<INBOX_REQUEST_ID>`;
- `<DISPATCH_REQUEST_ID>`;
- `<EXPIRY_UTC_BASIC>`;
- exact target-Issue task body and allowed-file list;
- bounded command timeout if the documented default is unsuitable.

## 6. Proposed single-run smoke test flow

The future flow has four separate authority stages:

| Stage | Meaning | Writes or execution |
|---|---|---|
| Read-only planning | Prepare exact IDs, SHA, expiry, marker bodies, commands, evidence paths, and approvals | No GitHub write; no Operator, Dispatcher, Runner, or Codex |
| Future dry-run execution | Run Bootstrap Audit, B4-B diagnostics, and B1 fixed-Inbox validation after approved request publication | Read-only GitHub access; no delegation or Codex |
| Future actual Codex execution | Run B2 once for the exact `run-reviewbundle` request | One Dispatcher delegation, one Runner invocation, one Codex run; local unstaged changes allowed |
| Future GitHub writeback | Publish and verify the Runner review bundle and Dispatcher result comment | Only the explicitly approved target-Issue comments |

Because Runner v1 and Dispatcher currently publish during the real delegation,
actual Codex execution and result writeback are operationally coupled. The B2
command must not run unless the human approval explicitly covers both expected
target-Issue comments. If writeback is not approved, stop after dry-run.

## 7. Exact expected request shape

The future smoke uses two separate standalone GitHub comment markers.

### Target Issue dispatch marker

Post exactly one current marker comment to the explicitly selected target Issue:

```text
CHATGPT-DISPATCH protocol=lawb.dispatch.v1 action=run-reviewbundle issue=<TARGET_ISSUE> repo=HarryWhite-TW/local-ai-workbench branch=master head=<MASTER_HEAD_40_SHA> expires=<EXPIRY_UTC_BASIC> requested_by=chatgpt request_id=<DISPATCH_REQUEST_ID>
```

No prose may share this comment. Optional Dispatcher fields are not needed for
this smoke.

### Fixed Inbox request marker

Post exactly one current marker comment to Bridge Inbox Issue `#147`:

```text
BRIDGE-INBOX-REQUEST protocol=lawb.bridge_inbox_request.v1 request_id=<INBOX_REQUEST_ID> repo=HarryWhite-TW/local-ai-workbench target_issue=<TARGET_ISSUE> target_dispatch_request_id=<DISPATCH_REQUEST_ID> branch=master head=<MASTER_HEAD_40_SHA> expires=<EXPIRY_UTC_BASIC> action=run-reviewbundle requested_by=chatgpt
```

No prose may share this comment. The Inbox request is a wake-up/control record,
not an approval token.

### Required identity relationship

The two markers must agree exactly on:

- repository;
- target Issue;
- branch;
- HEAD;
- expiry window;
- action;
- `requested_by=chatgpt`;
- `target_dispatch_request_id == CHATGPT-DISPATCH request_id`.

`<INBOX_REQUEST_ID>` and `<DISPATCH_REQUEST_ID>` must be distinct, unique,
ASCII request IDs accepted by the current validators.

## 8. Exact expected result packet shape

The request-bound completion record is one target-Issue comment with the marker:

```text
LAWBRUNNER-RESULT protocol=lawb.runner_result.v1
```

The next content must be one JSON object. Dispatcher v1 currently generates
this exact top-level field set for `PollOnce`:

```json
{
  "schema": "lawb.runner_result.v1",
  "repo": "HarryWhite-TW/local-ai-workbench",
  "issue": "<TARGET_ISSUE as integer>",
  "action": "run-reviewbundle",
  "result": "success",
  "branch": "master",
  "head": "<MASTER_HEAD_40_SHA>",
  "selected_issue": "<TARGET_ISSUE as integer>",
  "request_id": "<DISPATCH_REQUEST_ID>",
  "poll_mode": "PollOnce",
  "review_id": null,
  "diff_fingerprint": null,
  "files_fingerprint": null,
  "changed_files": [],
  "validations": {
    "dispatch_marker": {
      "status": "passed",
      "summary": "<non-empty summary>"
    },
    "git_status_clean": {
      "status": "passed",
      "summary": "<non-empty summary>"
    },
    "pytest": {
      "status": "not_run",
      "summary": "<non-empty Dispatcher summary>"
    },
    "git_diff_check": {
      "status": "not_run",
      "summary": "<non-empty Dispatcher summary>"
    },
    "runner_v1": {
      "status": "passed",
      "summary": "<summary containing runner v1 exit code 0>"
    }
  },
  "safety": {
    "no_stage": true,
    "no_commit": true,
    "no_push": true,
    "no_issue_close": true,
    "no_label": true,
    "no_pr": true,
    "no_merge": true,
    "no_approval_chaining": true
  },
  "next_recommended_action": "chatgpt_review"
}
```

JSON integer placeholders above are descriptive and must be actual JSON numbers,
not quoted strings.

The Dispatcher result separates request binding from execution evidence:

- B2 matches exactly these invariant request-binding fields:
  `issue`, `action`, `repo`, `branch`, `head`, and `request_id`.
- The marker protocol and JSON `schema` must identify
  `lawb.runner_result.v1`.
- Exactly one matching result must exist after delegation.
- Its GitHub author must be trusted and its `result` must equal `success`.
- Missing, malformed, partial, duplicate, untrusted, wrong-schema,
  identity-mismatched, or failure results fail closed.

The remaining generated fields are execution-dependent or reporting evidence:

- `selected_issue` and `poll_mode` describe the Dispatcher selection and mode.
- `validations.runner_v1` records whether Runner v1 exited successfully.
- Other `validations` entries describe Dispatcher checks or explicitly report
  that Dispatcher did not independently run those checks.
- `safety` records the Dispatcher's no-high-risk-action boundary.
- `next_recommended_action` remains a recommendation, not approval.

Dispatcher v1 currently guarantees `review_id=null`, `diff_fingerprint=null`,
`files_fingerprint=null`, and `changed_files=[]` in its own generated result.
That empty `changed_files` array is a Dispatcher placeholder; it does not claim
that Codex changed no files and must not be used as changed-file evidence.

Runner v1 separately publishes one `## local-runner-v1 review bundle`. Its
embedded runner result and human-readable sections carry the actual modified
file list, review ID, fingerprints, diff summary, verification report, Codex
final report, stderr summary, and final git status. The Runner review bundle is
the changed-file and execution-detail evidence. The Dispatcher
`LAWBRUNNER-RESULT` whose request-binding fields match the approved dispatch is
the authoritative B2 completion record.

A failure result must be reported as failure evidence, never rewritten or
interpreted as success.

## 9. What may be read

During the future smoke, reads are limited to:

- repository identity, branch, HEAD, `origin/master`, and git status;
- the governing documents and runbooks named in this plan;
- Bootstrap manifest, requirements, and local tool versions;
- Bridge Operator local state under
  `%LOCALAPPDATA%\LocalAIWorkbench\BridgeOperator\`;
- fixed Bridge Inbox Issue `#147` and its comments;
- the one explicit target Issue, its body, metadata, and comments;
- trusted GitHub author metadata for relevant comments;
- the exact Dispatcher and Runner scripts invoked by the existing path;
- Codex output, local diff, changed-file list, test output, and final status;
- the resulting target-Issue comments for ChatGPT review.

No broad Issue enumeration, repository-wide GitHub search, latest/next lookup,
unrelated Issue read, or cross-repository read is part of this smoke.

## 10. What may be written, only after explicit approval

The future smoke has two non-chainable approvals:

| Approval | Exact authorized action | Explicitly not authorized |
|---|---|---|
| Approval A | One standalone `CHATGPT-DISPATCH` comment on `<TARGET_ISSUE>` | B2 execution or any result write |
| Approval A | One standalone `BRIDGE-INBOX-REQUEST` comment on fixed Inbox Issue `#147` | B2 execution or any result write |
| Separate approval B | One B2 foreground one-shot execution and its single Dispatcher -> Runner v1 ReviewBundle -> Codex chain | Retry, another request, or any high-risk continuation |
| Separate approval B | One Runner review-bundle comment and one Dispatcher `LAWBRUNNER-RESULT` comment on `<TARGET_ISSUE>` | Any additional or substitute GitHub write |

Approval A cannot authorize approval B. Neither approval authorizes commit,
push, cleanup, Issue close, label change, PR creation, merge, retry, or another
request.

Approval B also permits local unstaged repository changes only within the target
Issue's exact allowed paths and existing B2/operator local runtime evidence
outside the repository, only as already implemented by the one-shot path.

Approval A must name the target Issue, branch, HEAD, both request IDs, expiry,
and exact marker bodies. Approval B must name the same state binding, allowed
local paths, exact B2 command, one execution chain, and both expected result
comments. Each approval must be current when used.

No approval may be inferred from an Inbox marker, dispatch marker, successful
dry-run, prior milestone, successful result, or natural-language enthusiasm.

## 11. What must never happen

- Branch switching, pulling, rebasing, merging, resetting, cleaning, or stashing.
- More than one Operator run, Dispatcher delegation, Runner invocation, or Codex
  execution for the approved request.
- B3 bounded-loop mode, even with one cycle.
- Background execution, hidden window, daemon, scheduler, service, login
  startup, or auto-start.
- Automatic retry after timeout, partial failure, missing result, or Codex error.
- Broad Issue scanning or latest/next target inference.
- Execution against any Issue other than `<TARGET_ISSUE>`.
- Unapproved GitHub comments or any Issue creation, close, label, PR, merge, or
  branch deletion.
- Stage, commit, push, force push, or approval consumption.
- Automatic cleanup of Codex changes.
- Automatic deletion of locks or operator state.
- Secret, token, credential, or authentication-material logging.
- Treating a result packet as approval for a later action.

## 12. Step-by-step manual execution plan

All commands below are future commands. This planning task does not run them.

### A. Read-only planning

1. Human selects `<TARGET_ISSUE>` explicitly.
2. Review the target Issue title plus body and require at least one phrase
   accepted by Runner v1's existing case-insensitive regex:
   `write-capable`, `write capable`, `review-bundle`, or `review bundle`.
   Also require:
   - one bounded objective;
   - exact allowed paths;
   - no commit, push, close, label, PR, merge, login, or workflow expansion;
   - exact validation and final-report requirements.
3. Record `master` and `<MASTER_HEAD_40_SHA>`.
4. Generate unique `<INBOX_REQUEST_ID>` and `<DISPATCH_REQUEST_ID>`.
5. Choose `<EXPIRY_UTC_BASIC>` with enough time for review and the bounded
   Codex timeout, but no unnecessary long-lived authority.
6. Prepare the exact two marker comments and approval A.
7. Stop for explicit approval A before either GitHub write.

### B. Approved request publication

8. After approval, publish only the exact target dispatch comment.
9. After approval, publish only the exact fixed-Inbox request comment.
10. Read both comments back and verify comment IDs, trusted author metadata,
    standalone marker bodies, and exact field values.
11. If either write or readback differs, stop. Do not edit around ambiguity by
    adding another current marker without a newly reviewed plan.

### C. Future read-only dry-run execution

12. Run Bootstrap Audit only:

```powershell
.\scripts\bootstrap_course_environment.ps1 -RepoRoot . -Json
```

13. Run B4-B diagnostics using the repository-local venv without activation:

```powershell
$env:PYTHONPATH='src'
.\.venv-course\Scripts\python.exe -m local_runner_bridge.bridge_diagnostics --repo-root . --pretty
```

14. Accept diagnostics only under this rule:
    - `status=READY`; or
    - for the pristine first-smoke baseline only, `status=ATTENTION` with the
      sole reason exactly `no_state_files_present`, plus matching repository,
      `master`, approved HEAD, HEAD equal to `origin/master`, clean tree, no
      lock/pause/stop flag, no read errors, no prior failure evidence, and all
      Dispatcher/Runner/Codex/GitHub-write flags false.
    Any additional `ATTENTION` reason or any `BLOCKED` state stops the smoke.
15. Recheck branch, full HEAD, `origin/master` equality, and clean status.
16. Run B1 read-only validation against fixed Inbox `#147`:

```powershell
$env:PYTHONPATH='src'
.\.venv-course\Scripts\python.exe -m local_runner_bridge.bridge_operator_b1_cli --inbox-issue 147 --repo-root .
```

17. Require `result=success`, `dry_run_result=ready_without_delegation`, and all
    invocation/write safety flags false.
18. Present the dry-run evidence and exact B2 command to the human.
19. Stop for separate approval B covering:
    - one B2 execution;
    - one Dispatcher delegation;
    - one Runner v1 ReviewBundle;
    - one Codex run;
    - local unstaged changes in the allowed paths;
    - the Runner review-bundle comment;
    - the Dispatcher `LAWBRUNNER-RESULT` comment.

### D. Future actual Codex execution and approved writeback

20. Immediately before execution, recheck:
    - branch is `master`;
    - HEAD equals `<MASTER_HEAD_40_SHA>`;
    - working tree is clean;
    - target Issue remains open;
    - markers remain current and unambiguous;
    - no matching result exists;
    - approval still matches the exact state.
21. Run the one-shot B2 command in a visible foreground PowerShell:

```powershell
$env:PYTHONPATH = "src"; & .\.venv-course\Scripts\python.exe -m local_runner_bridge.bridge_operator_b2_cli --repo-root .
```

22. Do not rerun the command regardless of outcome.
23. Capture B2 stdout/stderr and exit code.
24. Read only `<TARGET_ISSUE>` comments and identify:
    - the Runner v1 review bundle;
    - exactly one trusted, matching Dispatcher `LAWBRUNNER-RESULT`.
25. Capture local `git status --short`, changed files, `git diff --stat`, and
    `git diff --check`.
26. ChatGPT reviews the request, B1 evidence, B2 summary, Runner review bundle,
    matching result packet, and local diff.
27. Stop. Any commit, push, cleanup, Issue close, or follow-up task requires a
    separate decision and approval.

## 13. Failure modes and stop conditions

Stop before delegation for any of:

- wrong repository, branch, HEAD, or target Issue;
- dirty working tree;
- Bootstrap Audit not `READY`;
- diagnostics `BLOCKED`;
- diagnostics `ATTENTION` with any reason other than the sole pristine-baseline
  reason `no_state_files_present`;
- pristine-baseline diagnostics with repository/branch/HEAD/origin equality,
  clean-tree, flag, read-error, prior-failure, or invocation/write checks not
  all passing;
- active lock, pause, stop, corrupt state, or unclear prior failure;
- missing, malformed, expired, duplicate, ambiguous, or untrusted Inbox request;
- missing, malformed, expired, duplicate, ambiguous, or untrusted target dispatch;
- closed target Issue;
- identity mismatch between Inbox and dispatch;
- unsupported action or `requested_by` mismatch;
- matching result already present;
- missing, stale, or mismatched approval A for request publication;
- missing, stale, or mismatched approval B for the one execution chain and both
  expected result comments.

Stop after one attempted delegation for any of:

- Dispatcher timeout or nonzero exit;
- Runner timeout or nonzero exit;
- Codex timeout, quota, launcher, provider, or sandbox failure;
- changed files outside the approved paths;
- staged files, commit, push, or other forbidden side effect;
- missing, duplicate, malformed, untrusted, mismatched, or failure result;
- result publication failure;
- unexpected partial execution.

On failure:

- do not retry;
- do not publish substitute success;
- preserve stdout, stderr, local diff, status, and existing comments;
- report exactly which components were reached;
- require a new reviewed request and approval before another attempt.

## 14. Evidence to collect

Record compact evidence without secrets:

- timestamp and machine role;
- repository root;
- branch, HEAD, and optional reviewed `origin/master`;
- initial and final `git status --short`;
- Bootstrap Audit JSON;
- B4-B diagnostics JSON;
- target Issue number and URL;
- Inbox and dispatch comment IDs, URLs, authors, and exact marker bodies;
- B1 JSON summary and exit code;
- exact B2 command;
- B2 JSON summary, stdout/stderr, and exit code;
- whether Dispatcher, Runner, Codex, and each writeback point were reached;
- Runner review-bundle comment ID and URL;
- matching Dispatcher result comment ID, URL, marker, and JSON;
- changed-file list and `git diff --stat`;
- `git diff --check` result;
- tests reported by Codex;
- final confirmation of no stage, commit, push, close, label, PR, merge,
  approval consumption, retry, background process, or broad scan;
- ChatGPT review conclusion and recommended next action.

Evidence stored locally must remain outside the repository unless a later
docs-only evidence task explicitly approves a repository file.

## 15. Acceptance criteria

The smoke passes only if all are true:

1. The run starts from clean `master` at the approved HEAD.
2. Bootstrap Audit is `READY`, and B4-B diagnostics are either:
   - `READY`; or
   - for the pristine first smoke only, `ATTENTION` with sole reason
     `no_state_files_present` and every repository, origin equality, clean-tree,
     no-control-flag, no-read-error, no-prior-failure, and no-invocation/write
     condition in Section 2 passing.
3. Approval A separately authorizes the exact target dispatch and Inbox request
   comments, and those comments are published and read back without variation.
4. B1 validates the fixed Inbox request and target dispatch without delegation.
5. Separate approval B explicitly authorizes one B2 execution chain, one Runner
   review-bundle comment, and one Dispatcher result comment.
6. B2 runs once in the foreground and delegates exactly once.
7. Dispatcher processes only `<TARGET_ISSUE>` through `PollOnce`.
8. Runner v1 runs only `ReviewBundle`.
9. Codex runs once and stays within the exact allowed paths and authority.
10. Local changes, if any, remain unstaged and uncommitted.
11. One Runner review bundle is present and reviewable.
12. Exactly one trusted Dispatcher `LAWBRUNNER-RESULT` matches repository,
    Issue, action, branch, HEAD, and `<DISPATCH_REQUEST_ID>`.
13. The matching result reports `result=success`, `runner_v1.status=passed`,
    all safety flags true, and `next_recommended_action=chatgpt_review`.
14. ChatGPT can read and review the target-Issue result without the user copying
    a long Codex transcript.
15. No retry, loop, broad scan, background behavior, stage, commit, push, close,
    label, PR, merge, or approval chaining occurs.
16. The process stops after ChatGPT review.

Any missing criterion means the smoke is failed or incomplete, not partially
accepted.

## 16. Rollback / cleanup guidance

There is no automatic rollback.

- Do not reset, clean, checkout, restore, or delete Codex changes automatically.
- Preserve failed-run evidence until reviewed.
- If local changes are accepted, handle commit only through a separately
  approved later task.
- If local changes are rejected, the human must approve the exact cleanup
  command and paths after reviewing the diff.
- Do not delete `operator.lock` without confirming no process is running and
  reviewing heartbeat/state evidence.
- Do not delete or rewrite GitHub comments merely to make the smoke appear
  clean. Leave the audit trail intact unless exact comment cleanup is separately
  approved.
- Expired request markers may remain as historical evidence. A retry requires
  new unique IDs, new current markers, refreshed HEAD/expiry binding, and new
  approval.
- Confirm the repository's final status and any remaining operator state before
  declaring cleanup complete.

## 17. Recommended next implementation slice

After this planning document is reviewed, the next bounded slice should be a
documentation-and-test-only **B4-D smoke harness preparation** task:

- add no new runtime authority;
- add no GitHub writes;
- add no Operator, Dispatcher, Runner, or Codex invocation in tests;
- provide a local validator for a filled smoke manifest containing the explicit
  target Issue, master HEAD, request IDs, expiry, exact marker strings, allowed
  paths, expected write count, and stop conditions;
- validate that the manifest targets Inbox `#147`, action
  `run-reviewbundle`, branch `master`, one explicit target Issue, unique IDs,
  exact cross-marker binding, and no forbidden authority;
- emit a read-only preview package for human approval.

Only after that slice passes should a separately authorized live smoke populate
the manifest, publish the approved markers, run B1, stop for execution approval,
and then invoke B2 once.
