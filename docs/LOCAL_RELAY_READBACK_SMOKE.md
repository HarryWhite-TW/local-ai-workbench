# Local Relay Readback Smoke

## Purpose

This smoke is the next bounded bridge slice after #106. It proves a small, useful readback loop without treating manual copy/paste as the target workflow.

The target loop is:

1. ChatGPT writes a bridge task packet to GitHub.
2. A local foreground relay reads the task packet.
3. The relay executes one harmless bounded dry action.
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

## GitHub Result Writeback

Writing the result packet back to GitHub is explicit and manually started:

```powershell
.\scripts\local_bridge_relay_smoke.ps1 -TaskPacketFile .\docs\bridge_task_packet.readback_smoke.example.json -PostResultComment
```

This posts exactly the `BRIDGE-RESULT-PACKET` output to the bound issue as a comment. It is a medium-risk readback handoff, not an approval token for commit, push, close, or any follow-on action.

## ChatGPT Readback Path

After the relay posts the result comment, ChatGPT reads the same GitHub issue and inspects the `BRIDGE-RESULT-PACKET` marker and JSON directly. The user should not need to paste Codex output back into ChatGPT for the target workflow.

Until a direct ChatGPT-triggered relay exists, the remaining user action is manually starting the foreground relay. That is a visible temporary fallback, not the target end state.
