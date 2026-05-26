# Local Relay Readback Smoke

## Purpose

This smoke is the next bounded bridge slice after #106. It proves a small, useful readback loop without treating manual copy/paste as the target workflow.

The target loop is:

1. ChatGPT writes a bridge task packet to GitHub.
2. A local foreground relay reads the task packet.
3. The relay executes one harmless bounded dry action or one explicitly allowlisted bounded read-only local command.
4. The relay emits a bridge result packet.
5. The relay can write the result packet back to GitHub when explicitly requested.
6. ChatGPT reads the result packet from GitHub.

Manual relay remains fallback only. The target is still ChatGPT dispatching to Codex or a local relay through GitHub and reading the result back from GitHub.

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

## Smoke Result

```text
relay_smoke_defined=true
foreground_manual_start_only=true
harmless_dry_action_only=true
github_result_writeback_defined=true
chatgpt_readback_path_defined=true
bounded_local_command_defined=true
local_git_status_summary_only=true
```

This issue does not implement background watching, always-on polling, automatic commit, automatic push, automatic close, approval chaining, high-risk Release Bundle behavior, or real Codex code modification through the relay.

## Task Packet

ChatGPT writes or updates a task packet in a GitHub issue body or comment:

```text
BRIDGE-TASK-PACKET protocol=lawb.bridge_task_packet.v1
```

The packet JSON is mirrored in `docs/bridge_task_packet.readback_smoke.example.json` for local smoke testing.

Required task packet properties:

- `schema = "lawb.bridge_task_packet.v1"`
- `packet_id`
- `repo = "HarryWhite-TW/local-ai-workbench"`
- `issue = 107`
- `branch = "master"`
- `requested_by = "chatgpt"`
- `task_role = "core"`
- `manual_copy_paste_is_target = false`
- `action = "bounded-dry-echo"`
- `command.kind = "local-dry-action"`
- `command.timeout_seconds <= 30`
- safety flags for no watcher, no polling, no stage, no commit, no push, no close, and no approval chaining

## Local Foreground Relay

Run the local smoke relay manually:

```powershell
.\scripts\local_bridge_relay_smoke.ps1 -TaskPacketFile .\docs\bridge_task_packet.readback_smoke.example.json
```

Expected stdout starts with:

```text
BRIDGE-RESULT-PACKET protocol=lawb.bridge_result_packet.v1
```

The marker is followed by parseable JSON. The relay supports only the harmless `bounded-dry-echo` dry action in this slice. It does not call Codex, edit files, stage, commit, push, close issues, label, create PRs, merge, poll, watch, or chain approvals.

## GitHub Task Packet Read

The relay can also read exactly one task packet from one explicit GitHub issue:

```powershell
.\scripts\local_bridge_relay_smoke.ps1 -IssueNumber 109 -ReadTaskPacketFromGitHub
```

This command reads the issue body and comments with `gh issue view`, extracts exactly one current task packet, executes only `bounded-dry-echo`, and prints `BRIDGE-RESULT-PACKET` to stdout. It does not post a GitHub comment unless `-PostResultComment` is also passed.

The task packet marker must be a line by itself:

```text
BRIDGE-TASK-PACKET protocol=lawb.bridge_task_packet.v1
```

The marker must be followed by JSON. The GitHub-read packet must validate:

- exactly one packet exists on the selected issue
- `schema = "lawb.bridge_task_packet.v1"`
- `repo = "HarryWhite-TW/local-ai-workbench"`
- `issue` equals the explicit `-IssueNumber`
- `requested_by = "chatgpt"`
- `task_role = "core"`
- `manual_copy_paste_is_target = false`
- `expires_utc` is current and formatted as `yyyyMMddTHHmmssZ`
- `action = "bounded-dry-echo"`
- `command.kind = "local-dry-action"`
- `command.timeout_seconds <= 30`
- required safety flags are present and true

The relay fails closed for missing, duplicate, malformed, stale, schema-mismatched, repo-mismatched, issue-mismatched, unsupported, or unsafe packets. See `docs/bridge_task_packet.github_readback_smoke.example.json` and `docs/bridge_result_packet.github_readback_smoke.example.json` for the GitHub-read smoke packet examples.

## Bounded Local Command Smoke

The relay supports exactly one bounded local command kind for the #110 bridge slice:

```text
action=bounded-local-command
command.kind=local-git-status-summary
```

The task packet may request:

```json
{
  "action": "bounded-local-command",
  "command": {
    "kind": "local-git-status-summary",
    "description": "Read-only repository status summary.",
    "timeout_seconds": 30
  }
}
```

The relay does not execute shell text, user-provided arguments, scripts, paths, PowerShell, Bash, Cmd, or arbitrary commands from the task packet. For `local-git-status-summary`, it internally runs only hardcoded read-only git status commands:

- `git status --short`
- `git branch --show-current`
- `git rev-parse HEAD`
- `git rev-parse origin/master`

The result packet includes a bounded `command_result` object:

```json
{
  "kind": "local-git-status-summary",
  "branch": "master",
  "head": "<observed HEAD>",
  "origin_master": "<observed origin/master>",
  "git_status_short": "<bounded status text>",
  "is_clean": true
}
```

The relay rejects unknown command kinds, unsupported actions, unsafe command fields such as `shell`, `args`, `script`, `command_text`, `powershell`, `bash`, `cmd`, `exec`, or `path`, timeout values greater than 30 seconds, missing or false safety flags, and any packet requesting mutation, commit, push, close, labels, PRs, merges, watchers, polling, approval chaining, or real Codex code modification.

Run the local command smoke without GitHub posting:

```powershell
.\scripts\local_bridge_relay_smoke.ps1 -TaskPacketFile .\docs\bridge_task_packet.codex_command_smoke.example.json
```

See `docs/bridge_task_packet.codex_command_smoke.example.json` and `docs/bridge_result_packet.codex_command_smoke.example.json` for the bounded command packet examples.

## GitHub Result Writeback

Writing the result packet back to GitHub is explicit and manually started:

```powershell
.\scripts\local_bridge_relay_smoke.ps1 -TaskPacketFile .\docs\bridge_task_packet.readback_smoke.example.json -PostResultComment
```

For the GitHub-read smoke:

```powershell
.\scripts\local_bridge_relay_smoke.ps1 -IssueNumber 109 -ReadTaskPacketFromGitHub -PostResultComment
```

This posts exactly the `BRIDGE-RESULT-PACKET` output to the bound issue as a comment. It is a medium-risk readback handoff, not an approval token for commit, push, close, or any follow-on action.

## ChatGPT Readback Path

After the relay posts the result comment, ChatGPT reads the same GitHub issue and inspects the `BRIDGE-RESULT-PACKET` marker and JSON directly. The user should not need to paste Codex output back into ChatGPT for the target workflow.

Until a direct ChatGPT-triggered relay exists, the remaining user action is manually starting the foreground relay. That is a visible temporary fallback, not the target end state.
