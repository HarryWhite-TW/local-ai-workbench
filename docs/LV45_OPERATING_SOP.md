# Lv4.5 Operating SOP

## Purpose

Lv4.5 is the daily operating procedure for the completed minimum loop between ChatGPT, GitHub Issues, and the local manual dispatcher.

It is a semi-automated safe bridge:

- ChatGPT prepares or posts a structured `CHATGPT-DISPATCH` marker.
- The user runs the local `PollOnce` dispatcher for one explicit issue.
- The dispatcher executes one controlled low-risk action.
- The dispatcher posts `LAWBRUNNER-RESULT` back to the same GitHub Issue when explicitly requested.
- ChatGPT reads the GitHub result comment and reviews the outcome.

Lv4.5 keeps the repo aligned with the `Local Document Assistant Prototype` showcase as a local-first document workbench. It reduces manual relay, but it does not expand automation authority.

## What Lv4.5 Is Not

Lv4.5 is not:

- a background watcher
- always-on automation
- automatic commit
- automatic push
- automatic issue close
- approval chaining
- unrestricted Codex automation
- broad issue scanning
- a replacement for human / ChatGPT review

Lv4.5 dispatcher work is foreground, explicit, issue-scoped, and state-bound.

## Daily Usage Flow

Use this loop for normal Lv4.5 work:

1. User tells ChatGPT the task.
2. ChatGPT prepares a dispatch marker or gives the user the exact dispatch instruction.
3. User runs the local `PollOnce` command for the explicit issue.
4. Dispatcher validates the marker and, when requested, posts `LAWBRUNNER-RESULT` to the same GitHub Issue comment thread.
5. User tells ChatGPT: `#N has result, please review`.
6. ChatGPT reads the issue comment and gives a decision or next action.

The user remains the operator. PollOnce is manually invoked each time and stops after one selected issue.

## Supported Actions v1

The currently safe Lv4.5 dispatch action is:

- `maybe-status-check`: read-only status check used to decide whether action is needed.

Reserved / future dispatch action names:

- `run-reviewbundle`
- `read-final-audit`

Reserved actions are not currently active Lv4.5 daily actions. They must fail closed until explicitly implemented and verified.

Forbidden dispatch actions include commit, push, close, label, PR, merge, force-push, approval consumption, and any action that directly or indirectly performs those operations.

## Command Templates

Run PollOnce without posting a GitHub result comment:

```powershell
.\scripts\local_dispatcher_v1.ps1 -PollOnce -IssueNumber <N>
```

Run PollOnce and post a successful `LAWBRUNNER-RESULT` comment back to the same issue:

```powershell
.\scripts\local_dispatcher_v1.ps1 -PollOnce -IssueNumber <N> -PostResultComment
```

Do not run dispatcher PollOnce for this SOP issue itself unless a separate issue explicitly authorizes that dispatcher action. For issue #86, the authorized work is docs-only ReviewBundle generation.

## Marker Examples

Example `CHATGPT-DISPATCH` marker:

```text
CHATGPT-DISPATCH protocol=lawb.dispatch.v1 action=maybe-status-check issue=<N> repo=HarryWhite-TW/local-ai-workbench branch=master head=<sha> expires=<UTC_BASIC> requested_by=chatgpt request_id=<unique-id>
```

The marker must bind to the explicit issue, repo, branch, HEAD, and expiration time. The dispatcher must reject malformed, stale, mismatched, unsupported, or duplicate current markers.

Example `LAWBRUNNER-RESULT` summary shape:

