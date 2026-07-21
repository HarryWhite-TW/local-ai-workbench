# Bridge Operator B2 Runbook

## Purpose

Bridge Operator B2 is the foreground, one-shot delegation step after B1.

B1 proves that one fixed Bridge Inbox request is readable, trusted, explicit,
and locally ready without delegation. B2 reuses that B1 validation, checks that
the target Issue does not already contain the matching `LAWBRUNNER-RESULT`,
invokes the existing Dispatcher `PollOnce` path at most once, and verifies one
matching result comment on the explicit target Issue.

B2 is development workflow tooling only. It is not Local Document-to-Knowledge
Workbench product runtime.

## Fixed Boundary

- Control repository: `HarryWhite-TW/local-ai-workbench`
- Permanent Bridge Inbox: control repository Issue `#147`
- Target repository: `HarryWhite-TW/local-ai-workbench` or exactly
  `HarryWhite-TW/human-approval-automation-gateway`
- Mode: foreground one-shot
- Broad Issue scanning: forbidden
- Latest/next Issue inference: forbidden
- Retry: forbidden
- Loop: forbidden
- Background service: forbidden
- B3 behavior: out of scope

## B2-A And B2-B

B2 is intended to prove the same one-shot delegation path for two Dispatcher
actions:

- B2-A: `maybe-status-check`
- B2-B: `run-reviewbundle`

Both actions use the same B2 operator boundary. The Dispatcher and Runner keep
their existing action-specific policy, including clean repository checks for
`run-reviewbundle`.

## Production CLI

Run from the repository root:

```powershell
$env:PYTHONPATH='src'
python -m local_runner_bridge.bridge_operator_b2_cli --repo-root .
```

Optional arguments:

```powershell
--repo HarryWhite-TW/local-ai-workbench
--target-repo-root <EXPLICIT_LOCAL_TARGET_PATH>
--github-token-env <ENV_VAR_NAME>
--timeout-seconds <SECONDS>
```

`--repo-root` is the control repository root. For the local-ai-workbench
target, the target root defaults to that same path for backward compatibility.
For HAG, `--target-repo-root` is mandatory and is accepted only from the local
CLI/configuration boundary.

The CLI always uses Inbox `#147`. A verified success exits `0`. A blocked or
delegation-failure summary exits `1`. Invalid arguments exit `2`. Standard
output is one parseable JSON summary.

## Dispatcher Invocation Boundary

The production default invoker builds an argument array, not a shell string:

```text
powershell.exe
-NoProfile
-ExecutionPolicy Bypass
-File <control_repo_root>\scripts\local_dispatcher_v1.ps1
-PollOnce
-IssueNumber <target_issue>
-Repo HarryWhite-TW/local-ai-workbench
-TargetRepoRoot <target_repo_root> # present when separate
-PostResultComment
```

It runs with `cwd=<control_repo_root>`, captures stdout and stderr with UTF-8 decoding
and `errors="replace"`, and uses a bounded timeout. Timeout and nonzero exit
are failures. B2 does not retry.

Tests inject `dispatcher_invoker` and do not call the real Dispatcher, Runner,
Codex execution path, or GitHub write path.

## Duplicate-Result Rule

Before delegation, B2 reads comments on the explicit target Issue and looks for
a matching result:

```text
LAWBRUNNER-RESULT
protocol=lawb.runner_result.v1
```

The JSON payload must match:

```text
issue
action
repo
branch
head
request_id = target_dispatch_request_id
```

For HAG, `repo` is `HarryWhite-TW/human-approval-automation-gateway` and both
pre/post result reads are performed through the HAG target client; Inbox reads
remain on control Issue `#147`.

If a matching result already exists, B2 returns:

```text
result=blocked
blocked_reason=matching_result_already_exists
dispatcher_invoked=false
```

Partial results, malformed JSON, nearby Issue results, mismatched identity, a
wrong request ID, a wrong branch, or a wrong HEAD do not count as completion.

## Post-Delegation Verification

After Dispatcher exit `0`, B2 rereads the explicit target Issue and requires
exactly one matching trusted-author runner result:

```text
schema=lawb.runner_result.v1
issue=<target_issue>
action=<requested_action>
repo=HarryWhite-TW/local-ai-workbench
branch=<expected_branch>
head=<expected_head>
request_id=<target_dispatch_request_id>
result=success
```

The marker line carries `protocol=lawb.runner_result.v1`; the current
Dispatcher JSON payload carries `schema=lawb.runner_result.v1`.

Failure cases include Dispatcher nonzero exit, timeout, missing result,
multiple matching results, untrusted result author, identity mismatch, and
`result=failure`.

## Summary Protocol

B2 emits:

```text
lawb.bridge_operator_b2_delegation_summary.v1
```

Required safety fields remain false on every path:

```text
broad_issue_scan_performed=false
latest_next_inference_performed=false
retry_performed=false
loop_started=false
background_service_started=false
commit_performed=false
push_performed=false
issue_closed=false
label_changed=false
pr_created=false
merge_performed=false
branch_deleted=false
approval_consumed=false
```

`github_write_performed=true` is reserved for a future explicit accounting
change if B2 itself performs a GitHub write. In the current B2 implementation,
the Dispatcher may post the target Issue result comment; B2 does not post its
own result comment.

## Recovery

B2 stops after one decision. It does not repair local state, switch branches,
pull, reset, rerun failed delegation, infer another Issue, or consume approval.

For recovery, review the JSON summary, target Issue comments, and Dispatcher
output. Manual `PollOnce` remains the documented recovery path, not the target
daily workflow:

```powershell
.\scripts\local_dispatcher_v1.ps1 -PollOnce -IssueNumber <N> -PostResultComment
```

## Next Phase Boundary

B2 success does not authorize B3. Foreground bounded loop behavior, durable
idempotency state, locks, heartbeat, pause, stop, logs, retry behavior, visible
operator UX, startup behavior, or trusted-actor changes each require separate
approval according to `docs/BRIDGE_OPERATOR_V0_SPEC.md`.
