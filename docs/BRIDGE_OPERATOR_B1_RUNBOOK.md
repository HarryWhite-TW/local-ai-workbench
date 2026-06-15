# Bridge Operator B1 Runbook

Bridge Operator B1 is a foreground, one-shot, read-only dry run for the fixed
Bridge Inbox control surface. It validates one explicit Inbox request and one
explicit target Issue, then stops before Dispatcher, Runner, Codex, or GitHub
writeback.

## Required Audits

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
current_phase=B1
task_alignment=core
authority_change_requested=false
chatgpt_remains_primary_interface=true
manual_pollonce_is_recovery_only=true
high_risk_actions_remain_separate=true
failure_reason=none
```

## Request Marker

B1 accepts request markers only from configured Inbox Issue comments. GitHub
comment author metadata is the authoritative identity surface. Markers in the
Inbox Issue body are ignored and are not authorized requests.

B1 parses every marker-like Inbox comment before selecting the current request.
Malformed marker-like comments, duplicate field names, untrusted comment
authors, wrong repository, unsupported action, `requested_by` mismatch, invalid
ids, invalid branch, invalid HEAD, zero current valid requests, or multiple
current valid requests fail closed. Expired historical requests are permitted
only when their complete non-time semantics are otherwise valid and exactly one
current valid request remains.

The current request must be exactly one standalone comment line:

```text
BRIDGE-INBOX-REQUEST protocol=lawb.bridge_inbox_request.v1 request_id=<unique-id> repo=HarryWhite-TW/local-ai-workbench target_issue=<N> target_dispatch_request_id=<id> branch=<branch> head=<40-char-sha> expires=<UTC_BASIC> action=<maybe-status-check|run-reviewbundle> requested_by=chatgpt
```

The marker is a wake-up/readiness control surface only. It is not an approval
token and does not execute the target action in B1.

## One-Shot Dry Run

Run from the repository root:

```powershell
$env:PYTHONPATH='src'
python -m local_runner_bridge.bridge_operator_b1_cli --inbox-issue <INBOX_ISSUE_NUMBER> --repo-root .
```

Use `--github-token-env <ENV_NAME>` only when the process needs a token for
read-only GitHub API access. The token value is not printed in the JSON summary.

## Expected Result

The CLI prints one JSON object with protocol:

```text
lawb.bridge_operator_b1_dry_run_summary.v1
```

A successful B1 dry run reports:

- fixed Inbox read performed;
- one trusted Inbox request author from GitHub comment metadata;
- one explicit open target Issue;
- one matching standalone `CHATGPT-DISPATCH` comment on the explicit target
  Issue whose `request_id` equals `target_dispatch_request_id`;
- matching repository, branch, HEAD, expiry, action, and `requested_by=chatgpt`;
- compatibility with Dispatcher v1 target dispatch optional fields `mode`,
  `expected_state`, and `reason`, while still rejecting duplicate fields,
  unknown fields, and ambiguous `request_id` matches;
- local readiness for repository root, branch, HEAD, clean state when required,
  GitHub CLI, auth, and read availability through the same bounded authenticated
  GitHub CLI read path used by B1;
- `dispatcher_invoked=false`, `runner_invoked=false`, `codex_invoked=false`,
  and all GitHub write / commit / push / PR / merge / approval flags false.

The target dispatch identity check is read-only. GitHub Issue comments reads
that use `-f per_page=100` explicitly pass `--method GET` and remain limited to
the configured Inbox comments endpoint and the one explicit target Issue comments
endpoint. B1 does not execute Dispatcher policy and does not delegate work.

The CLI prints one JSON summary for normal success or blocked results. It
returns exit code `0` only when `result=success`; blocked dry runs return
non-zero. `--help` keeps normal argparse help behavior.

## Recovery Boundary

If the dry run fails, fix the reported input or local environment and rerun the
same one-shot command. B1 must not repair local git state, infer a target Issue,
scan broad Issue ranges, remove locks, invoke Dispatcher, invoke Runner, run
Codex, post comments, close Issues, edit labels, create PRs, merge, commit,
push, or consume approvals.

Manual Dispatcher recovery remains separate and starts only after B1/B2 authority
allows it:

```powershell
.\scripts\local_dispatcher_v1.ps1 -PollOnce -IssueNumber <N> -PostResultComment
```