```text
LAWBRUNNER-RESULT protocol=lawb.runner_result.v1
{
  "schema": "lawb.runner_result.v1",
  "repo": "HarryWhite-TW/local-ai-workbench",
  "issue": <N>,
  "action": "maybe-status-check",
  "result": "success",
  "branch": "master",
  "head": "<sha>",
  "selected_issue": <N>,
  "review_id": null,
  "diff_fingerprint": null,
  "files_fingerprint": null,
  "changed_files": [],
  "validations": {
    "git_status_clean": {
      "status": "passed",
      "summary": "Final git status is clean."
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

The marker line is followed immediately by parseable JSON. Consumers should not need Markdown fence parsing to recover the result.

## Success Criteria

A successful Lv4.5 run has all of the following:

- one valid current dispatch marker selected
- `result = success`
- `LAWBRUNNER-RESULT` posted back to the same issue when `-PostResultComment` is used
- repo clean
- no commit
- no push
- no issue close
- no label edit
- no PR
- no merge
- no approval chaining
- `next_recommended_action` present

If the dispatcher prints a result locally but `-PostResultComment` was not supplied, the user should relay the relevant result to ChatGPT manually.

## Failure Handling

Lv4.5 fails closed. The dispatcher should stop without running the action when it detects:

- expired marker
- duplicate current marker
- malformed marker
- unsupported action
- forbidden commit / push / close action
- HEAD mismatch
- wrong repo
- wrong branch
- wrong issue
- marker read failure
- result-comment target mismatch

Failure states are stdout-only. Invalid markers must not post result comments.

If no result comment appears after a run with `-PostResultComment`, check the local dispatcher output first. Treat the absence of a result comment as unresolved until the local output explains whether the dispatcher failed closed, the GitHub post failed, or the command was run without `-PostResultComment`.

Open a bugfix issue when the dispatcher behavior contradicts the documented safety contract, for example:

- it posts a result for an invalid marker
- it accepts duplicate current markers
- it ignores repo, branch, issue, HEAD, or expiry binding
- it attempts commit, push, close, label, PR, merge, force-push, or approval chaining from dispatch
- it reports success without `next_recommended_action`

## Safety Rules

Lv4.5 safety rules:

- explicit issue scope is required
- explicit HEAD binding is required
- no broad scan
- no high-risk action
- no background watcher
- no scheduler or daemon
- no approval chaining
- commit, push, close, label, PR, merge, and force-push remain approval-gated outside dispatch
- invalid markers must not post result comments
- PollOnce must process only the selected issue and then stop

The dispatcher result comment is an audit/reporting bridge. It is not an approval token.

## Recommended Intelligence Setting

Use the actual Codex intelligence labels as displayed in the UI:

- `低`: Use only for very simple, low-risk, no-write tasks such as small text cleanup or simple read-only checks.
- `中`: Use for read-only audits, status checks, docs-only SOP work, issue creation, and low-risk documentation review.
- `高`: Use for commit, push, close workflows, dispatcher changes, runner changes, GitHub state changes, and operations with safety boundaries.
- `超高`: Reserve for architecture redesign, cross-issue workflow redesign, complex risk analysis, or decisions that could reshape the automation model.

For normal Lv4.5 dispatcher smoke or status work, use `中` or `高` depending on whether GitHub comments are posted and how much state is involved.

Any operation involving an actual commit, push, close, or code change should use `高`.

If Lv5 or background watcher design is discussed later, use `超高`.

Do not replace these labels with question marks. The required codepoints are:

- `低`: U+4F4E
- `中`: U+4E2D
- `高`: U+9AD8
- `超高`: U+8D85 U+9AD8

## Boundaries Before Lv5

Lv5 / background watcher behavior is intentionally deferred.

Do not treat Lv4.5 as permission to add:

- always-on polling
- background schedulers
- automatic Codex execution
- automatic approval consumption
- automatic commit / push / close
- broad issue scanning
- multi-step action chaining

Lv4.5 is complete when the manual dispatch bridge can safely carry one bounded request, one bounded local action, and one structured result back to the same issue for review.

## Runner Capability

```text
review-bundle
```

This SOP is review-bundle capable for docs-only Lv4.5 operating procedure documentation. It does not authorize stage, commit, push, issue close, labels, PRs, merges, force push, `PushOnce`, `CloseIssueOnce`, dispatcher `PollOnce`, approval chaining, background watcher implementation, always-on polling, runner code changes, dispatcher code changes, test changes, or feature implementation.

