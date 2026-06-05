# Phase 3 Live Fetch To Result Surface Success Decision Note (#167)

## 1. Purpose

This note records that the authenticated explicit live fetch to Result Surface readback path succeeded in #166, defines what is now proven, preserves the current approval boundary, and sets the next bounded planning step.

This is a docs-only decision note. It does not implement GitHub writeback, Result Packet write, Codex-side action execution, runner behavior, dispatcher behavior, watcher behavior, or automation.

## 2. Issue Classification

- `issue_number`: `167`
- `issue_role`: `support`
- `risk_lane`: `fast`
- `alignment`: `core_support`
- `value_target`: record that the authenticated explicit live fetch to Result Surface readback path succeeded, define what is now proven, what remains forbidden, and set the next bounded planning step without implementing writeback or automation

## 3. Direction Lock

The project target remains:

```text
ChatGPT
-> explicit auditable Task Surface
-> local read-only fetch
-> validation dry-run
-> Result Surface stdout/readback
-> ChatGPT review
-> user approval decision
```

Manual paste in earlier setup was test setup only, not the target workflow. Manual copy/paste remains fallback only, not the final target workflow.

## 4. Evidence Summary: #164

#164 was safely blocked because the committed #163 CLI had no authenticated live-fetch token environment gate. That block preserved the intended boundary: no live GitHub fetch was attempted without an explicit authenticated gate.

## 5. Evidence Summary: #165

#165 added a narrow authenticated read-only live fetch gate using `--github-token-env`.

#165 did not perform live GitHub fetch during implementation or tests. Its implementation and tests stayed bounded to local validation and stubbed authenticated paths.

## 6. Evidence Summary: #166

#166 used exactly one explicit issue URL:

```text
https://github.com/HarryWhite-TW/local-ai-workbench/issues/114
```

#166 used authenticated read-only live fetch through the committed #165 CLI. It produced Result Surface JSON to stdout and recorded:

```text
live_github_fetch_performed=true
result_surface_stdout_observed=true
result_surface_json_valid=true
source_task_validation_result=success
result_surface_status=success
requires_user_approval=true
chatgpt_readback_boundary_preserved=true
```

No broad issue scan, next/latest issue inference, comment fetch, GitHub writeback, Result Packet write, Codex-side action execution, runner, dispatcher, watcher, PR, merge, issue close, or label change was performed.

## 7. What Is Now Proven

- Exactly one explicit GitHub issue URL can be fetched live.
- Authenticated read-only fetch works through the committed #165 gate.
- The fetched Task Surface can reach validation dry-run.
- Validation can succeed.
- The validation result can be wrapped into a Result Surface.
- The Result Surface can be emitted as stdout JSON.
- ChatGPT readback boundary can be preserved.
- User approval remains required.
- No broad scan is required.
- No GitHub writeback is required for this proof.

## 8. What Is Still Not Proven

- GitHub writeback.
- Result Packet write.
- Codex-side action execution.
- Runner behavior.
- Dispatcher behavior.
- Watcher behavior.
- Approval handling automation.
- PR, merge, issue close, or label change.

## 9. Boundary Decision

The decision is not to jump directly to GitHub writeback implementation.

The live read-only proof succeeded, but writeback is a separate boundary. It needs explicit planning before any implementation because it would change the workflow from readback-only evidence to externally visible repository state mutation.

## 10. Next Candidate Step

The next candidate issue should be:

```text
#168 Bounded Result Surface Writeback Planning
```

#168 should be docs-only planning for a future bounded Result Surface writeback path.

#168 must not implement GitHub writeback yet. #168 must not implement Result Packet write yet.

## 11. Still Forbidden Behaviors

- GitHub writeback implementation.
- Result Packet write implementation.
- Codex-side action execution.
- Runner.
- Dispatcher.
- Watcher.
- Broad issue scan.
- Autonomous execution.
- PR or merge.
- Issue close.
- Label change.

## 12. Final Boundary Statement

Phase 3 has now proven the narrow authenticated live read-only fetch to Result Surface stdout/readback path. The next safe boundary is docs-only planning for a future writeback path, while preserving ChatGPT review and user approval as required gates before any follow-up action.
