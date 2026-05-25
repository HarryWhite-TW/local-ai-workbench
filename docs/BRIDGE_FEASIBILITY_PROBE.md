# Bridge Feasibility Probe

## Purpose

This probe answers whether GitHub can act as the shared bridge surface for ChatGPT-to-Codex task dispatch and Codex-to-ChatGPT result readback.

The result for this slice is:

```text
bridge_feasibility_result=partial
```

GitHub is a workable shared packet surface for task and result exchange. The remaining gap is an implemented local foreground relay that reads a GitHub task packet, invokes a bounded Codex-side dry action, and writes a result packet back without the user manually copying Codex output into ChatGPT.

Manual copy/paste remains a temporary fallback. It is not the target workflow.

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

## Feasibility Answer

The bridge is partial:

- possible: GitHub issue bodies and comments can carry compact auditable task and result packets.
- possible: a local foreground relay can read packet text from GitHub with a bounded issue-scoped command.
- possible: a relay can run a harmless bounded dry action and write a compact result packet back to GitHub.
- blocked for target completion: no bridge relay is implemented in this issue.
- blocked for target completion: this issue does not prove ChatGPT has directly written the task packet and later read the result without the user acting as the relay.

The next implementation step should be a small foreground relay proof that exercises the packet loop end to end against one explicit issue. It must still avoid background watchers, always-on polling, automatic commit, automatic push, automatic close, and approval chaining.

## Minimal Task Packet Format

ChatGPT writes a task packet to a GitHub issue body or issue comment.

```text
BRIDGE-TASK-PACKET protocol=lawb.bridge_task_packet.v1
```

The marker is followed by compact JSON:

```json
{
  "schema": "lawb.bridge_task_packet.v1",
  "packet_id": "bridge-probe-106-task-001",
  "repo": "HarryWhite-TW/local-ai-workbench",
  "issue": 106,
  "branch": "master",
  "base_head": "REPLACE_WITH_CURRENT_HEAD",
  "requested_by": "chatgpt",
  "task_role": "core",
  "manual_copy_paste_is_target": false,
  "action": "bounded-dry-echo",
  "command": {
    "kind": "local-dry-action",
    "description": "Return a static bounded probe result without modifying files.",
    "timeout_seconds": 30
  },
  "expected_result_packet": "lawb.bridge_result_packet.v1",
  "safety": {
    "foreground_manual_start_only": true,
    "no_background_watcher": true,
    "no_always_on_polling": true,
    "no_stage": true,
    "no_commit": true,
    "no_push": true,
    "no_issue_close": true,
    "no_approval_chaining": true
  }
}
```

See `docs/bridge_task_packet.example.json` for the repo-local example packet.

## Minimal Result Packet Format

The local relay or Codex-side command writes the result packet back to the same GitHub issue body or issue comment.

```text
BRIDGE-RESULT-PACKET protocol=lawb.bridge_result_packet.v1
```

The marker is followed by compact JSON:

```json
{
  "schema": "lawb.bridge_result_packet.v1",
  "packet_id": "bridge-probe-106-result-001",
  "task_packet_id": "bridge-probe-106-task-001",
  "repo": "HarryWhite-TW/local-ai-workbench",
  "issue": 106,
  "result": "partial",
  "action": "bounded-dry-echo",
  "summary": "Task packet read path and result packet shape are defined; relay implementation remains future work.",
  "artifacts": [],
  "remaining_user_actions": [
    "User manually starts the foreground relay until a direct ChatGPT-triggered relay is implemented.",
    "User makes key approval decisions through ChatGPT."
  ],
  "safety": {
    "foreground_manual_start_only": true,
    "no_background_watcher": true,
    "no_always_on_polling": true,
    "no_stage": true,
    "no_commit": true,
    "no_push": true,
    "no_issue_close": true,
    "no_approval_chaining": true
  },
  "next_recommended_action": "chatgpt_review"
}
```

See `docs/bridge_result_packet.example.json` for the repo-local example packet.

## Dispatch And Readback Path

1. ChatGPT writes `BRIDGE-TASK-PACKET` to a GitHub issue body or comment.
2. The user starts one explicit foreground relay command for that issue.
3. The relay reads the GitHub issue text and extracts exactly one current task packet.
4. The relay validates repo, issue, branch, base `HEAD`, action name, timeout, and safety flags.
5. The relay invokes only the harmless bounded dry action from the packet.
6. The relay writes `BRIDGE-RESULT-PACKET` back to the same GitHub issue body or comment.
7. ChatGPT reads the GitHub result packet directly and reviews it.

This is the target bridge loop. Until the relay exists, manual copying remains fallback and must be named as fallback.

## Local Foreground Relay Constraints

The relay probe must be:

- foreground only
- manually started for one explicit issue
- bounded by timeout
- bounded by one packet and one harmless dry action
- fail-closed on malformed, stale, duplicated, mismatched, or unsupported packets
- observable through compact GitHub result text

The relay probe must not:

- run as a background watcher
- use always-on polling
- stage files
- commit
- push
- close issues
- edit labels
- create PRs
- merge
- consume approval tokens
- chain approvals
- implement a high-risk Release Bundle

## Remaining User Actions

The target workflow keeps the user in ChatGPT for key decisions, but this probe still has temporary manual steps:

- The user may need to approve ChatGPT writing the task packet to GitHub, depending on connector permissions.
- The user must manually start the foreground relay until a direct ChatGPT-to-relay trigger exists.
- The user must make approval decisions through ChatGPT after reading the result packet.

These are remaining bridge gaps, not the target end state.

## Single Review Packet

For ChatGPT review, the result packet should be compact enough to read in one issue body or issue comment. It should include:

- `schema`
- `packet_id`
- `task_packet_id`
- `repo`
- `issue`
- `result`
- `action`
- `summary`
- `remaining_user_actions`
- `safety`
- `next_recommended_action`

The result packet is not an approval token for commit, push, close, or any follow-on action.
